import asyncio
import logging
import os
import aio_pika
import json
from src.data.db import DatabaseManager

logger = logging.getLogger(__name__)

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
        self.exchange_name = os.getenv("RABBITMQ_EXCHANGE_PROCESAMIENTO", "cerebro.procesamiento")

    async def connect(self):
        await self.db.connect()
        self.connection = await aio_pika.connect_robust(self.rabbit_url)
        self.channel = await self.connection.channel()

    async def poll_outbox(self):
        logger.info("Iniciando escaneo de tabla Outbox (F-03.1)...")
        while True:
            try:
                # Obtenemos eventos y realizamos fetch para procesarlos atómicamente
                async with self.db.pool.acquire() as conn:
                    async with conn.transaction():
                        rows = await conn.fetch(
                            """
                            SELECT id, tenant_id, payload 
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
                            payload_dict = json.loads(row['payload'])
                            trace_id = payload_dict.get('trace_id', 'unknown-trace')
                            
                            # Publicar
                            msg = aio_pika.Message(
                                body=json.dumps(payload_dict).encode(),
                                content_type="application/json",
                                headers={"trace_id": trace_id}
                            )
                            await exchange.publish(msg, routing_key="")
                            
                            # Marcar completado
                            await conn.execute(
                                """
                                UPDATE outbox_eventos 
                                SET procesado = TRUE, procesado_en = NOW() 
                                WHERE id = $1
                                """, 
                                event_id
                            )
                            logger.info(f"[{trace_id}] Evento Outbox '{event_id}' publicado via RabbitMQ.")

            except Exception as e:
                logger.error(f"Falla crítica en el bucle Outbox: {e}")
                await asyncio.sleep(5)

    async def close(self):
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
