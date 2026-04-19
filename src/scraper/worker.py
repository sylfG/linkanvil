import asyncio
import aio_pika
import json
import logging
import os
from typing import Optional
import sys

# Ajuste el path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from src.scraper.strategy import ScraperContext
from src.data.db import DatabaseManager
from src.telemetry import configure_telemetry, trace_operation

logger = logging.getLogger(__name__)

# Activamos OpenTelemetry
configure_telemetry("scraper-worker")

class ScraperWorker:
    """
    Worker encargado de consumir mensajes asíncronamente desde "q.url.ingesta",
    ejecutar la extracción dinámica de la web mediante el Patrón Strategy,
    y publicar el resultado estructurado hacia el siguiente bloque del pipeline o DB.
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
        self.db = DatabaseManager()

    async def connect(self):
        self.connection = await aio_pika.connect_robust(self.rabbit_url)
        self.channel = await self.connection.channel()
        # Prefetch configurado para no ahogar al worker
        await self.channel.set_qos(prefetch_count=10)
        # Conectar a Base de datos (F-03.1)
        await self.db.connect()
        
    @trace_operation("process_scraper_message")
    async def process_message(self, message: aio_pika.IncomingMessage):
        """
        Lógica del consumidor:
        - Si extrae OK: emite ack y publica al siguiente exchange.
        - Si falla: emite reject (sin requeue) para derivarlo a la DLQ, F-01.5 Tolerancia.
        (Edge Case de la arquitectura implementada en tests anteriores).
        """
        async with message.process(requeue=False, ignore_processed=True):
            trace_id = "-".join(dict(message.headers).get("traceparent", "00-unknown-00-00").split("-")[1:3]) if "traceparent" in (message.headers or {}) else (message.headers.get("trace_id", "unknown-trace") if message.headers else "unknown-trace")
            
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
                
                # Preparar para publicar o guardar en BD localmente
                enrichment = {
                    **body,
                    "raw_content_length": len(raw_html),
                    "status": "extracted",
                }

                # Extraer la metadata si viene del Proxy IA
                extracted_data = {}
                try:
                    if raw_html:
                        extracted_data = json.loads(raw_html)
                except Exception:
                    # En BasicHttpStrategy no devuelve JSON estructurado,
                    # se adapta basico
                    extracted_data = {"summary": raw_html[:200], "title": url}
                
                # F-03.1 Patrón Outbox transaccional (reemplaza publicacion directa inconsistente)
                recurso_id = await self.db.save_with_outbox(
                    tenant_id=tenant_id,
                    trace_id=trace_id,
                    extracted_data=extracted_data,
                    url=url
                )
                
                logger.info(f"[{trace_id}] Extracción DB completada (ID={recurso_id}). Longitud: {len(raw_html)}")
                
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
        if hasattr(self, 'db'):
            await self.db.close()

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