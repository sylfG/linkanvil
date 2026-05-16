# linkanvil — Segundo Cerebro Autónomo

## Stack
- **Backend**: Python 3.12 + FastAPI + asyncpg (async PostgreSQL driver)
- **Workers**: aio_pika (RabbitMQ consumers) — outbox-worker, scraper-worker, embedder-worker, notifier-worker
- **Base de datos**: PostgreSQL 17 — schema `cerebro`, usuario `cerebro`, db `cerebro_brain`
- **Vector DB**: Qdrant — colecciones `cerebro_recursos` (doc-level) y `cerebro_chunks` (RAG chunks)
- **Message broker**: RabbitMQ — vhost `cerebro`, credenciales en `.env`
- **Embeddings/LLM**: LiteLLM proxy (`:4000`) → NVIDIA `nv-embedqa-e5-v5` (512 token limit)
- **Cache/state**: Redis
- **Infra**: Docker Compose — `docker-compose.yml`
- **Tests**: pytest + pytest-asyncio
- **Linter**: ruff + mypy
- **Observability**: OpenTelemetry → Jaeger + Prometheus + Grafana

## Arquitectura

Sistema multi-tenant de indexación semántica de URLs con RAG. Cada URL se scrapea, extrae texto (hasta 32000 chars), se embebe como vector doc-level en `cerebro_recursos`, y se trocea en chunks (1200 chars, 150 overlap) almacenados en `cerebro_chunks`.

**Flujo de ingesta**:
```
POST /ingest (ingestion-api)
  → q.recurso.scraper (scraper-worker: extrae texto → contenido en PG)
  → q.recurso.embedder (embedder-worker: embed + chunk → Qdrant)
  → outbox_eventos (outbox-worker: publica eventos externos)
```

**Patrón outbox**: Todas las notificaciones pasan por `cerebro.outbox_eventos` — nunca directamente a sistemas externos.

**Multi-tenant**: `tenant_id` filtra todos los datos. `cerebro.recursos` es global (URL deduplicada); `cerebro.usuario_recursos` mapea recursos a tenants; `cerebro_chunks` en Qdrant usa payload `tenant_id`.

**Reused path**: Si una URL ya existe globalmente, el embedder copia el vector doc-level y clona chunks al nuevo tenant sin re-scraping (`reused=True` en el mensaje).

## Modelos / Tablas principales (schema `cerebro`)

| Tabla | Descripción |
|---|---|
| `recursos` | URLs globales + texto extraído (`contenido TEXT`) + metadatos |
| `usuario_recursos` | Relación tenant ↔ recurso (con title, tags, estado) |
| `outbox_eventos` | Cola transaccional para notificaciones externas |
| `grafo_relaciones` | Grafo semántico: similitud entre recursos por tenant (`similitud BETWEEN 0 AND 1`) |

## Módulos críticos

| Archivo | Propósito |
|---|---|
| `src/data/embedder_worker.py` | Chunking (`_chunk_text`), embedding, colisiones semánticas |
| `src/data/db.py` | `save_semantic_collisions`, `find_existing_recurso_by_url`, outbox |
| `src/scraper/worker.py` | Extracción HTML → texto limpio (`_html_to_clean_text`, max 32000 chars) |
| `src/api/main.py` | FastAPI: endpoints `/ingest`, `/chat`, auth JWT |
| `src/ingestion/worker.py` | Ingestion API worker — publica a `q.recurso.scraper` |

## Convenciones

- Commits: Conventional Commits (`feat:`, `fix:`, `refactor:`, `docs:`)
- Ramas: `develop` para desarrollo, `main` para producción
- Tests: pytest con fixtures async — `tests/`
- Docker: reconstruir con `docker compose build <service> && docker compose up -d <service>`
- Editar código en servidor: escribir script Python en `/tmp/`, scp al server, ejecutar (sed/heredoc son poco fiables vía SSH)
- `contenido TEXT` en `recursos` es NULL para URLs con paywall (Medium, etc.) — comportamiento esperado, no un error

## Comandos críticos

```bash
# Estado de los servicios
ssh linkanvil "docker compose -f /root/linkanvil/docker-compose.yml ps"

# Logs de un worker
ssh linkanvil "docker logs cerebro-embedder 2>&1 | tail -50"

# PostgreSQL
ssh linkanvil "docker exec cerebro-postgres psql -U cerebro -d cerebro_brain -c '<SQL>'"

# Qdrant (desde el servidor)
ssh linkanvil "curl -s 'http://localhost:6333/collections/cerebro_chunks'"

# Re-ingestar recursos vía RabbitMQ (script Python en el contenedor)
# Ver /tmp/rechunk.py como referencia — usar passive=True en declare_queue
```

## Workflows prioritarios

| Workflow | Cuándo |
|---|---|
| `feature` | Nueva funcionalidad (endpoint `/chat`, nuevas colecciones Qdrant) |
| `review` | PRs sobre `scraper/worker.py` o `embedder_worker.py` |
| `security-audit` | Antes de cualquier exposición pública de la API |
| `hotfix` | Fix urgente en producción (bugs de embedding, constraint violations) |

## Git hooks (análisis de IA vía LiteLLM)

Los hooks están en `.githooks/` y usan LiteLLM local (`localhost:4000`). Activar en cada clon:

```bash
git config core.hooksPath .githooks
chmod +x .githooks/pre-push .githooks/pre-commit
```

| Hook | Cuándo corre | Qué hace |
|---|---|---|
| `pre-commit` | Cada commit | `ruff check` sobre archivos staged (sin IA, rápido) |
| `pre-push` | Antes de `git push` | LiteLLM analiza el diff de `src/api/`, `src/data/`, `src/scraper/`, `src/ingestion/` — bloquea en CRITICAL |

Variables de entorno opcionales (tienen defaults):
- `LITELLM_URL` — default `http://localhost:4000`
- `LITELLM_MODEL` — default `cerebro-lite`

Para saltarse un hook: `git push --no-verify` o `git commit --no-verify`

## Auditoría semanal (cron en servidor)

```bash
# Ejecutar manualmente:
python3 ops/cron/weekly-audit.py

# Instalar cron (lunes 09:00 UTC):
# Añadir a crontab -e:
# 0 9 * * 1 cd /root/linkanvil && python3 ops/cron/weekly-audit.py >> /var/log/linkanvil-audit.log 2>&1
```

El reporte se guarda en `ops/sessions/audit-YYYY-MM-DD.md`.

## Gotchas conocidos

- **NVIDIA embedding model**: límite de 512 tokens por chunk. `_chunk_text()` usa `target_chars=1200` (~350 tokens). Cambiar a valores más altos romperá el embedding.
- **`grafo_relaciones.similitud_check`**: constraint `BETWEEN 0 AND 1`. La similitud coseno puede devolver `1.0000002` — siempre usar `min(value, 1.0)` antes de insertar.
- **Queue `q.recurso.embedder`**: tiene `x-dead-letter-exchange` configurado. Declarar siempre con `passive=True` desde scripts externos.
- **Git**: cuenta `sylfG` / `silviagandia@gmail.com`, PAT en `~/.git-credentials` del servidor.
