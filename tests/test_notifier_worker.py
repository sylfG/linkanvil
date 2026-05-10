"""Test del notifier worker invocando `process_message` directamente con
un mensaje aio_pika simulado. Cubre:
  - Inserción en `notificaciones`
  - Llamada a Telegram cuando el usuario tiene chat_id (en Redis)
  - Skip de eventos no relevantes (ej. recurso.procesado)
  - Skip de Telegram cuando no hay chat_id
"""
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.data.db import DatabaseManager
from src.notifier.worker import NotifierWorker, _human_message


def _fake_message(payload: dict) -> MagicMock:
    """Construye un objeto que parece aio_pika.IncomingMessage para nuestro
    process_message: solo necesitamos `body`, `headers` y un `process()`
    async-context-manager que no haga nada."""
    msg = MagicMock()
    msg.body = json.dumps(payload).encode()
    msg.headers = {"evento_tipo": payload.get("evento_tipo")}

    cm = AsyncMock()
    cm.__aenter__.return_value = cm
    cm.__aexit__.return_value = None
    msg.process = MagicMock(return_value=cm)
    return msg


@pytest.mark.asyncio
async def test_process_inserts_notification_and_skips_telegram_when_no_chat():
    db = DatabaseManager()
    await db.connect()
    tenant_id = "tenant_test_worker_no_chat"

    rid = None
    try:
        # Recurso del que extrae el título
        async with db.pool.acquire() as conn:
            rid = await conn.fetchval(
                """INSERT INTO recursos (url, url_hash, titulo, volatilidad, estado)
                   VALUES ($1, $2, 'Worker test', 'media', 'activo')
                   ON CONFLICT (url_hash) DO UPDATE SET updated_at = NOW()
                   RETURNING id""",
                "http://worker-test.example/1", "hash_worker_no_chat",
            )

        worker = NotifierWorker()
        worker.db = db  # reusa la pool ya conectada
        worker.redis = AsyncMock()
        worker.redis.get = AsyncMock(return_value=None)  # sin chat_id en cache
        worker.http = AsyncMock()  # no debería llamarse

        msg = _fake_message({
            "evento_tipo": "recurso.cuarentena",
            "tenant_id": tenant_id,
            "recurso_id": str(rid),
            "url": "http://worker-test.example/1",
            "motivo": "caducidad",
            "trace_id": "trc-worker-1",
        })
        await worker.process_message(msg)

        async with db.pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT evento_tipo, motivo, titulo, url, leido
                   FROM notificaciones WHERE tenant_id = $1""",
                tenant_id,
            )
            assert row is not None
            assert row["evento_tipo"] == "recurso.cuarentena"
            assert row["motivo"] == "caducidad"
            assert row["titulo"] == "Worker test"
            assert row["leido"] is False

        # Sin chat_id ni en Redis ni en BD → no debe haber llamada HTTP
        worker.http.post.assert_not_called()
    finally:
        async with db.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM notificaciones WHERE tenant_id = $1", tenant_id,
            )
            if rid:
                await conn.execute("DELETE FROM recursos WHERE id = $1", rid)
        await db.close()


@pytest.mark.asyncio
async def test_process_sends_telegram_when_user_has_chat_id():
    db = DatabaseManager()
    await db.connect()
    tenant_id = "tenant_test_worker_chat_unique"
    user_email = "worker-chat-test@example.com"
    rid = None
    user_id = None
    try:
        async with db.pool.acquire() as conn:
            user_id = await conn.fetchval(
                """INSERT INTO usuarios (email, password_hash, tenant_id,
                                          telegram_bot_token, telegram_bot_token_hash,
                                          telegram_bot_active, telegram_chat_id)
                   VALUES ($1, 'hash', $2, 'TEST_BOT_TOKEN', 'h', TRUE, 999111)
                   RETURNING id""",
                user_email, tenant_id,
            )
            rid = await conn.fetchval(
                """INSERT INTO recursos (url, url_hash, titulo, volatilidad, estado)
                   VALUES ($1, $2, 'Test con chat', 'media', 'activo')
                   ON CONFLICT (url_hash) DO UPDATE SET updated_at = NOW()
                   RETURNING id""",
                "http://worker-test.example/2", "hash_worker_with_chat",
            )

        worker = NotifierWorker()
        worker.db = db
        worker.redis = AsyncMock()
        worker.redis.get = AsyncMock(return_value=None)  # forzar fallback a BD

        # http.post devuelve un response 200 falso
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.text = ""
        worker.http = AsyncMock()
        worker.http.post = AsyncMock(return_value=fake_resp)

        msg = _fake_message({
            "evento_tipo": "recurso.expirado",
            "tenant_id": tenant_id,
            "recurso_id": str(rid),
            "url": "http://worker-test.example/2",
            "motivo": "gracia_agotada",
            "trace_id": "trc-worker-2",
        })
        await worker.process_message(msg)

        # Debe haber llamado a la API de Telegram
        worker.http.post.assert_called_once()
        call_args = worker.http.post.call_args
        assert "api.telegram.org/botTEST_BOT_TOKEN/sendMessage" in call_args[0][0]
        assert call_args[1]["json"]["chat_id"] == "999111"
        assert "expirado" in call_args[1]["json"]["text"].lower() or \
               "gracia" in call_args[1]["json"]["text"].lower() or \
               "🗑" in call_args[1]["json"]["text"]
    finally:
        async with db.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM notificaciones WHERE tenant_id = $1", tenant_id,
            )
            if rid:
                await conn.execute("DELETE FROM recursos WHERE id = $1", rid)
            if user_id:
                await conn.execute("DELETE FROM usuarios WHERE id = $1", user_id)
        await db.close()


@pytest.mark.asyncio
async def test_process_ignores_irrelevant_events():
    """recurso.procesado y recurso.reusado deben pasar de largo sin
    insertar nada ni tocar Telegram."""
    db = DatabaseManager()
    await db.connect()
    tenant_id = "tenant_test_worker_ignored"
    try:
        worker = NotifierWorker()
        worker.db = db
        worker.redis = AsyncMock()
        worker.http = AsyncMock()

        for ev in ("recurso.procesado", "recurso.reusado"):
            msg = _fake_message({
                "evento_tipo": ev,
                "tenant_id": tenant_id,
                "recurso_id": "00000000-0000-0000-0000-000000000000",
                "url": "http://x.test",
                "trace_id": "trc-x",
            })
            await worker.process_message(msg)

        async with db.pool.acquire() as conn:
            n = await conn.fetchval(
                "SELECT COUNT(*) FROM notificaciones WHERE tenant_id = $1",
                tenant_id,
            )
            assert n == 0

        worker.http.post.assert_not_called()
    finally:
        await db.close()


def test_human_message_shapes():
    """Mensajes de Telegram contienen elementos clave."""
    msg = _human_message("recurso.cuarentena", "caducidad", "Mi evento", "http://x")
    assert "Mi evento" in msg
    assert "caduc" in msg.lower()

    msg = _human_message("recurso.expirado", "gracia_agotada", None, "http://y")
    assert "http://y" in msg

    msg = _human_message("recurso.rescatado", None, "Salvado", "http://z")
    assert "Salvado" in msg
