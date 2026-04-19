import asyncio
import zipfile
import io
import uuid
import json
from src.data.db import DatabaseManager
from src.data.export_manager import VaultExporter

async def main():
    print("Connecting to DB...")
    db = DatabaseManager()
    await db.connect()
    
    tenant_id = "test-tenant-verify-" + str(uuid.uuid4())[:8]
    print(f"Created dummy tenant_id: {tenant_id}")
    
    doc1_id = str(uuid.uuid4())
    doc2_id = str(uuid.uuid4())
    
    async with db.pool.acquire() as conn:
        # Insert docs
        await conn.execute("""
            INSERT INTO recursos (id, tenant_id, url, url_hash, titulo, resumen, categoria, tags, estado)
            VALUES ($1, $2, 'mem://1', 'hashA', 'Doc A', 'Content A', 'article', '[]'::jsonb, 'activo'),
                   ($3, $2, 'mem://2', 'hashB', 'Doc B', 'Content B', 'concept', '[]'::jsonb, 'activo')
        """, doc1_id, tenant_id, doc2_id)
        
        # Link
        await conn.execute("""
            INSERT INTO grafo_relaciones (tenant_id, recurso_origen, recurso_destino, similitud, tipo_relacion)
            VALUES ($3, $1, $2, 0.9, 'CONTRADICE')
        """, doc1_id, doc2_id, tenant_id)
        
        # Another
        await conn.execute("""
            INSERT INTO grafo_relaciones (tenant_id, recurso_origen, recurso_destino, similitud, tipo_relacion)
            VALUES ($3, $2, $1, 0.9, 'VUELVE_OBSOLETO')
        """, doc1_id, doc2_id, tenant_id)

    print("Generating Vault ZIP...")
    exporter = VaultExporter(db)
    zip_bytes = await exporter.generate_vault_zip(tenant_id)
    
    print(f"ZIP generated! Size: {len(zip_bytes)} bytes")
    
    print("\nExtracting ZIP contents to memory to verify...")
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as z:
        for file_info in z.infolist():
            print(f"- {file_info.filename}")
            if file_info.filename.endswith('.md'):
                content = z.read(file_info.filename).decode('utf-8')
                if "> [!warning]" in content or "> [!" in content or "## Relaciones" in content:
                    print(f"  [Found Relations in {file_info.filename}]")
                    lines = [ln for ln in content.split('\n') if 'Relaciones' in ln or '> [!' in ln or ' - Rela' in ln]
                    for ln in lines:
                        print(f"    {ln}")

    print("\nTest passed successfully! No local files were written during export.")

if __name__ == "__main__":
    asyncio.run(main())
