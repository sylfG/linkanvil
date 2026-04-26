"""
Background heartbeat task for workers without an HTTP endpoint.

Each worker writes a short-lived key in Redis every N seconds. A docker
healthcheck reads the key and fails when it's missing — detecting a
worker that has hung but not crashed.
"""
import asyncio
import logging
import os
from typing import Optional

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL = int(os.getenv("WORKER_HEARTBEAT_INTERVAL_SEC", "15"))
DEFAULT_TTL = int(os.getenv("WORKER_HEARTBEAT_TTL_SEC", "45"))


async def heartbeat_loop(
    redis_client: aioredis.Redis,
    worker_name: str,
    interval: int = DEFAULT_INTERVAL,
    ttl: int = DEFAULT_TTL,
) -> None:
    """Run forever; cancel-safe (CancelledError stops cleanly)."""
    key = f"worker:{worker_name}:heartbeat"
    try:
        while True:
            try:
                await redis_client.set(key, "1", ex=ttl)
            except Exception as e:
                logger.warning(f"heartbeat write failed for {worker_name}: {e}")
            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        return


def start_heartbeat(
    redis_client: aioredis.Redis, worker_name: str
) -> asyncio.Task:
    return asyncio.create_task(heartbeat_loop(redis_client, worker_name))
