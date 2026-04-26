FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    wget ca-certificates fonts-liberation \
    libasound2t64 libatk-bridge2.0-0 libatk1.0-0 libatspi2.0-0 \
    libcairo2 libcups2 libdbus-1-3 libdrm2 libgbm1 libgtk-3-0 \
    libnspr4 libnss3 libpango-1.0-0 libx11-6 libx11-xcb1 libxcb1 \
    libxcomposite1 libxdamage1 libxext6 libxfixes3 libxkbcommon0 \
    libxrandr2 libxshmfence1 xdg-utils \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    httpx aio-pika redis pydantic pydantic-settings asyncpg \
    beautifulsoup4 patchright trafilatura

# Non-root user (created BEFORE patchright install so the browser cache
# lives in /home/cerebro and is owned correctly)
RUN groupadd -r cerebro && useradd -r -g cerebro -u 1000 -m -d /home/cerebro cerebro \
    && mkdir -p /data /home/cerebro/.cache \
    && chown -R cerebro:cerebro /app /data /home/cerebro

USER cerebro

# patchright cache lands in /home/cerebro/.cache/ms-playwright
ENV PLAYWRIGHT_BROWSERS_PATH=/home/cerebro/.cache/ms-playwright
RUN python -m patchright install chromium

COPY --chown=cerebro:cerebro src /app/src

ENV PYTHONPATH=/app

VOLUME ["/data"]

CMD ["python", "-m", "src.scraper.worker"]
