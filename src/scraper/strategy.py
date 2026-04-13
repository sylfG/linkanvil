import abc
import logging
import httpx
import json
from typing import Optional, List, Literal
from pydantic import BaseModel, Field, ValidationError

logger = logging.getLogger(__name__)

class ScrapedDataSchema(BaseModel):
    """
    Schema for F-02.3 and F-02.4: Zero-Defect pipeline structural enforcement 
    and Intelligent Classification / Logical Useful Life Estimation (Volatility).
    """
    url: str = Field(..., description="The original URL")
    title: str = Field(..., description="The title of the extracted content")
    summary: str = Field(..., description="A short summary of the extracted content")
    keywords: List[str] = Field(default_factory=list, description="List of relevant keywords")
    category: Literal["news", "technical_article", "tutorial", "opinion", "documentation", "other"] = Field(
        ..., description="Intelligent classification of the content"
    )
    volatility_score: Literal["low", "medium", "high"] = Field(
        ..., description="Volatility of content (e.g. news is high because it expires fast, core documentation is low)"
    )
    estimated_useful_life_days: int = Field(
        ..., description="Estimated logical useful life of this content in days before it becomes completely obsolete."
    )

class ScraperStrategy(abc.ABC):

    """
    Estrategia base para extraccion de contenido.
    Patron Strategy para soportar multiples motores.
    """
    @abc.abstractmethod
    async def extract(self, url: str) -> str:
        pass

class BasicHttpStrategy(ScraperStrategy):
    """
    Extraccion rapida via HTTP estandar.
    Ideal para articulos y blogs.
    """
    async def extract(self, url: str) -> str:
        logger.info(f"Extrayendo contenido via BasicHttpStrategy: {url}")
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.text

class PuppeteerStrategy(ScraperStrategy):
    """
    Simulacion de Puppeteer / Browser Automation para SPAs.
    """
    async def extract(self, url: str) -> str:
        logger.info(f"Simulando extraccion via PuppeteerStrategy (Renderizado JS): {url}")
        return f"<html><body>Contenido renderizado JS de {url}</body></html>"

class AiProxyStrategy(ScraperStrategy):
    """
    Extraccion asistida por Proxy IA (LLM Gateway).
    Implementa F-02.2 y F-02.3
    """
    def __init__(self, tenant_id: str = "default_tenant", trace_id: str = "N/A"):
        self.tenant_id = tenant_id
        self.trace_id = trace_id
        self.llm_gateway_url = "http://litellm:4000/v1/chat/completions"
        self.api_key = "sk-cerebro-master-key-CHANGE_ME"

    async def extract(self, url: str) -> str:
        logger.info(f"Simulando extraccion asistida por AI Proxy: {url}")
        
        schema_json = json.dumps(ScrapedDataSchema.model_json_schema())
        system_prompt = (
            "You are a web scraper analyzer. You MUST output ONLY valid JSON "
            "that strictly conforms to this schema, with no markdown code blocks:\n"
            + schema_json
        )

        payload = {
            "model": "cerebro-mini",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Extract key information from this url or content: {url}"}
            ],
            "response_format": {"type": "json_object"},
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
            try:
                response = await client.post(self.llm_gateway_url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                content_str = data["choices"][0]["message"]["content"]
                
                # Zero-Defect Pipeline validation
                validated_data = ScrapedDataSchema.model_validate_json(content_str)
                return validated_data.model_dump_json()

            except ValidationError as ve:
                logger.error(f"F-02.3 Fallo Pydantic Zero-Defect JSON: {ve.errors()}")
                raise ValueError(f"Invalid JSON structure returned by LLM: {str(ve)}")
            except Exception as e:
                logger.error(f"Error procesando AI Proxy Strategy: {str(e)}")
                raise

class ScraperContext:
    def __init__(self, tenant_id: str = "default_tenant", trace_id: str = "N/A", default_strategy: ScraperStrategy = None):
        self.tenant_id = tenant_id
        self.trace_id = trace_id
        self.default_strategy = default_strategy or BasicHttpStrategy()

    def _determine_strategy(self, url: str, source: Optional[str] = None) -> ScraperStrategy:
        if source == "js_heavy" or "spa" in url:
            return PuppeteerStrategy()
        elif source == "ai_proxy" or "captcha" in url:
            return AiProxyStrategy(self.tenant_id, self.trace_id)
        return self.default_strategy

    async def execute(self, url: str, source: Optional[str] = None) -> str:
        strategy = self._determine_strategy(url, source)
        return await strategy.extract(url)
