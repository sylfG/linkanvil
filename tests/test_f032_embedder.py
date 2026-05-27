"""F-03.2 Embedder Worker — smoke publish.

Inyecta un mensaje en el exchange `cerebro.procesamiento` (fanout) que
consume `cerebro-embedder` para generar embeddings vía LiteLLM y
empujarlos a Qdrant. Como el resultado vive en otro servicio
(`docker logs cerebro-embedder` y la colección Qdrant), el test solo
verifica que la publicación AMQP no lanza errores y que el broker la
acepta. La verificación end-to-end de la inserción vectorial vive en
los tests de integración con Qdrant.

Cambios respecto a la versión anterior:
- Se sustituye `pika` (BlockingConnection sincrónico) por `aio_pika`
  (asíncrono) — `pika` no está instalado en los contenedores del
  ecosistema porque el resto del código usa `aio_pika`.
- Se omite limpiamente con `pytest.skip` si RabbitMQ no está disponible
  (entorno CI mínimo, falla de red), en lugar de hacer logger.error y
  pasar silenciosamente como antes.
"""
import asyncio
import json
import logging
import os
import uuid

import pytest


logger = logging.getLogger(__name__)


def test_f032_pipeline():
    """Inyecta un evento estructurado en `cerebro.procesamiento` (fanout)
    y verifica que el broker acepta la publicación."""
    aio_pika = pytest.importorskip("aio_pika")

    trace_id = "test-f032-" + str(uuid.uuid4())[:8]
    tenant_id = "tenant-032-test"
    url = "https://example.com/vector-db"

    rabbit_url = os.getenv(
        "RABBITMQ_URL",
        "amqp://cerebro:cerebro_pass_CHANGE_ME@localhost:5672/cerebro",
    )

    payload = {
        "trace_id": trace_id,
        "tenant_id": tenant_id,
        "recurso_id": str(uuid.uuid4()),
        "url": url,
        "extracted_info": {
            "title": "Introduction to Embeddings",
            "summary": (
                "This article discusses generating vectors locally and "
                "pushing them to Qdrant."
            ),
            "keywords": ["qdrant", "litellm", "ai", "embeddings"],
            "category": "technical_article",
            "volatility_score": "low",
            "estimated_useful_life_days": 365,
        },
    }

    async def _publish():
        try:
            connection = await aio_pika.connect_robust(rabbit_url, timeout=3.0)
        except Exception as e:
            pytest.skip(f"RabbitMQ no disponible: {e}")

        try:
            channel = await connection.channel()
            exchange = await channel.declare_exchange(
                "cerebro.procesamiento",
                aio_pika.ExchangeType.FANOUT,
                durable=True,
            )
            message = aio_pika.Message(
                body=json.dumps(payload).encode(),
                headers={"trace_id": trace_id},
            )
            await exchange.publish(message, routing_key="")
            logger.info(
                f"[{trace_id}] Evento publicado en 'cerebro.procesamiento'."
            )
        finally:
            await connection.close()

    asyncio.run(_publish())
    # Si llegamos aquí sin excepción, la publicación AMQP fue aceptada.
    # La verificación end-to-end (Qdrant) se cubre en otros tests.
