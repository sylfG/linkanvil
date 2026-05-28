#!/usr/bin/env bash
# bootstrap-env.sh — Completa .env con secretos auto-generados y prompts mínimos.
# Idempotente: solo toca líneas con valor vacío o terminadas en _CHANGE_ME.
# Uso:
#   bash scripts/bootstrap-env.sh                 # modo interactivo
#   WITH_TELEGRAM=1 bash scripts/bootstrap-env.sh # también pide TS_AUTHKEY
#   NON_INTERACTIVE=1 bash scripts/bootstrap-env.sh  # no prompts (deja vacíos)
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"

[[ -f .env ]] || { echo -e "${RED}✖ No existe .env. Copia .env.example primero.${RESET}" >&2; exit 1; }

WITH_TELEGRAM="${WITH_TELEGRAM:-0}"
NON_INTERACTIVE="${NON_INTERACTIVE:-0}"
RECONFIGURE_LLM="${RECONFIGURE_LLM:-0}"

# Backup
cp .env .env.bak
echo -e "${CYAN}ℹ Backup creado: .env.bak${RESET}"

# ─── Helpers ────────────────────────────────────────────────────────────────
needs_value() {
    # Devuelve 0 (true) si la variable está vacía o el valor sigue siendo
    # un placeholder de .env.example (acaba en CHANGE_ME, con guion o
    # underscore como separador para tolerar ambos estilos).
    local var="$1"
    local current
    current=$(grep "^${var}=" .env | head -1 | cut -d= -f2-)
    [[ -z "$current" || "$current" == *CHANGE_ME ]] && return 0
    return 1
}

set_value() {
    # Reemplaza la línea VAR=... preservando el resto del archivo.
    local var="$1" value="$2"
    # Escapar caracteres especiales para sed
    local escaped
    escaped=$(printf '%s' "$value" | sed -e 's/[\/&]/\\&/g')
    # GNU sed in-place; en BSD/macOS habría que usar -i ''
    sed -i "s|^${var}=.*|${var}=${escaped}|" .env
}

gen_password() {
    openssl rand -base64 "${1:-24}" | tr -d '/=+' | cut -c1-"${2:-32}"
}

gen_hex() {
    openssl rand -hex "${1:-32}"
}

gen_fernet() {
    if python3 -c "from cryptography.fernet import Fernet" 2>/dev/null; then
        python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    else
        # Fallback: Fernet exige 32 bytes URL-safe base64 (44 chars con padding)
        openssl rand 32 | base64 | tr '/+' '_-' | tr -d '\n'
        echo
    fi
}

# ─── Tier 2: auto-generables ────────────────────────────────────────────────
declare -A AUTO_VARS=(
    [POSTGRES_PASSWORD]="password:24:32"
    [REDIS_PASSWORD]="password:24:32"
    [RABBITMQ_PASS]="password:24:32"
    [RABBITMQ_ERLANG_COOKIE]="hex:32"
    [N8N_PASSWORD]="password:18:24"
    [GRAFANA_PASSWORD]="password:18:24"
    [JWT_SECRET]="hex:32"
    [AUDIT_CRON_TOKEN]="hex:32"
    [LITELLM_MASTER_KEY]="litellm"
    [LLM_KEYS_ENCRYPTION_KEY]="fernet"
)

# Fichero de "transcript" de secretos generados en esta corrida. Lo
# consume up.sh al final para mostrar la ruta al operador. chmod 600 →
# solo root (el operador del script). Está en .gitignore.
SECRETS_OUT="${SECRETS_OUT:-$SCRIPT_DIR/.secrets-generated.txt}"
# Reset por corrida: cada bootstrap empieza con un transcript vacío.
: > "$SECRETS_OUT"
chmod 600 "$SECRETS_OUT" 2>/dev/null || true

echo -e "${BOLD}━━ Rellenando secretos auto-generables ━━${RESET}"
generated=0
for var in "${!AUTO_VARS[@]}"; do
    if needs_value "$var"; then
        IFS=':' read -ra spec <<< "${AUTO_VARS[$var]}"
        case "${spec[0]}" in
            password) val=$(gen_password "${spec[1]}" "${spec[2]}") ;;
            hex)      val=$(gen_hex "${spec[1]}") ;;
            litellm)  val="sk-$(gen_hex 24)" ;;
            fernet)   val=$(gen_fernet) ;;
            *)        echo "Tipo desconocido: ${spec[0]}"; continue ;;
        esac
        set_value "$var" "$val"
        echo "${var}=${val}" >> "$SECRETS_OUT"
        echo -e "  ${GREEN}✔${RESET} $var generado"
        generated=$((generated + 1))
    fi
done
[[ $generated -eq 0 ]] && echo -e "  ${CYAN}ℹ Todas las claves auto ya tienen valor real${RESET}"

# ─── Tier 1: Configuración de proveedores LLM (multi-provider, prioritized) ─
echo ""
echo -e "${BOLD}━━ Proveedores LLM ━━${RESET}"

CATALOG_FILE="$SCRIPT_DIR/infra/litellm/providers.yaml"
[[ -f "$CATALOG_FILE" ]] || { echo -e "${RED}✖ No existe $CATALOG_FILE${RESET}" >&2; exit 1; }

# Volcamos el catálogo a 4 arrays bash paralelos vía Python (más fiable que parsing manual)
read_catalog() {
    python3 - "$CATALOG_FILE" <<'PYEOF'
import sys, yaml
with open(sys.argv[1]) as f:
    cat = yaml.safe_load(f)
for name, p in cat["providers"].items():
    dim = p.get("embedding_dim") if p.get("embedding_model") else 0
    notes = p.get("notes", "")
    print(f"{name}|{p['env_var']}|{p['register_url']}|{dim}|{notes}")
PYEOF
}

declare -a PROV_NAMES PROV_ENVVARS PROV_URLS PROV_DIMS PROV_NOTES
while IFS='|' read -r name envvar url dim notes; do
    PROV_NAMES+=("$name")
    PROV_ENVVARS+=("$envvar")
    PROV_URLS+=("$url")
    PROV_DIMS+=("$dim")
    PROV_NOTES+=("$notes")
done < <(read_catalog)

current_priority=$(grep '^LLM_PROVIDERS_PRIORITY=' .env 2>/dev/null | head -1 | cut -d= -f2-)

# ¿Hay que (re)preguntar la lista de proveedores?
ask_providers=false
if [[ "$RECONFIGURE_LLM" == "1" ]]; then
    ask_providers=true
elif [[ -z "$current_priority" ]]; then
    ask_providers=true
fi

if $ask_providers; then
    if [[ "$NON_INTERACTIVE" == "1" ]]; then
        echo -e "  ${YELLOW}⚠ LLM_PROVIDERS_PRIORITY vacía. El stack arrancará pero LiteLLM no podrá renderizar config.${RESET}"
        echo -e "     Edita .env y define LLM_PROVIDERS_PRIORITY (CSV, p.ej. nvidia,openai)"
    else
        # ── Menú numérico: lista de proveedores con índice ──────────────────
        echo -e "Proveedores disponibles:"
        echo ""
        for i in "${!PROV_NAMES[@]}"; do
            idx=$((i + 1))
            printf "  ${CYAN}[%d]${RESET} %-11s %s\n      %s\n" \
                "$idx" "${PROV_NAMES[$i]}" "${PROV_NOTES[$i]}" "${PROV_URLS[$i]}"
        done
        echo ""
        echo -e "Escribe los números separados por coma, ${BOLD}en orden de prioridad${RESET}."
        echo -e "Ejemplos: ${CYAN}1${RESET}  |  ${CYAN}1,3${RESET}  |  ${CYAN}2,5,6${RESET}   (Enter = 1 = nvidia)"
        read -r -p "  → tu elección: " indices_in || indices_in=""
        indices_in=$(echo "$indices_in" | tr -d ' ')
        [[ -z "$indices_in" ]] && indices_in="1"

        # Convertir índices → nombres
        valid_priority=()
        IFS=',' read -ra requested_idx <<< "$indices_in"
        for raw in "${requested_idx[@]}"; do
            if [[ ! "$raw" =~ ^[0-9]+$ ]]; then
                echo -e "  ${YELLOW}⚠ Entrada no numérica ignorada: '$raw'${RESET}"
                continue
            fi
            idx=$((raw - 1))
            if [[ $idx -lt 0 || $idx -ge ${#PROV_NAMES[@]} ]]; then
                echo -e "  ${YELLOW}⚠ Índice fuera de rango: $raw (válidos 1..${#PROV_NAMES[@]})${RESET}"
                continue
            fi
            valid_priority+=("${PROV_NAMES[$idx]}")
        done

        if [[ ${#valid_priority[@]} -eq 0 ]]; then
            echo -e "  ${RED}✖ Sin selección válida. Usando 'nvidia' por defecto.${RESET}"
            valid_priority=("nvidia")
        fi

        priority_csv=$(IFS=,; echo "${valid_priority[*]}")
        set_value LLM_PROVIDERS_PRIORITY "$priority_csv"
        echo -e "  ${GREEN}✔${RESET} Activados (en orden): ${BOLD}$priority_csv${RESET}"
        echo ""

        # ── Pedir API key de cada proveedor activado (texto, inevitable) ────
        for prov in "${valid_priority[@]}"; do
            for i in "${!PROV_NAMES[@]}"; do
                if [[ "${PROV_NAMES[$i]}" == "$prov" ]]; then
                    envvar="${PROV_ENVVARS[$i]}"
                    url="${PROV_URLS[$i]}"
                    if needs_value "$envvar"; then
                        echo -e "${CYAN}$envvar${RESET}  (registro: ${CYAN}$url${RESET})"
                        read -r -p "  → pega la clave: " key_in || key_in=""
                        if [[ -n "$key_in" ]]; then
                            set_value "$envvar" "$key_in"
                            echo -e "  ${GREEN}✔${RESET} $envvar guardada"
                        else
                            echo -e "  ${YELLOW}⚠ $envvar queda vacía. Este proveedor no se activará en LiteLLM.${RESET}"
                        fi
                    else
                        echo -e "  ${GREEN}✔${RESET} $envvar ya configurada"
                    fi
                    break
                fi
            done
        done
        echo ""

        # ── Embeddings: dimensión y proveedor (todo numérico) ──────────────
        current_dim=$(grep '^EMBEDDINGS_DIM=' .env 2>/dev/null | head -1 | cut -d= -f2-)
        [[ -z "$current_dim" ]] && current_dim=1024

        echo -e "${BOLD}Dimensión de embeddings${RESET}"
        echo -e "  ${CYAN}[1]${RESET} 1024 — NVIDIA, Mistral, Cohere (default)"
        echo -e "  ${CYAN}[2]${RESET} 1536 — OpenAI text-embedding-3"
        echo -e "  ${CYAN}[3]${RESET} 768  — Gemini text-embedding-004"
        echo -e "  ${CYAN}[4]${RESET} otra — escribir manualmente"
        read -r -p "  → tu elección [1]: " dim_choice || dim_choice=""
        case "${dim_choice:-1}" in
            1) dim_in=1024 ;;
            2) dim_in=1536 ;;
            3) dim_in=768 ;;
            4)
                read -r -p "  → dim manual: " dim_in || dim_in=""
                [[ "$dim_in" =~ ^[0-9]+$ ]] || dim_in="$current_dim"
                ;;
            *) dim_in="$current_dim" ;;
        esac
        set_value EMBEDDINGS_DIM "$dim_in"
        echo ""

        # Proveedor de embeddings: solo los activos con embeddings de la dim correcta
        echo -e "${BOLD}Proveedor de embeddings${RESET}"
        echo -e "  ${CYAN}[0]${RESET} auto — primer proveedor de la lista con dim=$dim_in (recomendado)"
        emb_candidates=()
        emb_idx=1
        for prov in "${valid_priority[@]}"; do
            for i in "${!PROV_NAMES[@]}"; do
                if [[ "${PROV_NAMES[$i]}" == "$prov" && "${PROV_DIMS[$i]}" == "$dim_in" ]]; then
                    echo -e "  ${CYAN}[$emb_idx]${RESET} $prov"
                    emb_candidates+=("$prov")
                    emb_idx=$((emb_idx + 1))
                fi
            done
        done
        if [[ ${#emb_candidates[@]} -eq 0 ]]; then
            echo -e "  ${YELLOW}⚠ Ninguno de los proveedores activos ofrece embeddings con dim=$dim_in.${RESET}"
            echo -e "  ${YELLOW}   Añade un proveedor compatible (NVIDIA/Mistral/Cohere para 1024, OpenAI para 1536) o cambia la dim.${RESET}"
        fi
        read -r -p "  → tu elección [0]: " emb_choice || emb_choice=""
        case "${emb_choice:-0}" in
            0|"") emb_in="auto" ;;
            *)
                if [[ "$emb_choice" =~ ^[0-9]+$ ]] && [[ $emb_choice -ge 1 && $emb_choice -le ${#emb_candidates[@]} ]]; then
                    emb_in="${emb_candidates[$((emb_choice - 1))]}"
                else
                    emb_in="auto"
                fi
                ;;
        esac
        set_value EMBEDDINGS_PROVIDER "$emb_in"
        echo -e "  ${GREEN}✔${RESET} EMBEDDINGS_DIM=$dim_in EMBEDDINGS_PROVIDER=$emb_in"
        if [[ "$dim_in" != "$current_dim" ]]; then
            echo -e "  ${YELLOW}⚠ La dimensión cambió ($current_dim→$dim_in). En el próximo up.sh las colecciones Qdrant se recrearán (destructivo).${RESET}"
        fi
    fi
else
    echo -e "  ${GREEN}✔${RESET} LLM_PROVIDERS_PRIORITY=$current_priority (usa --reconfigure-llm para reabrirlo)"
fi

# ─── Opcional: TS_AUTHKEY si --with-telegram ────────────────────────────────
if [[ "$WITH_TELEGRAM" == "1" ]]; then
    if needs_value TS_AUTHKEY; then
        if [[ "$NON_INTERACTIVE" == "1" ]]; then
            echo -e "  ${YELLOW}⚠ TS_AUTHKEY vacía. tailscale-funnel no podrá registrarse.${RESET}"
        else
            echo -e "${CYAN}TS_AUTHKEY${RESET} (Tailscale Funnel para webhooks Telegram)"
            echo -e "  Generar en: ${CYAN}https://login.tailscale.com/admin/settings/keys${RESET}"
            echo -e "  Marcar: Reusable=ON, Ephemeral=OFF"
            read -r -p "  TS_AUTHKEY: " ts_key || ts_key=""
            if [[ -n "$ts_key" ]]; then
                set_value TS_AUTHKEY "$ts_key"
                echo -e "  ${GREEN}✔${RESET} TS_AUTHKEY guardada"
            fi
        fi
    else
        echo -e "  ${GREEN}✔${RESET} TS_AUTHKEY ya configurada"
    fi
fi

# ─── SEED_DEMO: en bootstrap dev forzar a true si está en false default ─────
# Solo cambia si está exactamente "false" (default de .env.example).
seed_current=$(grep '^SEED_DEMO=' .env 2>/dev/null | head -1 | cut -d= -f2- || echo "")
if [[ "$seed_current" == "false" || -z "$seed_current" ]] && [[ "$NON_INTERACTIVE" != "1" ]]; then
    echo ""
    read -r -p "$(echo -e ${CYAN}¿Sembrar usuario demo + 18 recursos de ejemplo? \(Y/n\):${RESET} )" seed_yn || seed_yn="Y"
    case "${seed_yn:-Y}" in
        n|N|no|NO)
            set_value SEED_DEMO "false"
            echo -e "  ${CYAN}ℹ SEED_DEMO=false (sin demo)${RESET}" ;;
        *)
            set_value SEED_DEMO "true"
            echo -e "  ${GREEN}✔${RESET} SEED_DEMO=true (se creará demo@linkanvil.io / linkanvil-demo)" ;;
    esac
fi

# Hardening de permisos: .env y .env.bak contienen secretos en claro.
# 600 = solo el dueño (root operador) puede leerlos.
chmod 600 .env .env.bak 2>/dev/null || true
[[ -f "$SECRETS_OUT" ]] && chmod 600 "$SECRETS_OUT" 2>/dev/null || true

echo ""
echo -e "${GREEN}${BOLD}✔ .env listo${RESET} (backup en .env.bak, permisos 600)"
if [[ -s "$SECRETS_OUT" ]]; then
    echo -e "${CYAN}ℹ Secretos generados en esta corrida: $SECRETS_OUT${RESET}"
fi
