"""Test del enrutamiento Dead-Letter (F-01.5).

Verifica que, cuando el extractor rechaza un mensaje sin requeue, la
topología de RabbitMQ (dead-letter-exchange `cerebro.dlx` bound a
`q.url.fallidas`) lo redirige a la DLQ conservando los headers de traza.

Para evitar colisión con el consumidor productivo de `cerebro-scraper`
(que en CI/local consume q.url.ingesta y se llevaría el mensaje antes
que el test), publicamos a una cola dedicada `q.url.test_dlq.*`
con la misma política de DLX. El test queda autocontenido y reproducible
con o sin scraper levantado.
"""
import logging
import os
import uuid

import aio_pika
import pytest


logger = logging.getLogger(__name__)

RABBIT_URL = os.getenv(
    "RABBITMQ_URL",
    "amqp://cerebro:cerebro_pass@localhost:5672/cerebro",
)


@pytest.mark.asyncio
async def test_dlq_routing_logic():
    """Reject sin requeue + DLX configurado → mensaje aparece en la DLQ
    con `trace_id` preservado en headers."""
    trace_id = "test-fail-chronic-001"
    dlx_name = "cerebro.dlx"
    suffix = uuid.uuid4().hex[:8]
    test_queue_name = f"q.test_dlq.src.{suffix}"
    test_dlq_name = f"q.test_dlq.dst.{suffix}"
    routing_key = f"test.dlq.{suffix}"

    connection = await aio_pika.connect_robust(RABBIT_URL)
    channel = await connection.channel()

    # Reutilizamos el DLX existente (declarado como DIRECT por la infra).
    dlx = await channel.get_exchange(dlx_name)

    # Cola destino (DLQ) — el mensaje fluye aquí cuando es rejected en la src.
    test_dlq = await channel.declare_queue(
        test_dlq_name, durable=False, auto_delete=True,
    )
    await test_dlq.bind(dlx, routing_key=routing_key)

    # Cola origen con dead-letter-exchange configurado.
    test_queue = await channel.declare_queue(
        test_queue_name,
        durable=False,
        auto_delete=True,
        arguments={
            "x-dead-letter-exchange": dlx_name,
            "x-dead-letter-routing-key": routing_key,
        },
    )

    try:
        # Publicamos directo a la cola origen vía exchange default.
        payload = b'{"url":"https://chronic-fail.com","tenant_id":"tenant_x","source":"test"}'
        await channel.default_exchange.publish(
            aio_pika.Message(body=payload, headers={"trace_id": trace_id}),
            routing_key=test_queue_name,
        )

        # El "extractor" toma el mensaje y lo rechaza (fallo crónico).
        msg = await test_queue.get(timeout=2.0)
        logger.error(f"Fallo crónico al extraer {msg.body!r}, enviando a DLQ.")
        await msg.reject(requeue=False)

        # Debe haber aterrizado en la DLQ con headers preservados.
        dead_msg = await test_dlq.get(timeout=2.0)
        assert "trace_id" in dead_msg.headers
        assert dead_msg.headers["trace_id"] == trace_id
        assert b"tenant_id" in dead_msg.body
        await dead_msg.ack()
    finally:
        # auto_delete=True las purga al cerrar el canal, pero borrar
        # explícito acelera el cleanup en RabbitMQ.
        try:
            await test_queue.delete(if_unused=False, if_empty=False)
            await test_dlq.delete(if_unused=False, if_empty=False)
        except Exception:
            pass
        await channel.close()
        await connection.close()
