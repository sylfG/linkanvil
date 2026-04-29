import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)


async def with_retries(
    fn,
    *,
    attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 4.0,
    retry_on: tuple = (httpx.HTTPStatusError, httpx.TransportError, httpx.TimeoutException),
):
    last_exc = None
    for i in range(attempts):
        try:
            return await fn()
        except retry_on as e:
            last_exc = e
            if isinstance(e, httpx.HTTPStatusError) and e.response.status_code < 500 and e.response.status_code != 429:
                raise
            if i == attempts - 1:
                raise
            delay = min(base_delay * (3**i), max_delay)
            logger.warning(f"Retry {i + 1}/{attempts} tras {e!r} → sleep {delay:.1f}s")
            await asyncio.sleep(delay)
    raise last_exc
