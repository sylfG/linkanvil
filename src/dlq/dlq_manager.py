import aio_pika
import json
import logging
from typing import Callable, Any

logger = logging.getLogger(__name__)

class DLQManager:
    """
    Gestiona la Cola de Mensajes Muertos (DLQ) para tolerancia a fallos crónicos (F-01.5).
    Permite leer, inspeccionar, re-encolar o purgar elementos de una DLQ.
    """
    def __init__(self, rabbit_url: str):
        self.rabbit_url = rabbit_url
        self.connection = None
        self.channel = None

    async def connect(self):
        self.connection = await aio_pika.connect_robust(self.rabbit_url)
        self.channel = await self.connection.channel()

    async def close(self):
        if self.connection:
            await self.connection.close()

    async def get_dead_letters(self, dlq_name: str, count: int = 10) -> list[dict]:
        """Obtiene hasta 'count' mensajes de la DLQ sin sacarlos permanentemente (requiere rechazo)."""
        if not self.channel:
            await self.connect()
            
        queue = await self.channel.get_queue(dlq_name, ensure=False)
        messages = []
        
        while len(messages) < count:
            try:
                # get no-ack para solo inspeccionar? no, sacael mensaje
                msg = await queue.get(timeout=0.1, no_ack=False)
                parsed = json.loads(msg.body.decode())
                
                # Append metas like headers
                parsed["_headers"] = msg.headers
                messages.append((msg, parsed))
            except aio_pika.exceptions.QueueEmpty:
                break
                
        # Re-encolamos para no perderlos, solo estabamos inspeccionando
        for msg, _ in messages:
            await msg.reject(requeue=True)
            
        return [p for _, p in messages]

    async def retry_dead_letters(self, dlq_name: str, target_routing_key: str, target_exchange: str = ""):
        """Saca mensajes de la DLQ y los reinyecta a la cola original u otra llave de ruteo."""
        if not self.channel:
            await self.connect()
            
        queue = await self.channel.get_queue(dlq_name, ensure=False)
        exchange = await self.channel.get_exchange(target_exchange) if target_exchange else self.channel.default_exchange
        
        requeued = 0
        while True:
            try:
                msg = await queue.get(timeout=0.1, no_ack=False)
                # Re-publicar
                new_msg = aio_pika.Message(
                    body=msg.body,
                    content_type=msg.content_type,
                    headers=msg.headers
                )
                await exchange.publish(new_msg, routing_key=target_routing_key)
                await msg.ack()
                requeued += 1
            except aio_pika.exceptions.QueueEmpty:
                break
                
        logger.info(f"Re-encolados {requeued} mensajes desde la DLQ {dlq_name} hacia {target_routing_key}.")
        return requeued
        