import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.data.audit_cron import run_audit_cron


@pytest.mark.asyncio
async def test_audit_cron_two_phase():
    """El cron en dos fases (F-05.1 + F-05.2) tras migración 0012:

    Fase A — caducidad → cuarentena:
      1. UPDATE usuario_recursos FROM recursos … SET estado='cuarentena'
         RETURNING ur.tenant_id, r.id, r.url
      2. Por cada fila → INSERT outbox_eventos 'recurso.cuarentena'

    Fase B — gracia agotada → expirado:
      3. UPDATE usuario_recursos … SET estado='expirado'
         RETURNING ur.tenant_id, r.id, r.url
      4. Por cada fila → INSERT outbox_eventos 'recurso.expirado'
    """
    cuarentena_row = {
        "tenant_id": "tenant_A",
        "id": "11111111-1111-1111-1111-111111111111",
        "url": "http://stale.com",
    }
    expira_row = {
        "tenant_id": "tenant_A",
        "id": "22222222-2222-2222-2222-222222222222",
        "url": "http://very-stale.com",
    }

    mock_conn = AsyncMock()
    # Orden esperado (migración 0012):
    #   fetch[0] = UPDATE → cuarentena (devuelve 1 fila con tenant ya incluido)
    #   fetch[1] = UPDATE → expirado (devuelve 1 fila)
    mock_conn.fetch.side_effect = [
        [cuarentena_row],
        [expira_row],
    ]

    mock_acquire_context = AsyncMock()
    mock_acquire_context.__aenter__.return_value = mock_conn
    mock_acquire_context.__aexit__.return_value = None

    mock_pool = MagicMock()
    mock_pool.acquire.return_value = mock_acquire_context

    with patch("src.data.audit_cron.DatabaseManager") as MockDB:
        mock_db_instance = MockDB.return_value
        mock_db_instance.connect = AsyncMock()
        mock_db_instance.close = AsyncMock()
        mock_db_instance.pool = mock_pool

        result = await run_audit_cron()

        # Fase A — UPDATE a cuarentena (sobre usuario_recursos, no recursos)
        update_a_sql = mock_conn.fetch.call_args_list[0][0][0]
        assert "UPDATE usuario_recursos" in update_a_sql
        assert "estado = 'cuarentena'" in update_a_sql
        assert "quarantine_reason = 'caducidad'" in update_a_sql
        assert "ur.estado = 'activo'" in update_a_sql
        assert "RETURNING ur.tenant_id" in update_a_sql

        # Fase B — UPDATE a expirado
        update_b_sql = mock_conn.fetch.call_args_list[1][0][0]
        assert "UPDATE usuario_recursos" in update_b_sql
        assert "estado = 'expirado'" in update_b_sql
        assert "quarantine_grace_until" in update_b_sql

        # Outbox: 1 cuarentena + 1 expirado
        assert mock_conn.execute.call_count == 2
        evento_tipos = [
            call.args[3] for call in mock_conn.execute.call_args_list
        ]
        assert evento_tipos == ["recurso.cuarentena", "recurso.expirado"]

        assert result["cuarentenados"] == 1
        assert result["expirados"] == 1
        assert "trace_id" in result
