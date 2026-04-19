FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir httpx aio-pika redis pydantic pydantic-settings asyncpg "scrapling[all]"

# Instalamos navegador chromium y sus dependencias OS asociadas para el scraping dinámico (F-02.1)
RUN playwright install --with-deps chromium

COPY src /app/src

ENV PYTHONPATH=/app

CMD ["python", "-m", "src.scraper.worker"]
