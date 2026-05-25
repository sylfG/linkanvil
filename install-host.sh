#!/usr/bin/env bash
# install-host.sh — Instala las dependencias del SO necesarias para LinkAnvil.
# Soporta: Debian 12+, Ubuntu 22.04+.
# Uso:  sudo bash install-host.sh
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
log()  { echo -e "${CYAN}[$(date +%H:%M:%S)]${RESET} $*"; }
ok()   { echo -e "${GREEN}✔${RESET} $*"; }
warn() { echo -e "${YELLOW}⚠${RESET}  $*"; }
fail() { echo -e "${RED}✖ ERROR:${RESET} $*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || fail "Este script requiere sudo / root."

# ── 1. Detectar SO ──────────────────────────────────────────────────────────
[[ -f /etc/os-release ]] || fail "No se pudo detectar el SO (/etc/os-release no existe)."
# shellcheck disable=SC1091
. /etc/os-release
case "$ID" in
    debian)
        [[ "${VERSION_ID%%.*}" -ge 12 ]] || fail "Debian $VERSION_ID no soportada. Mínimo: Debian 12."
        ;;
    ubuntu)
        major="${VERSION_ID%%.*}"
        [[ "$major" -ge 22 ]] || fail "Ubuntu $VERSION_ID no soportada. Mínimo: 22.04."
        ;;
    *)
        fail "SO no soportado: $ID. Soportados: Debian 12+, Ubuntu 22.04+."
        ;;
esac
ok "SO detectado: $PRETTY_NAME"

echo ""
echo -e "${BOLD}╔══════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}║   LinkAnvil — Install Host Dependencies  ║${RESET}"
echo -e "${BOLD}╚══════════════════════════════════════════╝${RESET}"
echo ""

# ── 2. apt update ───────────────────────────────────────────────────────────
log "Actualizando índice de paquetes..."
apt-get update -qq
ok "apt-get update completado"

# ── 3. Paquetes base ────────────────────────────────────────────────────────
log "Instalando paquetes base..."
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    ca-certificates curl gnupg lsb-release \
    git python3 python3-pip python3-venv jq openssl
ok "Paquetes base instalados"

# Cryptography (para fernet en bootstrap-env.sh) — opcional, hay fallback openssl
if ! python3 -c "from cryptography.fernet import Fernet" 2>/dev/null; then
    log "Instalando python3-cryptography..."
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3-cryptography 2>/dev/null \
        || warn "python3-cryptography no disponible — se usará fallback openssl para Fernet"
fi

# ── 4. Docker Engine + Compose plugin ───────────────────────────────────────
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    ok "Docker y Compose plugin ya instalados"
else
    log "Instalando Docker Engine + Compose plugin..."
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL "https://download.docker.com/linux/$ID/gpg" \
        -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc

    codename="${VERSION_CODENAME:-$(lsb_release -cs)}"
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/$ID $codename stable" \
        > /etc/apt/sources.list.d/docker.list

    apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
        docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    ok "Docker instalado"
fi

systemctl enable --now docker >/dev/null
ok "Docker daemon activo (systemctl)"

# ── 5. Añadir usuario invocador al grupo docker ─────────────────────────────
if [[ -n "${SUDO_USER:-}" && "$SUDO_USER" != "root" ]]; then
    if ! id -nG "$SUDO_USER" | grep -qw docker; then
        usermod -aG docker "$SUDO_USER"
        warn "Usuario '$SUDO_USER' añadido al grupo docker — cierra sesión y vuelve a entrar (o ejecuta 'newgrp docker')."
    else
        ok "Usuario '$SUDO_USER' ya pertenece al grupo docker"
    fi
fi

# ── 6. Verificar versiones mínimas ──────────────────────────────────────────
log "Verificando versiones..."
ver_docker=$(docker --version | awk '{print $3}' | tr -d ',')
ver_compose=$(docker compose version --short 2>/dev/null || echo "0.0")
ver_py=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')

cmp_version() {
    # 1 si $1 < $2; 0 si $1 >= $2
    [[ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -1)" == "$2" ]] && return 0
    return 1
}

cmp_version "$ver_docker" "24.0"   || warn "Docker $ver_docker < 24 — algunas features pueden fallar"
cmp_version "$ver_compose" "2.22"  || warn "Compose $ver_compose < 2.22 — service_completed_successfully puede fallar"
cmp_version "$ver_py" "3.9"        || warn "Python $ver_py < 3.9"

# ── 7. Resumen ──────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}━━━━━━━━━━━━━━━━ INSTALACIÓN OK ━━━━━━━━━━━━━━━━${RESET}"
echo -e "  Docker        $ver_docker"
echo -e "  Compose       $ver_compose"
echo -e "  Python        $ver_py"
echo -e "  Git           $(git --version | awk '{print $3}')"
echo ""
echo -e "${BOLD}Siguiente paso:${RESET}"
if [[ -n "${SUDO_USER:-}" && "$SUDO_USER" != "root" ]] && ! id -nG "$SUDO_USER" | grep -qw docker; then
    echo -e "  ${YELLOW}newgrp docker${RESET}   # activar membresía al grupo docker"
fi
echo -e "  ${CYAN}bash up.sh${RESET}    # arrancar LinkAnvil (sin sudo)"
echo ""
