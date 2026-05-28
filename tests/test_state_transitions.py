"""Cubre las transiciones manuales nuevas:
- `rescue_recurso` desde estado expirado (no solo desde cuarentena)
- `quarantine_recurso` (manual desde activo/procesando)
- `get_resources` con `estado='todos'` excluye cuarentena/expirado
- `get_resources` con `estado='_all'` los incluye
"""
from datetime import date, timedelta

import pytest

from src.api import database as adb
from src.data.db import DatabaseManager


async def _insert_recurso(conn, url: str, hash_: str, tenant_id: str,
                           estado: str, fecha_caducidad: date | None = None) -> str:
    rid = await conn.fetchval(
        """INSERT INTO recursos (url, url_hash, titulo, volatilidad)
           VALUES ($1, $2, 'state-tx', 'media')
           ON CONFLICT (url_hash) DO UPDATE SET updated_at = NOW()
           RETURNING id""",
        url, hash_,
    )
    # Migración 0012: estado per-tenant en usuario_recursos.
    await conn.execute(
        """INSERT INTO usuario_recursos (
                tenant_id, recurso_id, estado, fecha_caducidad
            ) VALUES ($1, $2, $3, $4)
            ON CONFLICT (tenant_id, recurso_id) DO UPDATE
                SET estado = EXCLUDED.estado,
                    fecha_caducidad = EXCLUDED.fecha_caducidad""",
        tenant_id, rid, estado, fecha_caducidad,
    )
    return str(rid)


@pytest.mark.asyncio
async def test_rescue_from_expired_returns_to_active():
    db = DatabaseManager()
    await db.connect()
    tenant_id = "tenant_test_rescue_exp"
    rid = None
    try:
        async with db.pool.acquire() as conn:
            rid = await _insert_recurso(
                conn, "http://rescue-exp.example", "hash_rescue_exp",
                tenant_id, "expirado", date.today() - timedelta(days=10),
            )

        result = await adb.rescue_recurso(tenant_id, rid)
        assert result is not None
        assert result["fecha_caducidad"] is not None

        async with db.pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT estado FROM usuario_recursos
                    WHERE tenant_id = $1 AND recurso_id = $2::uuid""",
                tenant_id, rid,
            )
            assert row["estado"] == "activo"

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
async def test_quarantine_recurso_from_active():
    db = DatabaseManager()
    await db.connect()
    tenant_id = "tenant_test_quar_manual"
    rid = None
    try:
        async with db.pool.acquire() as conn:
            rid = await _insert_recurso(
                conn, "http://quar-manual.example", "hash_quar_manual",
                tenant_id, "activo", date.today() + timedelta(days=30),
            )

        result = await adb.quarantine_recurso(tenant_id, rid)
        assert result is not None
        assert result["quarantine_grace_until"] is not None

        async with db.pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT estado, quarantine_reason, quarantine_grace_until
                   FROM usuario_recursos
                   WHERE tenant_id = $1 AND recurso_id = $2::uuid""",
                tenant_id, rid,
            )
            assert row["estado"] == "cuarentena"
            assert row["quarantine_reason"] == "manual"
            assert row["quarantine_grace_until"] is not None

            evt = await conn.fetchval(
                """SELECT COUNT(*) FROM outbox_eventos
                   WHERE tenant_id = $1 AND evento_tipo = 'recurso.cuarentena'""",
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
async def test_quarantine_recurso_idempotent_when_already_quarantined():
    """No debe re-transicionar si ya está en cuarentena."""
    db = DatabaseManager()
    await db.connect()
    tenant_id = "tenant_test_quar_idem"
    rid = None
    try:
        async with db.pool.acquire() as conn:
            rid = await _insert_recurso(
                conn, "http://quar-idem.example", "hash_quar_idem",
                tenant_id, "cuarentena",
            )

        result = await adb.quarantine_recurso(tenant_id, rid)
        assert result is None
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
async def test_get_resources_default_excludes_cuarentena_and_expirado():
    db = DatabaseManager()
    await db.connect()
    tenant_id = "tenant_test_kb_filter"
    rids = []
    try:
        async with db.pool.acquire() as conn:
            rids.append(await _insert_recurso(
                conn, "http://kb-active.example", "hash_kb_active",
                tenant_id, "activo", date.today() + timedelta(days=30),
            ))
            rids.append(await _insert_recurso(
                conn, "http://kb-quar.example", "hash_kb_quar",
                tenant_id, "cuarentena",
            ))
            rids.append(await _insert_recurso(
                conn, "http://kb-expired.example", "hash_kb_expired",
                tenant_id, "expirado", date.today() - timedelta(days=5),
            ))

        # Default ('todos'): excluye cuarentena y expirado
        items = await adb.get_resources(tenant_id, estado="todos")
        assert len(items) == 1
        assert items[0]["estado"] == "activo"

        # Filtro explícito sigue funcionando
        items_quar = await adb.get_resources(tenant_id, estado="cuarentena")
        assert len(items_quar) == 1
        assert items_quar[0]["estado"] == "cuarentena"

        # _all incluye todo
        items_all = await adb.get_resources(tenant_id, estado="_all")
        assert len(items_all) == 3
    finally:
        async with db.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM usuario_recursos WHERE tenant_id = $1", tenant_id,
            )
            for rid in rids:
                await conn.execute("DELETE FROM recursos WHERE id = $1::uuid", rid)
        await db.close()
        await adb.close_pool()
