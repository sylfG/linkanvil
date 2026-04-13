import re

with open('src/scraper/strategy.py', 'r', encoding='utf-8') as f:
    text = f.read()

new_imports_and_schema = '''import abc
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
'''

pattern = re.compile(r'import abc(?:.*?)(?:class ScraperStrategy\(abc\.ABC\):)', re.DOTALL)
text = pattern.sub(new_imports_and_schema + '\nclass ScraperStrategy(abc.ABC):\n', text)

with open('src/scraper/strategy.py', 'w', encoding='utf-8') as f:
    f.write(text)
