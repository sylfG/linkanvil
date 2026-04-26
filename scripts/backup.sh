#!/usr/bin/env bash
# backup.sh — Postgres + Qdrant snapshot, gzipped, with retention.
#
# Usage:
#   bash scripts/backup.sh                     # writes to ./backups
#   BACKUP_DIR=/mnt/backups bash scripts/...   # custom destination
#   BACKUP_RETENTION_DAYS=14 bash scripts/...  # keep 14 days (default 7)
#
# Designed to be cron-friendly: runs to completion or fails non-zero, no
# interactive prompts.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"

BACKUP_DIR="${BACKUP_DIR:-$SCRIPT_DIR/backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"
TIMESTAMP="$(date +%Y%m%dT%H%M%SZ)"

POSTGRES_USER="${POSTGRES_USER:-cerebro}"
POSTGRES_DB="${POSTGRES_DB:-cerebro_brain}"

[[ -f .env ]] && source .env

mkdir -p "$BACKUP_DIR"

echo "==> Backup start: $TIMESTAMP"
echo "    destination: $BACKUP_DIR"

# ── Postgres ──
PG_FILE="$BACKUP_DIR/postgres_${POSTGRES_DB}_${TIMESTAMP}.sql.gz"
echo "==> pg_dump → $PG_FILE"
docker exec -e PGPASSWORD="${POSTGRES_PASSWORD:-cerebro_db_pass}" cerebro-postgres \
    pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --clean --if-exists \
    | gzip -9 > "$PG_FILE"
PG_SIZE=$(du -h "$PG_FILE" | cut -f1)
echo "    pg_dump ok ($PG_SIZE)"

# ── Qdrant ──
# Qdrant has an HTTP snapshot API that returns a tarball per collection.
QDRANT_DIR="$BACKUP_DIR/qdrant_${TIMESTAMP}"
mkdir -p "$QDRANT_DIR"
echo "==> Qdrant snapshots → $QDRANT_DIR"
COLLECTIONS=$(curl -fs http://localhost:6333/collections | python3 -c "
import json, sys
d = json.load(sys.stdin)
for c in d.get('result', {}).get('collections', []):
    print(c['name'])
")
for col in $COLLECTIONS; do
    echo "    snapshot of $col"
    SNAP_NAME=$(curl -fs -X POST "http://localhost:6333/collections/$col/snapshots" \
        | python3 -c "import json,sys; print(json.load(sys.stdin)['result']['name'])")
    curl -fs "http://localhost:6333/collections/$col/snapshots/$SNAP_NAME" \
        -o "$QDRANT_DIR/${col}.snapshot"
    # GC the snapshot inside qdrant so we don't accumulate them on disk
    curl -fs -X DELETE "http://localhost:6333/collections/$col/snapshots/$SNAP_NAME" >/dev/null || true
done
tar -czf "${QDRANT_DIR}.tar.gz" -C "$BACKUP_DIR" "$(basename "$QDRANT_DIR")"
rm -rf "$QDRANT_DIR"
QDRANT_SIZE=$(du -h "${QDRANT_DIR}.tar.gz" | cut -f1)
echo "    qdrant snapshot ok ($QDRANT_SIZE)"

# ── Retention ──
echo "==> Pruning backups older than $RETENTION_DAYS days"
find "$BACKUP_DIR" -maxdepth 1 -type f \
    \( -name 'postgres_*.sql.gz' -o -name 'qdrant_*.tar.gz' \) \
    -mtime +"$RETENTION_DAYS" -print -delete || true

echo "==> Backup complete: $TIMESTAMP"
