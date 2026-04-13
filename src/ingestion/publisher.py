import aio_pika
import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

class RabbitMQPublisher:
    """
    Gestiona la conexión y publicación asíncrona hacia RabbitMQ.
    """
    def __init__(self, rabbit_url: str):
        self.rabbit_url = rabbit_url
        self.connection: Optional[aio_pika.RobustConnection] = None
        self.channel: Optional[aio_pika.RobustChannel] = None
        self.exchange: Optional[aio_pika.RobustExchange] = None

    async def connect(self):
        self.connection = await aio_pika.connect_robust(self.rabbit_url)
        self.channel = await self.connection.channel()
        # Publish to the specific exchange where "q.url.ingesta" is bound via "url.nueva"
        self.exchange = await self.channel.get_exchange("cerebro.ingesta")

    async def publish_ingestion_message(self, queue_name: str, payload: dict, trace_id: str):
        if not self.channel:
            await self.connect()

        # In RabbitMQ terms, queue_name passed here works as 'routing_key' -> 'url.nueva'
        message = aio_pika.Message(
            body=json.dumps(payload).encode("utf-8"),
            content_type="application/json",
            headers={"trace_id": trace_id}
        )
        
        logger.info(f"[{trace_id}] Publicando mensaje a la cola '{queue_name}'")
        await self.exchange.publish(message, routing_key=queue_name)

    async def close(self):
        if self.connection:
            await self.connection.close()