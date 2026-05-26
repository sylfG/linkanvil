#!/usr/bin/env bash
# migrate.sh — apply pending SQL migrations from infra/postgres/migrations/
#
# Idempotent: keeps a `cerebro.schema_migrations(version, applied_at)`
# table and only runs files whose `version` (the leading number in the
# filename) isn't recorded yet. Each migration runs in a transaction.
#
# Env (all default to .env values when invoked from the project root):
#   PGHOST, PGUSER, PGPASSWORD, PGDATABASE
#   MIGRATIONS_DIR (defaults to infra/postgres/migrations/)
#
# Exit codes:
#   0 — all migrations applied (or none pending)
#   1 — at least one migration failed; the failed transaction is rolled
#       back and the runner exits without trying later migrations
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[[ -f "$SCRIPT_DIR/.env" ]] && source "$SCRIPT_DIR/.env"

PGHOST="${PGHOST:-localhost}"
PGUSER="${PGUSER:-${POSTGRES_USER:-cerebro}}"
PGPASSWORD="${PGPASSWORD:-${POSTGRES_PASSWORD:-cerebro_db_pass}}"
PGDATABASE="${PGDATABASE:-${POSTGRES_DB:-cerebro_brain}}"
MIGRATIONS_DIR="${MIGRATIONS_DIR:-$SCRIPT_DIR/infra/postgres/migrations}"

export PGHOST PGUSER PGPASSWORD PGDATABASE

if [[ ! -d "$MIGRATIONS_DIR" ]]; then
    echo "migrate: directory not found: $MIGRATIONS_DIR" >&2
    exit 1
fi

# Esperar a que Postgres ACEPTE conexiones TCP.
# El healthcheck de docker-compose puede marcar postgres como healthy
# antes de que el listener TCP esté abierto en algunos entornos LXC,
# provocando "Connection refused" inmediatamente al arrancar migrate.
# Usar pg_isready en lugar de psql evita ruido durante el polling.
for attempt in {1..30}; do
    if pg_isready -h "$PGHOST" -p "${PGPORT:-5432}" -U "$PGUSER" -d "$PGDATABASE" -q; then
        [[ $attempt -gt 1 ]] && echo "migrate: postgres listo en intento #$attempt"
        break
    fi
    if [[ $attempt -eq 30 ]]; then
        echo "migrate: postgres no acepta conexiones tras 30 intentos (60s)" >&2
        exit 2
    fi
    [[ $attempt -eq 1 ]] && echo "migrate: esperando a que postgres acepte conexiones..."
    sleep 2
done

# Ensure the bookkeeping table exists.
psql -v ON_ERROR_STOP=1 -q -c "
    CREATE SCHEMA IF NOT EXISTS cerebro;
    CREATE TABLE IF NOT EXISTS cerebro.schema_migrations (
        version     INTEGER PRIMARY KEY,
        applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
"

# Collect already-applied versions into a bash associative array.
declare -A APPLIED
while IFS= read -r v; do
    APPLIED["$v"]=1
done < <(psql -At -c "SELECT version FROM cerebro.schema_migrations ORDER BY version")

shopt -s nullglob
applied_count=0
for file in "$MIGRATIONS_DIR"/*.sql; do
    base=$(basename "$file")
    # extract leading digits: "0042_foo.sql" -> "0042" -> 42
    if ! [[ "$base" =~ ^([0-9]+)_ ]]; then
        echo "migrate: skipping (no version prefix): $base" >&2
        continue
    fi
    # Strip leading zeros via base-10 arithmetic so "0042" → 42 (not "042"
    # which wouldn't match the integer key returned from Postgres).
    version=$((10#${BASH_REMATCH[1]}))
    if [[ -n "${APPLIED[$version]:-}" ]]; then
        continue
    fi

    echo "migrate: applying $base (version $version)..."
    if ! psql -v ON_ERROR_STOP=1 -1 -f "$file"; then
        echo "migrate: FAILED on $base — transaction rolled back" >&2
        exit 1
    fi
    psql -v ON_ERROR_STOP=1 -q -c \
        "INSERT INTO cerebro.schema_migrations (version) VALUES ($version) ON CONFLICT DO NOTHING;"
    echo "migrate: OK $base"
    applied_count=$((applied_count + 1))
done

if [[ "$applied_count" -eq 0 ]]; then
    echo "migrate: schema is up to date"
else
    echo "migrate: applied $applied_count migration(s)"
fi
