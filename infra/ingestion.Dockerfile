FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn aio-pika redis pydantic pydantic-settings

COPY src /app/src

ENV PYTHONPATH=/app

CMD ["uvicorn", "src.ingestion.main:app", "--host", "0.0.0.0", "--port", "8000"]
