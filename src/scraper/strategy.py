import abc
import logging
import httpx
from typing import Optional

logger = logging.getLogger(__name__)

class ScraperStrategy(abc.ABC):
    """
    Estrategia base para extracción de contenido.
    Patrón Strategy para soportar múltiples motores.
    """
    @abc.abstractmethod
    async def extract(self, url: str) -> str:
        pass

class BasicHttpStrategy(ScraperStrategy):
    """
    Extracción rápida vía HTTP estándar.
    Ideal para artículos y blogs.
    """
    async def extract(self, url: str) -> str:
        logger.info(f"Extrayendo contenido vía BasicHttpStrategy: {url}")
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.text

class PuppeteerStrategy(ScraperStrategy):
    """
    Simulación de Puppeteer / Browser Automation para SPAs.
    """
    async def extract(self, url: str) -> str:
        logger.info(f"Simulando extracción vía PuppeteerStrategy (Renderizado JS): {url}")
        # Aquí en el futuro se llamaría a Playwright/Puppeteer/Browserless
        # Por ahora simulamos una respuesta exitosa
        return f"<html><body>Contenido renderizado JS de {url}</body></html>"

class AiProxyStrategy(ScraperStrategy):
    """
    Extracción asistida por Proxy IA (ej. Firecrawl o ScrapingBee).
    """
    async def extract(self, url: str) -> str:
        logger.info(f"Simulando extracción asistida por AI Proxy: {url}")
        # Aquí habría una llamada externa al proxy
        return f"<html><body>Contenido interpretado por IA de {url}</body></html>"

class ScraperContext:
    """
    Contexto de ruteo dinámico.
    Selecciona la estrategia adecuada en base a heurísticas o configuración.
    """
    def __init__(self, default_strategy: ScraperStrategy = None):
        self.default_strategy = default_strategy or BasicHttpStrategy()

    def _determine_strategy(self, url: str, source: Optional[str] = None) -> ScraperStrategy:
        """
        Ruteo dinámico rudimentario.
        En producción: Se puede expandir para verificar headers, meta-tags o dominios conocidos.
        """
        if source == "js_heavy" or "spa" in url:
            return PuppeteerStrategy()
        elif source == "ai_proxy" or "captcha" in url:
            return AiProxyStrategy()
        return self.default_strategy

    async def execute(self, url: str, source: Optional[str] = None) -> str:
        strategy = self._determine_strategy(url, source)
        return await strategy.extract(url)
