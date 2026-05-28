#!/usr/bin/env bash
# Borra toda la huella de sesiones demo para una IP concreta, sin esperar al TTL.
#
# Uso:
#   ./scripts/reset-demo-by-ip.sh <ip>            # solo BD + Redis del proyecto
#   ./scripts/reset-demo-by-ip.sh <ip> --dry-run  # muestra lo que borraria, sin tocar nada
#
# Qué limpia:
#   Postgres:
#     - demo_sessions WHERE ip = $IP  (cascade a demo_session_events)
#     - usuario_recursos  con tenant_id de esos demos
#     - notificaciones    con tenant_id de esos demos
#     - outbox_eventos    con tenant_id de esos demos
#     - recursos huérfanos (sin ninguna fila en usuario_recursos apuntándolos)
#
#   Redis:
#     - demo_session_started:<ip>:<YYYY-MM-DD>   (gate diario por IP)
#     - rl:demo:ingest:ip:<ip>:<YYYY-MM-DD>      (rate-limit ingest)
#     - rl:demo:chat:ip:<ip>:<YYYY-MM-DD>        (rate-limit chat)
#     - bf:tenant:<tenant>:ingestion             (bloom filter de cada demo)
#
# Lo que NO toca:
#   - usuarios de no-demo
#   - recursos que pertenecen a tenants registrados
#   - contadores globales de rate-limit (afectarían a otros visitantes)

set -euo pipefail

IP="${1:-}"
DRY_RUN=""
if [[ "${2:-}" == "--dry-run" ]]; then DRY_RUN=1; fi

if [[ -z "$IP" ]]; then
  echo "Uso: $0 <ip> [--dry-run]" >&2
  echo "Ejemplo: $0 192.168.1.3" >&2
  exit 1
fi

if ! [[ "$IP" =~ ^[0-9a-fA-F\.:]+$ ]]; then
  echo "ERROR: IP '$IP' no parece válida (solo dígitos, puntos, dos puntos, hex)" >&2
  exit 1
fi

PG="docker exec -i cerebro-postgres psql -U cerebro -d cerebro_brain"
REDIS="docker exec -i cerebro-redis redis-cli -a ${CEREBRO_REDIS_PASS:-zvUN9eVkZWKgqbQo8xllXi6ZsMyh9bmp} --no-auth-warning"

say() { printf "\033[1;34m[demo-reset]\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m[demo-reset]\033[0m %s\n" "$*"; }

say "IP objetivo: $IP   dry-run: ${DRY_RUN:-no}"

# Tenants demo asociados a esta IP (segun la columna ip de demo_sessions)
TENANTS=$($PG -tAc "SELECT tenant_id FROM demo_sessions WHERE ip = '$IP'" | tr -d '\r')

if [[ -z "$TENANTS" ]]; then
  warn "No hay demo_sessions vivos para $IP en Postgres."
else
  say "Tenants demo encontrados:"
  echo "$TENANTS" | sed 's/^/   - /'
fi

# Convertir la lista a CSV citado para los DELETE ... IN (...)
TENANTS_SQL=$(echo "$TENANTS" | awk 'NF{printf "%s'\'',", $0}' | sed "s/^/'/" | sed 's/,$//')
if [[ -n "$TENANTS_SQL" ]]; then TENANTS_SQL="($TENANTS_SQL)"; fi

# Claves Redis a borrar (gate diario + rate-limits del dia actual y de ayer
# por si la prueba ha cruzado medianoche UTC)
TODAY=$(date -u +%F)
YEST=$(date -u -d 'yesterday' +%F 2>/dev/null || date -u -v-1d +%F)

REDIS_KEYS=(
  "demo_session_started:$IP:$TODAY"
  "demo_session_started:$IP:$YEST"
  "rl:demo:ingest:ip:$IP:$TODAY"
  "rl:demo:ingest:ip:$IP:$YEST"
  "rl:demo:chat:ip:$IP:$TODAY"
  "rl:demo:chat:ip:$IP:$YEST"
)
# Bloom filter por cada tenant
while IFS= read -r t; do
  [[ -n "$t" ]] && REDIS_KEYS+=("bf:tenant:$t:ingestion")
done <<< "$TENANTS"

say "Claves Redis a eliminar (${#REDIS_KEYS[@]}):"
for k in "${REDIS_KEYS[@]}"; do echo "   - $k"; done

if [[ -n "$DRY_RUN" ]]; then
  warn "DRY-RUN: no se ha modificado nada."
  exit 0
fi

# -- Postgres --
if [[ -n "$TENANTS_SQL" ]]; then
  say "Borrando cascade en Postgres…"
  $PG <<SQL
BEGIN;
DELETE FROM notificaciones   WHERE tenant_id IN $TENANTS_SQL;
DELETE FROM outbox_eventos   WHERE tenant_id IN $TENANTS_SQL;
DELETE FROM usuario_recursos WHERE tenant_id IN $TENANTS_SQL;
-- demo_session_events cascadea desde demo_sessions
DELETE FROM demo_sessions    WHERE ip = '$IP';
-- Recursos huérfanos: ningún tenant los referencia ya
DELETE FROM recursos WHERE id NOT IN (SELECT DISTINCT recurso_id FROM usuario_recursos);
COMMIT;
SQL
else
  say "Sin tenants en BD — saltando bloque Postgres."
fi

# -- Redis --
say "Borrando claves en Redis…"
DELETED=$($REDIS DEL "${REDIS_KEYS[@]}" | tr -d '\r')
say "  claves eliminadas: $DELETED"

# -- Verificación final --
REMAIN_DB=$($PG -tAc "SELECT COUNT(*) FROM demo_sessions WHERE ip = '$IP'" | tr -d '\r')
REMAIN_REDIS=$($REDIS EVAL "return #redis.call('keys', 'demo_session_started:$IP:*') + #redis.call('keys', 'rl:demo:*:ip:$IP:*')" 0 | tr -d '\r')

say "Verificación final:"
echo "   demo_sessions con ip=$IP : $REMAIN_DB"
echo "   claves Redis con esta IP : $REMAIN_REDIS"

if [[ "$REMAIN_DB" == "0" && "$REMAIN_REDIS" == "0" ]]; then
  say "Limpieza completada para $IP."
else
  warn "Quedó algún residuo — revisa manualmente."
  exit 2
fi
