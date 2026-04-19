import pytest
import asyncio
import uuid
import os
import hashlib
from src.data.db import DatabaseManager

@pytest.mark.asyncio
async def test_f033_semantic_collider_insertion():
    db = DatabaseManager()
    await db.connect()
    
    tenant_id = "tenant_test_F033"
    recurso_1 = str(uuid.uuid4())
    recurso_2 = str(uuid.uuid4())
    
    url1 = "http://test1.com"
    url2 = "http://test2.com"
    hash1 = hashlib.sha256(url1.encode()).hexdigest()
    hash2 = hashlib.sha256(url2.encode()).hexdigest()

    try:
        # 1. Mock insert them in recursos to not violate foreign key constraints
        async with db.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO recursos (id, tenant_id, url, url_hash, titulo)
                VALUES 
                    ($1, $2, $3, $4, 'test1'),
                    ($5, $2, $6, $7, 'test2')
            """, recurso_1, tenant_id, url1, hash1, recurso_2, url2, hash2)
            
        # 2. Add collision
        collisions = [{"recurso_destino": recurso_2, "similitud": 0.95}]
        await db.save_semantic_collisions(tenant_id, recurso_1, collisions)
        
        # 3. Assert they exist bidirectionally
        async with db.pool.acquire() as conn:
            row1 = await conn.fetchrow(
                "SELECT similitud FROM grafo_relaciones WHERE recurso_origen=$1 AND recurso_destino=$2",
                recurso_1, recurso_2
            )
            row2 = await conn.fetchrow(
                "SELECT similitud FROM grafo_relaciones WHERE recurso_origen=$1 AND recurso_destino=$2",
                recurso_2, recurso_1
            )
            
        assert row1 is not None, "Relación directa (origen->destino) no encontrada"
        assert row2 is not None, "Relación inversa (destino->origen) no encontrada"
        assert row1['similitud'] == 0.95
        assert row2['similitud'] == 0.95

    finally:
        # Cleanup
        async with db.pool.acquire() as conn:
            await conn.execute("DELETE FROM recursos WHERE id IN ($1, $2)", recurso_1, recurso_2)
            
        await db.close()