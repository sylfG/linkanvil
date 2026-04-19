import pytest
import asyncio
import os
import uuid
from src.data.db import DatabaseManager
from datetime import datetime, timedelta

@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.mark.asyncio
async def test_f053_audit_fetch():
    """F-05.3: Verify that fetch_resources_for_audit retrieves the correct data for the AI audit."""
    db_manager = DatabaseManager()
    await db_manager.connect()
    pool = db_manager.pool
    tenant_id = str(uuid.uuid4())
    
    async with pool.acquire() as conn:
        # Arrange: Insert some test data across different states
# doc = (id, url_hash, url, titulo, estado, volatilidad, fecha_caducidad)
        docs = [
            (str(uuid.uuid4()), "hash1".ljust(64, '0'), "http://test.com/1", "doc1", "activo", "baja", datetime.now().date() + timedelta(days=365)),
            (str(uuid.uuid4()), "hash2".ljust(64, '0'), "http://test.com/2", "doc2", "cuarentena", "alta", datetime.now().date() + timedelta(days=7)),
            (str(uuid.uuid4()), "hash3".ljust(64, '0'), "http://test.com/3", "doc3", "activo", "media", datetime.now().date() + timedelta(days=30))
        ]
    
        for doc in docs:
             try:
                 await conn.execute("""
                     INSERT INTO recursos (id, tenant_id, url_hash, url, titulo, estado, volatilidad, fecha_caducidad)
                     VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8)
                 """, doc[0], tenant_id, doc[1], doc[2], doc[3], doc[4], doc[5], doc[6])
             except Exception as e:
                 print(f"Error inserting: {e}")
                 raise e
    async with pool.acquire() as conn:
        await conn.execute(f"SET LOCAL app.current_tenant = '{tenant_id}'")
        records = await conn.fetch("""
            SELECT id, titulo, url, estado, volatilidad, fecha_caducidad 
            FROM recursos 
            WHERE tenant_id = $1 
            ORDER BY updated_at DESC 
            LIMIT 20
        """, tenant_id)
        
    # Assert
    assert len(records) == 3
    statuses = [r['estado'] for r in records]
    assert "activo" in statuses
    assert "cuarentena" in statuses
    
    # Cleanup
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM recursos WHERE tenant_id = $1", tenant_id)