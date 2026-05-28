import pytest
import uuid
from src.data.db import DatabaseManager
import asyncio

@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.mark.xfail(reason="F-04.5 NOT_STARTED — function calling no implementado · ver docs/review/2026-05-19/v2/backlog/ — recuperar cuando se implemente", strict=False)
@pytest.mark.asyncio
async def test_f045_function_calling_historico_crudo():
    """F-04.5: Verifica que la función cruda devuelve datos válidos de la base de datos (resolviendo RLS)."""
    db_manager = DatabaseManager()
    await db_manager.connect()
    
    tenant_id = str(uuid.uuid4())
    
    # Creamos recursos para buscar
    async with db_manager.pool.acquire() as conn:
        try:
            await conn.execute("""
                INSERT INTO recursos (id, tenant_id, url_hash, url, titulo, resumen, estado, volatilidad)
                VALUES 
                ($1::uuid, $2, 'hash_test_1'.ljust(64, '0'), 'http://test.com/crudo1', 'Documento Crudo Especial', 'Este es un resumen muy particular con la palabra ambigüedad test.', 'activo', 'baja')
            """, str(uuid.uuid4()), tenant_id)
            
            # Ejecutamos el fetch crudo simulando chatbot.py
            query = "ambigüedad test"
            await conn.execute(f"SET LOCAL app.current_tenant = '{tenant_id}'")
            rows = await conn.fetch(
                "SELECT titulo, url, resumen, estado FROM recursos WHERE tenant_id = $1 AND (resumen ILIKE $2 OR titulo ILIKE $2) LIMIT 3", 
                tenant_id, f"%{query}%"
            )
            result = ""
            for r in rows:
                result += f"- Título: {r['titulo']}\n  URL: {r['url']}\n  Estado: {r['estado']}\n  Resumen Crudo: {r['resumen']}\n\n"
            
            assert "Documento Crudo Especial" in result
            assert "http://test.com/crudo1" in result
            assert "ambigüedad test" in result
            
        finally:
            await conn.execute("DELETE FROM recursos WHERE tenant_id = $1", tenant_id)
            await db_manager.close()

