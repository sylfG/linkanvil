#!/usr/bin/env bash
# wait-healthy.sh — Espera a que los servicios con healthcheck estén "healthy".
# Uso:
#   bash scripts/wait-healthy.sh                  # poll hasta 180s
#   bash scripts/wait-healthy.sh --timeout=300    # ajustar timeout
#   bash scripts/wait-healthy.sh --once           # imprime estado actual y sale
# Exit:
#   0 → todos healthy
#   1 → timeout o algún servicio unhealthy/missing
set -euo pipefail

TIMEOUT=180
ONCE=false

for arg in "$@"; do
    case "$arg" in
        --timeout=*) TIMEOUT="${arg#*=}" ;;
        --once)      ONCE=true ;;
        -h|--help)
            sed -n '2,9p' "$0"; exit 0 ;;
        *) echo "Argumento desconocido: $arg" >&2; exit 2 ;;
    esac
done

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; RESET='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"

# Servicios con healthcheck (los one-shot terminan en Exited(0), no se vigilan).
SERVICES_WITH_HC=(
    cerebro-traefik
    cerebro-rabbitmq
    cerebro-redis
    cerebro-postgres
    cerebro-qdrant
    cerebro-litellm
    cerebro-api
    cerebro-ingestion
    cerebro-scraper
    cerebro-outbox
    cerebro-notifier
    cerebro-embedder
    cerebro-web
    cerebro-prometheus
    cerebro-grafana
    cerebro-jaeger
    cerebro-n8n
    cerebro-redis-exporter
    cerebro-postgres-exporter
)

check_once() {
    local all_healthy=true
    local not_ready=()
    for svc in "${SERVICES_WITH_HC[@]}"; do
        local status
        status=$(docker inspect --format='{{.State.Health.Status}}' "$svc" 2>/dev/null || echo "missing")
        if [[ "$status" != "healthy" ]]; then
            all_healthy=false
            not_ready+=("$svc($status)")
        fi
    done
    if $all_healthy; then
        echo "ok"
    else
        printf '%s\n' "${not_ready[@]}"
    fi
}

if $ONCE; then
    result=$(check_once)
    if [[ "$result" == "ok" ]]; then
        echo -e "${GREEN}✔ Todos los servicios healthy${RESET}"
        exit 0
    else
        echo -e "${YELLOW}⚠ No healthy:${RESET}"
        echo "$result" | sed 's/^/  /'
        exit 1
    fi
fi

INTERVAL=5
ELAPSED=0

while [[ $ELAPSED -lt $TIMEOUT ]]; do
    result=$(check_once)
    if [[ "$result" == "ok" ]]; then
        printf '\r%*s\r' 100 ''
        echo -e "${GREEN}✔ Todos los servicios healthy${RESET} (en ${ELAPSED}s)"
        exit 0
    fi
    not_ready_line=$(echo "$result" | tr '\n' ' ')
    printf "\r${CYAN}[%ds/%ds]${RESET} esperando: %.90s" "$ELAPSED" "$TIMEOUT" "$not_ready_line"
    sleep $INTERVAL
    ELAPSED=$((ELAPSED + INTERVAL))
done

echo ""
echo -e "${RED}✖ Timeout tras ${TIMEOUT}s${RESET}"
echo "Servicios no healthy:"
check_once | sed 's/^/  /'
exit 1
