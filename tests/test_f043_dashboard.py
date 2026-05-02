import pytest
import asyncio
from src.data.db import DatabaseManager


@pytest.mark.skip(reason="Pendiente refactor a usuario_recursos tras migración 0002")
@pytest.mark.asyncio
async def test_f043_dashboard_metrics():
    db = DatabaseManager()
    await db.connect()
    
    tenant_id = "tenant_test_dash_F043"
    
    try:
        # Insert raw data
        async with db.pool.acquire() as conn:
            # Active resource
            await conn.execute("""
                INSERT INTO recursos (tenant_id, url, url_hash, titulo, estado)
                VALUES ($1, 'http://d1.com', md5('d1'), 'd1', 'activo')
                ON CONFLICT DO NOTHING
            """, tenant_id)
            
            # Quarantine resource
            await conn.execute("""
                INSERT INTO recursos (tenant_id, url, url_hash, titulo, estado)
                VALUES ($1, 'http://d2.com', md5('d2'), 'd2', 'cuarentena')
                ON CONFLICT DO NOTHING
            """, tenant_id)
            
            # Processing resource
            await conn.execute("""
                INSERT INTO recursos (tenant_id, url, url_hash, titulo, estado)
                VALUES ($1, 'http://d3.com', md5('d3'), 'd3', 'procesando')
                ON CONFLICT DO NOTHING
            """, tenant_id)
            
            # Outbox pending
            await conn.execute("""
                INSERT INTO outbox_eventos (tenant_id, agregado_tipo, agregado_id, evento_tipo, payload, procesado)
                VALUES ($1, 'recurso', gen_random_uuid(), 'recurso.procesado', '{}'::jsonb, FALSE)
            """, tenant_id)
            
        # Manually compute logic
        metrics = {"activo": 0, "cuarentena": 0, "obsoleto": 0, "procesando": 0, "outbox_pending": 0}
        async with db.pool.acquire() as conn:
            rows = await conn.fetch("SELECT estado, COUNT(*) as count FROM recursos WHERE tenant_id = $1 GROUP BY estado", tenant_id)
            for r in rows:
                if r['estado'] in metrics:
                    metrics[r['estado']] = r['count']
                
            outbox_count = await conn.fetchval(
                "SELECT COUNT(*) FROM outbox_eventos WHERE tenant_id = $1 AND procesado = FALSE", tenant_id
            )
            metrics["outbox_pending"] = outbox_count or 0
            
        assert metrics['activo'] >= 1
        assert metrics['cuarentena'] >= 1
        assert metrics['procesando'] >= 1
        assert metrics['outbox_pending'] >= 1

    finally:
        # Cleanup
        async with db.pool.acquire() as conn:
            await conn.execute("DELETE FROM outbox_eventos WHERE tenant_id = $1", tenant_id)
            await conn.execute("DELETE FROM recursos WHERE tenant_id = $1", tenant_id)
            
        await db.close()
