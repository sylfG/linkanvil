import pytest
import asyncio
import aio_pika
import logging
from unittest.mock import AsyncMock, patch

from src.ingestion.publisher import RabbitMQPublisher
from src.dlq.dlq_manager import DLQManager
import os

logger = logging.getLogger(__name__)

RABBIT_URL = os.getenv("RABBITMQ_URL", "amqp://cerebro:cerebro_pass@localhost:5672/cerebro")

@pytest.mark.asyncio
async def test_dlq_routing_logic():
    """
    Verifica minuciosamente que la Cola de Mensajes Muertos (DLQ) actua como
    salvavidas ante fallos de extracción (F-01.5), y mantenga trazabilidad (Trace_ID).
    """
    trace_id = "test-fail-chronic-001"
    queue_ingest = "q.url.ingesta"
    exchange_name = "cerebro.ingesta"
    dlq_name = "q.url.fallidas"
    routing_pass = "url.nueva"

    # 3. Simulamos un Extractor (Consumidor) que falla
    connection = await aio_pika.connect_robust(RABBIT_URL)
    channel = await connection.channel()
    
    # Tomar la cola
    queue = await channel.get_queue(queue_ingest, ensure=False)
    
    try:
        await queue.purge()
    except Exception:
        pass
        
    dlq_queue = await channel.get_queue(dlq_name, ensure=False)
    try:
        await dlq_queue.purge()
    except Exception:
        pass

    # 1. Conexión de Publicador y envio de mensaje simulado a la ingesta
    pub = RabbitMQPublisher(rabbit_url=RABBIT_URL)
    await pub.connect()
    
    payload = {
        "url": "https://chronic-fail.com",
        "tenant_id": "tenant_x",
        "source": "test"
    }

    # 2. Publicamos hacia el exchange de ingesta que enruta a la cola "q.url.ingesta"
    await pub.publish_ingestion_message(queue_name=routing_pass, payload=payload, trace_id=trace_id)
    
    # Extraemos 1 mensaje sincrónicamente para emular el extractor obteniendolo
    try:
        msg = await queue.get(timeout=2.0)
        # Simulamos Fallo Crónico: el scraper falló intentando leer el HTML
        logger.error(f"Fallo crónico al extraer {msg.body}, enviando a DLQ.")
        
        # Al rechazar sin requeue, la topología de RabbitMQ empuja este msg
        # hacia el dead-letter-exchange "cerebro.dlx" bound a "q.url.fallidas".
        await msg.reject(requeue=False)
    except aio_pika.exceptions.QueueEmpty:
        pytest.fail("No message in Ingestion queue! Topology wrong or publish failed.")

    # 4. Verificar que se ha enrutado a la DLQ (q.url.fallidas) y rescatar Trace_ID
    dlq_mgr = DLQManager(rabbit_url=RABBIT_URL)
    await dlq_mgr.connect()
    
    # Rescato el mensaje que acabo de mandar
    retry_message = None
    try:
        dead_msg = await dlq_queue.get(timeout=2.0)
        headers = dead_msg.headers
        body = dead_msg.body.decode()
        
        # Validar el Happy path del Edge case: Mantener traza Trace ID, Tenant_ID (aislamiento)
        assert "trace_id" in headers
        assert headers["trace_id"] == trace_id
        assert "tenant_id" in body
        
        retry_message = dead_msg
    except aio_pika.exceptions.QueueEmpty:
        pytest.fail("El mensaje NO FUE ENRUTADO a la DLQ q.url.fallidas.")
        
    # Limpiamos consumiendo todo (Ack definitivo del test)
    if retry_message:
        await retry_message.ack()
        
    await pub.close()
    await dlq_mgr.close()
    await channel.close()
    await connection.close()
