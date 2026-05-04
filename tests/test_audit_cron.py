import pytest

from src.data.db import DatabaseManager
from src.data.audit_cron import run_audit_cron


@pytest.mark.asyncio
async def test_audit_cron_two_phase_lifecycle():
    """Un recurso `activo` con `fecha_caducidad` superada debe pasar a
    `cuarentena` con motivo 'caducidad' y un `quarantine_grace_until`
    futuro. Un recurso ya en `cuarentena` cuyo período de gracia agotó
    debe pasar a `expirado` en la misma ejecución del cron."""
    db = DatabaseManager()
    await db.connect()

    tenant_id = "tenant_test_two_phase"
    fresh_id = stale_id = grace_expired_id = None

    try:
        async with db.pool.acquire() as conn:
            # 1. Recurso vigente (no debe tocarse).
            fresh_id = await conn.fetchval(
                """
                INSERT INTO recursos (url, url_hash, titulo, volatilidad,
                                       fecha_caducidad, estado)
                VALUES ($1, $2, 'fresh', 'baja',
                        NOW() + INTERVAL '10 day', 'activo')
                ON CONFLICT (url_hash) DO UPDATE SET updated_at = NOW()
                RETURNING id
                """,
                "http://fresh.example.com", "hash_two_phase_fresh",
            )

            # 2. Recurso con caducidad pasada → fase A debe moverlo a cuarentena.
            stale_id = await conn.fetchval(
                """
                INSERT INTO recursos (url, url_hash, titulo, volatilidad,
                                       fecha_caducidad, estado)
                VALUES ($1, $2, 'stale', 'alta',
                        NOW() - INTERVAL '1 day', 'activo')
                ON CONFLICT (url_hash) DO UPDATE SET updated_at = NOW()
                RETURNING id
                """,
                "http://stale.example.com", "hash_two_phase_stale",
            )

            # 3. Recurso ya en cuarentena con gracia agotada → fase B → expirado.
            grace_expired_id = await conn.fetchval(
                """
                INSERT INTO recursos (url, url_hash, titulo, volatilidad,
                                       estado, quarantined_at, quarantine_reason,
                                       quarantine_grace_until)
                VALUES ($1, $2, 'grace_expired', 'media',
                        'cuarentena', NOW() - INTERVAL '40 day',
                        'caducidad', (NOW() - INTERVAL '1 day')::DATE)
                ON CONFLICT (url_hash) DO UPDATE SET updated_at = NOW()
                RETURNING id
                """,
                "http://grace-expired.example.com", "hash_two_phase_grace",
            )

            for rid in (fresh_id, stale_id, grace_expired_id):
                await conn.execute(
                    """INSERT INTO usuario_recursos (tenant_id, recurso_id)
                       VALUES ($1, $2) ON CONFLICT DO NOTHING""",
                    tenant_id, rid,
                )

        result = await run_audit_cron()
        assert result["cuarentenados"] >= 1
        assert result["expirados"] >= 1

        async with db.pool.acquire() as conn:
            fresh_state = await conn.fetchval(
                "SELECT estado FROM recursos WHERE id = $1", fresh_id,
            )
            assert fresh_state == "activo"

            stale_row = await conn.fetchrow(
                """SELECT estado, quarantine_reason, quarantine_grace_until
                   FROM recursos WHERE id = $1""", stale_id,
            )
            assert stale_row["estado"] == "cuarentena"
            assert stale_row["quarantine_reason"] == "caducidad"
            assert stale_row["quarantine_grace_until"] is not None

            expired_state = await conn.fetchval(
                "SELECT estado FROM recursos WHERE id = $1", grace_expired_id,
            )
            assert expired_state == "expirado"

            cuarentena_events = await conn.fetchval(
                """SELECT COUNT(*) FROM outbox_eventos
                   WHERE tenant_id = $1 AND evento_tipo = 'recurso.cuarentena'""",
                tenant_id,
            )
            expirado_events = await conn.fetchval(
                """SELECT COUNT(*) FROM outbox_eventos
                   WHERE tenant_id = $1 AND evento_tipo = 'recurso.expirado'""",
                tenant_id,
            )
            assert cuarentena_events >= 1
            assert expirado_events >= 1

    finally:
        async with db.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM outbox_eventos WHERE tenant_id = $1", tenant_id,
            )
            await conn.execute(
                "DELETE FROM usuario_recursos WHERE tenant_id = $1", tenant_id,
            )
            for rid in (fresh_id, stale_id, grace_expired_id):
                if rid:
                    await conn.execute(
                        "DELETE FROM recursos WHERE id = $1", rid,
                    )
        await db.close()
