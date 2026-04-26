# LinkAnvil — Production deployment notes

## Overview

The default `docker-compose.yml` is tuned for local development:
internal services are exposed on the host (5432, 6379, 6333, 4000…)
and Traefik runs in `--api.insecure=true` mode without TLS.
For production, **always layer the production overlay**:

```
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

The overlay (`docker-compose.prod.yml`) does the following:

- Removes host-port publication for every internal service. Only
  Traefik publishes 80/443 to the host. Internal services keep talking
  to each other over the `cerebro-net` bridge.
- Switches Traefik to:
  - HTTPS-only (`websecure` entry point on 443),
  - HTTP→HTTPS redirect on 80,
  - Let's Encrypt automatic certificate provisioning (TLS-ALPN
    challenge),
  - dashboard secured (`--api.insecure=false`).
- Loads sensitive env vars from Docker secrets mounted at
  `/run/secrets/<name>`.

## Required environment

Production `.env` only carries non-sensitive operational config:

```
ACME_EMAIL=ops@example.com
PUBLIC_HOSTNAME=linkanvil.example.com
```

Add public hostname mappings in your DNS pointing to the host that
runs Traefik. Update the `Host(...)` Traefik labels in
`docker-compose.yml` if you use a different domain.

## Secret layout

The overlay reads secrets from `/etc/cerebro/secrets/<name>` on the
host. Each file contains a single value (no trailing newline) with
mode `0400` and ownership `root:root`.

Required secret files:

| File | Used by |
|---|---|
| `postgres_password` | postgres, n8n, cerebro-api, workers |
| `redis_password` | redis, all services that talk to Redis |
| `rabbitmq_password` | rabbitmq, ingestion-api, workers |
| `jwt_secret` | cerebro-api session signing |
| `litellm_master_key` | litellm, cerebro-api |
| `openai_api_key` | litellm provider |
| `anthropic_api_key` | litellm provider |

For a real production environment, replace this with a secret
manager:

- **HashiCorp Vault** + Vault Agent renders `/etc/cerebro/secrets/*`
  on disk with auto-rotation.
- **Doppler** CLI runs `doppler secrets download --no-file --format
  env` and pipes into a render step.
- **AWS Secrets Manager / GCP Secret Manager** with a sidecar that
  templates files.
- **Docker Swarm** native `docker secret` once the cluster grows beyond
  a single node.

The compose overlay is agnostic to the source — it just reads the
mounted files.

## Backups

`scripts/backup.sh` produces gzipped `pg_dump` and Qdrant snapshots
for every collection. Recommended cron:

```
0 3 * * * /opt/linkanvil/scripts/backup.sh && rsync -az /opt/linkanvil/backups/ backup-host:/backups/linkanvil/
```

`BACKUP_RETENTION_DAYS` (default 7) controls local retention. Keep a
longer retention on the off-host destination.

## Migrations

`infra/postgres/init.sql` runs only on a fresh data volume. Schema
changes against an existing volume require a migration tool. Add an
init container that runs Alembic before cerebro-api comes up:

```yaml
# Sketch — see C6 in audit plan
cerebro-api-migrate:
  image: linkanvil-cerebro-api
  command: ["alembic", "upgrade", "head"]
  depends_on:
    postgres:
      condition: service_healthy
```

## Rate limits and quotas

The cerebro-api enforces:

- `/auth/login`: 5/min per IP
- `/auth/register`: 3/hour per IP
- `/chat`: 30/min per tenant

The ingestion-api enforces 10/min per tenant on `/ingest`. Tune via
`INGESTION_RATE_LIMIT_PER_MIN`.

Traefik's `global-ratelimit` middleware also caps requests at the
gateway level.

## Observability

- Prometheus + Grafana provisioned with the dashboards in
  `infra/grafana/dashboards/`.
- Alert rules in `infra/prometheus/alert.rules.yml` cover p99 latency,
  queue backlogs, DLQ depth, Postgres connections, worker liveness,
  and disk usage. Wire these to PagerDuty/Slack via Alertmanager
  (Alertmanager itself is not bundled — add it on top).
- Logs are JSON; ship `docker logs --since 1m` via promtail/vector to
  Loki/ELK.

## Open items

The audit plan lists several deferred refactors that should land
before a real production deployment:

- C1: migrate session token from `Authorization: Bearer` +
  `localStorage` to httpOnly cookies + CSRF tokens. Reduces XSS blast
  radius.
- C6: introduce Alembic so schema changes are explicit and reversible
  across deployments.
- C4: pin the four images currently on `:latest` (redis-stack-server,
  jaeger, kbudde/rabbitmq-exporter, ghcr.io/berriai/litellm).
