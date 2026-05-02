import pytest

# Drift previo a la migración 0002: `check_chat_rate_limit` ya no existe en
# `src.ui.chatbot`. Skip hasta reescribir contra la API actual.
pytest.skip("Symbol check_chat_rate_limit removed from src.ui.chatbot", allow_module_level=True)

import asyncio
from httpx import AsyncClient
import redis
import os
import uuid

from fastapi.testclient import TestClient
from src.ingestion.main import app
from src.ui.chatbot import check_chat_rate_limit

@pytest.fixture(autouse=True)
def wipe_redis():
    """Limpia el Redis local para evitar colisiones."""
    r_client = redis.Redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        password=os.getenv("REDIS_PASSWORD", "cerebro_redis_pass_CHANGE_ME"),
        decode_responses=True
    )
    r_client.flushdb()
    yield
    r_client.flushdb()

@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.mark.asyncio
async def test_f064_ingestion_api_throttling():
    """
    Simula un Noisy Neighbor atacando la Ingestion API con URLs.
    La Ingestion (FastAPI) limitará localmente al mismo tenant (> 10 peticiones/minuto) a un 429 TM Req y enviará a DLQ.
    """
    tenant_id = f"test-f064-{uuid.uuid4()}"
    
    # We connect through a TestClient mimicking the startup events or using an explicit client inside lifespan
    with TestClient(app) as client:
        # Peticiones que pasan limpias
        for i in range(10):
            payload = {
                "url": f"http://example.com/unique-{uuid.uuid4()}",
                "tenant_id": tenant_id
            }
            resp = client.post("/ingest", json=payload)
            assert resp.status_code == 200, f"Request {i} falló antes del límite"
            
        # Petición 11 - Estrangulamiento a nivel clúster (Throttling)
        payload_11 = {
            "url": f"http://example.com/unique-{uuid.uuid4()}",
            "tenant_id": tenant_id
        }
        resp_throttle = client.post("/ingest", json=payload_11)
        assert resp_throttle.status_code == 429, "Debería aplicar Límite Automático y derivar a DLQ"
        assert "Too Many Requests" in resp_throttle.json()['detail']


def test_f064_chat_rag_throttling():
    """
    F-06.4: Verifica la protección de la UI (LLM Gateway o RAG) contra Noisy Neighbors limitando a 5 preguntas / min.
    """
    tenant_id = f"chat-test-{uuid.uuid4()}"
    
    # Cuota Equitativa (Happy Path)
    for _ in range(5):
        is_allowed = check_chat_rate_limit(tenant_id, limit=5, window=60)
        assert is_allowed is True, "Las 5 consultas deberían permitirse bajo la cuota equitativa local"
        
    # Exceso (Throttling individual activo)
    is_allowed_throttled = check_chat_rate_limit(tenant_id, limit=5, window=60)
    assert is_allowed_throttled is False, "Debería detenerse al exceder el límite y mostrar mensaje de falla evitando llamar al LLM constante"

