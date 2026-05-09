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


class BlockedContentError(Exception):
    """El scraper recibió una página de bloqueo anti-bot (CF/Datadome/etc.)
    que no contiene el contenido real. El worker la captura para mover el
    recurso a cuarentena en lugar de embeder texto basura."""


def _rewrite_for_scrape(url: str) -> str:
    """Reescribe dominios con anti-bot agresivo a un espejo legible. La URL
    original se conserva en la BD; solo la descarga usa el espejo. Hoy:
    medium.com → readmedium.com (Medium usa Datadome y nuestro Stealth no lo
    bypassa)."""
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return url
    if host == "medium.com" or host.endswith(".medium.com"):
        return f"https://readmedium.com/{url}"
    return url


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
        lowered = html[:4000].lower()
        # Inglés (Cloudflare/genérico) + español (Datadome muestra el aviso
        # localizado, p.ej. Medium con visitantes desde España).
        # Marcadores específicos de páginas de bloqueo / challenge.
        # IMPORTANTE: NO usar "cloudflare" o "captcha" en plano — cualquier
        # web que cargue assets de cdnjs.cloudflare.com o que mencione
        # "captcha" en su contenido editorial caería por falso positivo.
        markers = [
            "checking your browser",
            "cf-challenge",
            "cf-mitigated",
            "attention required! | cloudflare",
            "performance & security by cloudflare",
            "just a moment...",
            "ddos protection by",
            "verifying you are human",
            "verify you are human",
            "press and hold to confirm",
            "datadome",
            "are you a robot",
            "verifica que usted no es un bot",
            "verifica que no eres un bot",
            "verificación de seguridad para protegerse",
            "comprobando su navegador antes de acceder",
            "servicio de seguridad para protegerse",
            # Espejos rotos / dominios parked (readmedium fallback,
            # medium.rip aparcado, etc.). Si el espejo no consigue renderizar
            # el artículo nos devuelve un shell sin contenido útil.
            "failed to render this page",
            "this domain is for sale",
        ]
        return any(s in lowered for s in markers)

    async def execute(self, url: str, source: str | None = None) -> str:
        # Reescritura anti-bot: si el dominio es notoriamente complicado
        # (Medium/Datadome), pedimos contenido al espejo legible. La URL
        # original sigue siendo la que ve el usuario en su KB.
        fetch_url = _rewrite_for_scrape(url)
        if fetch_url != url:
            logger.info(f"[{self.trace_id}] URL reescrita para fetch: {fetch_url}")

        if (source or "").lower() in DYNAMIC_SOURCES or _is_js_heavy(fetch_url):
            logger.info(f"[{self.trace_id}] [StealthPlaywrightStrategy] Extrayendo: {fetch_url}")
            html = await StealthPlaywrightStrategy(self.redis).scrape(fetch_url)
            if self._looks_blocked(html):
                logger.warning(f"[{self.trace_id}] Stealth bloqueado, marcando para cuarentena: {url}")
                raise BlockedContentError(url)
            return html
        try:
            logger.info(f"[{self.trace_id}] [BasicHttpStrategy] Extrayendo: {fetch_url}")
            html = await BasicHttpStrategy().scrape(fetch_url)
            if self._looks_blocked(html):
                logger.info(f"[{self.trace_id}] Basic devolvió bloqueo, escalando a Stealth")
                html = await StealthPlaywrightStrategy(self.redis).scrape(fetch_url)
                if self._looks_blocked(html):
                    logger.warning(f"[{self.trace_id}] Stealth tampoco superó el muro, cuarentena: {url}")
                    raise BlockedContentError(url)
            return html
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (403, 429, 503):
                logger.info(f"[{self.trace_id}] HTTP {e.response.status_code}, escalando a Stealth")
                html = await StealthPlaywrightStrategy(self.redis).scrape(fetch_url)
                if self._looks_blocked(html):
                    logger.warning(f"[{self.trace_id}] Stealth bloqueado tras {e.response.status_code}, cuarentena: {url}")
                    raise BlockedContentError(url)
                return html
            raise
