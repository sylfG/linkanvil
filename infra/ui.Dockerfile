FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    streamlit \
    httpx \
    pydantic \
    pydantic-settings \
    asyncpg \
    psycopg2-binary \
    aiohttp \
    redis \
    opentelemetry-sdk \
    opentelemetry-exporter-otlp-proto-grpc

# Copy src for any shared modules
COPY src /app/src

ENV PYTHONPATH=/app

EXPOSE 8501

CMD ["streamlit", "run", "src/ui/chatbot.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.enableCORS=false", \
     "--server.enableXsrfProtection=false"]