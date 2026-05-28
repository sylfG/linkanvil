#!/usr/bin/env bash
# up.sh — Bootstrap idempotente de LinkAnvil sobre Docker + Compose.
# No requiere sudo (asume que install-host.sh corrió antes).
# Uso:
#   bash up.sh                                    # arranque normal interactivo
#   bash up.sh --with-telegram                    # incluye Tailscale Funnel para webhook Telegram
#   bash up.sh --public                           # expone frontend público vía Tailscale Funnel
#   bash up.sh --private                          # fuerza modo privado (sin prompt público)
#   bash up.sh --no-build                         # salta docker compose build
#   bash up.sh --no-wait                          # no espera healthchecks
#   bash up.sh --reconfigure-llm                  # reabre el prompt de proveedores LLM
#   bash up.sh --reconfigure-public               # reabre el prompt de modo público (re-pide authkey)
#   bash up.sh --print-secrets                    # imprime por pantalla los secretos generados (riesgo scrollback)
#
# Modo no interactivo (CI/Ansible/Terraform):
#   bash up.sh --non-interactive \
#              --provider nvidia \
#              --api-key  nvapi-XXXX \
#              --embedding-dim 1024
#
#   --non-interactive          desactiva prompts; usa valores por defecto + flags
#   --provider <name>          proveedor LLM primario (nvidia|openai|anthropic|gemini|mistral|cohere|groq|xai|openrouter)
#                              (puede repetirse o pasar CSV: --provider nvidia,openai)
#   --api-key <key>            API key del proveedor primario (también admite --api-key VAR=valor para múltiples)
#   --embedding-dim <N>        dimensión embeddings (default 1024)
#   --env-key KEY=VALUE        setea cualquier variable de .env (puede repetirse)
#
#   bash up.sh -h | --help
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
log()  { echo -e "${CYAN}[$(date +%H:%M:%S)]${RESET} $*"; }
ok()   { echo -e "${GREEN}✔${RESET} $*"; }
warn() { echo -e "${YELLOW}⚠${RESET}  $*"; }
fail() { echo -e "${RED}✖ ERROR:${RESET} $*" >&2; exit 1; }

WITH_TELEGRAM=false
WITH_PUBLIC_FLAG=""           # "true" / "false" / "" (preguntar)
RECONFIGURE_PUBLIC=false
DO_BUILD=true
DO_WAIT=true
RECONFIGURE_LLM=false
PRINT_SECRETS=false
NON_INTERACTIVE=false
CLI_PROVIDERS=""
CLI_EMBEDDING_DIM=""
declare -a CLI_API_KEYS=()
declare -a CLI_ENV_KEYS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --with-telegram)        WITH_TELEGRAM=true; shift ;;
        --public)               WITH_PUBLIC_FLAG=true; shift ;;
        --private)              WITH_PUBLIC_FLAG=false; shift ;;
        --reconfigure-public)   RECONFIGURE_PUBLIC=true; shift ;;
        --no-build)         DO_BUILD=false; shift ;;
        --no-wait)          DO_WAIT=false; shift ;;
        --reconfigure-llm)  RECONFIGURE_LLM=true; shift ;;
        --print-secrets)    PRINT_SECRETS=true; shift ;;
        --non-interactive)  NON_INTERACTIVE=true; shift ;;
        --provider)         [[ -z "${2:-}" ]] && fail "--provider requiere un valor"
                            CLI_PROVIDERS="$2"; shift 2 ;;
        --api-key)          [[ -z "${2:-}" ]] && fail "--api-key requiere un valor"
                            CLI_API_KEYS+=("$2"); shift 2 ;;
        --embedding-dim)    [[ -z "${2:-}" ]] && fail "--embedding-dim requiere un valor"
                            CLI_EMBEDDING_DIM="$2"; shift 2 ;;
        --env-key)          [[ -z "${2:-}" ]] && fail "--env-key requiere KEY=VALUE"
                            CLI_ENV_KEYS+=("$2"); shift 2 ;;
        -h|--help)
            sed -n '2,22p' "$0"; exit 0 ;;
        *) fail "Argumento desconocido: $1" ;;
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

# Pre-seed .env desde flags CLI antes de invocar bootstrap-env.sh
# (idempotente: solo setea si el valor actual está vacío o termina en _CHANGE_ME)
preseed_env() {
    local key="$1" value="$2"
    [[ -z "$value" ]] && return 0
    local current
    current=$(grep "^${key}=" .env 2>/dev/null | head -1 | cut -d= -f2- || echo "")
    if [[ -z "$current" || "$current" == *_CHANGE_ME ]]; then
        local escaped
        escaped=$(printf '%s' "$value" | sed -e 's/[\/&]/\\&/g')
        if grep -q "^${key}=" .env 2>/dev/null; then
            sed -i "s|^${key}=.*|${key}=${escaped}|" .env
        else
            echo "${key}=${value}" >> .env
        fi
    fi
}

if [[ -n "$CLI_PROVIDERS" ]]; then
    preseed_env LLM_PROVIDERS_PRIORITY "$CLI_PROVIDERS"
    ok "Proveedores LLM preconfigurados desde --provider: $CLI_PROVIDERS"
fi
if [[ -n "$CLI_EMBEDDING_DIM" ]]; then
    preseed_env EMBEDDINGS_DIM "$CLI_EMBEDDING_DIM"
fi
# --api-key admite formato simple "valor" (asigna a la env-var del primer proveedor del CSV)
# o formato KEY=valor (asigna explícitamente a esa variable).
for entry in "${CLI_API_KEYS[@]:-}"; do
    [[ -z "$entry" ]] && continue
    if [[ "$entry" == *=* ]]; then
        preseed_env "${entry%%=*}" "${entry#*=}"
    elif [[ -n "$CLI_PROVIDERS" ]]; then
        first_prov=$(echo "$CLI_PROVIDERS" | cut -d, -f1 | tr -d ' ')
        envvar=$(python3 -c "
import yaml
with open('infra/litellm/providers.yaml') as f:
    cat = yaml.safe_load(f)
print(cat['providers'].get('$first_prov', {}).get('env_var', ''))
")
        [[ -n "$envvar" ]] && preseed_env "$envvar" "$entry" \
            || warn "--api-key '$entry' descartado: proveedor '$first_prov' no encontrado en catalog"
    else
        warn "--api-key '$entry' descartado: usa --provider antes o el formato KEY=valor"
    fi
done
for entry in "${CLI_ENV_KEYS[@]:-}"; do
    [[ -z "$entry" ]] && continue
    [[ "$entry" == *=* ]] || { warn "--env-key debe ser KEY=VALUE, ignorando '$entry'"; continue; }
    preseed_env "${entry%%=*}" "${entry#*=}"
done

# Re-evaluar NEEDS_BOOTSTRAP tras el pre-seed CLI
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
    # NOTA: WITH_TELEGRAM/RECONFIGURE_LLM se pasan al hijo como int 1/0 sin reasignar el bool local
    WITH_TELEGRAM_INT=$( $WITH_TELEGRAM && echo 1 || echo 0 )
    RECONFIGURE_LLM_INT=$( $RECONFIGURE_LLM && echo 1 || echo 0 )
    NON_INTERACTIVE_INT=$( $NON_INTERACTIVE && echo 1 || echo 0 )
    WITH_TELEGRAM=$WITH_TELEGRAM_INT \
    RECONFIGURE_LLM=$RECONFIGURE_LLM_INT \
    NON_INTERACTIVE=$NON_INTERACTIVE_INT \
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

# ── 5b. Modo público / privado (Tailscale Funnel frontend) ──────────────────
upsert_env_key() {
    local key="$1" value="$2"
    local escaped
    escaped=$(printf '%s' "$value" | sed -e 's/[\\/&|]/\\&/g')
    if grep -q "^${key}=" .env 2>/dev/null; then
        sed -i "s|^${key}=.*|${key}=${escaped}|" .env
    else
        echo "${key}=${value}" >> .env
    fi
}

prompt_public_mode() {
    local resp existing_hostname existing_authkey
    existing_hostname=$(grep '^TS_PUBLIC_HOSTNAME=' .env 2>/dev/null | head -1 | cut -d= -f2- || echo "")
    existing_authkey=$(grep '^TS_AUTHKEY_WEB=' .env 2>/dev/null | head -1 | cut -d= -f2- || echo "")

    echo ""
    echo -e "${BOLD}━━━ Modo de despliegue ━━━${RESET}"

    if [[ -n "$existing_authkey" && -n "$existing_hostname" && "$RECONFIGURE_PUBLIC" == false ]]; then
        echo "Tailscale Funnel ya está configurado:"
        echo "  hostname: ${existing_hostname}"
        echo "  authkey:  ${existing_authkey:0:18}…"
        read -rp "¿Arrancar en modo público? [S/n]: " resp
        [[ "$resp" =~ ^[nN] ]] && return 1
        return 0
    fi

    echo ""
    echo "LinkAnvil puede levantarse en dos modos:"
    echo ""
    echo -e "  ${BOLD}privado${RESET} → solo accesible desde la red interna del host (default)."
    echo -e "  ${BOLD}público${RESET}  → frontend expuesto vía Tailscale Funnel en"
    echo "            https://<hostname>.<tu-tailnet>.ts.net (HTTPS automático)."
    echo "            Requiere un authkey de Tailscale."
    echo ""

    read -rp "¿Modo público? [s/N]: " resp
    [[ ! "$resp" =~ ^[sSyY] ]] && return 1

    echo ""
    echo "Genera un authkey en: https://login.tailscale.com/admin/settings/keys"
    echo "  · Reusable: ON   · Ephemeral: OFF"
    echo ""

    local new_hostname new_authkey
    local default_hostname="${existing_hostname:-linkanvil}"
    read -rp "Hostname Tailscale (sin .ts.net) [${default_hostname}]: " new_hostname
    new_hostname="${new_hostname:-$default_hostname}"

    while true; do
        read -rp "Authkey (tskey-...): " new_authkey
        if [[ "$new_authkey" =~ ^tskey- ]]; then
            break
        fi
        warn "Formato inválido — debe empezar por 'tskey-'."
    done

    upsert_env_key "TS_PUBLIC_HOSTNAME" "$new_hostname"
    upsert_env_key "TS_AUTHKEY_WEB" "$new_authkey"
    ok "TS_PUBLIC_HOSTNAME y TS_AUTHKEY_WEB guardados en .env"
    return 0
}

WITH_PUBLIC=false
if [[ "$WITH_PUBLIC_FLAG" == "true" ]]; then
    existing_hostname=$(grep '^TS_PUBLIC_HOSTNAME=' .env 2>/dev/null | head -1 | cut -d= -f2- || echo "")
    existing_authkey=$(grep '^TS_AUTHKEY_WEB=' .env 2>/dev/null | head -1 | cut -d= -f2- || echo "")
    if [[ -z "$existing_hostname" || -z "$existing_authkey" ]]; then
        if [[ "$NON_INTERACTIVE" == true ]]; then
            fail "--public requiere TS_PUBLIC_HOSTNAME y TS_AUTHKEY_WEB en .env (modo non-interactive)."
        fi
        prompt_public_mode && WITH_PUBLIC=true
    else
        WITH_PUBLIC=true
        ok "Modo público activado (config existente en .env)"
    fi
elif [[ "$WITH_PUBLIC_FLAG" == "false" ]]; then
    WITH_PUBLIC=false
    log "Modo privado forzado (--private)"
elif [[ "$NON_INTERACTIVE" == true ]]; then
    WITH_PUBLIC=false
    log "Modo privado (default en non-interactive)"
else
    prompt_public_mode && WITH_PUBLIC=true
fi

# ── 6. Up ────────────────────────────────────────────────────────────────────
log "Levantando servicios..."
COMPOSE_ARGS=()
$WITH_TELEGRAM && COMPOSE_ARGS+=(--profile telegram)
$WITH_PUBLIC   && COMPOSE_ARGS+=(--profile public)
docker compose "${COMPOSE_ARGS[@]}" up -d
profiles_msg=""
$WITH_TELEGRAM && profiles_msg+=" telegram"
$WITH_PUBLIC   && profiles_msg+=" public"
ok "Servicios iniciados${profiles_msg:+ (perfiles:${profiles_msg})}"

# Si el config de LiteLLM cambió, force-recreate solo ese servicio para recargar.
if $LITELLM_CONFIG_CHANGED; then
    log "Config LiteLLM cambió — recreando cerebro-litellm..."
    docker compose "${COMPOSE_ARGS[@]}" up -d --force-recreate litellm
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

# ── 7b. URL pública (si modo público) ───────────────────────────────────────
if $WITH_PUBLIC; then
    log "Esperando a que Tailscale Funnel registre el nodo (~10 s)..."
    sleep 10
    funnel_url=$(docker logs cerebro-tailscale-web 2>&1 | grep -oE 'https://[a-zA-Z0-9.-]+\.ts\.net' | head -1 || true)
    echo ""
    if [[ -n "$funnel_url" ]]; then
        echo -e "${GREEN}${BOLD}🌐 URL pública:${RESET}  ${funnel_url}"
    else
        warn "No se pudo extraer la URL Funnel del log del sidecar."
        warn "Revisa: docker logs cerebro-tailscale-web"
    fi
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

# ── 9. Resumen de secretos auto-generados ───────────────────────────────────
# bootstrap-env.sh ha dejado en .secrets-generated.txt SOLO los secretos
# que generó en esta corrida (las claves ya presentes en .env no se tocan).
# Por defecto NO los imprimimos en pantalla: el scrollback del terminal y
# los logs SSH son superficie de fuga. Se muestra ruta + comando, con
# `--print-secrets` el operador acepta el riesgo explícitamente.
SECRETS_FILE=".secrets-generated.txt"
if [[ -s "$SECRETS_FILE" ]]; then
    echo -e "${BOLD}━━━━━━━━━━━━━ SECRETOS AUTO-GENERADOS ━━━━━━━━━━━━━${RESET}"
    n_secrets=$(wc -l < "$SECRETS_FILE" | tr -d ' ')
    echo -e "  Se generaron ${BOLD}${n_secrets}${RESET} secretos en esta corrida."
    echo -e "  Archivo: ${CYAN}$(pwd)/${SECRETS_FILE}${RESET}  (chmod 600, en .gitignore)"
    echo ""
    if $PRINT_SECRETS; then
        warn "Imprimiendo secretos en pantalla (--print-secrets). El scrollback los retendrá."
        echo ""
        # Los rotulamos en amarillo para que sean visualmente "tóxicos".
        while IFS='=' read -r k v; do
            echo -e "  ${YELLOW}${k}${RESET}=${v}"
        done < "$SECRETS_FILE"
        echo ""
        echo -e "  ${YELLOW}↑ Guárdalos en un gestor (1Password/Bitwarden/Vault) y limpia el scrollback:${RESET}"
        echo -e "  ${CYAN}history -c && clear${RESET}"
    else
        echo -e "  Para verlos una vez: ${CYAN}sudo cat ${SECRETS_FILE}${RESET}"
        echo -e "  Para imprimirlos en pantalla en futuros arranques: ${CYAN}bash up.sh --print-secrets${RESET}"
        echo -e "  ${YELLOW}Recomendación:${RESET} copia los que necesites a un gestor de secretos y borra el archivo:"
        echo -e "  ${CYAN}shred -u ${SECRETS_FILE}${RESET}   (o ${CYAN}rm -f ${SECRETS_FILE}${RESET})"
    fi
    echo ""
fi
