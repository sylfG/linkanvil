"""Ciclo end-to-end de la bandeja de cuarentena (F-05.2).

No hace HTTP: ejecuta directamente las helpers de `src.api.database` para
aislar la lógica del transport y mantener los tests rápidos."""
import pytest

from src.api import database as adb
from src.data.db import DatabaseManager


async def _insert_recurso_cuarentena(conn, url: str, hash_: str, tenant_id: str,
                                      grace_offset_days: int = 7) -> str:
    rid = await conn.fetchval(
        """
        INSERT INTO recursos (url, url_hash, titulo, volatilidad, estado,
                              quarantined_at, quarantine_reason,
                              quarantine_grace_until)
        VALUES ($1, $2, 'lifecycle', 'media', 'cuarentena',
                NOW(), 'caducidad',
                (NOW() + ($3::int * INTERVAL '1 day'))::DATE)
        ON CONFLICT (url_hash) DO UPDATE SET updated_at = NOW()
        RETURNING id
        """,
        url, hash_, grace_offset_days,
    )
    await conn.execute(
        """INSERT INTO usuario_recursos (tenant_id, recurso_id)
           VALUES ($1, $2) ON CONFLICT DO NOTHING""",
        tenant_id, rid,
    )
    return str(rid)


@pytest.mark.asyncio
async def test_rescue_returns_resource_to_active():
    """Rescatar un recurso en cuarentena lo devuelve a 'activo' con
    fecha_caducidad recalculada."""
    db = DatabaseManager()
    await db.connect()
    tenant_id = "tenant_test_rescue"
    rid = None
    try:
        async with db.pool.acquire() as conn:
            rid = await _insert_recurso_cuarentena(
                conn, "http://rescue-me.example.com", "hash_rescue", tenant_id,
            )

        result = await adb.rescue_recurso(tenant_id, rid)
        assert result is not None
        assert result["fecha_caducidad"] is not None

        async with db.pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT estado, quarantined_at, quarantine_reason,
                          quarantine_grace_until, fecha_caducidad
                   FROM recursos WHERE id = $1::uuid""", rid,
            )
            assert row["estado"] == "activo"
            assert row["quarantined_at"] is None
            assert row["quarantine_reason"] is None
            assert row["quarantine_grace_until"] is None
            assert row["fecha_caducidad"] is not None

            evt = await conn.fetchval(
                """SELECT COUNT(*) FROM outbox_eventos
                   WHERE tenant_id = $1 AND evento_tipo = 'recurso.rescatado'""",
                tenant_id,
            )
            assert evt == 1
    finally:
        async with db.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM outbox_eventos WHERE tenant_id = $1", tenant_id,
            )
            await conn.execute(
                "DELETE FROM usuario_recursos WHERE tenant_id = $1", tenant_id,
            )
            if rid:
                await conn.execute("DELETE FROM recursos WHERE id = $1::uuid", rid)
        await db.close()
        await adb.close_pool()


@pytest.mark.asyncio
async def test_expire_fast_track_marks_expirado():
    """Expire fast-track: usuario confirma antes del fin del período de gracia."""
    db = DatabaseManager()
    await db.connect()
    tenant_id = "tenant_test_expire"
    rid = None
    try:
        async with db.pool.acquire() as conn:
            rid = await _insert_recurso_cuarentena(
                conn, "http://expire-now.example.com", "hash_expire", tenant_id,
            )

        result = await adb.expire_recurso(tenant_id, rid)
        assert result is not None

        async with db.pool.acquire() as conn:
            estado = await conn.fetchval(
                "SELECT estado FROM recursos WHERE id = $1::uuid", rid,
            )
            assert estado == "expirado"

            evt = await conn.fetchval(
                """SELECT COUNT(*) FROM outbox_eventos
                   WHERE tenant_id = $1 AND evento_tipo = 'recurso.expirado'""",
                tenant_id,
            )
            assert evt == 1
    finally:
        async with db.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM outbox_eventos WHERE tenant_id = $1", tenant_id,
            )
            await conn.execute(
                "DELETE FROM usuario_recursos WHERE tenant_id = $1", tenant_id,
            )
            if rid:
                await conn.execute("DELETE FROM recursos WHERE id = $1::uuid", rid)
        await db.close()
        await adb.close_pool()


@pytest.mark.asyncio
async def test_delete_unlinks_and_removes_globally_when_last():
    """Borrar para el último tenant que lo tiene linkeado debe limpiar la
    fila global. Borrar mientras quedan otros tenants no la borra."""
    db = DatabaseManager()
    await db.connect()
    tenant_a = "tenant_test_delete_A"
    tenant_b = "tenant_test_delete_B"
    rid_shared = rid_lonely = None

    try:
        async with db.pool.acquire() as conn:
            rid_shared = await _insert_recurso_cuarentena(
                conn, "http://shared.example.com", "hash_shared", tenant_a,
            )
            await conn.execute(
                """INSERT INTO usuario_recursos (tenant_id, recurso_id)
                   VALUES ($1, $2::uuid) ON CONFLICT DO NOTHING""",
                tenant_b, rid_shared,
            )

            rid_lonely = await _insert_recurso_cuarentena(
                conn, "http://lonely.example.com", "hash_lonely", tenant_a,
            )

        # Borrar el compartido para A: NO debe desaparecer la fila global.
        r1 = await adb.delete_recurso_for_tenant(tenant_a, rid_shared)
        assert r1 is not None
        assert r1["deleted_globally"] is False

        # Borrar el huérfano para A: SÍ debe desaparecer.
        r2 = await adb.delete_recurso_for_tenant(tenant_a, rid_lonely)
        assert r2 is not None
        assert r2["deleted_globally"] is True

        async with db.pool.acquire() as conn:
            shared_state = await conn.fetchval(
                "SELECT estado FROM recursos WHERE id = $1::uuid", rid_shared,
            )
            assert shared_state == "cuarentena"  # sigue ahí para tenant_b

            lonely_count = await conn.fetchval(
                "SELECT COUNT(*) FROM recursos WHERE id = $1::uuid", rid_lonely,
            )
            assert lonely_count == 0
    finally:
        async with db.pool.acquire() as conn:
            for t in (tenant_a, tenant_b):
                await conn.execute(
                    "DELETE FROM outbox_eventos WHERE tenant_id = $1", t,
                )
                await conn.execute(
                    "DELETE FROM usuario_recursos WHERE tenant_id = $1", t,
                )
            for rid in (rid_shared, rid_lonely):
                if rid:
                    await conn.execute(
                        "DELETE FROM recursos WHERE id = $1::uuid", rid,
                    )
        await db.close()
        await adb.close_pool()


@pytest.mark.asyncio
async def test_cross_tenant_rescue_returns_none():
    """Un tenant no debería poder rescatar un recurso que no le pertenece."""
    db = DatabaseManager()
    await db.connect()
    owner = "tenant_test_owner"
    intruder = "tenant_test_intruder"
    rid = None
    try:
        async with db.pool.acquire() as conn:
            rid = await _insert_recurso_cuarentena(
                conn, "http://owned.example.com", "hash_owned", owner,
            )

        result = await adb.rescue_recurso(intruder, rid)
        assert result is None

        async with db.pool.acquire() as conn:
            estado = await conn.fetchval(
                "SELECT estado FROM recursos WHERE id = $1::uuid", rid,
            )
            assert estado == "cuarentena"  # intacto
    finally:
        async with db.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM outbox_eventos WHERE tenant_id = ANY($1)",
                [owner, intruder],
            )
            await conn.execute(
                "DELETE FROM usuario_recursos WHERE tenant_id = ANY($1)",
                [owner, intruder],
            )
            if rid:
                await conn.execute("DELETE FROM recursos WHERE id = $1::uuid", rid)
        await db.close()
        await adb.close_pool()


@pytest.mark.asyncio
async def test_list_quarantine_includes_dias_restantes():
    db = DatabaseManager()
    await db.connect()
    tenant_id = "tenant_test_list"
    rid = None
    try:
        async with db.pool.acquire() as conn:
            rid = await _insert_recurso_cuarentena(
                conn, "http://list-me.example.com", "hash_list", tenant_id,
                grace_offset_days=12,
            )

        items = await adb.list_quarantine(tenant_id)
        assert len(items) == 1
        item = items[0]
        assert item["quarantine_reason"] == "caducidad"
        # Tolera ±1 día por el truncado a DATE.
        assert 11 <= item["dias_restantes"] <= 12

        count = await adb.count_quarantine(tenant_id)
        assert count == 1
    finally:
        async with db.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM usuario_recursos WHERE tenant_id = $1", tenant_id,
            )
            if rid:
                await conn.execute("DELETE FROM recursos WHERE id = $1::uuid", rid)
        await db.close()
        await adb.close_pool()
