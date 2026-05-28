"""Tests del RedisDeduplicator (RedisBloom + async).

Refactor previo (#643361b) cambió la implementación a `redis.asyncio` y
los tests del archivo original quedaron rotos: usaban MagicMock síncrono
sobre un cliente async y no hacían await. Aquí reescribimos los tests
con AsyncMock y @pytest.mark.asyncio.
"""
import pytest
from unittest.mock import AsyncMock

import redis.exceptions

from src.ingestion.deduplicator import RedisDeduplicator


def _async_redis_mock(*, exists_return=0, bf_add_return=1):
    """Construye un AsyncMock que parece `redis.asyncio.Redis` para el
    contrato que usa RedisDeduplicator (`exists`, `execute_command`)."""
    m = AsyncMock()
    m.exists = AsyncMock(return_value=exists_return)
    # execute_command se llama con (\"BF.RESERVE\", ...) y (\"BF.ADD\", ...).
    # Devolvemos bf_add_return para el caso típico; para BF.RESERVE no
    # importa lo que devuelva (no se usa).
    m.execute_command = AsyncMock(return_value=bf_add_return)
    return m


@pytest.mark.asyncio
async def test_bloom_filter_happy_path():
    """Primer elemento es nuevo; duplicado es rechazado; otro distinto es nuevo."""
    # Simulamos un bloom "real": guardamos en un set lo que hemos visto y
    # devolvemos 1/0 según corresponda en BF.ADD.
    seen: set = set()

    async def fake_execute(*args, **kwargs):
        if args[0] == "BF.RESERVE":
            return True
        if args[0] == "BF.ADD":
            key = (args[1], args[2])
            if key in seen:
                return 0
            seen.add(key)
            return 1
        return None

    m = AsyncMock()
    m.exists = AsyncMock(return_value=1)  # bloom ya existe → no reserve
    m.execute_command = AsyncMock(side_effect=fake_execute)

    dedup = RedisDeduplicator(redis_client=m)
    tenant_id = "tenant_xyz"
    trace_id = "trace-1234"
    item1 = "https://example.com/article/1"
    item2 = "https://example.com/article/2"

    assert await dedup.is_new_item(item1, tenant_id, trace_id) is True
    assert await dedup.is_new_item(item1, tenant_id, trace_id) is False
    assert await dedup.is_new_item(item2, tenant_id, trace_id) is True


@pytest.mark.asyncio
async def test_bloom_filter_tenant_isolation():
    """El mismo item para tenants distintos genera filtros distintos."""
    seen: set = set()

    async def fake_execute(*args, **kwargs):
        if args[0] == "BF.RESERVE":
            return True
        if args[0] == "BF.ADD":
            key = (args[1], args[2])
            if key in seen:
                return 0
            seen.add(key)
            return 1
        return None

    m = AsyncMock()
    m.exists = AsyncMock(return_value=1)
    m.execute_command = AsyncMock(side_effect=fake_execute)

    dedup = RedisDeduplicator(redis_client=m)
    item = "https://example.com/article/1"

    assert await dedup.is_new_item(item, "Tenant_A", "t-001") is True
    assert await dedup.is_new_item(item, "Tenant_B", "t-002") is True
    assert await dedup.is_new_item(item, "Tenant_A", "t-003") is False


@pytest.mark.asyncio
async def test_bloom_filter_redis_down_triggers_dlq():
    """Si Redis cae y hay dlq_callback configurado, se invoca y devuelve False."""
    m = AsyncMock()
    err = redis.exceptions.ConnectionError("Connection refused")
    m.exists = AsyncMock(side_effect=err)
    m.execute_command = AsyncMock(side_effect=err)

    triggered = {"value": False}

    async def my_dlq_callback(item, tenant_id, trace_id, _exc):
        triggered["value"] = True

    dedup = RedisDeduplicator(
        redis_client=m,
        dlq_callback=my_dlq_callback,
    )

    is_new = await dedup.is_new_item(
        "https://example.com/broken", "Tenant_C", "t-004",
    )
    assert triggered["value"] is True
    assert is_new is False


@pytest.mark.asyncio
async def test_bloom_filter_redis_down_fallback():
    """Sin dlq_callback, política fail-open: trata como nuevo y deja pasar."""
    m = AsyncMock()
    err = redis.exceptions.ConnectionError("Connection refused")
    m.exists = AsyncMock(side_effect=err)
    m.execute_command = AsyncMock(side_effect=err)

    dedup = RedisDeduplicator(redis_client=m, dlq_callback=None)

    is_new = await dedup.is_new_item(
        "https://example.com/broken", "Tenant_C", "t-005",
    )
    assert is_new is True
