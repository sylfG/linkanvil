"""Integración real contra redis-stack-server (Bloom filter en vivo).

Usa REDIS_URL del entorno (mismo cliente que el resto del stack) y la
API async de redis.asyncio — RedisDeduplicator es async-only desde el
refactor previo. Si REDIS_URL no apunta a una instancia con módulo
RedisBloom, el test se salta con un skip explícito.
"""
import os
import time

import pytest
import redis.asyncio as aioredis
from redis.exceptions import ConnectionError as RedisConnectionError

from src.ingestion.deduplicator import RedisDeduplicator


REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")


@pytest.mark.asyncio
async def test_live_redis_bloom_filter():
    """Latencia y comportamiento del bloom filter contra Redis real."""
    client = aioredis.from_url(REDIS_URL, decode_responses=True)

    # Skip si Redis no está accesible (entorno local sin docker compose).
    try:
        await client.ping()
    except RedisConnectionError as exc:
        pytest.skip(f"Redis no accesible en {REDIS_URL}: {exc}")

    try:
        dedup = RedisDeduplicator(redis_client=client)
        tenant_id = "test_tenant_live"
        trace_id = "trace-live-001"
        key = dedup._get_bloom_key(tenant_id)
        await client.delete(key)

        item = "https://example.com/live/1"

        # 1. Primer insert: debe ser nuevo y rápido.
        t0 = time.perf_counter()
        is_new = await dedup.is_new_item(item, tenant_id, trace_id)
        dt_ms = (time.perf_counter() - t0) * 1000
        assert is_new is True, "El item debería ser nuevo"
        assert dt_ms < 200, f"Latencia excedida: {dt_ms:.2f} ms"

        # 2. Duplicado: debe ser rechazado y igual de rápido.
        t0 = time.perf_counter()
        is_new2 = await dedup.is_new_item(item, tenant_id, trace_id)
        dt_ms2 = (time.perf_counter() - t0) * 1000
        assert is_new2 is False, "El item debería ser duplicado"
        assert dt_ms2 < 200, f"Latencia excedida en duplicado: {dt_ms2:.2f} ms"

        await client.delete(key)
    finally:
        await client.aclose()
