import asyncio
import os
import json
import logging
import pytest
from src.data.db import DatabaseManager

logging.basicConfig(level=logging.INFO)

@pytest.mark.asyncio
async def test_save_with_outbox():
    # Asegúrate de ejecutar este test contra la BD local para validar el Outbox pattern (F-03.1)
    db_url = os.getenv("DATABASE_URL", "postgresql://cerebro:cerebro_db_pass_CHANGE_ME@localhost:5432/cerebro_brain")
    db = DatabaseManager(db_url)
    
    await db.connect()
    
    tenant_id = "test-tenant-031"
    trace_id = "trc-031-1"
    url = "https://example.outbox.com/article/1"
    
    extracted_data = {
        "title": "Outbox Pattern Tutorial",
        "summary": "A deep dive into dual-write problems.",
        "keywords": ["database", "rabbitmq", "events"],
        "category": "tutorial",
        "volatility_score": "low",
        "estimated_useful_life_days": 365
    }
    
    try:
        # Ejecutar la lógica outbox
        recurso_id = await db.save_with_outbox(
            tenant_id=tenant_id,
            trace_id=trace_id,
            extracted_data=extracted_data,
            url=url
        )
        
        assert recurso_id is not None
        
        # Validar en la BD usando asyncpg directamente
        async with db.pool.acquire() as conn:
            # 1. El recurso es global (sin tenant_id); verificamos sus campos
            #    y que el tenant esté asociado vía la pivote.
            row = await conn.fetchrow(
                "SELECT volatilidad FROM recursos WHERE id = $1", recurso_id,
            )
            assert row is not None
            assert row["volatilidad"] == "baja"  # 'low' → 'baja'

            link = await conn.fetchval(
                "SELECT 1 FROM usuario_recursos WHERE tenant_id = $1 AND recurso_id = $2",
                tenant_id, recurso_id,
            )
            assert link == 1, "El tenant debe quedar asociado al recurso global"

            # 2. Outbox event aún no procesado, con payload coherente.
            outbox_row = await conn.fetchrow(
                "SELECT payload, procesado FROM outbox_eventos WHERE agregado_id = $1",
                recurso_id,
            )
            assert outbox_row is not None
            assert outbox_row["procesado"] is False
            payload = json.loads(outbox_row["payload"])
            assert payload["trace_id"] == trace_id
            assert payload["event_origin"] == "scraper_worker"
            assert payload["url"] == url
    finally:
        async with db.pool.acquire() as conn:
            await conn.execute("DELETE FROM outbox_eventos WHERE tenant_id = $1", tenant_id)
            await conn.execute("DELETE FROM usuario_recursos WHERE tenant_id = $1", tenant_id)
            await conn.execute("DELETE FROM recursos WHERE id = $1", recurso_id)
        await db.close()

if __name__ == "__main__":
    pytest.main(["-v", __file__])
