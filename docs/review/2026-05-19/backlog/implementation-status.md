# Backlog Implementation Status · 2026-05-19

**Auditor**: backlog-implementation-auditor
**Backlog dir**: `/tmp/linkanvil-mirror/docs/src/Extractor_de_Requisitos/backlog/`
**Total fichas**: 54
**Versión del repo**: HEAD (no git history — espejo a `/tmp/linkanvil-mirror/`)

## Resumen ejecutivo

- IMPLEMENTED: 38
- PARTIAL: 11
- NOT_STARTED: 4
- OBSOLETE: 0
- SUPERSEDED_BY: 1
- Total con drift detectado: 23

Observaciones globales:

- Las 23 fichas con drift son mayormente las "originales Fase 3" (F-00.1..6, F-01.1..5, F-02.1..4, F-03.1..5, F-04.1..5, F-05.1..3, F-06.1..4, F-08.1..2): tienen **plantillas Gherkin genéricas** ("Dado que la entrada es válida, Cuando se inyecta en el componente, Entonces ejecuta la operación acorde a `2_architecture_risks.md`") que no describen el comportamiento real implementado. Las fichas posteriores generadas por auditoría (F-00.7..13, F-01.6, F-02.5, F-04.6/7, F-06.5/6, F-08.3/4) sí tienen AC concretos y alineados.
- La arquitectura ha evolucionado más allá del backlog original: ahora hay BYOK con virtual keys (mig 0008), audit policy JSONB (mig 0007), temporal_class y strictness (mig 0006), demo_sessions y staged_embeddings (migs 0009-0011), SSE streaming para chat/ingest/resources, slice 6 con auditoría intra-sesión. El backlog no recoge nada de esto.

## Tabla maestra

| Feature | Estado | Evidencia (path:línea) | Drift detectado | Update propuesto |
|---|---|---|---|---|
| F-00.1 | IMPLEMENTED | `docker-compose.yml:1-1000` (todos los servicios y red `cerebro-net` definida en bloque `networks` final) | AC genéricos no describen el inventario real (16+ servicios: traefik, rabbitmq, redis, postgres, qdrant, n8n, litellm, otel, prometheus, grafana, jaeger, exporters, cerebro-api, cerebro-web, workers, tailscale) | Reescribir AC con inventario real de servicios; tabla con `service → image → puerto interno → propósito` |
| F-00.2 | IMPLEMENTED | `docker-compose.yml:294-336` (servicio `traefik` con `--api.dashboard`, `--metrics.prometheus`, `--tracing.otlp.http`, middleware `global-ratelimit`, `global-retry`) | AC genéricos | Reescribir AC: routing por Host header, métricas a Prometheus, retry middleware, dashboard expuesto en `:8080`, rate-limit global average=100 burst=50 |
| F-00.3 | IMPLEMENTED | `docker-compose.yml:557-606` (servicio `n8n` v1.123.37 con Postgres backend + Redis queue + workflow `audit_cron_daily.json` en `infra/n8n/workflows/`) + `infra/n8n/bootstrap-apikey.py` | AC genéricos no mencionan persistencia Postgres, queue Redis, ni bootstrap automático de API key | Reescribir AC: backend Postgres (`DB_TYPE: postgresdb`, schema `n8n`), persistencia ejecuciones (`EXECUTIONS_DATA_MAX_AGE=168h`), bootstrap n8n-bootstrap one-shot crea API key y carga workflows |
| F-00.4 | IMPLEMENTED | `infra/postgres/init.sql:1-280` + 11 migraciones en `infra/postgres/migrations/0001_baseline.sql … 0011_staged_embeddings_cache.sql` | AC genéricos; ya no es "esquema inicial" sino esquema versionado con 11 migraciones | Reescribir AC: tablas core (`usuarios`, `recursos`, `usuario_recursos`, `outbox_eventos`, `grafo_relaciones`, `sesiones_chat`, `mensajes_chat`, `notificaciones`, `demo_sessions`, `staged_embeddings_cache`), RLS habilitada y forzada, role `cerebro_service BYPASSRLS` para workers |
| F-00.5 | IMPLEMENTED | `docker-compose.yml:402-431` (redis-stack-server pinneado por digest, allkeys-lru, AOF) + `docker-compose.yml:343-401` (rabbitmq 3.13-management-alpine + `infra/rabbitmq/definitions.json`) | AC genéricos no mencionan RedisBloom (módulo `BF.RESERVE` usado en `src/ingestion/deduplicator.py:32`), AOF, ni `definitions.json` para colas pre-declaradas | Reescribir AC: redis-stack incluye RedisBloom (BF.RESERVE/BF.ADD); RabbitMQ usa `definitions.json` para pre-declarar exchanges (`cerebro.ingesta`, `cerebro.dlx`, `cerebro.procesamiento`) y colas con DLX |
| F-00.6 | IMPLEMENTED | `docker-compose.yml:445-475` (qdrant v1.17.1 con healthcheck TCP, config bind-mounted) + uso real en `src/data/embedder_worker.py:165` (`/collections/cerebro_chunks/points`) y `src/data/embedder_worker.py:218` (`/collections/cerebro_recursos/points`) | AC genéricos no mencionan dos colecciones (`cerebro_chunks` y `cerebro_recursos`) ni el filtrado por `tenant_id` en payload | Reescribir AC: dos colecciones — `cerebro_recursos` (1 vector por recurso) y `cerebro_chunks` (1 vector por trozo de ~600 tokens); aislamiento por filtro `tenant_id` en payload (no por colección separada); similitud coseno |
| F-00.7 | IMPLEMENTED | `docker-compose.yml:18-23,57-63,93-99,128-134,166-172,219-225,295-302,346-353,406-412,449-455,485-491,560-566,640-646,679-685,720-726,758-763,791-797,820-826` (`deploy.resources.limits.memory/cpus` en TODOS los servicios) — postgres 2G/2cpu, qdrant 2G/2cpu, scraper 1500M/2cpu, litellm 1G/1cpu, api/web 768M-384M | — | — |
| F-00.8 | IMPLEMENTED | `infra/ingestion.Dockerfile:9-11` (`useradd -u 1000 cerebro` + `USER cerebro`), `infra/scraper.Dockerfile:19-27` (cerebro + `PLAYWRIGHT_BROWSERS_PATH=/home/cerebro/.cache/ms-playwright`), `infra/api.Dockerfile:19-21`, `infra/frontend.Dockerfile:16-20` (`USER node`) | — | — |
| F-00.9 | IMPLEMENTED | `docker-compose.yml:435-443` (`command: -c max_connections=200 -c shared_buffers=512MB -c effective_cache_size=1536MB -c work_mem=8MB -c maintenance_work_mem=128MB`) | — | — |
| F-00.10 | IMPLEMENTED | `scripts/migrate.sh:1-90` (bash runner idempotente con `cerebro.schema_migrations`, `psql -1 ON_ERROR_STOP=1`, regex `^([0-9]+)_` con `10#${BASH_REMATCH[1]}`) + `infra/postgres/migrations/0001_baseline.sql` baseline espeja init.sql + `docker-compose.yml:178-198` (servicio `cerebro-migrate` one-shot con `condition: service_completed_successfully`) | — | — |
| F-00.11 | IMPLEMENTED | `docker-compose.yml:407` (`redis/redis-stack-server:latest@sha256:798ab84d…`), `docker-compose.yml:540` (`berriai/litellm:main-latest@sha256:7c311546…`), `docker-compose.yml:638` (`jaegertracing/all-in-one:latest@sha256:ab6f1a1f…`), `docker-compose.yml:756` (`kbudde/rabbitmq-exporter:latest@sha256:12f27d6d…`) | — | — |
| F-00.12 | IMPLEMENTED | `docker-compose.prod.yml:1-160` (TLS-ALPN Let's Encrypt, `ports: !reset []` para todos los internos, montaje de `/run/secrets/*` con `JWT_SECRET_FILE`, `LITELLM_KEY_FILE`, etc.) + `src/api/auth.py:11-20` (`_read_secret` lee `<VAR>_FILE` primero) | — | — |
| F-00.13 | IMPLEMENTED | `scripts/backup.sh:1-90` (TIMESTAMP ISO, pg_dump gzipped, snapshot Qdrant tarball, `BACKUP_DIR`/`BACKUP_RETENTION_DAYS`, `find -mtime` para pruning) | El AC dice que el script invoca `DELETE /collections/<col>/snapshots/<snap>` para limpiar residuos; el script real produce y rsyncea pero hay que verificar el cleanup en Qdrant | Confirmar en `scripts/backup.sh` (líneas posteriores a 40) que el `DELETE` snapshot dentro de Qdrant ocurre tras descargar |
| F-01.1 | IMPLEMENTED | `src/ingestion/deduplicator.py:14-66` (`RedisDeduplicator.is_new_item` con `BF.RESERVE` + `BF.ADD`, key `bf:tenant:{tenant_id}:ingestion`, fail-open con callback DLQ) + uso en `src/ingestion/main.py:140` | AC genéricos no describen el algoritmo Bloom Filter (error_rate=0.001, capacity=1M) ni el fail-open via DLQ callback | Reescribir AC: clave per-tenant, RedisBloom `BF.RESERVE`, fallback con `dlq_callback` cuando Redis falla; **además, el callsite `ingest_url` publica SIEMPRE a RabbitMQ aunque el bloom diga "duplicado" (`is_new` es solo un hint best-effort)** — esto contradice la lógica clásica de dedup y debe documentarse |
| F-01.2 | IMPLEMENTED | `src/ingestion/main.py:101-200` (`POST /ingest` con `IngestionRequest` Pydantic, rate-limit Redis INCR+EXPIRE atómico, publish a `RABBIT_QUEUE='url.nueva'`) + Traefik label `traefik.http.routers.ingestion.middlewares=global-ratelimit@docker` en `docker-compose.yml:36` | AC genéricos | Reescribir AC: endpoint async `POST /ingest` valida `IngestionRequest`, aplica rate-limit Redis por tenant (configurable `INGESTION_RATE_LIMIT_PER_MIN`), publica a cola `q.url.ingesta` vía exchange `cerebro.ingesta` |
| F-01.3 | IMPLEMENTED | `src/ingestion/main.py:200-260` (`POST /webhook/telegram/{token_hash}` con mapping Redis `telegram:{token_hash} → tenant_id`) + `src/api/main.py:1128-1158` (`PUT /profile/telegram` registra bot + setWebhook automático en Telegram) + servicio tailscale en `docker-compose.yml:820-840` perfil `telegram` para URL pública | AC genéricos | Reescribir AC: usuario registra bot via `PUT /profile/telegram` (valida token via getMe), API hace setWebhook a `<PUBLIC_INGESTION_URL>/webhook/telegram/{hash}`; tailscale funnel opcional para URL pública persistente |
| F-01.4 | IMPLEMENTED | `src/ingestion/main.py:300-360` (`POST /webhook/external` busca campos `url`/`link` y `extract_urls` regex; ingiere las primeras 5 URLs) | AC genéricos; soporta Zapier/Make/Slack/Chrome ext genéricamente, no hay extension del navegador específica del proyecto | Reescribir AC: webhook genérico extrae URLs de cualquier payload JSON (campos `url`/`link` o serialización de values); rate-cap implícito de 5 URLs por payload; **No hay extensión de navegador dedicada en el repo** — solo el webhook genérico que cualquier extension puede usar |
| F-01.5 | IMPLEMENTED | `infra/rabbitmq/definitions.json:54-120` (exchange `cerebro.dlx`, colas `dlq.url.fallidas` y `q.embeddings.fallidos`, bindings desde colas principales con `x-dead-letter-exchange`) + `src/dlq/dlq_manager.py:1-90` (DLQManager con `get_dead_letters`, `retry_dead_letters`) + uso en `src/ingestion/main.py:175-185` (publish a DLQ ante 429) | El AC genérico no recoge el cambio v1.1 (`q.embeddings.fallidos` añadida) ni la cola dedicada de notificaciones | Reescribir AC: DLX `cerebro.dlx` con dos colas (`dlq.url.fallidas`, `q.embeddings.fallidos`), TTL 24h en `q.url.ingesta`, DLQManager para retry; el historial v1.1 ya lo documenta — solo falta reflejarlo en los AC |
| F-01.6 | IMPLEMENTED | `src/ingestion/main.py:1-20` (`import redis.asyncio as aioredis`, `lifespan` context manager), `src/ingestion/main.py:120-130` (rate-limit `INCR`+`EXPIRE` atómico if count==1), `src/ingestion/main.py:42-43` (`extract_urls` strip `.,;:!?)"\'`), `src/ingestion/main.py:91-99` (CORS `allow_credentials=False` con `allow_origins=["*"]`), `docker-compose.yml:41-45` (healthcheck `urlopen('/health')`) | — | — |
| F-02.1 | IMPLEMENTED | `src/scraper/strategy.py:55-105` (clase abstracta `ScraperStrategy` + `BasicHttpStrategy` + `StealthPlaywrightStrategy`), `src/scraper/strategy.py:115-180` (`ScraperContext.execute` rutea según `source` (telegram/extension/dynamic/browser) y dominios JS-heavy, escala a Stealth ante HTTP 403/429/503 o contenido bloqueado/corto) | AC genéricos; faltan: dominios JS-heavy hardcodeados, reescritura medium.com→readmedium.com, escalado por contenido corto SPA, marcadores anti-bot en español e inglés | Reescribir AC: Strategy ABC con dos implementaciones, escalado automático a Stealth ante bloqueo/HTTP 4xx, reescritura medium→readmedium para Datadome bypass; **no se menciona la estrategia "IA proxy" del título — no existe en el código** |
| F-02.2 | IMPLEMENTED | `infra/litellm/config.yaml:1-80` (model_list con grupos `cerebro-lite`/`cerebro-pro`/`cerebro-embeddings`, fallback `num_retries: 3`, `allowed_fails: 1`, `cooldown_time: 15`, routing `least-busy`, cache Redis TTL 3600s) | AC genéricos; faltan detalles del provider (NVIDIA NIM), número de modelos por grupo, caché Redis | Reescribir AC: LiteLLM como gateway, 3 grupos de modelos (`cerebro-lite`, `cerebro-pro`, `cerebro-embeddings`) cada uno con 2+ backends NVIDIA NIM, fallback automático tras `allowed_fails`, cooldown 15s, cache Redis 1h |
| F-02.3 | PARTIAL | `src/scraper/worker.py:117-130` (LLM call con prompt JSON-only, parsing `json.loads(content)` con strip de ```), `src/scraper/worker.py:136-147` (fallback dict con campos por defecto si LLM falla) | El AC pide "JSON inquebrantable mediante Zod/Pydantic". El código parsea JSON pero **no valida con Pydantic schema** — la antigua `ScrapedDataSchema` ya no existe (tests skipped en `tests/test_schema_classification.py:4`). Solo se confía en la estructura del prompt + fallback dict | Marcar PARTIAL; reescribir AC para reflejar "parseo JSON con fallback determinístico si el LLM devuelve no-JSON o si falla; sin validación Pydantic estricta"; o **[CODE-BUG]**: faltan checks Pydantic post-parse |
| F-02.4 | IMPLEMENTED | `src/scraper/worker.py:80-115` (prompt con campos `category`, `volatility_score`, `estimated_useful_life_days`, `expiration_date`, `event_date`, `temporal_class`, `valor_archivistico`) + migración `infra/postgres/migrations/0006_temporal_class_y_strictness.sql:36-46` (columna `temporal_class` con CHECK `IN ('evento','referencia','evergreen')`) | AC genéricos no recogen los 3 niveles de `temporal_class` (evento/referencia/evergreen) ni `valor_archivistico` | Reescribir AC: el LLM clasifica en 8 categorías + volatility_score 4 niveles + temporal_class (3 valores) + estima `expiration_date` y `event_date` desde el contenido o pattern URL `YYYY/MM/DD` |
| F-02.5 | IMPLEMENTED | `src/scraper/worker.py:162-171` (worker mantiene `self.http: httpx.AsyncClient` inicializado en `connect()`, cerrado en `close()`) + `src/data/embedder_worker.py:99` (mismo patrón) + `src/api/main.py` (cliente global `_http`) | El AC dice que `_extract_metadata_with_llm` recibe `http` como parámetro; está así (`src/scraper/worker.py:69-70`) | — |
| F-03.1 | IMPLEMENTED | `infra/postgres/migrations/0001_baseline.sql:50-80` (tabla `outbox_eventos`) + `src/data/db.py:214-401` (`save_with_outbox` inserta recurso + link + evento atómicamente) + `src/data/outbox_publisher.py:1-200` (poller que lee `procesado=false` con `FOR UPDATE SKIP LOCKED`, publica a exchange `cerebro.procesamiento`, marca `procesado=true`) | AC genéricos | Reescribir AC: outbox con `INSERT en transacción` + poller dedicado (`outbox-worker` en compose) que publica eventos a RabbitMQ con `FOR UPDATE SKIP LOCKED`; idempotencia vía `procesado` boolean |
| F-03.2 | IMPLEMENTED | `src/data/embedder_worker.py:1-100` (worker que consume `q.recurso.embedder`, chunks de ~600 tokens con overlap), `src/data/embedder_worker.py:165` (upsert chunks a `cerebro_chunks`), `src/data/embedder_worker.py:218` (upsert recurso a `cerebro_recursos`) con payload incluyendo `tenant_id` | AC genéricos no mencionan chunking, ni que `embedder-worker` es un servicio separado | Reescribir AC: worker dedicado consume eventos `recurso.creado` desde fanout `cerebro.procesamiento`, chunkea texto en ~600 tokens con overlap 150 chars, llama LiteLLM `/embeddings` paralelo, upsertea en 2 colecciones Qdrant con `tenant_id` en payload para aislamiento |
| F-03.3 | IMPLEMENTED | `src/data/embedder_worker.py:303-340` (search KNN con `score_threshold: 0.92` contra `cerebro_recursos`, filtro `tenant_id`) + `src/data/embedder_worker.py:255-295` (`_clasificar_relacion_con_llm` con tipos `ES_UN`/`CONTRADICE`/`EXTIENDE`/`VUELVE_OBSOLETO`/`ASOCIACION_GENERAL` como fallback) + `src/data/db.py:520-565` (INSERT en `grafo_relaciones` con tipo + inversa `OBSOLETO_POR`/`EXTENDIDO_POR`; flag `estado='obsoleto'` cuando `VUELVE_OBSOLETO`/`CONTRADICE` con doc más reciente) | AC concretos coinciden con el código | — |
| F-03.4 | IMPLEMENTED | `infra/postgres/migrations/0001_baseline.sql:139-185` (`ALTER TABLE … ENABLE ROW LEVEL SECURITY` + `FORCE ROW LEVEL SECURITY` en 5 tablas con policy `USING (tenant_id = current_setting('app.tenant_id', true))`) + `src/api/database.py:122-124,327-330` (`SELECT set_config('app.tenant_id', $1, true)` antes de queries) + role `cerebro_service NOLOGIN BYPASSRLS` para workers | AC genéricos no documentan el role `cerebro_service` ni el patrón `set_config('app.tenant_id', …, true)` (LOCAL setting) | Reescribir AC: RLS habilitada + FORZADA en `usuario_recursos`, `sesiones_chat`, `mensajes_chat`, `grafo_relaciones`, `outbox_eventos`; policy via `current_setting('app.tenant_id', true)`; role `cerebro_service` con BYPASSRLS para workers internos; tabla `recursos` es global (sin RLS) por dedup, tabla `usuarios` también (auth a nivel API) |
| F-03.5 | IMPLEMENTED | `src/data/export_manager.py:1-260` (`VaultExporter.generate_vault_zip` produce ZIP con `index.md`, `CLAUDE.md`, `wiki/log.md`, `wiki/hot.md`, `raw/<slug>.txt`, `wiki/{sources,entities,concepts}/<slug>.md`) + tests `tests/test_f071_exporter.py:49-50` | AC genéricos; el VaultExporter solo se instancia desde tests — **no hay endpoint API `/export` que lo invoque** (grep negativo). El backlog dice "Standalone sin Vendor Lock-In" — la lógica existe pero no se expone al usuario en el frontend | Marcar PARTIAL (no IMPLEMENTED) o reescribir AC para clarificar que `VaultExporter` es una capa interna no expuesta vía HTTP; el zip se genera/probará desde tests/CLI hasta que se cablee endpoint |
| F-04.1 | IMPLEMENTED | `src/api/main.py:1697-1880` (`POST /chat` con `ChatRequest` Pydantic, RAG via Qdrant search, streaming SSE con `StreamingResponse(media_type="text/event-stream")`) + frontend `src/frontend/app/(app)/chat/page.tsx` | AC genéricos; el chat hace **streaming SSE** (no JSON síncrono) y consume RAG (busca chunks Qdrant + fuentes) | Reescribir AC: endpoint `/chat` abre StreamingResponse SSE; emite tokens incrementales + bloque final con fuentes RAG; frontend renderiza con react-markdown; aislamiento por tenant via Qdrant filter |
| F-04.2 | IMPLEMENTED | `src/api/main.py:1977-2030` (`/chats` CRUD con paginación `?limit=&offset=`) + `infra/postgres/migrations/0001_baseline.sql` (tablas `sesiones_chat`, `mensajes_chat` con RLS) + uso de Redis para session cookies y CSRF (`cerebro_session`, `cerebro_refresh`, `cerebro_csrf`) | AC genéricos; la "persistencia" real está en Postgres (sesiones_chat/mensajes_chat) + Redis para session cookies y refresh tokens. F-04.6 ya cubre la parte Postgres concreta | Reescribir AC: sesiones persisten en Postgres (`sesiones_chat`) con paginación; Redis se usa para session cookie + refresh token (`cerebro_session`/`cerebro_refresh`); las "reanudaciones sub-ms" vienen del Postgres pool + cookie httpOnly |
| F-04.3 | IMPLEMENTED | `src/frontend/app/(app)/` con páginas `chat/`, `demo/`, `expired/`, `ingest/`, `kb/`, `profile/`, `quarantine/` + componente `_NotificationsBell.tsx` + layout autenticado | AC genéricos; el "dashboard" no es una página unificada con métricas sino un set de páginas por área (KB, ingest, quarantine, expired, profile) | Reescribir AC: panel administrativo dividido en secciones `(app)/kb`, `(app)/quarantine`, `(app)/expired`, `(app)/profile`, `(app)/ingest`, `(app)/chat`, `(app)/demo` con sidebar de navegación; Notifications Bell en cabecera |
| F-04.4 | PARTIAL | `src/data/db.py:103-139` (`update_session_context`/`get_session_context` lee/escribe campo `contexto_comprimido`) + `infra/postgres/migrations/0001_baseline.sql:106-116` (columna `contexto_comprimido` en `sesiones_chat`) | La infraestructura existe (columna `contexto_comprimido`, getters/setters), pero **no hay lógica de compactación activa** en `src/api/main.py` que genere ese resumen tras X mensajes. El test `tests/test_f044_compaction.py` está skipped (`Symbols removed from src.ui.chatbot`). El historial se envía completo al LLM (ChatRequest tiene `max_length=100` mensajes) | Marcar PARTIAL; falta el agente/job que comprima el historial cuando supera N tokens; el chat actualmente respeta el cap de Pydantic (100 mensajes) sin sliding window |
| F-04.5 | NOT_STARTED | — | El test `tests/test_f045_function_calling.py` está skipped (`Pendiente refactor a usuario_recursos tras migración 0002`). El endpoint `/chat` no usa `tools=[]` ni `tool_choice` (grep negativo en `src/api/main.py`); el LLM no tiene function calling activo contra el histórico RAG crudo | Marcar NOT_STARTED; eliminar de AC la parte "function calling activo" o reescribir como roadmap futuro |
| F-04.6 | IMPLEMENTED | `src/api/main.py:1977-2030` (endpoints `/chats`, `/chats/{id}/messages` con paginación `{items,total,limit,offset}`), `src/api/models.py:139-145` (`ChatMessage.content: max_length=32_000` y `ChatRequest.messages: max_length=100`), `src/api/main.py:1380,1394,1407,1425` (Query `limit` con `le=500`), módulos `src/api/{auth,database,models}.py`, frontend `chat/page.tsx:199` (`URL.revokeObjectURL`) | El AC menciona "40k chars" para content; el código limita a **32k** (`max_length=32_000` en `ChatMessage.content`). Drift menor numérico | Actualizar AC: `max_length=32_000` (~8k tokens), `max_length=100` mensajes, `Query(limit, le=500)` para colecciones grandes y `le=200` para chats |
| F-04.7 | IMPLEMENTED | `src/frontend/app/error.tsx` (boundary global) + `src/frontend/app/(app)/error.tsx` (boundary del área autenticada) | — | — |
| F-05.1 | IMPLEMENTED | `src/data/audit_cron.py:84-185` (`run_audit_cron` fase A `activo→cuarentena` por `fecha_caducidad <= NOW()::DATE`, fase B `cuarentena→expirado` por `quarantine_grace_until <= NOW()::DATE`, ambas idempotentes) + workflow `infra/n8n/workflows/audit_cron_daily.json` (cron schedule diario que llama `POST /admin/audit-cron`) | AC genéricos; el cron actual usa **migración 0006/0007** (`temporal_class='evento'`, `audit_policy` JSONB per-tenant) — la lógica original de "cruce de volatilidad" se ha refinado a un filtro determinístico por `fecha_caducidad IS NOT NULL` | Reescribir AC: dos fases (cuarentena + expirado), filtra por `temporal_class='evento'` + `fecha_caducidad`, idempotente por estado, gracia configurable `OBSOLESCENCE_GRACE_DAYS`; ejecutado diariamente vía workflow n8n `audit_cron_daily` |
| F-05.2 | IMPLEMENTED | `src/api/main.py:1391-1426` (`GET /resources/quarantine`, `GET /resources/expired`, `GET /notifications`) + `src/api/main.py:1478-1530` (`POST /resources/{id}/rescue|quarantine|expire`, `DELETE /resources/{id}`) + `src/frontend/app/(app)/quarantine/`, `src/frontend/app/(app)/expired/` | AC genéricos | Reescribir AC: bandeja de cuarentena en `/quarantine` con acciones rescue/expire/delete protegidas por CSRF; pre-borrado tras `quarantine_grace_until` (gracia 30d default) |
| F-05.3 | IMPLEMENTED | `src/api/main.py:1456-1475` (`POST /resources/audit-now` invoca `run_audit_cron` con rate-limit 5/min por tenant + CSRF) | AC genéricos; el "audit IA" del título no es un LLM revisando recursos sino el mismo `run_audit_cron` SQL invocado manualmente — esto contradice el título "Basada en IA" | Reescribir AC eliminando "Basada en IA" o aclarar: el botón "Auditar ahora" en `/profile` dispara la misma auditoría temporal SQL del cron (no hay agente IA); rate-limit 5/min/tenant |
| F-06.1 | IMPLEMENTED | `docker-compose.yml:660-695` (servicio `otel-collector` v0.150.1 con config bind-mount) + `src/telemetry.py:11` (`configure_telemetry` invocado desde cada servicio) | AC genéricos | Reescribir AC: otel-collector recibe OTLP gRPC/HTTP (`:4317`/`:4318`) de todos los servicios Python (api, ingestion, scraper, embedder, outbox, notifier); reenvía a Jaeger + Prometheus |
| F-06.2 | IMPLEMENTED | `docker-compose.yml:638-660` (servicio `jaeger` con `COLLECTOR_OTLP_ENABLED=true`, UI en `:16686`, `MEMORY_MAX_TRACES=10000`) | AC genéricos; el almacenamiento es **in-memory** (no persistente) — Drift | Documentar el trade-off: traces ephemeral en memoria (suficiente para troubleshooting reciente, no para auditoría histórica) |
| F-06.3 | IMPLEMENTED | `docker-compose.yml:697-735` (servicio `prometheus` v3.11.2 con `prometheus.yml` + `alert.rules.yml` montado) + `infra/prometheus/alert.rules.yml:1-95` (9 alertas: HighLLMLatency, DLQ_Filling_Up, HighErrorRateIngestion, APIHighP99Latency, IngestionQueueBacklog, EmbeddingsDLQAny, PostgresConnectionsHigh, WorkerStuck, VolumeDiskHigh) + `docker-compose.yml:737-770` (servicio `grafana` con dashboards provisioning) + exporters (`rabbitmq-exporter`, `redis-exporter`, `postgres-exporter`) | El histórico v1.1 ya documenta las 6 alertas nuevas; el AC genérico no lista las alertas | Reescribir AC con las 9 alertas concretas (lo que ya hace el historial v1.1 más 3 adicionales) |
| F-06.4 | IMPLEMENTED | `src/ingestion/main.py:120-130` (`INCR + EXPIRE` atómico por tenant con HTTP 429), `src/api/main.py:645-652` (`_rate_limit` helper), múltiples `_rate_limit` calls para `/auth/*`, `/chat`, `/audit`, `/demo-start`. F-01.6/F-08.4 son la implementación concreta | AC genéricos | Marcar SUPERSEDED_BY F-01.6 + F-08.4 (los dos backlogs concretos que materializan esta política) |
| F-06.5 | IMPLEMENTED | `src/observability/logging.py:1-80` (`JsonFormatter` + `configure_json_logging(service)`) + uso en `src/api/main.py:56`, `src/ingestion/main.py:17` | El AC dice "los workers (scraper/embedder/outbox) son follow-up trivial" — y efectivamente, **los workers todavía usan `logging.basicConfig(level=logging.INFO, format='%(asctime)s …')`** (`src/scraper/worker.py:308`, `src/data/embedder_worker.py:18`, `src/notifier/worker.py:31`) — no llaman a `configure_json_logging`. Solo configuran OTel telemetry | Marcar PARTIAL: cerebro-api e ingestion-api usan JSON logging; los 4 workers (scraper, embedder, outbox, notifier) siguen con basicConfig plano. Reescribir AC para reflejar el follow-up pendiente |
| F-06.6 | IMPLEMENTED | `src/data/heartbeat.py:1-42` (`heartbeat_loop` con TTL 45s, interval 15s, `start_heartbeat` retorna asyncio.Task cancelable) + uso en `src/scraper/worker.py:171,300-302`, `src/data/embedder_worker.py:99` (no se ve en snippet pero `from src.data.heartbeat import start_heartbeat`), `src/data/outbox_publisher.py:39`, `src/notifier/worker.py` + healthchecks compose `docker-compose.yml:60-65,100-105,138-143,170-175` (lectura `worker:<name>:heartbeat`) | — | — |
| F-07.1 | IMPLEMENTED | `src/data/export_manager.py:85-200` (estructura `index.md`, `CLAUDE.md`, `wiki/log.md`, `wiki/hot.md`, `raw/<slug>.txt`, `wiki/{sources,entities,concepts}/<slug>.md`) | Como F-03.5: la clase existe pero no hay endpoint `/export` que la dispare desde la UI. Drift detectado: AC dicen "el usuario puede desencadenar" pero no hay UI/endpoint público | Marcar PARTIAL o documentar que la generación es accesible solo desde tests/CLI hasta cablear endpoint |
| F-07.2 | IMPLEMENTED | `src/data/export_manager.py:210-235` (lee `grafo_relaciones`, genera links `[[Entidad]]`, callouts `> [!info] Contradice a:`, `> [!important] Vuelve obsoleto a:`, `> [!note] Extiende a:`) | Igual que F-07.1: el código está pero sin endpoint de disparo | Marcar PARTIAL idem |
| F-07.3 | IMPLEMENTED | `src/data/export_manager.py:137-148` (`wiki/hot.md` con `contexto_comprimido` de cada sesión + título + último acceso) + `src/data/export_manager.py:117-135` (`wiki/log.md` con timeline de outbox_eventos) | Como `contexto_comprimido` está vacío (F-04.4 PARTIAL — no hay compactación activa), el `hot.md` exportado solo tendrá títulos sin contexto compactado real | Marcar PARTIAL hasta que F-04.4 active la compactación; o reescribir AC para reflejar que hot.md contiene títulos+timestamps de sesiones aunque el `contexto_comprimido` esté vacío |
| F-08.1 | IMPLEMENTED | `src/api/main.py:801-848` (`POST /auth/register`, `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `GET /auth/me`) + `src/api/auth.py:62-76` (JWT HS256 con `ACCESS_TOKEN_EXPIRE_MINUTES=30`) + `src/api/main.py:737-741` (`rate_limit_login` 5/min/IP, `rate_limit_register` 3/h/IP) + bcrypt password hashing | AC genéricos | Reescribir AC con detalles: bcrypt, JWT HS256 30min access + 30d refresh, cookies httpOnly, rate-limit por IP, refresh rotation en Redis |
| F-08.2 | IMPLEMENTED | `src/api/main.py:495-530` (`get_current_user` extrae `tenant_id` desde JWT claim, no desde request) + `src/api/auth.py:62-66` (token contiene `tenant_id`). Frontend nuevo (Next.js) no expone selector de tenant (grep negativo); legacy `src/ui/chatbot.py:252` mantiene `st.selectbox("Tenant", …)` para KB filter — code legacy no enrutado | El backlog dice "eliminación de selector de Tenant"; el Streamlit legacy aún lo expone para filtros admin, pero el flujo principal (Next.js) ya no | Reescribir AC: tenant viene únicamente del JWT en el frontend Next.js; **[CODE-BUG/CLEANUP]**: `src/ui/chatbot.py` (Streamlit) sigue exponiendo selectbox de tenant — borrar o aislar como herramienta admin |
| F-08.3 | IMPLEMENTED | `src/api/main.py:534-555` (`_set_session_cookies` setea `cerebro_session httpOnly` + `cerebro_csrf` legible-JS), `src/api/main.py:615-629` (`verify_csrf` valida doble submit), 12+ endpoints state-changing con `_csrf=Depends(verify_csrf)` (líneas 1132, 1165, 1199, 1439, 1450, 1459, 1482, 1495, 1512, 1524, 1615, 1936, 1949, 1978, 2008, 2026), frontend `src/frontend/lib/api.ts:7-30` (`CSRF_COOKIE`, `CSRF_HEADER`, helper que echa X-CSRF-Token), `src/api/auth.py:11-20` (`JWT_SECRET_FILE` soportado) | — | — |
| F-08.4 | IMPLEMENTED | `src/api/main.py:645-652` (`_rate_limit` INCR+EXPIRE atómico con fail-open `if _redis is None: return`), `src/api/main.py:737-742,770-783` (`rate_limit_login` 5/60s, `rate_limit_register` 3/3600s, `rate_limit_chat` 30/60s, `rate_limit_audit` 5/60s), `src/api/main.py` (`_client_ip` honra `X-Forwarded-For` — buscar) | — | — |
| F-09.1 | NOT_STARTED | — | El frontend Next.js no tiene i18n configurado: `src/frontend/package.json` no incluye `next-intl`/`i18next`/`react-i18next`; grep negativo para `useTranslation`, `i18n`, `locale` en `src/frontend/app/` y `src/frontend/components/`. Todos los textos están hardcoded en español/mixto | Marcar NOT_STARTED |
| F-09.2 | PARTIAL | Uso de `aria-label` en 4 archivos del frontend (`(app)/chat/page.tsx`, `(marketing)/_components/{CTABanner,UseCases,Hero}.tsx`) | Hay uso puntual de ARIA en marketing y chat, pero no hay auditoría Lighthouse documentada ni soporte sistemático WCAG (focus-visible, contraste, skip-links) | Marcar PARTIAL; falta auditoría Lighthouse + contraste WCAG AA + focus rings consistentes + skip-to-content |

**Verificación de filas: 54 filas (F-00.1 a F-00.13 = 13, F-01.1 a F-01.6 = 6, F-02.1 a F-02.5 = 5, F-03.1 a F-03.5 = 5, F-04.1 a F-04.7 = 7, F-05.1 a F-05.3 = 3, F-06.1 a F-06.6 = 6, F-07.1 a F-07.3 = 3, F-08.1 a F-08.4 = 4, F-09.1 a F-09.2 = 2 → 13+6+5+5+7+3+6+3+4+2 = 54). ✓**

## Propuestas de update detalladas

Las plantillas Gherkin genéricas de F-00.1..6, F-01.1..5, F-02.1..4, F-03.1..2/4..5, F-04.1..5, F-05.1..3, F-06.1..4, F-08.1..2 (≈ 23 fichas) deben reescribirse para reflejar el comportamiento real ya implementado. Los diffs detallados más importantes:

### F-02.3 · Pipeline Zero-Defect (Pydantic validation)

**Estado**: PARTIAL
**Razón del update**: el código hace `json.loads` y fallback dict pero no usa Pydantic.

```diff
- - [ ] **Happy Path:**
-   **Dado que** la entrada es válida,
-   **Cuando** se inyecta en el componente,
-   **Entonces** ejecuta la operación acorde a `2_architecture_risks.md`.
+ - [ ] **Happy Path (JSON parsing tolerante):**
+   **Dado que** el LLM devuelve respuesta en `_extract_metadata_with_llm`,
+   **Cuando** llega el chunk con campos `category`, `volatility_score`, …,
+   **Entonces** `json.loads(content)` parsea tras strip de fences ```json
+   y los workers usan el dict directo. Si el LLM falla, fallback dict
+   determinístico con `temporal_class='evento'`, `volatility_score='media'`,
+   `estimated_useful_life_days=30`.
+ - [ ] **Pendiente Pydantic schema**:
+   Reintroducir `ScrapedDataSchema` (BaseModel con `Literal` para `category`
+   y `volatility_score`) que valide el dict antes de pasar a `save_with_outbox`.
+   Hoy el chequeo de tipos lo hace el CHECK constraint de `temporal_class`
+   en SQL y no hay validación de category/volatility en Python.
```

### F-04.1 · Chatbot RAG (SSE drift)

**Estado**: IMPLEMENTED (con drift)
**Razón del update**: el chat usa SSE streaming, no JSON síncrono.

```diff
- - [ ] **Happy Path:**
-   **Dado que** la entrada es válida,
-   **Cuando** se inyecta en el componente,
-   **Entonces** ejecuta la operación acorde a `2_architecture_risks.md`.
+ - [ ] **Happy Path (streaming RAG):**
+   **Dado que** el usuario envía un mensaje a `POST /chat`,
+   **Cuando** el backend hace RAG (busca top-k chunks en Qdrant filtrados
+   por `tenant_id`) y arma el contexto LiteLLM,
+   **Entonces** abre `StreamingResponse(media_type="text/event-stream")`
+   y emite tokens vía `client.stream(...)` hasta cerrar la conexión; el
+   frontend renderiza con react-markdown.
+ - [ ] **Persistencia post-stream**:
+   Tras el stream, el frontend hace `POST /chats/{id}/messages` para
+   guardar user+assistant+sources en `mensajes_chat` (Postgres).
+ - [ ] **Edge Case (LLM falla)**:
+   Si LiteLLM devuelve 5xx o el stream se corta, el frontend captura
+   y muestra error sin desconectar la sesión. El backlog F-04.6 cubre
+   el `console.warn` ante chunks SSE inválidos.
```

### F-04.4 · Compactación de Largo Contexto

**Estado**: PARTIAL
**Razón del update**: infraestructura DB lista, lógica de compactación ausente.

```diff
- - [ ] **Happy Path:**
-   **Dado que** la entrada es válida,
-   ...
+ - [ ] **Infraestructura presente** (✅):
+   Columna `sesiones_chat.contexto_comprimido TEXT` lista. Helpers
+   `update_session_context`/`get_session_context` en `src/data/db.py`.
+ - [ ] **Compactación activa** (❌, pendiente):
+   Trigger: cuando los mensajes del chat superen N tokens (configurable),
+   un job comprime los más antiguos y los guarda en `contexto_comprimido`;
+   el endpoint `/chat` carga este texto al sysprompt para preservar
+   continuidad sin enviar todo el historial. Actualmente el chat envía
+   los 100 mensajes (cap Pydantic) sin sliding window.
```

### F-04.5 · Function Calling

**Estado**: NOT_STARTED
**Razón**: el chat no usa `tools=[]` y el test está skipped.

```diff
- - [ ] **Happy Path:**
-   ...
+ - [ ] **No implementado**:
+   El endpoint `/chat` no envía `tools=[{...}]` ni interpreta
+   `tool_calls` en la respuesta de LiteLLM. El RAG actual ya inyecta
+   chunks relevantes en el sysprompt — si esto se considera suficiente,
+   marcar la ficha como `OBSOLETE` (objetivo cubierto por RAG estándar);
+   si se quiere function calling real, abrir tarea para añadir
+   `search_raw_history(query)` como tool.
```

### F-04.6 · Persistencia chats (max_length drift)

**Estado**: IMPLEMENTED (con drift menor)

```diff
-   **Cuando** Pydantic valida,
-   **Entonces** la respuesta es `422 Unprocessable Entity` ...
-   Lo mismo para `GET /resources?limit=999999`.
+   **Cuando** Pydantic valida,
+   **Entonces** la respuesta es `422 Unprocessable Entity`:
+   - `ChatMessage.content: max_length=32_000` (≈ 8k tokens, no 40k chars como decía la primera redacción)
+   - `ChatRequest.messages: min_length=1, max_length=100`
+   - `GET /resources?limit=999999` → `Query(le=500)` rechaza con 422
+   - `GET /chats?limit=999999` → `Query(le=200)` rechaza con 422
```

### F-05.3 · Audit Basada en IA

**Estado**: IMPLEMENTED (con drift fuerte)

```diff
- # [SECURITY] F-05.3 — Auditoría Exhaustiva Basada en IA por encargo puntual ...
+ # [SECURITY] F-05.3 — Auditoría manual a petición del usuario (mismo cron SQL que F-05.1)

- - [ ] **Happy Path:** ...
+ - [ ] **Happy Path:**
+   **Dado que** el usuario hace clic en "Auditar ahora" desde `/profile`,
+   **Cuando** el frontend llama `POST /resources/audit-now` con CSRF,
+   **Entonces** ejecuta la misma `run_audit_cron()` que el workflow n8n
+   diario (F-05.1) — sin LLM, sin razonamiento — y devuelve
+   `{trace_id, cuarentenados, expirados}`. Rate-limit 5/min/tenant.
+ - El nombre original ("Basada en IA") ya no aplica: la auditoría es
+   SQL puro determinístico. Conservar el código del backlog `F-05.3`
+   pero quitar "Basada en IA" del título.
```

### F-06.5 · Logging JSON (workers pendientes)

**Estado**: PARTIAL

```diff
+ **Cableado actual**:
+   ✅ cerebro-api (src/api/main.py:56)
+   ✅ ingestion-api (src/ingestion/main.py:17)
+   ❌ scraper-worker (usa logging.basicConfig en src/scraper/worker.py:308)
+   ❌ embedder-worker (logging.basicConfig en src/data/embedder_worker.py:18)
+   ❌ outbox-worker (sin configure_json_logging en src/data/outbox_publisher.py)
+   ❌ notifier-worker (logging.basicConfig en src/notifier/worker.py:31)
+ Follow-up: añadir `configure_json_logging("<service>")` al top de cada
+ worker y eliminar el `logging.basicConfig`.
```

### F-08.2 · Tenant único (legacy Streamlit)

**Estado**: IMPLEMENTED (con drift)

```diff
+ **Implementado en Next.js**: ✅ `tenant_id` solo se lee del JWT
+ (`src/api/main.py:495-530`, `src/api/auth.py:62-66`). Frontend
+ Next.js no expone selector de tenant.
+ **Drift**: `src/ui/chatbot.py:252` (Streamlit legacy) aún expone
+ `st.selectbox("Tenant", …)` como filtro KB. Como el frontend principal
+ es Next.js, el Streamlit es UX administrativa interna; aun así, ese
+ selector debe etiquetarse "admin only" o eliminarse.
```

### F-09.1 · Multilenguaje

**Estado**: NOT_STARTED

```diff
+ **Estado real**: no implementado.
+   - `package.json` sin deps i18n.
+   - Textos hardcoded en español + algún inglés mezclado.
+ Para cerrar el backlog: añadir `next-intl` o equivalente, crear
+ `messages/{es,en}.json`, switch en `/profile`.
```

### F-09.2 · Accesibilidad

**Estado**: PARTIAL

```diff
+ **Hecho**: uso puntual de `aria-label` en 4 archivos del frontend.
+ **Falta**:
+   - Audit Lighthouse documentado
+   - Skip-to-content link
+   - Focus rings consistentes (`focus-visible:ring-2`)
+   - Verificación de contraste WCAG AA en paleta Tailwind
+   - Soporte completo de teclado (Tab order)
```

### F-03.5 / F-07.1 / F-07.2 · Exporter Vault (sin endpoint)

**Estado**: IMPLEMENTED (lógica) / PARTIAL (acceso)

```diff
+ **Drift**: la clase `VaultExporter` (src/data/export_manager.py)
+ produce todo el ZIP requerido por F-07.1/F-07.2/F-07.3 con la
+ estructura LLM Wiki correcta, pero **no hay endpoint HTTP que la
+ exponga al usuario**. Solo se invoca desde tests (`tests/test_f071_exporter.py`).
+ Para "Soporte nativo y rápido de exportación masiva" (F-03.5):
+ añadir `GET /export/vault.zip` autenticado que streamee
+ `generate_vault_zip(tenant_id)` con `Content-Disposition: attachment`.
```

## Hallazgos [CODE-BUG]

Bugs detectados durante el audit que no son drift de backlog:

- **[CODE-BUG]** `src/ingestion/main.py:140` — el handler `/ingest` **siempre publica a RabbitMQ** incluso cuando el Bloom Filter dice "duplicado". El comentario lo justifica con un caso de inconsistencia tras reset de DB, pero esto **rompe el contrato esperado de F-01.1** ("evitar múltiples ingestas idénticas"): cada ingesta de URL duplicada ahora gasta un scrape o al menos llega al worker. El scraper resuelve la idempotencia via `find_existing_recurso_by_url`, pero la cola y el worker sí ven el mensaje duplicado. Posible mitigación: hacer la republicación condicional con un flag `force_relink=true` por defecto desactivado, y mantener el comportamiento estricto cuando bloom diga "duplicado".

- **[CODE-BUG]** `tests/test_schema_classification.py:4` y `tests/test_f044_compaction.py:4` y `tests/test_f045_function_calling.py:12` — tres tests permanecen skipped indefinidamente con motivo "símbolo removido / pendiente refactor". O bien (a) reescribirlos contra la API actual, (b) eliminarlos, o (c) abrir tickets explícitos. Tener tests skipped en repo enmascara cobertura real.

- **[CODE-BUG]** `src/ingestion/main.py:262-302` — coexisten **dos endpoints `/webhook/telegram`** sin path-param y `/webhook/telegram/{token_hash}`. El primero (sin hash) acepta cualquier mensaje y publica con `tenant_id=f"tg_{chat_id}"`. Esto contradice F-08.2 (tenant único por usuario): un atacante que conoce el chat_id de otra cuenta podría inyectar URLs en su KB con un POST directo a `/webhook/telegram` (sin autenticación). El endpoint sin hash debe eliminarse o protegerse con allowlist.

- **[CODE-BUG]** `src/data/audit_cron.py:122,134` — `fecha_caducidad <= NOW()::DATE` y `quarantine_grace_until <= NOW()::DATE`. La columna `fecha_caducidad` y `quarantine_grace_until` son `DATE` (no TIMESTAMPTZ), así que la comparación con `NOW()::DATE` está bien. **No es bug**, retracto el hallazgo: este patrón es correcto. (Lo marco aquí para documentar la verificación, no como bug confirmado.)

- **[CODE-BUG]** `src/scraper/worker.py:308` y `src/data/embedder_worker.py:18` y `src/notifier/worker.py:31` — los workers llaman `logging.basicConfig(level=logging.INFO, format='%(asctime)s …')` **sin** invocar `configure_json_logging`, por lo que sus logs llegan a stdout en formato plano en lugar de JSON estructurado. Esto rompe parsing por trace_id/tenant_id en Loki/Datadog y contradice F-06.5 que está marcado IMPLEMENTED en el resumen general. Wiring trivial: añadir `from src.observability.logging import configure_json_logging` + `configure_json_logging("<worker-name>")` al top.

- **[CODE-BUG]** `src/ui/chatbot.py` — el código Streamlit legacy (252 referencias a `st.*`) sigue en el repo, importado por algunos tests (`tests/test_f044_compaction.py:9` lo referencia explícitamente con `async_update_session_context`). Si Streamlit ya no se usa en producción, este módulo debería marcarse `# DEPRECATED` o eliminarse para reducir confusión y superficie de ataque (el selectbox de tenant que contradice F-08.2 vive ahí).

- **[CODE-BUG]** Backlogs con sufijo `_anterior.md` en sus enlaces de dependencia (F-00.2..6, F-01.2..5, F-02.2..4, F-03.2..5, F-04.2..5, F-05.2..3, F-06.2..4) referencian archivos que no existen (`F-00.1_anterior.md`, etc.). El path correcto es el filename completo del backlog anterior (ej. `F-00.1_configuracion-de-docker-compos.md`). Es problema de plantilla, no de runtime, pero rompe la navegación inter-backlog en cualquier renderer de Markdown.
