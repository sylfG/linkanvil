#!/bin/sh
# init_qdrant.sh — Inicializa colecciones base en Qdrant (F-00.6).
# Dim-aware: si la colección ya existe con otra dimensión, la borra y recrea.
# Variables:
#   $1 (arg)         → host base, default http://localhost:6333
#   EMBEDDINGS_DIM   → dimensión del vector (default 1024)
set -e

QDRANT_HOST="${1:-http://localhost:6333}"
DIM="${EMBEDDINGS_DIM:-1024}"

echo "Inicializando colecciones en Qdrant ($QDRANT_HOST) con dim=$DIM..."

ensure_collection() {
    name="$1"
    existing=$(curl -s -o /dev/null -w "%{http_code}" "$QDRANT_HOST/collections/$name")
    if [ "$existing" = "200" ]; then
        current_dim=$(curl -s "$QDRANT_HOST/collections/$name" \
            | sed -n 's/.*"size":\s*\([0-9]*\).*/\1/p' | head -1)
        if [ "$current_dim" = "$DIM" ]; then
            echo "  ✔ $name ya existe con dim=$DIM"
            return 0
        else
            echo "  ⚠ $name existe con dim=$current_dim — borrando para recrear con dim=$DIM (destructivo)" >&2
            curl -s -X DELETE "$QDRANT_HOST/collections/$name" >/dev/null
        fi
    fi

    echo "  → creando $name (dim=$DIM, cosine)"
    curl -s -X PUT "$QDRANT_HOST/collections/$name" \
        -H "Content-Type: application/json" \
        -d "{\"vectors\":{\"size\":$DIM,\"distance\":\"Cosine\"}}" >/dev/null
}

ensure_collection cerebro_recursos
ensure_collection cerebro_chunks

# Índices de payload para filtrar/agrupar rápido por tenant y recurso.
# PUT /index es idempotente — Qdrant devuelve 200 si ya existe.
curl -s -X PUT "$QDRANT_HOST/collections/cerebro_chunks/index" \
    -H "Content-Type: application/json" \
    -d '{"field_name":"tenant_id","field_schema":"keyword"}' >/dev/null

curl -s -X PUT "$QDRANT_HOST/collections/cerebro_chunks/index" \
    -H "Content-Type: application/json" \
    -d '{"field_name":"recurso_id","field_schema":"keyword"}' >/dev/null

echo "Colecciones inicializadas exitosamente (dim=$DIM)."
