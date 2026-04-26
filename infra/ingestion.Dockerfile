FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn aio-pika redis pydantic pydantic-settings httpx

COPY src /app/src

RUN groupadd -r cerebro && useradd -r -g cerebro -u 1000 cerebro \
    && chown -R cerebro:cerebro /app
USER cerebro

ENV PYTHONPATH=/app

CMD ["uvicorn", "src.ingestion.main:app", "--host", "0.0.0.0", "--port", "8000"]
