import asyncio
import logging
import os
import aio_pika
import json
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from src.data.db import DatabaseManager
from src.data.heartbeat import start_heartbeat
from src.telemetry import configure_telemetry, trace_operation

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

configure_telemetry("outbox-worker")

class OutboxPublisher:
    """
    Poller dedicado a leer eventos guardados asíncronamente en PostgreSQL 'outbox_eventos'
    y emitirlos al message broker garantizando la consistencia eventual estricta.
    """
    def __init__(self, rabbit_url: str):
        self.rabbit_url = rabbit_url
        self.db = DatabaseManager()
        self.connection = None
        self.channel = None
        self.redis = None
        self.heartbeat_task = None
        self.exchange_name = os.getenv("RABBITMQ_EXCHANGE_PROCESAMIENTO", "cerebro.procesamiento")

    async def connect(self):
        await self.db.connect()
        self.connection = await aio_pika.connect_robust(self.rabbit_url)
        self.channel = await self.connection.channel()
        self.redis = aioredis.from_url(
            os.getenv("REDIS_URL", "redis://:cerebro_redis_pass@redis:6379"),
            decode_responses=True,
        )
        self.heartbeat_task = start_heartbeat(self.redis, "outbox")

    @trace_operation("poll_outbox")
    async def poll_outbox(self):
        logger.info("Iniciando escaneo de tabla Outbox (F-03.1)...")
        while True:
            try:
                # Obtenemos eventos y realizamos fetch para procesarlos atómicamente
                async with self.db.pool.acquire() as conn:
                    async with conn.transaction():
                        rows = await conn.fetch(
                            """
                            SELECT id, tenant_id, evento_tipo, payload
                            FROM outbox_eventos
                            WHERE procesado = FALSE
                            ORDER BY creado_en ASC
                            LIMIT 50
                            FOR UPDATE SKIP LOCKED
                            """
                        )

                        if not rows:
                            await asyncio.sleep(2)
                            continue

                        exchange = await self.channel.get_exchange(self.exchange_name)

                        for row in rows:
                            event_id = row['id']
                            try:
                                # `payload` viene como str (asyncpg sin codec jsonb en
                                # este pool). Hubo un periodo en que se grabó doblemente
                                # codificado: json.loads devolvía str. Lo detectamos y
                                # re-decodificamos para no atascar el bucle.
                                raw = json.loads(row['payload'])
                                if isinstance(raw, str):
                                    raw = json.loads(raw)
                                if not isinstance(raw, dict):
                                    raise ValueError(f"payload no es dict: {type(raw).__name__}")
                                payload_dict = raw
                                payload_dict['tenant_id'] = row['tenant_id']
                                payload_dict['evento_tipo'] = row['evento_tipo']
                                trace_id = payload_dict.get('trace_id', 'unknown-trace')

                                msg = aio_pika.Message(
                                    body=json.dumps(payload_dict).encode(),
                                    content_type="application/json",
                                    headers={
                                        "trace_id": trace_id,
                                        "evento_tipo": row['evento_tipo'],
                                    },
                                )
                                await exchange.publish(msg, routing_key="")

                                await conn.execute(
                                    """
                                    UPDATE outbox_eventos
                                    SET procesado = TRUE, procesado_en = NOW()
                                    WHERE id = $1
                                    """,
                                    event_id,
                                )
                                logger.info(f"[{trace_id}] Evento Outbox '{event_id}' publicado via RabbitMQ.")
                            except Exception as ev_err:
                                # Aislamos el error de UNA fila: la marcamos procesado
                                # con reintentos++ para que no bloquee el resto del lote.
                                # En el futuro se podría rutear a una DLQ de outbox.
                                logger.error(
                                    f"Evento outbox {event_id} ({row['evento_tipo']}) "
                                    f"corrupto, descartando: {ev_err}"
                                )
                                await conn.execute(
                                    """
                                    UPDATE outbox_eventos
                                    SET procesado = TRUE, procesado_en = NOW(),
                                        reintentos = reintentos + 1
                                    WHERE id = $1
                                    """,
                                    event_id,
                                )

            except Exception as e:
                logger.error(f"Falla crítica en el bucle Outbox: {e}")
                await asyncio.sleep(5)

    async def close(self):
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
        if self.redis:
            await self.redis.aclose()
        if self.connection:
            await self.connection.close()
        await self.db.close()

async def run_outbox():
    logging.basicConfig(level=logging.INFO)
    rabbit_url = os.getenv("RABBITMQ_URL", "amqp://cerebro:cerebro_pass@localhost:5672/cerebro")
    publisher = OutboxPublisher(rabbit_url)
    
    await publisher.connect()
    try:
        await publisher.poll_outbox()
    except asyncio.CancelledError:
        pass
    finally:
        await publisher.close()

if __name__ == "__main__":
    asyncio.run(run_outbox())
