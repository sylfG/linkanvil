import pytest
from fastapi.testclient import TestClient
from src.ingestion.main import app
from unittest.mock import AsyncMock, patch

@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client

@pytest.fixture(autouse=True)
def patch_rabbit():
    with patch("src.ingestion.main.RabbitMQPublisher") as mock_rabbit_class:
        mock_instance = AsyncMock()
        mock_instance.connect = AsyncMock()
        mock_instance.publish_ingestion_message = AsyncMock(return_value=True)
        mock_instance.close = AsyncMock()
        mock_rabbit_class.return_value = mock_instance
        yield mock_rabbit_class

@pytest.fixture(autouse=True)
def clean_redis():
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

def test_f014_external_webhook_plain_text(client):
    """Test webhook con string directo (ej. SMS relay simple)"""
    payload = "Encontré este sitio interesante: https://example.com/blog/1"
    response = client.post("/webhook/external?tenant_id=cliente1", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "processed"
    assert len(data["results"]) == 1


def test_f014_external_webhook_structured_json(client):
    """Test webhook con JSON de n8n, Make u otras plataformas estructuradas."""
    payload = {
        "event": "new_link",
        "user_data": "cliente2",
        "url": "https://example.com/articulo-estructurado",
        "body": "Mira https://otrolink.com por si acaso"
    }
    
    response = client.post("/webhook/external?tenant_id=cliente2", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "processed"
    
    # Debe priorizar extraer "url", o hacer texto y extraer todo.
    # main.py dice: si data.get("url"), asume como text_content el direct URL y oculta el resto de texto 
    # (por simplificar, o si no extrae el resto).
    # Como tiene key "url", procesa esa url exacta:
    assert len(data["results"]) == 1


def test_f014_external_webhook_no_url(client):
    """Test de webhook que no contiene ninguna URL para evitar spam"""
    payload = {"text": "Hola Cerebro, ¿qué tal?"}
    response = client.post("/webhook/external?tenant_id=cliente3", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ignored"
    assert data["reason"] == "no url found in generic payload"