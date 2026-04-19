import pytest
import asyncio
import uuid
import json
import zipfile
import io
from src.data.db import DatabaseManager
from src.data.export_manager import VaultExporter

@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.mark.asyncio
async def test_f072_bidirectional_links():
    """F-07.2: Verifica que el Zipping incluye los enlaces bidireccionales."""
    db_manager = DatabaseManager()
    await db_manager.connect()
    pool = db_manager.pool
    
    tenant_id = "tenant_export_f072_test"
    
    try:
        # Preamble: Insert Data
        doc_a_id = str(uuid.uuid4())
        doc_b_id = str(uuid.uuid4())
        
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO recursos (id, tenant_id, url_hash, url, titulo, resumen, categoria, tags)
                VALUES 
                    ($1::uuid, $2, 'hash_docs_1', 'http://test.com/1', 'Doc A', 'Resumen A', 'article', '[]'::jsonb),
                    ($3::uuid, $2, 'hash_docs_2', 'http://test.com/2', 'Doc B', 'Resumen B', 'article', '[]'::jsonb)
            """, doc_a_id, tenant_id, doc_b_id)
            
            # Setup relation: B contradice A
            await conn.execute("""
                INSERT INTO grafo_relaciones (tenant_id, recurso_origen, recurso_destino, similitud, tipo_relacion)
                VALUES ($1, $2::uuid, $3::uuid, 0.95, 'CONTRADICE')
            """, tenant_id, doc_b_id, doc_a_id)
                
        # Act
        exporter = VaultExporter(db_manager)
        zip_bytes = await exporter.generate_vault_zip(tenant_id)
        
        # Unzip virtually to verify
        mem_zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        namelist = mem_zf.namelist()
        
        # Verify content
        sources_files = [n for n in namelist if n.startswith("wiki/sources/")]
        assert len(sources_files) == 2
        
        file_a = [f for f in sources_files if "DocA" in f.replace(" ", "")][0]
        file_b = [f for f in sources_files if "DocB" in f.replace(" ", "")][0]
        
        content_b = mem_zf.read(file_b).decode()
        
        # Identify the generated name for B
        file_a_name = file_a.split("/")[-1].replace(".md", "")
        
        # Test markdown string logic for CONTRADICE
        assert f"> [!warning] Contradice a: [[{file_a_name}]]" in content_b

    finally:
        # Limpieza
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM recursos WHERE tenant_id = $1", tenant_id)
