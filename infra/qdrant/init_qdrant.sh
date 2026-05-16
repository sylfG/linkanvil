#!/bin/bash
# init_qdrant.sh - Script para inicializar colecciones base en Qdrant (F-00.6)

set -e

QDRANT_HOST=${1:-"http://localhost:6333"}

echo "Inicializando colecciones en Qdrant ($QDRANT_HOST)..."

# Coleccion: cerebro_recursos (vector doc-level, usado para detección de colisiones)
curl -X PUT "$QDRANT_HOST/collections/cerebro_recursos" \
  -H "Content-Type: application/json" \
  -d '{
    "vectors": {
      "size": 1024,
      "distance": "Cosine"
    }
  }'

# Coleccion: cerebro_chunks (un punto por chunk de contenido, usado por el RAG del chat)
curl -X PUT "$QDRANT_HOST/collections/cerebro_chunks" \
  -H "Content-Type: application/json" \
  -d '{
    "vectors": {
      "size": 1024,
      "distance": "Cosine"
    }
  }'

# Índices de payload para filtrar/agrupar rápido por tenant y recurso
curl -X PUT "$QDRANT_HOST/collections/cerebro_chunks/index" \
  -H "Content-Type: application/json" \
  -d '{"field_name": "tenant_id", "field_schema": "keyword"}'

curl -X PUT "$QDRANT_HOST/collections/cerebro_chunks/index" \
  -H "Content-Type: application/json" \
  -d '{"field_name": "recurso_id", "field_schema": "keyword"}'

echo -e "\nColecciones inicializadas exitosamente."


