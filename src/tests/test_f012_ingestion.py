import pytest
import asyncio
from fastapi.testclient import TestClient
from src.ingestion.main import app, deduplicator, redis_client
from unittest.mock import AsyncMock, patch

@pytest.fixture
def client():
    # Asumimos que los eventos de startup de FastAPI configuran las dependencias reales.
    # En un entorno de CI local sin redis, pytest requeriria un mock de redis completo o skip if no connect.
    # Por ahora confiaremos arrancar con `TestClient` triggerendo `startup`.
    with TestClient(app) as test_client:
        yield test_client

@pytest.fixture(autouse=True)
def patch_rabbit():
    # Mockear RabbitMQPublisher clase para evitar conexiones reales
    with patch("src.ingestion.main.RabbitMQPublisher") as mock_rabbit_class:
        mock_instance = AsyncMock()
        mock_instance.connect = AsyncMock()
        mock_instance.publish_ingestion_message = AsyncMock(return_value=True)
        mock_instance.close = AsyncMock()
        mock_rabbit_class.return_value = mock_instance
        yield mock_rabbit_class

@pytest.fixture(autouse=True)
def clean_redis():
    """Limpia Redis rate limiter antes de cada test si está disponible"""
    from src.ingestion.main import redis_client
    if redis_client:
        try:
            redis_client.flushdb()
        except:
            pass
    yield
    if redis_client:
        try:
            redis_client.flushdb()
        except:
            pass

def test_f012_ingest_endpoint_success(client):
    """Prueba el Happy Path: Ingestar una nueva URL para un Tenant."""
    target_url = "https://example.com/test1"
    response = client.post("/ingest", json={
        "url": target_url,
        "tenant_id": "test_tenant",
        "source": "api_test"
    })
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Accepted & Published"
    assert data["is_duplicate"] == False

def test_f012_ingest_duplicate_rejected(client):
    """Prueba F-01.1: Deduplicación usando el mismo enlace."""
    target_url = "https://example.com/duplicate"
    body = {
        "url": target_url,
        "tenant_id": "test_tenant",
        "source": "api_test"
    }
    
    # Ingesta inicial
    res1 = client.post("/ingest", json=body)
    assert res1.status_code == 200
    assert res1.json()["is_duplicate"] == False
    
    # Ingesta repetida
    res2 = client.post("/ingest", json=body)
    assert res2.status_code == 200
    assert res2.json()["is_duplicate"] == True
    assert res2.json()["status"] == "Ignored"

def test_f012_ingest_rate_limiting(client):
    """Prueba el comportamiento de Noisy Neighbor (Throttling)"""
    body = {
        "tenant_id": "noisy_tenant",
        "source": "api_test"
    }

    # Mandar 10 peticiones (límite por minuto actual en main.py es 10)
    for i in range(10):
        body["url"] = f"https://example.com/noise_{i}"
        res = client.post("/ingest", json=body)
        assert res.status_code == 200

    # La petición 11 debe de rebotar con 429 Too Many Requests
    body["url"] = "https://example.com/noise_11"
    res_rejected = client.post("/ingest", json=body)
    assert res_rejected.status_code == 429
    assert "Too Many Requests" in res_rejected.json()["detail"]