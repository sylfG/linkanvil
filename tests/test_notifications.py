"""Tests para el feed in-app de notificaciones (F-05.3) y el procesado
de mensajes del notifier worker."""
import pytest

from src.api import database as adb
from src.data.db import DatabaseManager


async def _insert_notification(conn, tenant_id: str, evento_tipo: str,
                                titulo: str = "Test", motivo: str | None = None,
                                leido: bool = False) -> str:
    return str(await conn.fetchval(
        """INSERT INTO notificaciones (tenant_id, evento_tipo, titulo, motivo, leido)
           VALUES ($1, $2, $3, $4, $5)
           RETURNING id""",
        tenant_id, evento_tipo, titulo, motivo, leido,
    ))


@pytest.mark.asyncio
async def test_list_notifications_orders_recent_first():
    db = DatabaseManager()
    await db.connect()
    tenant_id = "tenant_test_notif_list"
    try:
        async with db.pool.acquire() as conn:
            await _insert_notification(conn, tenant_id, "recurso.cuarentena", "Primero", "caducidad")
            await _insert_notification(conn, tenant_id, "recurso.expirado", "Segundo", "gracia_agotada")

        items = await adb.list_notifications(tenant_id)
        assert len(items) == 2
        # La más reciente (Segundo) primero
        assert items[0]["titulo"] == "Segundo"
        assert items[1]["titulo"] == "Primero"
        for it in items:
            assert it["leido"] is False
    finally:
        async with db.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM notificaciones WHERE tenant_id = $1", tenant_id,
            )
        await db.close()
        await adb.close_pool()


@pytest.mark.asyncio
async def test_count_unread_excludes_read():
    db = DatabaseManager()
    await db.connect()
    tenant_id = "tenant_test_notif_count"
    try:
        async with db.pool.acquire() as conn:
            await _insert_notification(conn, tenant_id, "recurso.cuarentena")
            await _insert_notification(conn, tenant_id, "recurso.expirado")
            await _insert_notification(conn, tenant_id, "recurso.expirado", leido=True)

        assert await adb.count_unread_notifications(tenant_id) == 2
    finally:
        async with db.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM notificaciones WHERE tenant_id = $1", tenant_id,
            )
        await db.close()
        await adb.close_pool()


@pytest.mark.asyncio
async def test_mark_notification_read_idempotent_and_tenant_scoped():
    db = DatabaseManager()
    await db.connect()
    owner = "tenant_test_notif_owner"
    intruder = "tenant_test_notif_intruder"
    nid = None
    try:
        async with db.pool.acquire() as conn:
            nid = await _insert_notification(conn, owner, "recurso.cuarentena")

        # Tenant ajeno NO debe poder marcarla
        assert await adb.mark_notification_read(intruder, nid) is False

        # Owner sí
        assert await adb.mark_notification_read(owner, nid) is True
        # Segunda vez → ya leída, devuelve False
        assert await adb.mark_notification_read(owner, nid) is False

        async with db.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT leido, leido_en FROM notificaciones WHERE id = $1::uuid", nid,
            )
            assert row["leido"] is True
            assert row["leido_en"] is not None
    finally:
        async with db.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM notificaciones WHERE tenant_id = ANY($1)",
                [owner, intruder],
            )
        await db.close()
        await adb.close_pool()


@pytest.mark.asyncio
async def test_mark_all_notifications_read():
    db = DatabaseManager()
    await db.connect()
    tenant_id = "tenant_test_notif_all"
    try:
        async with db.pool.acquire() as conn:
            await _insert_notification(conn, tenant_id, "recurso.cuarentena")
            await _insert_notification(conn, tenant_id, "recurso.expirado")
            await _insert_notification(conn, tenant_id, "recurso.expirado", leido=True)

        marked = await adb.mark_all_notifications_read(tenant_id)
        assert marked == 2  # las dos no-leídas
        assert await adb.count_unread_notifications(tenant_id) == 0

        # Re-ejecutar es no-op
        assert await adb.mark_all_notifications_read(tenant_id) == 0
    finally:
        async with db.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM notificaciones WHERE tenant_id = $1", tenant_id,
            )
        await db.close()
        await adb.close_pool()


@pytest.mark.asyncio
async def test_only_unread_filter():
    db = DatabaseManager()
    await db.connect()
    tenant_id = "tenant_test_notif_filter"
    try:
        async with db.pool.acquire() as conn:
            await _insert_notification(conn, tenant_id, "recurso.cuarentena", "U1")
            await _insert_notification(conn, tenant_id, "recurso.expirado", "U2", leido=True)

        all_items = await adb.list_notifications(tenant_id, only_unread=False)
        assert len(all_items) == 2

        unread = await adb.list_notifications(tenant_id, only_unread=True)
        assert len(unread) == 1
        assert unread[0]["titulo"] == "U1"
    finally:
        async with db.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM notificaciones WHERE tenant_id = $1", tenant_id,
            )
        await db.close()
        await adb.close_pool()
