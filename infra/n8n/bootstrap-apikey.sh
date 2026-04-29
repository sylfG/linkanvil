#!/usr/bin/env bash
# Genera una API key en n8n y la escribe en .env.
# Uso: bash infra/n8n/bootstrap-apikey.sh
# Prerequisito: stack levantado con docker compose up -d

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../../.env"
N8N_URL="${N8N_URL:-http://localhost:5678}"
N8N_USER="${N8N_USER:-admin}"
N8N_PASSWORD="${N8N_PASSWORD:-}"

# ---------------------------------------------------------------------------
# Carga .env si aún no está exportado
# ---------------------------------------------------------------------------
if [[ -f "$ENV_FILE" && -z "$N8N_PASSWORD" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

if [[ -z "$N8N_PASSWORD" ]]; then
  echo "ERROR: N8N_PASSWORD no definido. Carga el .env o exporta la variable." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Espera a que n8n esté operativo (máx. 90s)
# ---------------------------------------------------------------------------
echo "Esperando a que n8n esté listo en $N8N_URL ..."
TIMEOUT=90
ELAPSED=0
until curl -sf "$N8N_URL/healthz" > /dev/null 2>&1; do
  if [[ $ELAPSED -ge $TIMEOUT ]]; then
    echo "ERROR: n8n no respondió en ${TIMEOUT}s." >&2
    exit 1
  fi
  sleep 3
  ELAPSED=$((ELAPSED + 3))
done
echo "n8n listo."

# ---------------------------------------------------------------------------
# Elimina keys previas con la etiqueta 'claude-mcp' para evitar duplicados
# ---------------------------------------------------------------------------
EXISTING=$(curl -sf "$N8N_URL/api/v1/api-key" \
  -u "${N8N_USER}:${N8N_PASSWORD}" 2>/dev/null || echo "[]")

if command -v python3 &>/dev/null; then
  OLD_ID=$(echo "$EXISTING" | python3 -c "
import sys, json
keys = json.load(sys.stdin)
ids = [k['id'] for k in (keys if isinstance(keys, list) else []) if k.get('label') == 'claude-mcp']
print(ids[0] if ids else '')
" 2>/dev/null || true)
  if [[ -n "$OLD_ID" ]]; then
    curl -sf -X DELETE "$N8N_URL/api/v1/api-key/$OLD_ID" \
      -u "${N8N_USER}:${N8N_PASSWORD}" > /dev/null
    echo "Key anterior eliminada (id: $OLD_ID)."
  fi
fi

# ---------------------------------------------------------------------------
# Crea la nueva API key
# ---------------------------------------------------------------------------
RESPONSE=$(curl -sf -X POST "$N8N_URL/api/v1/api-key" \
  -u "${N8N_USER}:${N8N_PASSWORD}" \
  -H "Content-Type: application/json" \
  -d '{"label":"claude-mcp"}')

API_KEY=$(echo "$RESPONSE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(data.get('apiKey') or data.get('api_key') or '')
")

if [[ -z "$API_KEY" ]]; then
  echo "ERROR: No se pudo extraer la API key. Respuesta:" >&2
  echo "$RESPONSE" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Escribe la key en .env (crea la línea si no existe)
# ---------------------------------------------------------------------------
if grep -q "^N8N_API_KEY=" "$ENV_FILE" 2>/dev/null; then
  sed -i "s|^N8N_API_KEY=.*|N8N_API_KEY=$API_KEY|" "$ENV_FILE"
else
  echo "N8N_API_KEY=$API_KEY" >> "$ENV_FILE"
fi

echo "API key guardada en .env"
echo "  N8N_API_KEY=$API_KEY"
echo ""
echo "Recarga el entorno antes de usar Claude:"
echo "  set -a && source .env && set +a"
