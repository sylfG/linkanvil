import pytest
import datetime
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch
from src.ingestion.main import app

client = TestClient(app)

@patch('src.ingestion.main.rabbit_publisher')
@patch('src.ingestion.main.deduplicator')
def test_telegram_webhook_valid_url(mock_deduplicator, mock_rabbit):
    mock_rabbit.publish_ingestion_message = AsyncMock()
    # Asignar mocks para evitar el bloqueo 503
    mock_deduplicator.is_new_item.return_value = True
    
    # Simular un webhook de Telegram
    payload = {
        "update_id": 12345,
        "message": {
            "message_id": 100,
            "from": {
                "id": 8888,
                "is_bot": False,
                "first_name": "TestUser"
            },
            "chat": {
                "id": 9999,
                "type": "private"
            },
            "date": 1718104500,
            "text": "Mira esto: https://test-article.cloud"
        }
    }
    
    response = client.post("/webhook/telegram", json=payload)
    
    # Validar Happy Path
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "processed"
    assert data["result"]["status"] == "Accepted & Published"
    
    # Verificar interaccion con el deduplicador (Requisito Tecnico: Aislamiento por Tenant)
    mock_deduplicator.is_new_item.assert_called_once()
    args = mock_deduplicator.is_new_item.call_args[0]
    
    # URL parseada correctamente
    assert args[0] == "https://test-article.cloud"
    # Tenant_id asilado bajo prefijo e ID de Chat (Aislamiento Multi-Tenant)
    assert args[1] == "tg_9999"

@patch('src.ingestion.main.rabbit_publisher')
@patch('src.ingestion.main.deduplicator')
def test_telegram_webhook_no_urls(mock_deduplicator, mock_rabbit):
    # Simular texto sin URLs
    payload = {
        "update_id": 12345,
        "message": {
            "chat": { "id": 9999 },
            "text": "Hola, ¿cómo estás?"
        }
    }
    
    response = client.post("/webhook/telegram", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ignored"
    assert data["reason"] == "no url found in text"

def test_telegram_webhook_edge_case_not_a_message():
    payload = {
        "update_id": 12345,
        "edited_message": {
            "chat": { "id": 9999 },
            "text": "Editado..."
        }
    }
    
    response = client.post("/webhook/telegram", json=payload)
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ignored"
    assert data["reason"] == "not a message"
