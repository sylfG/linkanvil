"""Notifier worker (F-05.3) — Avisa al usuario de transiciones del ciclo
de obsolescencia: `recurso.cuarentena`, `recurso.expirado` y `recurso.rescatado`. Tambien `recurso.activado` cuando un recurso entra por primera vez en la BC.

Consume de la fanout `cerebro.procesamiento` (a través de la cola dedicada
`q.notifications`), crea una fila en `notificaciones` (feed in-app) y, si el
tenant tiene un bot de Telegram configurado y un chat_id capturado, envía
un mensaje al chat correspondiente.

El chat_id se cachea en Redis (`telegram_chat:{tenant_id}`) cuando el usuario
manda un mensaje al bot por primera vez (ver `src/ingestion/main.py`). El
worker lo persiste en `usuarios.telegram_chat_id` la primera vez que lo
ve, para sobrevivir a un flush de Redis.
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Optional

import aio_pika
import httpx
import redis.asyncio as aioredis

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
from src.data.db import DatabaseManager
from src.data.heartbeat import start_heartbeat
from src.telemetry import configure_telemetry, trace_operation

from src.observability.logging import configure_json_logging

configure_json_logging("notifier-worker")
logger = logging.getLogger(__name__)

configure_telemetry("notifier-worker")

RABBIT_URL = os.getenv(
    "RABBITMQ_URL", "amqp://cerebro:cerebro_pass@localhost:5672/cerebro"
)
EXCHANGE_NAME = os.getenv("RABBITMQ_EXCHANGE_PROCESAMIENTO", "cerebro.procesamiento")
QUEUE_NAME = os.getenv("NOTIFIER_QUEUE", "q.notifications")
REDIS_URL = os.getenv("REDIS_URL", "redis://:cerebro_redis_pass@redis:6379")

# Sólo nos interesan estos eventos. El resto los ack-eamos sin tocar BD.
RELEVANT_EVENTS = {
    "recurso.cuarentena",
    "recurso.expirado",
    "recurso.rescatado",
    "recurso.activado",
}

REASON_LABELS = {
    "caducidad": "ha caducado",
    "colision_semantica": "ha sido reemplazado por contenido más reciente",
    "manual": "se marcó manualmente",
    "gracia_agotada": "agotó su período de gracia",
    # Migración 0006: cuarentena automática al detectar fecha pasada al ingestar.
    "evento_pasado": "tiene fecha pasada y requiere revisión",
    # Migración 0007: archivo automático tras detectar valor archivístico alto.
    "auto_archive": "tiene fecha pasada y se archivó automáticamente",
}


def _human_message(
    evento_tipo: str, motivo: Optional[str], titulo: Optional[str], url: str
) -> str:
    """Compose a short Telegram message from the event."""
    label = titulo or url
    if evento_tipo == "recurso.cuarentena":
        razon = REASON_LABELS.get(motivo or "", "ha entrado en cuarentena")
        return (
            f'⚠️ Tu recurso "{label}" {razon}.\n'
            f"Revísalo en la bandeja de cuarentena para rescatarlo o expirarlo.\n"
            f"{url}"
        )
    if evento_tipo == "recurso.expirado":
        # Auto-archive (migración 0007) usa el mismo evento_tipo que la
        # expiración tradicional, pero el copy es distinto: no se borra
        # del RAG, se archiva (recuperable con toggle Archivo ON).
        if motivo == "auto_archive":
            return (
                f'📦 Tu recurso "{label}" se archivó automáticamente al detectar '
                f"valor archivístico alto. Recuperable en el chat con el toggle "
                f'"Archivo ON".\n{url}'
            )
        razon = REASON_LABELS.get(motivo or "", "ha expirado")
        return f'🗑 Tu recurso "{label}" {razon} y se eliminó del RAG activo.\n{url}'
    if evento_tipo == "recurso.rescatado":
        return f'♻️ Has rescatado "{label}" — vuelve a estar activo.\n{url}'
    if evento_tipo == "recurso.activado":
        return (
            f'📚 Tu recurso "{label}" se ha añadido a tu Base de Conocimiento.\n{url}'
        )
    return f"{evento_tipo}: {label}"


class NotifierWorker:
    def __init__(self):
        self.db = DatabaseManager()
        self.redis: Optional[aioredis.Redis] = None
        self.http: Optional[httpx.AsyncClient] = None
        self.connection: Optional[aio_pika.RobustConnection] = None
        self.channel: Optional[aio_pika.RobustChannel] = None
        self.queue: Optional[aio_pika.RobustQueue] = None
        self.heartbeat_task: Optional[asyncio.Task] = None

    async def connect(self):
        await self.db.connect()
        self.redis = aioredis.from_url(REDIS_URL, decode_responses=True)
        self.http = httpx.AsyncClient(timeout=15.0)
        self.heartbeat_task = start_heartbeat(self.redis, "notifier")

        self.connection = await aio_pika.connect_robust(RABBIT_URL)
        self.channel = await self.connection.channel()
        await self.channel.set_qos(prefetch_count=10)

        exchange = await self.channel.get_exchange(EXCHANGE_NAME)
        self.queue = await self.channel.declare_queue(QUEUE_NAME, durable=True)
        await self.queue.bind(exchange, routing_key="")

    async def close(self):
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
        if self.http:
            await self.http.aclose()
        if self.redis:
            await self.redis.aclose()
        if self.connection:
            await self.connection.close()
        await self.db.close()

    async def _resolve_titulo(self, recurso_id: str) -> Optional[str]:
        if not recurso_id:
            return None
        async with self.db.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT titulo FROM recursos WHERE id = $1::uuid",
                recurso_id,
            )
            return row["titulo"] if row else None

    async def _insert_notification(
        self,
        tenant_id: str,
        evento_tipo: str,
        recurso_id: Optional[str],
        titulo: Optional[str],
        url: Optional[str],
        motivo: Optional[str],
    ) -> None:
        async with self.db.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO notificaciones (
                    tenant_id, evento_tipo, recurso_id, titulo, url, motivo
                ) VALUES (
                    $1, $2, $3::uuid, $4, $5, $6
                )
                """,
                tenant_id,
                evento_tipo,
                recurso_id,
                titulo,
                url,
                motivo,
            )

    async def _get_telegram_target(self, tenant_id: str) -> Optional[tuple[str, str]]:
        """Devuelve (bot_token, chat_id) o None si el usuario no tiene
        Telegram configurado o no hemos capturado su chat_id todavía.

        Lookup chat_id: Redis primero (caché caliente, set por ingestion al
        recibir mensajes), DB después como fallback persistente. Si lo
        encontramos en Redis pero no en DB, lo sincronizamos.
        """
        bot_token = chat_id_from_db = None
        try:
            async with self.db.pool.acquire() as conn:
                row = await conn.fetchrow(
                    """SELECT telegram_bot_token, telegram_bot_active, telegram_chat_id
                       FROM usuarios WHERE tenant_id = $1""",
                    tenant_id,
                )
                if (
                    not row
                    or not row["telegram_bot_active"]
                    or not row["telegram_bot_token"]
                ):
                    return None
                bot_token = row["telegram_bot_token"]
                chat_id_from_db = row["telegram_chat_id"]
        except Exception as e:
            logger.warning(f"DB lookup falló para tenant={tenant_id}: {e}")
            return None

        chat_id_from_cache = None
        try:
            if self.redis:
                v = await self.redis.get(f"telegram_chat:{tenant_id}")
                if v:
                    chat_id_from_cache = int(v)
        except Exception as e:
            logger.warning(f"Redis lookup chat_id falló: {e}")

        chat_id = chat_id_from_cache or chat_id_from_db
        if chat_id is None:
            return None

        # Sync DB <- cache si el cache tenía valor y la BD no
        if chat_id_from_cache and not chat_id_from_db:
            try:
                async with self.db.pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE usuarios SET telegram_chat_id = $1 WHERE tenant_id = $2",
                        chat_id_from_cache,
                        tenant_id,
                    )
            except Exception as e:
                logger.warning(f"No pudimos persistir chat_id en BD: {e}")

        return bot_token, str(chat_id)

    async def _send_telegram(self, bot_token: str, chat_id: str, text: str) -> None:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        try:
            resp = await self.http.post(
                url,
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "disable_web_page_preview": False,
                },
            )
            if resp.status_code >= 400:
                logger.warning(
                    f"Telegram sendMessage falló ({resp.status_code}): {resp.text[:200]}"
                )
        except Exception as e:
            logger.warning(f"Telegram sendMessage error: {e}")

    @trace_operation("process_notification")
    async def process_message(self, message: aio_pika.IncomingMessage):
        async with message.process(requeue=False, ignore_processed=True):
            try:
                payload = json.loads(message.body.decode())
            except Exception as e:
                logger.error(f"Payload inválido, descartando: {e}")
                return

            evento_tipo = payload.get("evento_tipo") or message.headers.get(
                "evento_tipo"
            )
            if evento_tipo not in RELEVANT_EVENTS:
                # Otros consumidores (embedder) procesan el resto; nosotros no.
                return

            tenant_id = payload.get("tenant_id")
            recurso_id = payload.get("recurso_id")
            url = payload.get("url")
            motivo = payload.get("motivo")
            if not tenant_id:
                logger.warning(f"Evento sin tenant_id, ignorado: {payload}")
                return

            titulo = payload.get("titulo") or await self._resolve_titulo(recurso_id)

            try:
                await self._insert_notification(
                    tenant_id,
                    evento_tipo,
                    recurso_id,
                    titulo,
                    url,
                    motivo,
                )
            except Exception as e:
                logger.error(f"INSERT notificacion falló: {e}")
                return

            # Fan-out a SSE: cualquier UI suscrita a `resources:{tenant_id}`
            # se entera al instante. No bloqueante: si Redis falla, ya hemos
            # persistido la notificación; el polling de fallback recoge.
            try:
                if self.redis is not None:
                    await self.redis.publish(
                        f"resources:{tenant_id}",
                        json.dumps(
                            {
                                "evento_tipo": evento_tipo,
                                "recurso_id": recurso_id,
                                "url": url,
                                "titulo": titulo,
                                "motivo": motivo,
                                "created_at": datetime.now(timezone.utc).isoformat(),
                            }
                        ),
                    )
            except Exception as e:
                logger.warning(f"redis.publish resources:{tenant_id} falló: {e}")

            target = await self._get_telegram_target(tenant_id)
            if target:
                bot_token, chat_id = target
                text = _human_message(evento_tipo, motivo, titulo, url or "")
                await self._send_telegram(bot_token, chat_id, text)

            logger.info(
                f"Notificación procesada: tenant={tenant_id} evento={evento_tipo} "
                f"recurso={recurso_id} telegram={'sí' if target else 'no'}"
            )

    async def consume(self):
        logger.info(f"Notifier consumiendo de {QUEUE_NAME} (exchange {EXCHANGE_NAME})")
        await self.queue.consume(self.process_message)
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            pass


async def run_notifier():
    worker = NotifierWorker()
    await worker.connect()
    try:
        await worker.consume()
    finally:
        await worker.close()


if __name__ == "__main__":
    asyncio.run(run_notifier())
