#!/usr/bin/env bash
# up.sh — Bootstrap idempotente de LinkAnvil sobre Docker + Compose.
# No requiere sudo (asume que install-host.sh corrió antes).
# Uso:
#   bash up.sh                       # arranque normal (perfil core)
#   bash up.sh --with-telegram       # incluye Tailscale Funnel (perfil telegram)
#   bash up.sh --no-build            # salta docker compose build
#   bash up.sh --no-wait             # no espera healthchecks
#   bash up.sh --reconfigure-llm     # reabre el prompt de proveedores LLM
#   bash up.sh -h | --help
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
log()  { echo -e "${CYAN}[$(date +%H:%M:%S)]${RESET} $*"; }
ok()   { echo -e "${GREEN}✔${RESET} $*"; }
warn() { echo -e "${YELLOW}⚠${RESET}  $*"; }
fail() { echo -e "${RED}✖ ERROR:${RESET} $*" >&2; exit 1; }

WITH_TELEGRAM=false
DO_BUILD=true
DO_WAIT=true
RECONFIGURE_LLM=false

for arg in "$@"; do
    case "$arg" in
        --with-telegram)   WITH_TELEGRAM=true ;;
        --no-build)        DO_BUILD=false ;;
        --no-wait)         DO_WAIT=false ;;
        --reconfigure-llm) RECONFIGURE_LLM=true ;;
        -h|--help)
            sed -n '2,10p' "$0"; exit 0 ;;
        *) fail "Argumento desconocido: $arg" ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── 0. Prerequisitos ────────────────────────────────────────────────────────
[[ -f docker-compose.yml ]] || fail "No se encontró docker-compose.yml. Estás en $PWD."
command -v docker >/dev/null 2>&1 || fail "docker no disponible. Ejecuta: sudo bash install-host.sh"
docker info >/dev/null 2>&1 || fail "Docker daemon no responde. ¿Pertenece tu usuario al grupo docker? Prueba 'newgrp docker'."
docker compose version >/dev/null 2>&1 || fail "docker compose plugin no disponible."

echo ""
echo -e "${BOLD}╔══════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}║      LinkAnvil — Bootstrap                ║${RESET}"
echo -e "${BOLD}╚══════════════════════════════════════════╝${RESET}"
echo ""

# ── 1. .env ──────────────────────────────────────────────────────────────────
if [[ ! -f .env ]]; then
    log "Copiando .env.example → .env"
    cp .env.example .env
    ok ".env creado"
fi

# Migración silenciosa: .env antiguo con solo NVIDIA_API_KEY → multi-provider
priority_in_env=$(grep '^LLM_PROVIDERS_PRIORITY=' .env 2>/dev/null | head -1 | cut -d= -f2- || echo "")
nvidia_in_env=$(grep '^NVIDIA_API_KEY=' .env 2>/dev/null | head -1 | cut -d= -f2- || echo "")
if [[ -z "$priority_in_env" && -n "$nvidia_in_env" ]]; then
    log "Migrando .env antiguo a formato multi-provider..."
    # Si ni siquiera existe la línea, añadirla; si existe vacía, fijarla
    if grep -q '^LLM_PROVIDERS_PRIORITY=' .env; then
        sed -i 's|^LLM_PROVIDERS_PRIORITY=.*|LLM_PROVIDERS_PRIORITY=nvidia|' .env
    else
        echo 'LLM_PROVIDERS_PRIORITY=nvidia' >> .env
    fi
    grep -q '^EMBEDDINGS_PROVIDER=' .env || echo 'EMBEDDINGS_PROVIDER=auto' >> .env
    grep -q '^EMBEDDINGS_DIM=' .env || echo 'EMBEDDINGS_DIM=1024' >> .env
    ok ".env migrado (LLM_PROVIDERS_PRIORITY=nvidia)"
fi

# Detectar placeholders y rellenar
NEEDS_BOOTSTRAP=false
for var in POSTGRES_PASSWORD REDIS_PASSWORD RABBITMQ_PASS LITELLM_MASTER_KEY \
           JWT_SECRET LLM_KEYS_ENCRYPTION_KEY N8N_PASSWORD GRAFANA_PASSWORD AUDIT_CRON_TOKEN \
           LLM_PROVIDERS_PRIORITY; do
    val=$(grep "^${var}=" .env 2>/dev/null | head -1 | cut -d= -f2- || echo "")
    if [[ -z "$val" || "$val" == *_CHANGE_ME ]]; then
        NEEDS_BOOTSTRAP=true
        break
    fi
done

if $NEEDS_BOOTSTRAP || $RECONFIGURE_LLM; then
    log "Completando .env (secretos auto-generables + prompts mínimos)..."
    export WITH_TELEGRAM=$( $WITH_TELEGRAM && echo 1 || echo 0 )
    export RECONFIGURE_LLM=$( $RECONFIGURE_LLM && echo 1 || echo 0 )
    bash scripts/bootstrap-env.sh
else
    ok ".env ya tiene todas las claves críticas"
fi

# Aviso si el proveedor primario sigue sin API key
primary=$(grep '^LLM_PROVIDERS_PRIORITY=' .env | head -1 | cut -d= -f2- | cut -d, -f1 | tr -d ' ')
if [[ -n "$primary" ]]; then
    envvar=$(python3 -c "
import yaml
with open('infra/litellm/providers.yaml') as f:
    cat = yaml.safe_load(f)
print(cat['providers'].get('$primary', {}).get('env_var', ''))
")
    if [[ -n "$envvar" ]]; then
        primary_key=$(grep "^${envvar}=" .env | head -1 | cut -d= -f2-)
        [[ -z "$primary_key" ]] && warn "$envvar vacía — el proveedor primario ($primary) no responderá."
    fi
fi

# ── 2. Aviso mirror Docker Hub (solo informativo) ───────────────────────────
if [[ ! -f /etc/docker/daemon.json ]] || ! grep -q "mirror.gcr.io" /etc/docker/daemon.json 2>/dev/null; then
    warn "Mirror Docker Hub no configurado. Si los pulls fallan: sudo bash reset.sh (configura mirror)."
fi

# ── 3. Hash RabbitMQ ────────────────────────────────────────────────────────
log "Sincronizando hash RabbitMQ con .env..."
bash scripts/regen-rabbitmq-hash.sh

# ── 3b. Render config LiteLLM desde .env ────────────────────────────────────
log "Renderizando config de LiteLLM..."
set +e
python3 scripts/render-litellm-config.py
RENDER_RC=$?
set -e
case $RENDER_RC in
    0) LITELLM_CONFIG_CHANGED=false ;;
    2) LITELLM_CONFIG_CHANGED=true ;;
    *) fail "render-litellm-config.py falló (exit=$RENDER_RC). Revisa LLM_PROVIDERS_PRIORITY y las API keys en .env." ;;
esac

# ── 4. Pull imágenes externas (idempotente) ─────────────────────────────────
log "Pull de imágenes externas..."
docker compose pull --ignore-buildable 2>&1 | grep -Ei '(pull|already|error)' || true
ok "Pull completado"

# ── 5. Build imágenes locales ───────────────────────────────────────────────
if $DO_BUILD; then
    log "Build de imágenes locales..."
    docker compose build --parallel
    ok "Build completado"
else
    warn "Skip build (--no-build)"
fi

# ── 6. Up ────────────────────────────────────────────────────────────────────
log "Levantando servicios..."
COMPOSE_ARGS=()
$WITH_TELEGRAM && COMPOSE_ARGS+=(--profile telegram)
docker compose "${COMPOSE_ARGS[@]}" up -d
ok "Servicios iniciados$( $WITH_TELEGRAM && echo ' (perfil: telegram)' )"

# Si el config de LiteLLM cambió, force-recreate solo ese servicio para recargar.
if $LITELLM_CONFIG_CHANGED; then
    log "Config LiteLLM cambió — recreando cerebro-litellm..."
    docker compose "${COMPOSE_ARGS[@]}" up -d --force-recreate cerebro-litellm
fi

# ── 7. Healthchecks ─────────────────────────────────────────────────────────
if $DO_WAIT; then
    echo ""
    log "Esperando healthchecks..."
    if bash scripts/wait-healthy.sh --timeout=240; then
        :
    else
        warn "Algunos servicios no quedaron healthy. Revisa: docker compose ps"
        warn "Logs: docker compose logs <servicio>"
    fi
else
    warn "Skip wait (--no-wait)"
fi

# ── 8. Resumen ──────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}━━━━━━━━━━━━━━━━ ENDPOINTS ━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "  Frontend      → http://localhost:3001"
echo -e "  API docs      → http://localhost:8001/docs"
echo -e "  n8n           → http://localhost:5678"
echo -e "  Grafana       → http://localhost:3000"
echo -e "  Jaeger        → http://localhost:16686"
echo -e "  RabbitMQ Mgmt → http://localhost:15672"
echo -e "  Qdrant        → http://localhost:6333/dashboard"
echo ""
if [[ "$(grep '^SEED_DEMO=' .env | cut -d= -f2-)" == "true" ]]; then
    echo -e "${BOLD}Demo:${RESET} demo@linkanvil.io / linkanvil-demo"
    echo ""
fi
echo -e "${BOLD}Útiles:${RESET}"
echo -e "  ${CYAN}make ps${RESET}              # estado runtime"
echo -e "  ${CYAN}make ps-oneshot${RESET}      # estado init containers"
echo -e "  ${CYAN}make health${RESET}          # health rápido"
echo -e "  ${CYAN}bash scripts/wait-healthy.sh --once${RESET}"
echo ""
