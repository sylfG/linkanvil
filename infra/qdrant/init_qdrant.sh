#!/bin/bash
# init_qdrant.sh - Script para inicializar colecciones base en Qdrant (F-00.6)

set -e

QDRANT_HOST=${1:-"http://localhost:6333"}

echo "Inicializando colecciones en Qdrant ($QDRANT_HOST)..."

# Coleccion: cerebro_recursos
curl -X PUT "$QDRANT_HOST/collections/cerebro_recursos" \
  -H "Content-Type: application/json" \
  -d '{
    "vectors": {
      "size": 1536,
      "distance": "Cosine"
    }
  }'

echo -e "\nColecciones inicializadas exitosamente."


