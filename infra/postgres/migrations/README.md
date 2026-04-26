# Schema migrations

`init.sql` only runs the **first time** Postgres initializes a fresh
data volume. In production the volume is never wiped, so any schema
change after the initial deployment must come through this directory.

## How to add a migration

1. Create a new file `NNNN_short_description.sql` where NNNN is the
   next free four-digit number (zero-padded).
2. Write the change as **idempotent SQL** — every statement must use
   `IF NOT EXISTS`, `IF EXISTS`, `ON CONFLICT`, etc. The runner
   re-applies pending migrations on every boot, so a non-idempotent
   migration would error on the second run.
3. Test it against a fresh volume (`bash reset.sh`) and against an
   existing one (start the stack, then run migrations).

## How it runs

`scripts/migrate.sh` ships with the project. It:

1. Connects to Postgres as `cerebro` using the credentials from `.env`.
2. Creates a `cerebro.schema_migrations(version, applied_at)` table if
   it doesn't exist.
3. Scans `infra/postgres/migrations/` for `*.sql` files.
4. For every file whose `version` (the leading number) is not yet in
   the table, runs the file inside a transaction and inserts the
   version.

Each migration runs in its own transaction; partial application is
rolled back on error and the runner exits non-zero so docker / CI can
fail the deployment.

## Wiring into compose

`docker-compose.prod.yml` should add a one-shot service that runs the
migration before `cerebro-api` starts:

```yaml
cerebro-migrate:
  image: postgres:16-alpine     # for the psql client
  container_name: cerebro-migrate
  restart: "no"
  depends_on:
    postgres:
      condition: service_healthy
  volumes:
    - ./scripts/migrate.sh:/migrate.sh:ro
    - ./infra/postgres/migrations:/migrations:ro
  environment:
    PGHOST: postgres
    PGUSER: ${POSTGRES_USER:-cerebro}
    PGPASSWORD: ${POSTGRES_PASSWORD:-cerebro_db_pass}
    PGDATABASE: ${POSTGRES_DB:-cerebro_brain}
    MIGRATIONS_DIR: /migrations
  command: ["bash", "/migrate.sh"]

cerebro-api:
  depends_on:
    cerebro-migrate:
      condition: service_completed_successfully
```

## Naming examples

```
0001_initial_schema.sql         <- mirrors init.sql for compliance
0002_add_chat_fuentes_column.sql
0003_index_outbox_unprocessed.sql
```
