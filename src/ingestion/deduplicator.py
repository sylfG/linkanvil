import logging
from typing import Optional, Callable, Awaitable

import redis.asyncio as aioredis
from redis.exceptions import RedisError, ResponseError

logger = logging.getLogger(__name__)

DLQCallback = Callable[[str, str, str, Exception], Awaitable[None]]


class RedisDeduplicator:
    """
    Filtro Deduplicador en Tiempo Real basado en Bloom Filters (RedisBloom).
    Async-only — usa redis.asyncio para no bloquear el event loop.
    """

    def __init__(
        self,
        redis_client: aioredis.Redis,
        dlq_callback: Optional[DLQCallback] = None,
    ):
        self.redis = redis_client
        self.dlq_callback = dlq_callback
        self.default_error_rate = 0.001
        self.default_capacity = 1000000

    def _get_bloom_key(self, tenant_id: str) -> str:
        return f"bf:tenant:{tenant_id}:ingestion"

    async def _ensure_bloom_filter(self, key: str, trace_id: str) -> None:
        try:
            exists = await self.redis.exists(key)
            if not exists:
                await self.redis.execute_command(
                    "BF.RESERVE", key, self.default_error_rate, self.default_capacity
                )
                logger.info(f"[{trace_id}] Bloom Filter creado para llave: {key}")
        except ResponseError as e:
            if "already exists" not in str(e).lower():
                raise

    async def is_new_item(self, item_hash: str, tenant_id: str, trace_id: str) -> bool:
        """
        Devuelve True si el elemento es nuevo (y queda registrado en el filtro).
        Devuelve False si ya existía o si Redis falla y la política es fail-open.
        """
        key = self._get_bloom_key(tenant_id)
        try:
            await self._ensure_bloom_filter(key, trace_id)
            result = await self.redis.execute_command("BF.ADD", key, item_hash)
            is_new = bool(int(result))
            if is_new:
                logger.info(f"[{trace_id}] [TENANT:{tenant_id}] Nuevo elemento ingerido: {item_hash}")
            else:
                logger.info(f"[{trace_id}] [TENANT:{tenant_id}] Elemento DUPLICADO ignorado: {item_hash}")
            return is_new
        except (RedisError, Exception) as e:
            logger.error(
                f"[{trace_id}] [TENANT:{tenant_id}] Error validando duplicidad '{item_hash}': {e}"
            )
            if self.dlq_callback:
                await self.dlq_callback(item_hash, tenant_id, trace_id, e)
                return False
            logger.warning(f"[{trace_id}] [TENANT:{tenant_id}] Fallback aplicado (fail-open).")
            return True
