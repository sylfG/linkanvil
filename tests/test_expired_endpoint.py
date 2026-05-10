"""Cobertura de las helpers `list_expired` / `count_expired` que respaldan
`GET /resources/expired`. No hace HTTP — invoca las funciones de
`src.api.database` directamente, igual que test_quarantine_lifecycle.py."""
from datetime import date, timedelta

import pytest

from src.api import database as adb
from src.data.db import DatabaseManager


async def _insert_recurso(conn, url: str, hash_: str, tenant_id: str,
                           estado: str, fecha_caducidad: date | None) -> str:
    rid = await conn.fetchval(
        """
        INSERT INTO recursos (url, url_hash, titulo, volatilidad,
                              fecha_caducidad, estado)
        VALUES ($1, $2, 'expired test', 'media', $3, $4)
        ON CONFLICT (url_hash) DO UPDATE SET
            estado = EXCLUDED.estado,
            fecha_caducidad = EXCLUDED.fecha_caducidad,
            updated_at = NOW()
        RETURNING id
        """,
        url, hash_, fecha_caducidad, estado,
    )
    await conn.execute(
        """INSERT INTO usuario_recursos (tenant_id, recurso_id)
           VALUES ($1, $2) ON CONFLICT DO NOTHING""",
        tenant_id, rid,
    )
    return str(rid)


@pytest.mark.asyncio
async def test_list_expired_returns_only_expired():
    db = DatabaseManager()
    await db.connect()
    tenant_id = "tenant_test_expired_list"
    rid_active = rid_quar = rid_expired = None
    try:
        async with db.pool.acquire() as conn:
            rid_active = await _insert_recurso(
                conn, "http://expired-test.example/active", "hash_exp_active",
                tenant_id, "activo", date.today() + timedelta(days=30),
            )
            rid_quar = await _insert_recurso(
                conn, "http://expired-test.example/quar", "hash_exp_quar",
                tenant_id, "cuarentena", date.today() - timedelta(days=1),
            )
            rid_expired = await _insert_recurso(
                conn, "http://expired-test.example/expired", "hash_exp_expired",
                tenant_id, "expirado", date.today() - timedelta(days=15),
            )

        items = await adb.list_expired(tenant_id)
        assert len(items) == 1
        item = items[0]
        assert str(item["id"]) == rid_expired
        assert item["dias_desde_expiracion"] is not None
        assert item["dias_desde_expiracion"] >= 14  # ~15, tolerando truncado a DATE
    finally:
        async with db.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM usuario_recursos WHERE tenant_id = $1", tenant_id,
            )
            for rid in (rid_active, rid_quar, rid_expired):
                if rid:
                    await conn.execute("DELETE FROM recursos WHERE id = $1::uuid", rid)
        await db.close()
        await adb.close_pool()


@pytest.mark.asyncio
async def test_count_expired():
    db = DatabaseManager()
    await db.connect()
    tenant_id = "tenant_test_expired_count"
    rids = []
    try:
        async with db.pool.acquire() as conn:
            for i in range(3):
                rid = await _insert_recurso(
                    conn,
                    f"http://expired-count.example/{i}",
                    f"hash_count_{i}",
                    tenant_id,
                    "expirado",
                    date.today() - timedelta(days=5 + i),
                )
                rids.append(rid)
            # uno activo no debe contar
            rid_active = await _insert_recurso(
                conn, "http://expired-count.example/active", "hash_count_active",
                tenant_id, "activo", date.today() + timedelta(days=10),
            )
            rids.append(rid_active)

        count = await adb.count_expired(tenant_id)
        assert count == 3
    finally:
        async with db.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM usuario_recursos WHERE tenant_id = $1", tenant_id,
            )
            for rid in rids:
                await conn.execute("DELETE FROM recursos WHERE id = $1::uuid", rid)
        await db.close()
        await adb.close_pool()


@pytest.mark.asyncio
async def test_cross_tenant_isolation():
    """Recursos `expirado` de otro tenant no deben filtrar al actual."""
    db = DatabaseManager()
    await db.connect()
    owner = "tenant_test_expired_owner"
    intruder = "tenant_test_expired_intruder"
    rid = None
    try:
        async with db.pool.acquire() as conn:
            rid = await _insert_recurso(
                conn, "http://expired-iso.example/owned", "hash_expired_iso",
                owner, "expirado", date.today() - timedelta(days=2),
            )

        items_intruder = await adb.list_expired(intruder)
        assert items_intruder == []
        assert await adb.count_expired(intruder) == 0

        items_owner = await adb.list_expired(owner)
        assert len(items_owner) == 1
    finally:
        async with db.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM usuario_recursos WHERE tenant_id = ANY($1)",
                [owner, intruder],
            )
            if rid:
                await conn.execute("DELETE FROM recursos WHERE id = $1::uuid", rid)
        await db.close()
        await adb.close_pool()
