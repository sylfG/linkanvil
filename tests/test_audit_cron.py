import pytest

from src.data.db import DatabaseManager
from src.data.audit_cron import run_audit_cron


@pytest.mark.asyncio
async def test_audit_cron():
    db = DatabaseManager()
    await db.connect()

    tenant_id = "tenant_test_cron"
    expired_id = None
    valid_id = None

    try:
        async with db.pool.acquire() as conn:
            # Recurso global caducado, asociado a `tenant_id`.
            expired_id = await conn.fetchval(
                """
                INSERT INTO recursos (url, url_hash, titulo, resumen, categoria, tags,
                                      volatilidad, fecha_caducidad, estado)
                VALUES ($1, $2, 'test_caducado', '', 'other', '[]'::jsonb,
                        'alta', NOW() - INTERVAL '1 day', 'activo')
                ON CONFLICT (url_hash) DO UPDATE SET updated_at = NOW()
                RETURNING id
                """,
                "http://expired.com", "hash_expired",
            )
            await conn.execute(
                "INSERT INTO usuario_recursos (tenant_id, recurso_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                tenant_id, expired_id,
            )

            # Recurso global vigente, también asociado.
            valid_id = await conn.fetchval(
                """
                INSERT INTO recursos (url, url_hash, titulo, resumen, categoria, tags,
                                      volatilidad, fecha_caducidad, estado)
                VALUES ($1, $2, 'test_vigente', '', 'other', '[]'::jsonb,
                        'baja', NOW() + INTERVAL '10 day', 'activo')
                ON CONFLICT (url_hash) DO UPDATE SET updated_at = NOW()
                RETURNING id
                """,
                "http://valid.com", "hash_valid",
            )
            await conn.execute(
                "INSERT INTO usuario_recursos (tenant_id, recurso_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                tenant_id, valid_id,
            )

        await run_audit_cron()

        async with db.pool.acquire() as conn:
            expired_state = await conn.fetchval(
                "SELECT estado FROM recursos WHERE id = $1", expired_id,
            )
            assert expired_state == "expirado", "El recurso caducado debió pasar a expirado"

            valid_state = await conn.fetchval(
                "SELECT estado FROM recursos WHERE id = $1", valid_id,
            )
            assert valid_state == "activo", "El recurso no caducado no debe ser tocado"

            outbox_count = await conn.fetchval(
                "SELECT COUNT(*) FROM outbox_eventos WHERE tenant_id = $1 AND evento_tipo = 'recurso.expirado'",
                tenant_id,
            )
            assert outbox_count >= 1, "Debe existir al menos 1 evento outbox 'recurso.expirado'."
    finally:
        async with db.pool.acquire() as conn:
            await conn.execute("DELETE FROM outbox_eventos WHERE tenant_id = $1", tenant_id)
            await conn.execute("DELETE FROM usuario_recursos WHERE tenant_id = $1", tenant_id)
            if expired_id:
                await conn.execute("DELETE FROM recursos WHERE id = $1", expired_id)
            if valid_id:
                await conn.execute("DELETE FROM recursos WHERE id = $1", valid_id)
        await db.close()
