"""
Tests del webhook de Telegram tras el audit de seguridad 2026-05-19.

El endpoint legacy `/webhook/telegram` (sin path-param) **fue eliminado**:
aceptaba cualquier payload sin auth y permitía crear sub-tenants
`tg_{chat_id}` arbitrarios. El único endpoint válido es ahora
`/webhook/telegram/{token_hash}` que resuelve `tenant_id` desde Redis
(`telegram:{token_hash}`) — el token_hash lo registra el usuario vía
`PUT /profile/telegram` en cerebro-api.

Estos tests cubren:
1. Regresión de seguridad: el endpoint legacy devuelve 404.
2. Happy path del endpoint autenticado: URL válida + token válido →
   ingestion.
3. Edge case del endpoint autenticado: texto sin URLs → ignored.
4. Edge case del endpoint autenticado: edited_message → ignored.
5. Defensa: token_hash desconocido (no mapeado en Redis) → 404.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch
from src.ingestion.main import app

client = TestClient(app)

VALID_TOKEN_HASH = "a" * 64  # SHA256 ficticio del bot token registrado
TENANT_FOR_TOKEN = "user_test_tenant"


# ---------------------------------------------------------------------------
# Regresión de seguridad — endpoint legacy eliminado
# ---------------------------------------------------------------------------

def test_legacy_telegram_webhook_returns_404():
    """El endpoint legacy `/webhook/telegram` sin path-param fue eliminado
    en el audit 2026-05-19 por aceptar cualquier payload sin auth.
    Cualquier integración debe migrar al endpoint con `{token_hash}`."""
    payload = {
        "update_id": 1,
        "message": {
            "chat": {"id": 9999},
            "text": "https://evil.example/exfil"
        }
    }
    response = client.post("/webhook/telegram", json=payload)
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Endpoint autenticado `/webhook/telegram/{token_hash}`
# ---------------------------------------------------------------------------

@patch("src.ingestion.main.rabbit_publisher")
@patch("src.ingestion.main.deduplicator")
@patch("src.ingestion.main.redis_client")
def test_telegram_webhook_valid_url(mock_redis, mock_deduplicator, mock_rabbit):
    """Happy path: token registrado + URL extraída del mensaje → publica
    en la cola de ingesta con el tenant_id resuelto desde Redis."""
    mock_redis.get = AsyncMock(return_value=TENANT_FOR_TOKEN)
    mock_redis.set = AsyncMock(return_value=None)
    # ingest_url usa redis_client.incr/expire para rate-limit; mockear async.
    mock_redis.incr = AsyncMock(return_value=1)
    mock_redis.expire = AsyncMock(return_value=True)
    mock_rabbit.publish_ingestion_message = AsyncMock()
    mock_deduplicator.is_new_item = AsyncMock(return_value=True)

    payload = {
        "update_id": 12345,
        "message": {
            "message_id": 100,
            "from": {"id": 8888, "is_bot": False, "first_name": "TestUser"},
            "chat": {"id": 9999, "type": "private"},
            "date": 1718104500,
            "text": "Mira esto: https://test-article.cloud",
        },
    }

    response = client.post(f"/webhook/telegram/{VALID_TOKEN_HASH}", json=payload)

    assert response.status_code == 200
    # El deduplicador se llama con el tenant resuelto desde Redis,
    # no con un tenant fabricado desde el chat_id (anti-spoof).
    mock_deduplicator.is_new_item.assert_called_once()
    args = mock_deduplicator.is_new_item.call_args[0]
    assert args[0] == "https://test-article.cloud"
    assert args[1] == TENANT_FOR_TOKEN  # NO "tg_9999"


@patch("src.ingestion.main.rabbit_publisher")
@patch("src.ingestion.main.deduplicator")
@patch("src.ingestion.main.redis_client")
def test_telegram_webhook_no_urls(mock_redis, mock_deduplicator, mock_rabbit):
    """Edge case: el mensaje no contiene URLs → ignored sin publicar."""
    mock_redis.get = AsyncMock(return_value=TENANT_FOR_TOKEN)
    mock_redis.set = AsyncMock(return_value=None)
    mock_redis.incr = AsyncMock(return_value=1)
    mock_redis.expire = AsyncMock(return_value=True)
    mock_rabbit.publish_ingestion_message = AsyncMock()
    mock_deduplicator.is_new_item = AsyncMock(return_value=True)

    payload = {
        "update_id": 12345,
        "message": {"chat": {"id": 9999}, "text": "Hola, ¿cómo estás?"},
    }

    response = client.post(f"/webhook/telegram/{VALID_TOKEN_HASH}", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data.get("status") == "ignored"


@patch("src.ingestion.main.redis_client")
def test_telegram_webhook_edited_message_ignored(mock_redis):
    """Edge case: el update no es un mensaje nuevo (es edited_message) →
    ignored sin tocar nada."""
    mock_redis.get = AsyncMock(return_value=TENANT_FOR_TOKEN)

    payload = {
        "update_id": 12345,
        "edited_message": {"chat": {"id": 9999}, "text": "Editado..."},
    }
    response = client.post(f"/webhook/telegram/{VALID_TOKEN_HASH}", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data.get("status") == "ignored"


@patch("src.ingestion.main.redis_client")
def test_telegram_webhook_unknown_token_returns_404(mock_redis):
    """Defensa: si el token_hash NO está mapeado en Redis (bot no
    registrado vía /profile/telegram), el endpoint devuelve 404 — no
    se procesa el mensaje y no se filtra información sobre tokens
    válidos."""
    mock_redis.get = AsyncMock(return_value=None)

    payload = {
        "update_id": 1,
        "message": {"chat": {"id": 9999}, "text": "https://example.com/x"},
    }
    response = client.post(f"/webhook/telegram/{VALID_TOKEN_HASH}", json=payload)
    assert response.status_code == 404
