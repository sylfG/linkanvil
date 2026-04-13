FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir httpx aio-pika redis pydantic pydantic-settings asyncpg

COPY src /app/src

ENV PYTHONPATH=/app

CMD ["python", "-m", "src.scraper.worker"]
