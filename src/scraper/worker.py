import asyncio
import aio_pika
import json
import logging
import os
from typing import Optional
from src.scraper.strategy import ScraperContext

logger = logging.getLogger(__name__)

class ScraperWorker:
    """
    Worker encargado de consumir mensajes asíncronamente desde "q.url.ingesta",
    ejecutar la extracción dinámica de la web mediante el Patrón Strategy,
    y publicar el resultado estructurado hacia el siguiente bloque del pipeline (Ej. LiteLLM Proxy)
    """
    def __init__(
            self, 
            rabbit_url: str, 
            input_queue: str = "q.url.ingesta",
            output_exchange: str = "cerebro.procesamiento",
            dlq_routing_key: str = "dlq.url.fallidas"
    ):
        self.rabbit_url = rabbit_url
        self.input_queue = input_queue
        self.output_exchange = output_exchange
        self.dlq_routing_key = dlq_routing_key
        
        self.connection: Optional[aio_pika.RobustConnection] = None
        self.channel: Optional[aio_pika.RobustChannel] = None

    async def connect(self):
        self.connection = await aio_pika.connect_robust(self.rabbit_url)
        self.channel = await self.connection.channel()
        # Prefetch configurado para no ahogar al worker
        await self.channel.set_qos(prefetch_count=10)
        
    async def process_message(self, message: aio_pika.IncomingMessage):
        """
        Lógica del consumidor:
        - Si extrae OK: emite ack y publica al siguiente exchange.
        - Si falla: emite reject (sin requeue) para derivarlo a la DLQ, F-01.5 Tolerancia.
        (Edge Case de la arquitectura implementada en tests anteriores).
        """
        async with message.process(requeue=False, ignore_processed=True):
            trace_id = message.headers.get("trace_id", "unknown-trace")
            
            try:
                body = json.loads(message.body.decode())
                url = body.get("url")
                tenant_id = body.get("tenant_id")
                source = body.get("source")
                
                logger.info(f"[{trace_id}] [TENANT:{tenant_id}] Ruteando extracción de: {url}")
                
                # Instanciar el contexto de extracción dinámica (Strategy)
                scraper_ctx = ScraperContext(tenant_id=tenant_id, trace_id=trace_id)
                
                # Ejecutar extraccion
                raw_html = await scraper_ctx.execute(url=url, source=source)
                
                # Preparar para publicar
                enrichment = {
                    **body,
                    "raw_content_length": len(raw_html),
                    "status": "extracted",
                }
                
                # F-02.3 y etc definen los exchanges posteriores (ej. procesamiento LLM)
                exchange = await self.channel.get_exchange(self.output_exchange)
                
                out_msg = aio_pika.Message(
                    body=json.dumps(enrichment).encode(),
                    content_type="application/json",
                    headers={"trace_id": trace_id}
                )
                
                await exchange.publish(out_msg, routing_key="") # fanout / default
                logger.info(f"[{trace_id}] Extracción completada para {url}. Longitud: {len(raw_html)}")
                
                await message.ack()
                
            except Exception as e:
                logger.error(f"[{trace_id}] Fallo crónico durante la extracción: {e}")
                # Rechazar para derivar a la Dead Letter Queue (q.url.fallidas) -> F-01.5 / F-02.1 DLQ derivación.
                await message.reject(requeue=False)

    async def consume(self):
        if not self.channel:
            await self.connect()
            
        queue = await self.channel.get_queue(self.input_queue, ensure=False)
        logger.info(f"Iniciando consumo del Worker Scraper en cola '{self.input_queue}'")
        
        await queue.consume(self.process_message)

    async def close(self):
        if self.connection:
            await self.connection.close()

async def run_worker():
    import os
    logging.basicConfig(level=logging.INFO)
    RABBIT_URL = os.getenv("RABBITMQ_URL", "amqp://cerebro:cerebro_pass@localhost:5672/cerebro")
    
    worker = ScraperWorker(rabbit_url=RABBIT_URL)
    await worker.consume()
    logger.info("Scraper Worker escuchando activamente...")
    
    # Keep running forever
    try:
        await asyncio.Future()
    except asyncio.CancelledError:
        pass
    finally:
        await worker.close()

if __name__ == "__main__":
    asyncio.run(run_worker())