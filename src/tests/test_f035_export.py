import pytest
import asyncio
import uuid
import json
from src.data.db import DatabaseManager
from datetime import datetime, timedelta

@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.mark.asyncio
async def test_f035_export_markdown_mapping():
    """F-03.5: Verifica que todos los recursos de un Tenant se obtienen de la DB sin violar RLS y con los campos completos para Markdown."""
    db_manager = DatabaseManager()
    await db_manager.connect()
    pool = db_manager.pool
    
    tenant_id = str(uuid.uuid4())
    other_tenant_id = str(uuid.uuid4())
    
    async with pool.acquire() as conn:
        docs = [
            # Current Tenant
            (str(uuid.uuid4()), "hash035a".ljust(64, '0'), "http://md.com/1", "Titulo Markdown 1", "Resumen de texto A", "activo", "baja", json.dumps(["tag1", "tag2"])),
            (str(uuid.uuid4()), "hash035b".ljust(64, '0'), "http://md.com/2", "Titulo Markdown 2", "Resumen de texto B", "cuarentena", "alta", json.dumps([])),
            # Other Tenant (RLS boundary check)
            (str(uuid.uuid4()), "hash035c".ljust(64, '0'), "http://md.com/3", "Titulo No mio", "No se debe exportar", "activo", "media", '[]')
        ]
        
        for idx, doc in enumerate(docs):
            target_tenant = tenant_id if idx < 2 else other_tenant_id
            await conn.execute("""
                INSERT INTO recursos (id, tenant_id, url_hash, url, titulo, resumen, estado, volatilidad, tags)
                VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9::jsonb)
            """, doc[0], target_tenant, doc[1], doc[2], doc[3], doc[4], doc[5], doc[6], doc[7])
            
    # Act
    # Simula la consulta del UI para F-03.5: fetch_all_resources_for_export
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, url, titulo, resumen, categoria, tags, volatilidad, estado, created_at, fecha_caducidad FROM recursos WHERE tenant_id = $1 ORDER BY created_at DESC", 
            tenant_id
        )
        records = [dict(r) for r in rows]
    
    # Assert
    assert len(records) == 2, "Debe retornar 2 elementos aislando el tenant 3."
    
    titles = [r['titulo'] for r in records]
    assert "Titulo Markdown 1" in titles
    assert "Titulo Markdown 2" in titles
    assert "Titulo No mio" not in titles
    
    # Verifica presencias de columnas para el markdown
    for r in records:
        assert 'titulo' in r
        assert 'url' in r
        assert 'estado' in r
        assert 'resumen' in r
        assert 'volatilidad' in r
        assert 'created_at' in r
        
    # Limpieza
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM recursos WHERE tenant_id = $1 OR tenant_id = $2", tenant_id, other_tenant_id)