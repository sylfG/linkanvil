#!/usr/bin/env bash
# regen-rabbitmq-hash.sh — Regenera el password_hash del usuario `cerebro`
# en infra/rabbitmq/definitions.json a partir de $RABBITMQ_PASS leído desde .env.
# Idempotente: el hash incluye salt aleatorio, así que cada ejecución produce
# un hash distinto pero RabbitMQ lo acepta igual contra la misma contraseña.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"

[[ -f .env ]] || { echo "✖ No se encontró .env" >&2; exit 1; }
[[ -f infra/rabbitmq/definitions.json ]] || { echo "✖ definitions.json no encontrado" >&2; exit 1; }

RABBIT_PASS=$(grep '^RABBITMQ_PASS=' .env | head -1 | cut -d= -f2-)
[[ -n "$RABBIT_PASS" ]] || { echo "✖ RABBITMQ_PASS vacía en .env" >&2; exit 1; }

command -v python3 >/dev/null 2>&1 || { echo "✖ python3 requerido" >&2; exit 1; }

NEW_HASH=$(python3 - "$RABBIT_PASS" <<'PYEOF'
import sys, hashlib, os, base64
p = sys.argv[1].encode()
s = os.urandom(4)
print(base64.b64encode(s + hashlib.sha256(s + p).digest()).decode())
PYEOF
)

python3 - "$NEW_HASH" <<'PYEOF'
import json, sys
path = 'infra/rabbitmq/definitions.json'
with open(path) as f:
    d = json.load(f)
updated = False
for u in d.get('users', []):
    if u.get('name') == 'cerebro':
        u['password_hash'] = sys.argv[1]
        updated = True
if not updated:
    raise SystemExit("✖ Usuario 'cerebro' no encontrado en definitions.json")
with open(path, 'w') as f:
    json.dump(d, f, indent=2)
PYEOF

echo "✔ Hash RabbitMQ actualizado en infra/rabbitmq/definitions.json"
