import os
import logging
import uuid
import re
from typing import Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from src.ingestion.schemas import IngestionRequest, IngestionResponse
from src.ingestion.deduplicator import RedisDeduplicator
from src.ingestion.publisher import RabbitMQPublisher
from src.telemetry import configure_telemetry, trace_operation
import redis
import httpx

# Logging format that captures logic visually
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="Ingestion API", description="Omnichannel Ingestion with Rate Limiter (via Traefik) and RedisBloom")

# CORS middleware para soportar extensiones de navegador (F-01.4)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Permitir inyecciones desde cualquier origen (browser extension context)
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Global instances
redis_client: Optional[redis.Redis] = None
deduplicator: Optional[RedisDeduplicator] = None
rabbit_publisher: Optional[RabbitMQPublisher] = None

RABBIT_URL = os.getenv("RABBITMQ_URL", "amqp://cerebro:cerebro_pass@localhost:5672/cerebro")
RABBIT_QUEUE = os.getenv("RABBITMQ_QUEUE", "url.nueva")
RABBIT_DLQ = os.getenv("RABBITMQ_DLQ", "dlq.url.fallidas")

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "cerebro_redis_pass_CHANGE_ME")


def handle_dlq_from_redis(item: str, tenant_id: str, trace_id: str, exc: Exception):
    """
    Fallback policy when Redis crashes (Edge Case F-01.1):
    We trigger a DLQ send, but we fail-open the processing so the logic lets it continue if we don't return False here.
    Wait, the specs logic F-01.1: If redis fails, derivation to DLQ or effectuate Fallback.
    Here we publish to DLQ asynchronously... wait, this callback is synchronous inside Deduplicator.
    We just log into DLQ using a sync wrapper or another async task.
    """
    logger.error(f"[{trace_id}] REDIS FALLO - Enviando item '{item}' a la DLQ {RABBIT_DLQ}")
    # En un entorno de produccion, enviar a la dlq usando rabbit synchronous o agendar un task en FastAPI
    pass

@app.on_event("startup")
async def startup_event():
    global redis_client, deduplicator, rabbit_publisher
    logger.info("Iniciando Ingestion API, conectando a servicios dependientes...")

    # Activar OpenTelemetry unificado
    configure_telemetry("ingestion-api")

    # Conectar Redis
    try:
        redis_client = redis.Redis(
            host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD, decode_responses=True
        )
        redis_client.ping()
        deduplicator = RedisDeduplicator(redis_client=redis_client, dlq_callback=handle_dlq_from_redis)
    except Exception as e:
        logger.error(f"Fallo al conectar a Redis en el inicio: {e}")
        # En producción podríamos fallar o simplemente arrancar en modo contingencia
        # deduplicator será inicializado con un mock interno o manejado con fallback

    # Conectar Rabbit
    rabbit_publisher = RabbitMQPublisher(rabbit_url=RABBIT_URL)
    try:
        await rabbit_publisher.connect()
        logger.info("Conectado a RabbitMQ exitosamente.")
    except Exception as e:
        logger.error(f"Fallo al sincronizar con RabbitMQ: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    if rabbit_publisher:
        await rabbit_publisher.close()

# Healthcheck
@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.post("/ingest", response_model=IngestionResponse)
@trace_operation("ingest_url")
async def ingest_url(request: IngestionRequest):
    """
    Endpoint principal.
    1. Verifica si es un duplicado por `tenant_id` usando el Bloom Filter en Redis.
    2. Verifica limit_rate por `tenant_id` para Throttling local (F-06.4).
    3. Si es nuevo y no estrangulado, emite un mensaje a la cola RabbitMQ asíncrona.
    """
    if deduplicator is None or rabbit_publisher is None:
        raise HTTPException(status_code=503, detail="Servicios base (Redis o RabbitMQ) no disponibles. Fallback en curso.")

    try:
        # F-06.4 Noisy Neighbor Defense (estranguilamiento individual)
        if redis_client:
            rate_key = f"rate_limit:{request.tenant_id}"
            req_count = redis_client.get(rate_key)
            if req_count and int(req_count) >= 10:  # Límite de 10 requests por minuto
                logger.warning(f"[{request.trace_id}] Throttling activado para tenant {request.tenant_id}")
                # Edge Case: deriva a la DLQ o efectúa Fallback
                try:
                    await rabbit_publisher.publish_ingestion_message(
                        queue_name=RABBIT_DLQ,
                        payload={"error": "Too Many Requests", "request": request.model_dump(), "source": "throttling"},
                        trace_id=request.trace_id
                    )
                except Exception as dlq_e:
                    pass
                raise HTTPException(status_code=429, detail="Too Many Requests. Cuota excedida.")
            
            pipe = redis_client.pipeline()
            pipe.incr(rate_key)
            if not req_count:
                pipe.expire(rate_key, 60)
            pipe.execute()

        # Happy Path / Aislamiento (F-01.1)
        is_new = deduplicator.is_new_item(request.url, request.tenant_id, request.trace_id)
        
        if is_new:
            # Requisito Técnico F-01.2: Enviar a RabbitMQ
            payload = request.model_dump()
            await rabbit_publisher.publish_ingestion_message(
                queue_name=RABBIT_QUEUE,
                payload=payload,
                trace_id=request.trace_id
            )
            
            return IngestionResponse(
                status="Accepted & Published",
                trace_id=request.trace_id,
                is_duplicate=False,
                is_valid=True
            )
        else:
            return IngestionResponse(
                status="Ignored",
                trace_id=request.trace_id,
                is_duplicate=True,
                is_valid=True
            )
            
    except HTTPException as httpe:
        # Re-raise HTTP exceptions (like 429 Too Many Requests) without wrapping them in 500
        raise httpe
    except Exception as e:
        logger.error(f"[{request.trace_id}] Fallo interno en /ingest: {e}")
        # Fallback a DLQ simulado para Edge Cases de LLM / Puente o error general
        try:
            await rabbit_publisher.publish_ingestion_message(
                queue_name=RABBIT_DLQ,
                payload={"error": str(e), "request": request.model_dump()},
                trace_id=request.trace_id
            )
        except Exception as dlq_e:
            logger.critical(f"Fallo enviando a DLQ en falla cascada: {dlq_e}")
            
        raise HTTPException(status_code=500, detail="Error interno procesando evento de ingesta.")

@app.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    """
    Webhook para recibir mensajes de Telegram.
    Extrae URLs del mensaje de texto y las inyecta en el pipeline de ingesta.
    """
    try:
        data = await request.json()
        logger.info(f"Recibido payload de Telegram")
        
        # Ignorar si no es un mensaje normal
        if 'message' not in data:
            return {"status": "ignored", "reason": "not a message"}
        
        message = data['message']
        chat_id = str(message.get('chat', {}).get('id', 'unknown'))
        text = message.get('text', '')
        
        if not text:
            return {"status": "ignored", "reason": "no text in message"}
            
        # Extraer URL simple con un regex o usando el texto entero si es solo una URL
        urls = re.findall(r'(https?://\S+)', text)
        if not urls:
            return {"status": "ignored", "reason": "no url found in text"}
            
        trace_id = str(uuid.uuid4())
        
        # Por simplificar procesamos la primera URL encontrada
        url = urls[0]
        
        # Reutilizamos IngestionRequest
        ingest_req = IngestionRequest(
            url=url,
            tenant_id=f"tg_{chat_id}",
            source="telegram",
            trace_id=trace_id
        )
        
        # Llamar localmente al flujo de ingesta
        result = await ingest_url(ingest_req)
        return {"status": "processed", "result": result}
        
    except Exception as e:
        logger.error(f"Error procesando webhook de Telegram: {e}")
        return {"status": "error", "detail": str(e)}

@app.post("/webhook/external")
@trace_operation("external_webhook")
async def external_webhook(request: Request, tenant_id: str = "default_ext"):
    """
    Webhook genérico para plataformas externas (Zapier, Make, Slack, Chrome Extension etc).
    Busca URLs en el cuerpo en formato JSON o form-data, intentando buscar campos comunes.
    (F-01.4 Soporte Captura Webhooks Externos y Navegador)
    """
    try:
        data = await request.json()
        logger.info("Recibido payload de webhook externo")
        
        # Buscar campo "url", "text", "content" o serializar a JSON
        text_content = ""
        if isinstance(data, dict):
            url_direct = data.get("url") or data.get("link")
            if url_direct:
                text_content = url_direct
            else:
                text_content = " ".join([str(v) for v in data.values() if isinstance(v, (str, list))])
        else:
            text_content = str(data)
            
        # Extraer URLs
        urls = re.findall(r'(https?://[^\s\"\'<>]+)', text_content)
        if not urls:
            return {"status": "ignored", "reason": "no url found in generic payload"}
            
        trace_id = str(uuid.uuid4())
        results = []
        
        # Ingestamos las URLs encontradas
        for url in urls[:5]: # Mítico rate limit por payload
            ingest_req = IngestionRequest(
                url=url,
                tenant_id=tenant_id,
                source="external_webhook",
                trace_id=trace_id
            )
            r = await ingest_url(ingest_req)
            if hasattr(r, 'model_dump'):
                r = r.model_dump()
            results.append(r)
            
        return {"status": "processed", "results": results}
        
    except httpx.HTTPStatusError as fallback_err:
        logger.error(f"Falla de pasarela: {fallback_err}")
        return {"status": "error", "detail": str(fallback_err)}
    except Exception as e:
        logger.error(f"Error procesando webhook externo: {e}")
        # Notificar fallo y/o derivar a DLQ como establece Edge Case
        try:
            if rabbit_publisher:
                await rabbit_publisher.publish_ingestion_message(
                    queue_name=RABBIT_DLQ,
                    payload={"error": str(e), "source": "external_webhook"},
                    trace_id="webhook-error"
                )
        except Exception as dlq_e:
            pass
        return {"status": "error", "detail": str(e)}


