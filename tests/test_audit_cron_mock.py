import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.data.audit_cron import run_audit_cron


@pytest.mark.asyncio
async def test_audit_cron_mock():
    """Tras la migración a recursos global, el cron:
      1. UPDATE recursos ... RETURNING id, url   (1ª llamada a fetch)
      2. Por cada recurso → SELECT tenants en usuario_recursos (2ª llamada a fetch)
      3. Por cada tenant → INSERT outbox_eventos 'recurso.expirado' (execute)
    """
    expired_row = {
        "id": "123e4567-e89b-12d3-a456-426614174000",
        "url": "http://expired.domain",
    }
    tenant_row = {"tenant_id": "tenant_A"}

    mock_conn = AsyncMock()
    # Primera fetch → recursos expirados; segunda fetch → tenants asociados.
    mock_conn.fetch.side_effect = [[expired_row], [tenant_row]]

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

        await run_audit_cron()

        # 1) UPDATE recursos
        update_sql = mock_conn.fetch.call_args_list[0][0][0]
        assert "UPDATE recursos" in update_sql
        assert "estado = 'expirado'" in update_sql
        assert "fecha_caducidad <= NOW()" in update_sql

        # 2) SELECT tenants
        tenants_sql = mock_conn.fetch.call_args_list[1][0][0]
        assert "FROM usuario_recursos" in tenants_sql

        # 3) Outbox event insertado por tenant
        assert mock_conn.execute.call_count == 1
        exec_sql = mock_conn.execute.call_args[0][0]
        assert "INSERT INTO outbox_eventos" in exec_sql
        assert "'recurso.expirado'" in exec_sql
