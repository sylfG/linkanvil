import asyncio
import os
import httpx
import json
import logging
import uuid
import pika

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_f032_pipeline():
    logger.info("Verificando Embedder Worker de extremo a extremo")
    trace_id = "test-f032-" + str(uuid.uuid4())[:8]
    tenant_id = "tenant-032-test"
    url = "https://example.com/vector-db"
    
    rabbit_url = os.getenv("RABBITMQ_URL", "amqp://cerebro:cerebro_pass_CHANGE_ME@localhost:5672/cerebro")
    parameters = pika.URLParameters(rabbit_url)
    
    try:
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        channel.exchange_declare("cerebro.procesamiento", exchange_type="fanout", durable=True)
        
        # Simulamos que el Outbox Publisher leyó el recurso estructurado
        payload = {
            "trace_id": trace_id,
            "tenant_id": tenant_id,
            "recurso_id": str(uuid.uuid4()),
            "url": url,
            "extracted_info": {
                "title": "Introduction to Embeddings",
                "summary": "This article discusses generating vectors locally and pushing them to Qdrant.",
                "keywords": ["qdrant", "litellm", "ai", "embeddings"],
                "category": "technical_article",
                "volatility_score": "low",
                "estimated_useful_life_days": 365
            }
        }
        
        properties = pika.BasicProperties(headers={"trace_id": trace_id})
        
        channel.basic_publish(
            exchange="cerebro.procesamiento",
            routing_key="",
            body=json.dumps(payload).encode(),
            properties=properties
        )
        logger.info(f"[{trace_id}] Evento en procesado inyectado directamente al Exchange 'cerebro.procesamiento'")
        
        connection.close()
        logger.info("Revisa los logs del contenedor embedder-worker ('docker logs cerebro-embedder') para confirmar inyección vectorial a Qdrant.")
        
    except Exception as e:
        logger.error(f"Fallo al publicar: {e}")

if __name__ == "__main__":
    test_f032_pipeline()