import pytest
import asyncio
from datetime import datetime, timedelta
import sys
import os

# Ensure src module path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from data.db import DatabaseManager
from data.audit_cron import run_audit_cron

@pytest.mark.asyncio
async def test_audit_cron():
    db = DatabaseManager()
    await db.connect()
    
    tenant_id = "tenant_test_cron"
    trace_id_1 = "trace_cron_1"
    trace_id_2 = "trace_cron_2"

    try:
        # Create an expired record manually via raw SQL inserts to skip outbox auto-logic
        async with db.pool.acquire() as conn:
            # 1. Obsolete item
            await conn.execute(
                """
                INSERT INTO recursos (tenant_id, url, url_hash, titulo, resumen, categoria, tags, volatilidad, fecha_caducidad, estado)
                VALUES ($1, $2, $3, 'test_obsoleto', '', 'other', '[]'::jsonb, 'alta', NOW() - INTERVAL '1 day', 'procesando')
                ON CONFLICT DO NOTHING
                """,
                tenant_id, "http://expired.com", "hash_expired"
            )
            
            # 2. Valid item
            await conn.execute(
                """
                INSERT INTO recursos (tenant_id, url, url_hash, titulo, resumen, categoria, tags, volatilidad, fecha_caducidad, estado)
                VALUES ($1, $2, $3, 'test_vigente', '', 'other', '[]'::jsonb, 'baja', NOW() + INTERVAL '10 day', 'procesando')
                ON CONFLICT DO NOTHING
                """,
                tenant_id, "http://valid.com", "hash_valid"
            )
            
        # Run Audit Cron
        await run_audit_cron()

        # Assertions
        async with db.pool.acquire() as conn:
            expired_state = await conn.fetchval(
                "SELECT estado FROM recursos WHERE tenant_id = $1 AND url_hash = $2",
                tenant_id, "hash_expired"
            )
            assert expired_state == 'obsoleto', "El recurso caducado debió pasar a obsoleto"
            
            valid_state = await conn.fetchval(
                "SELECT estado FROM recursos WHERE tenant_id = $1 AND url_hash = $2",
                tenant_id, "hash_valid"
            )
            assert valid_state == 'procesando', "El recurso no caducado no debe ser tocado"
            
            # Check outbox event
            outbox_count = await conn.fetchval(
                "SELECT COUNT(*) FROM outbox_eventos WHERE tenant_id = $1 AND evento_tipo = 'recurso.obsoleto'",
                tenant_id
            )
            assert outbox_count >= 1, "Debe existir al menos 1 evento en outbox indicando obsoleto."
            
    finally:
        # Cleanup
        async with db.pool.acquire() as conn:
            await conn.execute("DELETE FROM outbox_eventos WHERE tenant_id = $1", tenant_id)
            await conn.execute("DELETE FROM recursos WHERE tenant_id = $1", tenant_id)
        await db.close()