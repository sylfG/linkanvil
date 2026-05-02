import pytest
import asyncio
import uuid
import zipfile
import io
from datetime import datetime
from src.data.db import DatabaseManager
from src.data.export_manager import VaultExporter

@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.mark.asyncio
async def test_f073_hot_md_and_log_md_export():
    """F-07.3: Verifica el Hot Cache dinámico (hot.md) y el Log de auditoria (log.md)."""
    db_manager = DatabaseManager()
    await db_manager.connect()
    pool = db_manager.pool
    
    tenant_id = "tenant_export_f073_test"
    sesion_id = str(uuid.uuid4())
    agg_id = str(uuid.uuid4())
    
    try:
        # Preamble: Insert Data for Chat Sessions & Audit Logs
        async with pool.acquire() as conn:
            # 1. Sesiones Chat
            await conn.execute("""
                INSERT INTO sesiones_chat (id, tenant_id, titulo, contexto_comprimido, ultimo_acceso)
                VALUES ($1::uuid, $2, 'Sesion Python', 'Resumen: hablando sobre Python', NOW())
            """, sesion_id, tenant_id)
            
            # 2. Outbox Eventos (Auditoria)
            await conn.execute("""
                INSERT INTO outbox_eventos (id, tenant_id, agregado_tipo, agregado_id, evento_tipo, payload, procesado, creado_en)
                VALUES ($1::uuid, $2, 'recurso', $3::uuid, 'recurso.creado', '{"test":1}'::jsonb, TRUE, NOW())
            """, str(uuid.uuid4()), tenant_id, agg_id)

        # Act
        exporter = VaultExporter(db_manager)
        zip_bytes = await exporter.generate_vault_zip(tenant_id)
        
        # Unzip virtually to verify
        mem_zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        namelist = mem_zf.namelist()
        
        # Verify content exists
        assert "wiki/hot.md" in namelist, "hot.md no fue generado en el zip."
        assert "wiki/log.md" in namelist, "log.md no fue generado en la carpeta wiki."
        
        # Read content
        hot_content = mem_zf.read("wiki/hot.md").decode()
        log_content = mem_zf.read("wiki/log.md").decode()
        
        # Test exact patterns F-07.3
        assert "Sesion Python" in hot_content
        assert "Resumen: hablando sobre Python" in hot_content
        
        assert "recurso.creado" in log_content
        assert str(agg_id) in log_content
        assert "Procesado" in log_content

    finally:
        # Limpieza
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM sesiones_chat WHERE tenant_id = $1", tenant_id)
            await conn.execute("DELETE FROM outbox_eventos WHERE tenant_id = $1", tenant_id)
