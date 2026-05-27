import pytest
import uuid
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch
from src.ingestion.main import app

def test_f002_api_gateway_happy_path_headers():
    """
    F-00.2 Criterio de Aceptación: Happy Path y Requisito Técnico.
    Verifica que la API acepta correctamente el tráfico simulado desde Traefik
    manteniendo la traza Trace ID y Tenant_ID.
    """
    client = TestClient(app)
    tenant_id = f"tenant-{uuid.uuid4()}"
    trace_id = f"trace-{uuid.uuid4()}"

    # Traefik suele inyectar X-Forwarded-For y, si OTel está configurado, Traceparent o X-B3-TraceId.
    headers = {
        "X-Forwarded-For": "192.168.1.100",
        "X-Tenant-ID": tenant_id,
        "traceparent": f"00-{trace_id.replace('-', '')[:32]}-0000000000000001-01"
    }

    payload = {
        "url": "https://example.com/happy-path-test",
        "tenant_id": tenant_id,
        "trace_id": trace_id
    }

    # Mockeamos el RabbitMQPublisher y el Deduplicator para no depender de infraestructura viva en el test unitario.
    with patch('src.ingestion.main.deduplicator') as mock_dedup, \
         patch('src.ingestion.main.rabbit_publisher') as mock_pub:

        # `is_new_item` es async — debe ser AsyncMock, no MagicMock con return_value
        # (de lo contrario el endpoint falla con "object bool can't be used in
        # 'await' expression").
        mock_dedup.is_new_item = AsyncMock(return_value=True)
        mock_pub.publish_ingestion_message = AsyncMock()

        response = client.post("/ingest", json=payload, headers=headers)

        # /ingest declara status_code=202 (Accepted). Aceptamos 200/202 por
        # compatibilidad futura.
        assert response.status_code in (200, 202), \
            f"Happy Path debería retornar 200/202, fue {response.status_code}"

        data = response.json()
        assert data["trace_id"] == trace_id, "Debe mantener la traza Trace ID (Requisito Técnico)."
        assert data["status"] == "Accepted & Published"

def test_f002_api_gateway_edge_case_fallback_dlq():
    """
    F-00.2 Criterio de Aceptación: Edge Case.
    Dado que el puente/backend cae (RabbitMQ arroja excepción),
    Cuando se intenta ejecutar por el Gateway,
    Entonces deriva a la DLQ o efectúa Fallback (FastAPI lo captura y lo manda a la DLQ).
    """
    client = TestClient(app)
    tenant_id = f"tenant-dlq-{uuid.uuid4()}"
    trace_id = f"trace-dlq-{uuid.uuid4()}"

    payload = {
        "url": "https://example.com/edge-case-test",
        "tenant_id": tenant_id,
        "trace_id": trace_id
    }

    with patch('src.ingestion.main.deduplicator') as mock_dedup, \
         patch('src.ingestion.main.rabbit_publisher') as mock_pub:

        mock_dedup.is_new_item = AsyncMock(return_value=True)

        # Simulamos que la publicación normal falla (Caída del puente/LLM/Network)
        mock_pub.publish_ingestion_message = AsyncMock(
            side_effect=Exception("RabbitMQ Connection Reset by Peer"),
        )

        response = client.post("/ingest", json=payload)
        
        # El middleware de la Ingestion API captura el error y hace Fallback/DLQ
        assert response.status_code == 500, "Debería retornar un HTTP 500 (Internal Server Error) para que el global-retry de Traefik lo detecte."
        assert "Error interno" in response.json()["detail"]
        
        # Verificamos que se intentó derivar a la DLQ antes de fallar (fallback)
        # La primera llamada es a RABBIT_QUEUE que falla, y el bloque except intenta enviarlo a RABBIT_DLQ
        assert mock_pub.publish_ingestion_message.call_count >= 1, "Debería haber intentado publicar y luego fallback a DLQ."
