import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from data.audit_cron import run_audit_cron

@pytest.mark.asyncio
async def test_audit_cron_mock():
    # Mock row returned by postgres
    mock_row = {
        'id': '123e4567-e89b-12d3-a456-426614174000',
        'tenant_id': 'tenant_A',
        'url': 'http://expired.domain'
    }
    
    mock_conn = AsyncMock()
    mock_conn.fetch.return_value = [mock_row]
    # conn.execute should return normally
    
    mock_acquire_context = AsyncMock()
    mock_acquire_context.__aenter__.return_value = mock_conn
    mock_acquire_context.__aexit__.return_value = None

    mock_pool = MagicMock()
    mock_pool.acquire.return_value = mock_acquire_context

    with patch('data.audit_cron.DatabaseManager') as MockDB:
        mock_db_instance = MockDB.return_value
        mock_db_instance.connect = AsyncMock()
        mock_db_instance.close = AsyncMock()
        mock_db_instance.pool = mock_pool
        
        await run_audit_cron()
        
        # Verify fetch was called with the exact sql for updating
        assert mock_conn.fetch.call_count == 1
        
        sql_fetch = mock_conn.fetch.call_args[0][0]
        assert "UPDATE recursos" in sql_fetch
        assert "estado = 'obsoleto'" in sql_fetch
        assert "fecha_caducidad <= NOW()" in sql_fetch

        # Verify outbox event insertion was called
        assert mock_conn.execute.call_count == 1
        
        sql_exec = mock_conn.execute.call_args[0][0]
        assert "INSERT INTO outbox_eventos" in sql_exec
        assert "'recurso.obsoleto'" in sql_exec