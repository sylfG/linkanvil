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

@pytest.mark.xfail(reason="F-07.1 sin endpoint /export · ver docs/review/2026-05-19/v2/backlog/ — recuperar cuando se implemente", strict=False)
@pytest.mark.asyncio
async def test_f071_vault_export():
    """F-07.1: Verifica que el Zipping genera el arbol dictado."""
    db_manager = DatabaseManager()
    await db_manager.connect()
    pool = db_manager.pool
    
    tenant_id = "tenant_export_f071_test"
    other_tenant_id = "tenant_other_f071_test"
    
    try:
        # Preamble: Insert Data
        async with pool.acquire() as conn:
            docs = [
                # Current Tenant - Article
                (str(uuid.uuid4()), "hash071a".ljust(64, '0'), "http://test.com/source", "Mi Articulo", "Un recurso asombroso", "article", json.dumps(["tagA"])),
                # Current Tenant - Concept
                (str(uuid.uuid4()), "hash071b".ljust(64, '0'), "http://test.com/idea", "Mi Idea", "Un concepto clave", "concept", json.dumps(["tagB"])),
                # Current Tenant - Entity
                (str(uuid.uuid4()), "hash071c".ljust(64, '0'), "http://test.com/tool", "Herramienta X", "Una entidad utilizada", "tool", json.dumps(["tagC"])),
                # Other Tenant (RLS boundary check)
                (str(uuid.uuid4()), "hash071d".ljust(64, '0'), "http://test.com/other", "No debe verse", "Otra cuenta", "article", '[]')
            ]
            
            for idx, doc in enumerate(docs):
                target_tenant = tenant_id if idx < 3 else other_tenant_id
                await conn.execute("""
                    INSERT INTO recursos (id, tenant_id, url_hash, url, titulo, resumen, categoria, tags)
                    VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8::jsonb)
                """, doc[0], target_tenant, doc[1], doc[2], doc[3], doc[4], doc[5], doc[6])
                
        # Act
        exporter = VaultExporter(db_manager)
        zip_bytes = await exporter.generate_vault_zip(tenant_id)
        
        # Unzip virtually to verify
        mem_zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        namelist = mem_zf.namelist()
        
        # Assert Structure Core
        assert "CLAUDE.md" in namelist, "Falta archivo semilla CLAUDE.md"
        assert "index.md" in namelist, "Falta index.md principal"
        
        # Assert Ontology classification and files
        raw_files = [n for n in namelist if n.startswith("raw/")]
        sources_files = [n for n in namelist if n.startswith("wiki/sources/")]
        concepts_files = [n for n in namelist if n.startswith("wiki/concepts/")]
        entities_files = [n for n in namelist if n.startswith("wiki/entities/")]
        
        # 3 documents belong to the user
        assert len(raw_files) == 3, "No se aislaron correctamente o no se copiaron todos los .txt"
        assert len(sources_files) == 1, "Debe haber 1 articulo en sources"
        assert len(concepts_files) == 1, "Debe haber 1 concepto en concepts"
        assert len(entities_files) == 1, "Debe haber 1 herramienta/entidad en entities"
        
        # Check actual content of one file
        concept_file_path = concepts_files[0]
        content = mem_zf.read(concept_file_path).decode()
        
        # The content should be templated well
        assert "Mi Idea" in content
        assert "http://test.com/idea" in content
        assert "#tagB" in content
        assert "Un concepto clave" in content

    finally:
        # Limpieza
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM recursos WHERE tenant_id = $1 OR tenant_id = $2", tenant_id, other_tenant_id)
