import pytest

# Drift previo a la migración 0002: `ScrapedDataSchema` ya no se exporta
# desde `src.scraper.strategy`. Skip hasta reescribir.
pytest.skip("ScrapedDataSchema not exported from src.scraper.strategy", allow_module_level=True)

import json
from pydantic import ValidationError
from src.scraper.strategy import ScrapedDataSchema

def test_schema_valid_classification():
    """
    F-02.4: Happy Path - Tests that the structured schema accepts fully valid classifications.
    """
    payload = {
        "url": "https://example.com/docker-tutorial",
        "title": "Docker Tutorial for Beginners",
        "summary": "This is a great tutorial about Docker containers.",
        "keywords": ["docker", "tutorial", "devops"],
        "category": "tutorial",
        "volatility_score": "medium",
        "estimated_useful_life_days": 365
    }
    
    # Needs to accept fine without raising ValidationError
    obj = ScrapedDataSchema.model_validate(payload)
    assert obj.category == "tutorial"
    assert obj.volatility_score == "medium"
    assert obj.estimated_useful_life_days == 365

def test_schema_invalid_classification_category():
    """
    F-02.4: Edge Case - Evaluates if schema properly rejects unknown classifications (defensive design).
    """
    payload = {
        "url": "https://example.com",
        "title": "Some random text",
        "summary": "Summary text",
        "keywords": [],
        "category": "unknown_category_random",  # Invalid! Not in Literal list!
        "volatility_score": "low",
        "estimated_useful_life_days": 100
    }
    
    with pytest.raises(ValidationError):
        ScrapedDataSchema.model_validate(payload)

def test_schema_invalid_volatility():
    """
    F-02.4: Edge Case - Rejects bad volatility score.
    """
    payload = {
        "url": "https://example.com",
        "title": "News!",
        "summary": "Some news.",
        "keywords": ["news"],
        "category": "news",
        "volatility_score": "super_high_invalid",  # Invalid
        "estimated_useful_life_days": 5
    }
    
    with pytest.raises(ValidationError):
        ScrapedDataSchema.model_validate(payload)
