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
    ExtracciÃ³n asistida por Proxy IA (LLM Gateway).
    Implementa F-02.2: Llama a LiteLLM con metadatos para trazabilidad.
    """
    def __init__(self, tenant_id: str = "default_tenant", trace_id: str = "N/A"):
        self.tenant_id = tenant_id
        self.trace_id = trace_id
        self.llm_gateway_url = "http://litellm:4000/v1/chat/completions"
        ref_key = "sk-cerebro-master-key-CHANGE_ME"
        self.api_key = ref_key

    async def extract(self, url: str) -> str:
        logger.info(f"Simulando extracciÃ³n asistida por AI Proxy: {url}")
        
        payload = {
            "model": "cerebro-mini",
            "messages": [
                {"role": "system", "content": "You are a web scraper analyzer."},
                {"role": "user", "content": f"Extract key information from this url or content: {url}"}
            ],
            "metadata": {
                "trace_id": self.trace_id,
                "tenant_id": self.tenant_id
            }
        }
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(self.llm_gateway_url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]

class ScraperContext:
    """
    Contexto de ruteo dinámico.
    Selecciona la estrategia adecuada en base a heurísticas o configuración.
    """
    def __init__(self, tenant_id: str = "default_tenant", trace_id: str = "N/A", default_strategy: ScraperStrategy = None):
        self.tenant_id = tenant_id
        self.trace_id = trace_id
        self.default_strategy = default_strategy or BasicHttpStrategy()

    def _determine_strategy(self, url: str, source: Optional[str] = None) -> ScraperStrategy:
        """
        Ruteo dinÃ¡mico rudimentario.
        En producciÃ³n: Se puede expandir para verificar headers, meta-tags o dominios conocidos.
        """
        if source == "js_heavy" or "spa" in url:
            return PuppeteerStrategy()
        elif source == "ai_proxy" or "captcha" in url:
            return AiProxyStrategy(self.tenant_id, self.trace_id)
        return self.default_strategy

    async def execute(self, url: str, source: Optional[str] = None) -> str:
        strategy = self._determine_strategy(url, source)
        return await strategy.extract(url)
