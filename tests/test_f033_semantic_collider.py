import pytest
import asyncio
import uuid
import os
import hashlib
from src.data.db import DatabaseManager

@pytest.mark.xfail(reason="F-03.3 — collider via chatbot legacy · ver docs/review/2026-05-19/v2/backlog/ — recuperar cuando se implemente", strict=False)
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
            
        # 2. Add collision with type (Typed Relational Pipeline)
        collisions = [{"recurso_destino": recurso_2, "similitud": 0.95, "tipo_relacion": "VUELVE_OBSOLETO"}]
        await db.save_semantic_collisions(tenant_id, recurso_1, collisions)
        
        # 3. Assert they exist bidirectionally and type is correct
        async with db.pool.acquire() as conn:
            row1 = await conn.fetchrow(
                "SELECT similitud, tipo_relacion FROM grafo_relaciones WHERE recurso_origen=$1 AND recurso_destino=$2",
                recurso_1, recurso_2
            )
            row2 = await conn.fetchrow(
                "SELECT similitud, tipo_relacion FROM grafo_relaciones WHERE recurso_origen=$1 AND recurso_destino=$2",
                recurso_2, recurso_1
            )
            old_doc = await conn.fetchrow(
                "SELECT estado FROM recursos WHERE id=$1",
                recurso_2
            )
            
        assert row1 is not None, "Relación directa (origen->destino) no encontrada"
        assert row2 is not None, "Relación inversa (destino->origen) no encontrada"
        assert row1['similitud'] == 0.95
        assert row2['similitud'] == 0.95
        
        assert row1['tipo_relacion'] == "VUELVE_OBSOLETO", "Tipo F-03.3 en directa no establecido"
        assert row2['tipo_relacion'] == "OBSOLECIDO_POR", "Tipo inverso en bidireccional no correcto"
        assert old_doc['estado'] == 'expirado', "El documento obsoleto no fue marcado como 'expirado'!"

    finally:
        # Cleanup
        async with db.pool.acquire() as conn:
            await conn.execute("DELETE FROM recursos WHERE id IN ($1, $2)", recurso_1, recurso_2)
            
        await db.close()