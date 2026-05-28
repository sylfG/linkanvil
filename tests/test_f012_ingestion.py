import pytest
import asyncio
from fastapi.testclient import TestClient
from src.ingestion.main import app
from unittest.mock import AsyncMock, patch


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def patch_rabbit():
    """Mockear RabbitMQPublisher para evitar conexiones reales."""
    with patch("src.ingestion.main.RabbitMQPublisher") as mock_rabbit_class:
        mock_instance = AsyncMock()
        mock_instance.connect = AsyncMock()
        mock_instance.publish_ingestion_message = AsyncMock(return_value=True)
        mock_instance.close = AsyncMock()
        mock_rabbit_class.return_value = mock_instance
        yield mock_rabbit_class


@pytest.fixture(autouse=True)
def clean_redis():
    """Limpia Redis (bloom filters + rate_limit) antes/después de cada test.

    El cliente es async (`redis.asyncio`), así que las llamadas hay que awaitarlas
    en un event loop. La versión anterior usaba `flushdb()` sincrónico contra un
    cliente async, lo que ensuciaba el estado del bloom entre tests y generaba
    falsos positivos de duplicado.
    """
    from src.ingestion.main import redis_client

    async def _flush():
        if redis_client is None:
            return
        try:
            await redis_client.flushdb()
        except Exception:
            pass

    if redis_client:
        try:
            asyncio.get_event_loop().run_until_complete(_flush())
        except RuntimeError:
            asyncio.run(_flush())
    yield
    if redis_client:
        try:
            asyncio.get_event_loop().run_until_complete(_flush())
        except RuntimeError:
            asyncio.run(_flush())


# El endpoint /ingest devuelve siempre status 202 (Accepted) — fija en main.py
# vía `@app.post("/ingest", ..., status_code=202)`. Las respuestas concretas
# distinguen el resultado funcional vía `status` e `is_duplicate`:
#   - URL nueva  → status="Accepted & Published", is_duplicate=False
#   - URL repetida → status="Accepted (relink)",   is_duplicate=True
# (cambio de contrato 2026-05: siempre se publica, el dedup solo es hint
# para evitar re-scrape cuando el worker ya tiene el recurso).


def test_f012_ingest_endpoint_success(client):
    """Happy Path: ingestar una nueva URL para un tenant."""
    target_url = "https://example.com/test1_success"
    response = client.post("/ingest", json={
        "url": target_url,
        "tenant_id": "test_tenant_success",
        "source": "api_test",
    })

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "Accepted & Published"
    assert data["is_duplicate"] is False


def test_f012_ingest_duplicate_rejected(client):
    """F-01.1: una segunda ingesta de la misma URL marca is_duplicate=True
    pero sigue siendo aceptada (relink) — el worker resuelve idempotencia."""
    target_url = "https://example.com/duplicate_unique"
    body = {
        "url": target_url,
        "tenant_id": "test_tenant_dup",
        "source": "api_test",
    }

    res1 = client.post("/ingest", json=body)
    assert res1.status_code == 202
    assert res1.json()["is_duplicate"] is False
    assert res1.json()["status"] == "Accepted & Published"

    res2 = client.post("/ingest", json=body)
    assert res2.status_code == 202
    assert res2.json()["is_duplicate"] is True
    assert res2.json()["status"] == "Accepted (relink)"


def test_f012_ingest_rate_limiting(client):
    """F-06.4 Noisy Neighbor: 10 reqs aceptadas, la 11ª devuelve 429."""
    body = {
        "tenant_id": "noisy_tenant_unique",
        "source": "api_test",
    }

    for i in range(10):
        body["url"] = f"https://example.com/noise_{i}"
        res = client.post("/ingest", json=body)
        assert res.status_code == 202, f"req {i} debería ser 202 (Accepted), fue {res.status_code}"

    body["url"] = "https://example.com/noise_11"
    res_rejected = client.post("/ingest", json=body)
    assert res_rejected.status_code == 429
    assert "Too Many Requests" in res_rejected.json()["detail"]
