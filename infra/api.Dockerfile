FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    fastapi \
    "uvicorn[standard]" \
    "python-jose[cryptography]" \
    bcrypt \
    asyncpg \
    pydantic \
    pydantic-settings \
    httpx \
    "redis[asyncio]"

COPY src /app/src

# Non-root user for defense in depth
RUN groupadd -r cerebro && useradd -r -g cerebro -u 1000 cerebro \
    && chown -R cerebro:cerebro /app
USER cerebro

ENV PYTHONPATH=/app

EXPOSE 8001

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8001"]
