import asyncio
import aio_pika
import httpx
import json
import logging
import os
import re
import sys
from datetime import datetime, timedelta
from typing import Optional

import redis.asyncio as aioredis

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from src.scraper.strategy import ScraperContext, BlockedContentError
from src.scraper._retry import with_retries
from src.data.db import DatabaseManager
from src.data.heartbeat import start_heartbeat
from src.telemetry import configure_telemetry, trace_operation

logger = logging.getLogger(__name__)

configure_telemetry("scraper-worker")

LITELLM_URL = os.getenv("LITELLM_URL", "http://litellm:4000")
LITELLM_KEY = os.getenv("LITELLM_API_KEY", "sk-cerebro-master-key-CHANGE_ME")
REDIS_URL = os.getenv("REDIS_URL", "redis://:cerebro_redis_pass@redis:6379")
# Cuántos días de margen exigimos sobre fecha_caducidad para reusar un recurso global
# sin re-scrapear. Por debajo se asume que conviene refrescar.
REUSE_FRESHNESS_MARGIN_DAYS = int(os.getenv("REUSE_FRESHNESS_MARGIN_DAYS", "15"))


def _html_to_clean_text(html: str, max_chars: int = 8000) -> tuple[str, str]:
    """(title, clean_text). Try trafilatura → BeautifulSoup → regex."""
    try:
        import trafilatura
        extracted = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=True,
            no_fallback=False,
            favor_precision=True,
        )
        meta = trafilatura.extract_metadata(html)
        title = (meta.title if meta else "") or ""
        if extracted and len(extracted) >= 200:
            return title, extracted[:max_chars]
    except Exception as e:
        logger.warning(f"trafilatura falló: {e}")

    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        title = soup.title.string.strip() if soup.title and soup.title.string else ""
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' {2,}', ' ', text)
        return title, text[:max_chars]
    except Exception:
        clean = re.sub(r'<[^>]+>', ' ', html)
        return "", re.sub(r'\s+', ' ', clean).strip()[:max_chars]


async def _extract_metadata_with_llm(
    http: httpx.AsyncClient, clean_text: str, title: str, url: str
) -> dict:
    """Call LiteLLM to extract structured metadata from page text."""
    prompt = (
        "Analiza el siguiente texto extraído de una página web y responde ÚNICAMENTE "
        "con un JSON válido (sin markdown) con estos campos:\n"
        "- \"title\": título del contenido\n"
        "- \"summary\": resumen de 2-3 frases en español\n"
        "- \"category\": una palabra en inglés (technology, science, business, health, "
        "politics, entertainment, education, other)\n"
        "- \"keywords\": lista de 3-5 palabras clave\n"
        "- \"volatility_score\": \"baja\" (docs/tutoriales), \"media\" (artículos), "
        "\"alta\" (noticias), o \"dinamica\" (precios/stocks)\n"
        "- \"estimated_useful_life_days\": entero entre 30 y 365\n"
        "- \"expiration_date\": fecha ISO YYYY-MM-DD si el contenido menciona una "
        "fecha concreta de evento, deadline, fin de oferta o caducidad explícita; "
        "null si no aplica o no se puede determinar\n\n"
        f"URL: {url}\n"
        f"Título HTML: {title or '(sin título)'}\n\n"
        f"Texto:\n{clean_text[:6000]}\n\n"
        "Responde SOLO con el JSON."
    )

    headers = {"Authorization": f"Bearer {LITELLM_KEY}", "Content-Type": "application/json"}
    try:
        async def _call():
            resp = await http.post(
                f"{LITELLM_URL}/v1/chat/completions",
                headers=headers,
                json={
                    "model": "cerebro-lite",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"].strip()
            if "```" in content:
                content = re.sub(r"```(?:json)?", "", content).strip()
            return json.loads(content)

        return await with_retries(_call)
    except Exception as e:
        logger.warning(f"LLM metadata extraction failed: {e}")

    return {
        "title": title or url,
        "summary": clean_text[:400],
        "category": "other",
        "keywords": [],
        "volatility_score": "media",
        "estimated_useful_life_days": 30,
        "expiration_date": None,
    }


class ScraperWorker:
    def __init__(
        self,
        rabbit_url: str,
        input_queue: str = "q.url.ingesta",
    ):
        self.rabbit_url = rabbit_url
        self.input_queue = input_queue
        self.connection: Optional[aio_pika.RobustConnection] = None
        self.channel: Optional[aio_pika.RobustChannel] = None
        self.db = DatabaseManager()
        self.redis: Optional[aioredis.Redis] = None
        self.http: Optional[httpx.AsyncClient] = None
        self.heartbeat_task: Optional[asyncio.Task] = None

    async def connect(self):
        self.connection = await aio_pika.connect_robust(self.rabbit_url)
        self.channel = await self.connection.channel()
        await self.channel.set_qos(prefetch_count=5)
        await self.db.connect()
        self.redis = aioredis.from_url(REDIS_URL, decode_responses=True)
        self.http = httpx.AsyncClient(timeout=30.0)
        self.heartbeat_task = start_heartbeat(self.redis, "scraper")

    @trace_operation("process_scraper_message")
    async def process_message(self, message: aio_pika.IncomingMessage):
        async with message.process(requeue=False, ignore_processed=True):
            headers = message.headers or {}
            trace_id = headers.get("trace_id", "unknown")

            try:
                body = json.loads(message.body.decode())
                url = body.get("url")
                tenant_id = body.get("tenant_id")
                source = body.get("source")

                logger.info(f"[{trace_id}] [TENANT:{tenant_id}] Recibida URL: {url}")

                # 0. Reuso global: si la URL ya existe en `recursos` con estado='activo'
                # y la caducidad está lejos, asociarla al tenant y pedir al embedder
                # que copie el punto Qdrant existente — saltamos scrape + LLM.
                existing = await self.db.find_existing_recurso_by_url(url)
                margin = timedelta(days=REUSE_FRESHNESS_MARGIN_DAYS)
                if existing and existing["estado"] == "activo":
                    fecha_cad = existing["fecha_caducidad"]
                    fresh = (fecha_cad is None) or (fecha_cad > (datetime.utcnow().date() + margin))
                    if fresh:
                        recurso_id = str(existing["id"])
                        await self.db.link_user_to_recurso(tenant_id, recurso_id)
                        await self.db.emit_reuse_event(tenant_id, trace_id, recurso_id, url)
                        logger.info(
                            f"[{trace_id}] Recurso reusado ({recurso_id}) — saltando scrape+LLM"
                        )
                        await message.ack()
                        return

                # 0.5 Pre-insert placeholder para feedback visual inmediato en KB.
                # save_with_outbox lo enriquecerá vía ON CONFLICT DO UPDATE.
                placeholder_id = None
                try:
                    placeholder_id = await self.db.insert_placeholder_recurso(
                        tenant_id=tenant_id, url=url
                    )
                except Exception as e:
                    logger.warning(f"[{trace_id}] No se pudo pre-insertar placeholder: {e}")

                # 1. Scrape
                logger.info(f"[{trace_id}] [TENANT:{tenant_id}] Extrayendo: {url}")
                scraper_ctx = ScraperContext(tenant_id=tenant_id, trace_id=trace_id, redis=self.redis)
                try:
                    raw_html = await scraper_ctx.execute(url=url, source=source)
                except BlockedContentError:
                    # El sitio devolvió un muro anti-bot que no pudimos
                    # superar. En vez de embeder texto basura, marcamos el
                    # recurso como cuarentena y ack-eamos el mensaje (no DLQ:
                    # no es un fallo técnico recuperable).
                    if placeholder_id:
                        try:
                            await self.db.quarantine_recurso_blocked(placeholder_id)
                        except Exception as qe:
                            logger.error(f"[{trace_id}] Fallo marcando cuarentena: {qe}")
                    logger.info(f"[{trace_id}] Recurso bloqueado por anti-bot, en cuarentena: {url}")
                    await message.ack()
                    return

                # 2. Clean HTML → plain text
                html_title, clean_text = _html_to_clean_text(raw_html)
                logger.info(f"[{trace_id}] Texto limpio: {len(clean_text)} chars")

                # Guard de calidad: si el contenido extraído es trivialmente
                # corto, el LLM solo podría inventar un resumen sin sustancia.
                # Mejor cuarentena que basura indexada en RAG.
                if len(clean_text.strip()) < 300:
                    if placeholder_id:
                        try:
                            await self.db.quarantine_recurso_blocked(placeholder_id)
                        except Exception as qe:
                            logger.error(f"[{trace_id}] Fallo marcando cuarentena: {qe}")
                    logger.info(
                        f"[{trace_id}] Contenido demasiado corto ({len(clean_text)} chars), cuarentena: {url}"
                    )
                    await message.ack()
                    return

                # 3. LLM metadata extraction
                extracted_data = await _extract_metadata_with_llm(self.http, clean_text, html_title, url)
                logger.info(
                    f"[{trace_id}] Metadata extraída: title='{extracted_data.get('title','')[:60]}' "
                    f"category={extracted_data.get('category','?')}"
                )

                # 4. Save to DB (outbox pattern)
                recurso_id = await self.db.save_with_outbox(
                    tenant_id=tenant_id,
                    trace_id=trace_id,
                    extracted_data=extracted_data,
                    url=url,
                )

                logger.info(f"[{trace_id}] Guardado con ID={recurso_id}")
                await message.ack()

            except Exception as e:
                logger.error(f"[{trace_id}] Fallo en extracción: {e}")
                await message.reject(requeue=False)

    async def consume(self):
        if not self.channel:
            await self.connect()
        queue = await self.channel.get_queue(self.input_queue, ensure=False)
        logger.info(f"Iniciando consumo del Worker Scraper en cola '{self.input_queue}'")
        await queue.consume(self.process_message)

    async def close(self):
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
        if self.connection:
            await self.connection.close()
        if hasattr(self, "db"):
            await self.db.close()
        if self.redis:
            await self.redis.aclose()
        if self.http:
            await self.http.aclose()


async def run_worker():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    RABBIT_URL = os.getenv("RABBITMQ_URL", "amqp://cerebro:cerebro_pass@localhost:5672/cerebro")
    worker = ScraperWorker(rabbit_url=RABBIT_URL)
    await worker.consume()
    logger.info("Scraper Worker escuchando activamente...")
    try:
        await asyncio.Future()
    except asyncio.CancelledError:
        pass
    finally:
        await worker.close()


if __name__ == "__main__":
    asyncio.run(run_worker())
