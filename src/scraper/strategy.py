import json
import logging
import os
from abc import ABC, abstractmethod
from urllib.parse import urlparse

import httpx

from src.scraper._retry import with_retries

logger = logging.getLogger(__name__)

DYNAMIC_SOURCES = {"telegram", "extension", "dynamic", "browser"}

JS_HEAVY_DOMAINS = {
    "medium.com", "towardsdatascience.com", "betterprogramming.pub",
    "javascript.plainenglish.io", "levelup.gitconnected.com",
    "substack.com", "notion.so", "twitter.com", "x.com",
    "linkedin.com", "instagram.com", "facebook.com",
}

PROFILE_DIR = os.getenv("PLAYWRIGHT_PROFILE", "/data/playwright_profile")
STEALTH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--window-size=1920,1080",
]


class ScraperStrategy(ABC):
    @abstractmethod
    async def scrape(self, url: str) -> str: ...


class BasicHttpStrategy(ScraperStrategy):
    async def scrape(self, url: str) -> str:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            async def _do():
                resp = await client.get(
                    url, headers={"User-Agent": "Mozilla/5.0 (compatible; LinkAnvil/1.0)"}
                )
                resp.raise_for_status()
                return resp.text

            return await with_retries(_do)


class StealthPlaywrightStrategy(ScraperStrategy):
    def __init__(self, redis_client=None):
        self.redis = redis_client

    async def scrape(self, url: str) -> str:
        from patchright.async_api import async_playwright

        domain = urlparse(url).netloc
        cf_cookies = await self._load_cf_cookies(domain)
        async with async_playwright() as p:
            ctx = await p.chromium.launch_persistent_context(
                user_data_dir=PROFILE_DIR,
                headless=True,
                args=STEALTH_ARGS,
                viewport={"width": 1920, "height": 1080},
                locale="es-ES",
            )
            if cf_cookies:
                await ctx.add_cookies(cf_cookies)
            page = await ctx.new_page()
            try:
                await page.goto(url, timeout=60000, wait_until="domcontentloaded")
                await page.wait_for_timeout(1500)
                return await page.content()
            finally:
                await ctx.close()

    async def _load_cf_cookies(self, domain: str) -> list[dict]:
        if not self.redis:
            return []
        raw = await self.redis.get(f"cf:cookies:{domain}")
        return json.loads(raw) if raw else []


def _is_js_heavy(url: str) -> bool:
    try:
        host = urlparse(url).hostname or ""
        return any(host == d or host.endswith("." + d) for d in JS_HEAVY_DOMAINS)
    except Exception:
        return False


class ScraperContext:
    def __init__(self, tenant_id: str, trace_id: str, redis=None):
        self.tenant_id = tenant_id
        self.trace_id = trace_id
        self.redis = redis

    def _looks_blocked(self, html: str) -> bool:
        if len(html) < 500:
            return True
        lowered = html[:2000].lower()
        return any(s in lowered for s in [
            "checking your browser", "cf-challenge", "cloudflare",
            "just a moment", "captcha", "ddos protection",
        ])

    async def execute(self, url: str, source: str | None = None) -> str:
        if (source or "").lower() in DYNAMIC_SOURCES or _is_js_heavy(url):
            logger.info(f"[{self.trace_id}] [StealthPlaywrightStrategy] Extrayendo: {url}")
            return await StealthPlaywrightStrategy(self.redis).scrape(url)
        try:
            logger.info(f"[{self.trace_id}] [BasicHttpStrategy] Extrayendo: {url}")
            html = await BasicHttpStrategy().scrape(url)
            if self._looks_blocked(html):
                logger.info(f"[{self.trace_id}] Basic devolvió bloqueo, escalando a Stealth")
                return await StealthPlaywrightStrategy(self.redis).scrape(url)
            return html
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (403, 429, 503):
                logger.info(f"[{self.trace_id}] HTTP {e.response.status_code}, escalando a Stealth")
                return await StealthPlaywrightStrategy(self.redis).scrape(url)
            raise
