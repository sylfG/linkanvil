import asyncio
import aio_pika
import httpx
import json
import logging
import os
from typing import Optional

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

LITELLM_URL = os.getenv("LITELLM_EMBEDDINGS_URL", "http://litellm:4000/v1/embeddings")
LITELLM_KEY = os.getenv("LITELLM_API_KEY", "sk-cerebro-master-key-CHANGE_ME")
QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
RABBIT_URL = os.getenv("RABBITMQ_URL", "amqp://cerebro:cerebro_pass@localhost:5672/cerebro")
EXCHANGE_NAME = os.getenv("RABBITMQ_EXCHANGE_PROCESAMIENTO", "cerebro.procesamiento")
QUEUE_NAME = "q.recurso.embedder"
DLQ_ROUTING_KEY = "dlq.url.fallidas"

class EmbedderWorker:
    def __init__(self):
        self.connection: Optional[aio_pika.RobustConnection] = None
        self.channel: Optional[aio_pika.RobustChannel] = None
        self.queue: Optional[aio_pika.RobustQueue] = None

    async def connect(self):
        self.connection = await aio_pika.connect_robust(RABBIT_URL)
        self.channel = await self.connection.channel()
        await self.channel.set_qos(prefetch_count=10) # Paralelismo
        
        exchange = await self.channel.get_exchange(EXCHANGE_NAME)
        
        # Declarar Q asíncrona de embedder
        queue = await self.channel.declare_queue(
            QUEUE_NAME, 
            durable=True,
            arguments={
                "x-dead-letter-exchange": "",
                "x-dead-letter-routing-key": DLQ_ROUTING_KEY
            }
        )
        await queue.bind(exchange, routing_key="")
        self.queue = queue

    async def _generate_embedding(self, text: str, trace_id: str) -> list[float]:
        headers = {"Authorization": f"Bearer {LITELLM_KEY}", "Content-Type": "application/json"}
        payload = {"model": "cerebro-embeddings", "input": text}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(LITELLM_URL, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["data"][0]["embedding"]

    async def _inject_to_qdrant(self, recurso_id: str, tenant_id: str, vector: list[float], extracted_info: dict, url: str, trace_id: str):
        points_payload = {
            "points": [
                {
                    "id": recurso_id,
                    "vector": vector,
                    "payload": {
                        "tenant_id": tenant_id,
                        "url": url,
                        "title": extracted_info.get("title", ""),
                        "category": extracted_info.get("category", "other"),
                        "volatility": extracted_info.get("volatility_score", "media")
                    }
                }
            ]
        }
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.put(f"{QDRANT_URL}/collections/cerebro_recursos/points?wait=true", json=points_payload)
            resp.raise_for_status()

    async def process_message(self, message: aio_pika.IncomingMessage):
        async with message.process(requeue=False, ignore_processed=True):
            payload = json.loads(message.body.decode())
            trace_id = payload.get("trace_id", "unknown-trace")
            tenant_id = payload.get("tenant_id", "default_tenant")
            recurso_id = payload.get("recurso_id")
            url = payload.get("url", "")
            ext_info = payload.get("extracted_info", {})
            
            if not recurso_id:
                logger.error(f"[{trace_id}] Payload inválido: sin recurso_id")
                # Al fallar, el requeue=False envía a la DLQ ("x-dead-letter-routing-key")
                raise ValueError("Missing recurso_id in payload")

            keywords_str = ','.join(ext_info.get('keywords', []))
            text_to_embed = f"{ext_info.get('title', '')} | {ext_info.get('summary', '')} | Tags: {keywords_str}"
            
            logger.info(f"[{trace_id}] [TENANT:{tenant_id}] Generando embedding. Text Length: {len(text_to_embed)}")
            
            try:
                # 1. Llamar a LiteLLM
                vector = await self._generate_embedding(text_to_embed, trace_id)
                logger.info(f"[{trace_id}] Generado vector de {len(vector)} dimensiones")
                
                # 2. Inyectar a Qdrant
                await self._inject_to_qdrant(recurso_id, tenant_id, vector, ext_info, url, trace_id)
                logger.info(f"[{trace_id}] Vector inyectado exitosamente en Qdrant. Aislado a tenant_id: {tenant_id}")
                
            except Exception as e:
                logger.error(f"[{trace_id}] F-03.2 Fallo crítico procesando embedding/qdrant: {e}")
                # Rechazar para derivar a DQL (F-03.2 Tolerancia Edge Case)
                # raise the Exception, `message.process(requeue=False)` catches it and rejects it
                raise e

    async def consume(self):
        if not self.channel:
            await self.connect()
        logger.info(f"Iniciando consumo en EmbedderWorker cola '{QUEUE_NAME}'")
        await self.queue.consume(self.process_message)

    async def close(self):
        if self.connection:
            await self.connection.close()

async def run_worker():
    worker = EmbedderWorker()
    await worker.connect()
    await worker.consume()
    try:
        await asyncio.Future()
    except asyncio.CancelledError:
        pass
    finally:
        await worker.close()

if __name__ == '__main__':
    asyncio.run(run_worker())
