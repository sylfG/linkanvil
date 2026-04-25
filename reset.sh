#!/usr/bin/env bash
# reset.sh — Limpieza total y relanzamiento de LinkAnvil
# Uso: bash reset.sh [--keep-images]   (--keep-images omite el pull de imágenes externas)
set -euo pipefail

# ── Colores ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

log()  { echo -e "${CYAN}[$(date +%H:%M:%S)]${RESET} $*"; }
ok()   { echo -e "${GREEN}✔${RESET} $*"; }
warn() { echo -e "${YELLOW}⚠${RESET}  $*"; }
fail() { echo -e "${RED}✖ ERROR:${RESET} $*" >&2; exit 1; }

KEEP_IMAGES=false
[[ "${1:-}" == "--keep-images" ]] && KEEP_IMAGES=true

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

[[ -f docker-compose.yml ]] || fail "No se encontró docker-compose.yml en $SCRIPT_DIR"
[[ -f .env ]]               || fail "No se encontró .env — copia .env.example y configúralo"

# ── 0. Asegurar mirror de Docker Hub (evita MITM proxy con cert inválido) ────
log "Verificando mirror de Docker Hub..."
DAEMON_CFG=/etc/docker/daemon.json
if ! grep -q "mirror.gcr.io" "$DAEMON_CFG" 2>/dev/null; then
    warn "Configurando mirror.gcr.io en Docker daemon (requiere sudo)..."
    echo '{"registry-mirrors":["https://mirror.gcr.io"]}' > "$DAEMON_CFG"
    systemctl restart docker
    sleep 5
    ok "Mirror configurado y Docker reiniciado"
else
    ok "Mirror mirror.gcr.io ya configurado"
fi

echo ""
echo -e "${BOLD}╔══════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}║      LinkAnvil — Reset & Relaunch        ║${RESET}"
echo -e "${BOLD}╚══════════════════════════════════════════╝${RESET}"
echo ""

# ── 1. Parar y eliminar contenedores + redes ─────────────────────────────────
log "Parando contenedores y eliminando redes..."
docker compose down --remove-orphans 2>/dev/null || true
ok "Contenedores y redes eliminados"

# ── 2. Eliminar volúmenes del proyecto ───────────────────────────────────────
log "Eliminando volúmenes del proyecto..."
VOLUMES=$(docker volume ls --filter "name=linkanvil_" --format "{{.Name}}")
if [[ -n "$VOLUMES" ]]; then
    echo "$VOLUMES" | xargs docker volume rm
    ok "Volúmenes eliminados: $(echo "$VOLUMES" | wc -l | tr -d ' ')"
else
    warn "No se encontraron volúmenes del proyecto"
fi

# ── 3. Eliminar imágenes construidas localmente ───────────────────────────────
log "Eliminando imágenes construidas (linkanvil-*)..."
BUILT_IMAGES=$(docker images --filter "reference=linkanvil-*" --format "{{.ID}}" | sort -u)
if [[ -n "$BUILT_IMAGES" ]]; then
    echo "$BUILT_IMAGES" | xargs docker rmi -f 2>/dev/null || true
    ok "Imágenes locales eliminadas"
else
    warn "No se encontraron imágenes construidas localmente"
fi

# ── 4. Eliminar imágenes externas (pull fresco) ───────────────────────────────
if [[ "$KEEP_IMAGES" == false ]]; then
    log "Eliminando imágenes externas para forzar pull fresco..."
    EXTERNAL_IMAGES=(
        "traefik:v3.6.14"
        "rabbitmq:3.13-management-alpine"
        "redis/redis-stack-server:latest"
        "postgres:16-alpine"
        "qdrant/qdrant:v1.17.1"
        "ghcr.io/berriai/litellm:main-latest"
        "n8nio/n8n:1.123.37"
        "python:3.12-alpine"
        "jaegertracing/all-in-one:latest"
        "otel/opentelemetry-collector-contrib:0.150.1"
        "prom/prometheus:v3.11.2"
        "grafana/grafana:11.4.0"
        "kbudde/rabbitmq-exporter:latest"
        "oliver006/redis_exporter:v1.82.0-alpine"
        "prometheuscommunity/postgres-exporter:v0.19.1"
    )
    for img in "${EXTERNAL_IMAGES[@]}"; do
        docker rmi "$img" 2>/dev/null && echo "  removed $img" || true
    done
    ok "Imágenes externas eliminadas"
else
    warn "Modo --keep-images: se omite la eliminación de imágenes externas"
fi

# ── 5. Limpiar builder cache ──────────────────────────────────────────────────
log "Limpiando build cache de Docker..."
docker builder prune -f --filter "until=1h" 2>/dev/null || true
ok "Build cache limpiado"

# ── 6. Pull de imágenes externas ─────────────────────────────────────────────
log "Descargando imágenes externas actualizadas..."
docker compose pull --ignore-buildable 2>&1 | grep -E "Pull|pull|already|error" || true
ok "Pull completado"

# ── 7. Build de imágenes locales ─────────────────────────────────────────────
log "Construyendo imágenes locales (--no-cache)..."
docker compose build --no-cache --parallel
ok "Build completado"

# ── 8. Actualizar hash de contraseña RabbitMQ en definitions.json ────────────
log "Actualizando hash de contraseña RabbitMQ..."
RABBIT_PASS=$(grep ^RABBITMQ_PASS .env | cut -d= -f2)
NEW_HASH=$(python3 - "$RABBIT_PASS" << 'PYEOF'
import sys, hashlib, os, base64
p = sys.argv[1].encode()
s = os.urandom(4)
print(base64.b64encode(s + hashlib.sha256(s + p).digest()).decode())
PYEOF
)
# Reemplazar el hash en definitions.json
python3 -c "
import json, sys
with open('infra/rabbitmq/definitions.json') as f:
    d = json.load(f)
for u in d.get('users', []):
    if u['name'] == 'cerebro':
        u['password_hash'] = sys.argv[1]
with open('infra/rabbitmq/definitions.json', 'w') as f:
    json.dump(d, f, indent=2)
" "$NEW_HASH"
ok "Hash RabbitMQ actualizado"

# ── 9. Levantar todos los servicios ──────────────────────────────────────────
log "Levantando todos los servicios..."
docker compose up -d
ok "Servicios iniciados"

# ── 10. Esperar a que los health checks pasen ────────────────────────────────
log "Esperando health checks (máx 3 minutos)..."
echo ""

SERVICES_WITH_HC=(
    "cerebro-traefik"
    "cerebro-rabbitmq"
    "cerebro-redis"
    "cerebro-postgres"
    "cerebro-litellm"
    "cerebro-api"
    "cerebro-prometheus"
    "cerebro-grafana"
    "cerebro-jaeger"
    "cerebro-n8n"
)

TIMEOUT=180
INTERVAL=5
ELAPSED=0
ALL_HEALTHY=false

while [[ $ELAPSED -lt $TIMEOUT ]]; do
    ALL_HEALTHY=true
    NOT_READY=()

    for svc in "${SERVICES_WITH_HC[@]}"; do
        STATUS=$(docker inspect --format='{{.State.Health.Status}}' "$svc" 2>/dev/null || echo "missing")
        if [[ "$STATUS" != "healthy" ]]; then
            ALL_HEALTHY=false
            NOT_READY+=("$svc($STATUS)")
        fi
    done

    if [[ "$ALL_HEALTHY" == true ]]; then
        break
    fi

    printf "\r  Esperando: %s   [%ds/%ds]    " "${NOT_READY[*]}" "$ELAPSED" "$TIMEOUT"
    sleep $INTERVAL
    ELAPSED=$((ELAPSED + INTERVAL))
done

echo ""

# ── 11. Reporte final ─────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}━━━━━━━━━━━━━━━━ ESTADO FINAL ━━━━━━━━━━━━━━━━${RESET}"
echo ""

docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Image}}" | \
    awk 'NR==1 {print} NR>1 {
        if ($0 ~ /healthy/) printf "\033[0;32m✔\033[0m  %s\n", $0
        else if ($0 ~ /unhealthy/) printf "\033[0;31m✖\033[0m  %s\n", $0
        else if ($0 ~ /Up/) printf "\033[1;33m~\033[0m  %s\n", $0
        else printf "   %s\n", $0
    }'

echo ""
echo -e "${BOLD}━━━━━━━━━━━━━━━━ ENDPOINTS ━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "  Frontend      → http://localhost:3001"
echo -e "  API           → http://localhost:8001/docs"
echo -e "  n8n           → http://localhost:5678"
echo -e "  LiteLLM       → http://localhost:4000"
echo -e "  Grafana       → http://localhost:3000"
echo -e "  Prometheus    → http://localhost:9090"
echo -e "  Jaeger UI     → http://localhost:16686"
echo -e "  Traefik Dash  → http://localhost:8080"
echo -e "  RabbitMQ Mgmt → http://localhost:15672"
echo -e "  Qdrant        → http://localhost:6333/dashboard"
echo ""

if [[ "$ALL_HEALTHY" == true ]]; then
    echo -e "${GREEN}${BOLD}✔ Reset completado — todos los servicios healthy${RESET}"
else
    echo -e "${YELLOW}${BOLD}⚠ Reset completado con advertencias — algunos servicios aún no están healthy${RESET}"
    echo -e "  Ejecuta: ${CYAN}docker ps${RESET} para ver el estado actual"
fi

echo ""
