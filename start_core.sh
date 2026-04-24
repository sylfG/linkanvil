#!/bin/bash

echo "Iniciando los servicios fundamentales de Cerebro (sin observabilidad/telemetría)..."

docker compose up -d \
  traefik \
  postgres \
  qdrant \
  redis \
  rabbitmq \
  litellm \
  n8n \
  ingestion-api \
  scraper-worker \
  outbox-worker \
  embedder-worker \
  cerebro-chat

echo ""
echo "¡Servicios fundamentales iniciados!"
echo "Puedes ver los logs usando: docker compose logs -f"
