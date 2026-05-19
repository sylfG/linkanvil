# Review · docs/src/4-arquitectura.md · 2026-05-19

**Auditor**: docs-reality-auditor
**Doc revisado**: `docs/src/4-arquitectura.md`
**Áreas de código verificadas**:
- `src/api/auth.py`, `src/api/main.py` (endpoints), `src/api/database.py` (pool/search_path)
- `src/data/db.py` (`save_with_outbox`, RLS), `src/data/outbox_publisher.py`, `src/data/audit_cron.py`
- `src/notifier/worker.py` (no existe `src/notifier/main.py`)
- `src/observability/logging.py`, `infra/otel/config.yaml`, `infra/prometheus/alert.rules.yml`, `infra/grafana/`
- `src/data/embedder_worker.py`, `src/scraper/strategy.py`
- `infra/postgres/migrations/0001_baseline.sql` … `0011_staged_embeddings_cache.sql`
- `docker-compose.yml`, `docker-compose.prod.yml`, `scripts/migrate.sh`, `scripts/backup.sh`

**Versión del repo**: `develop` @ `7c723f3`

## Resumen
- **2 CRITICAL**, **4 HIGH**, **6 MEDIUM**, **2 LOW**, **1 UNVERIFIED**
- 0 hallazgos [CODE-BUG]
- **Veredicto: RED** (hay CRITICAL: el diagrama RAG y la sección §3.1 ocultan el modelo de chunks que es el real, y la sección §4 omite endpoints clave del flujo de auth `/auth/demo-start` y `/auth/refresh` que cambian el comportamiento mostrado en el diagrama).

---

## Hallazgos

### [CRITICAL] §3.1 — "Un punto por (recurso_id, tenant_id)" no es el modelo real de Qdrant
- **Ubicación**: línea 230 (§3.1, último bullet del bloque Qdrant)
- **Lo que dice el doc**:
  > "**Un punto por `(recurso_id, tenant_id)`** con `point_id = uuid5(ns, "<recurso_id>:<tenant_id>")`. El payload incluye `tenant_id` y `recurso_id` separados, así el filtrado per-tenant se hace sin JOIN adicional. Cuando un segundo tenant reusa una URL, su punto se crea **copiando el vector** del primero (sin re-embedding) y solo se varía el payload."
- **Realidad en el código**: existen DOS colecciones en Qdrant — `cerebro_recursos` (1 punto por recurso/tenant, "resumen") y `cerebro_chunks` (N puntos por chunk del contenido, ~1200 chars con overlap 150). Los chunks son la fuente real del RAG en `/chat` y el embedder chunkea contenido y emite múltiples puntos:
  - `src/api/main.py:65` → `COLLECTION = "cerebro_recursos"`
  - `src/api/main.py:212` → upsert en `cerebro_chunks` (staging)
  - `src/api/main.py:295` → delete iterativo en `("cerebro_chunks", "cerebro_recursos")`
  - `src/api/main.py:1748-1753` → búsqueda del `/chat` se hace contra `cerebro_chunks` ("cerebro_chunks tiene un punto por trozo de ~600 tokens")
  - `src/data/embedder_worker.py:38-39, 42-79, 137-169` → `_chunk_text(target_chars=1200, overlap_chars=150)`, `_qdrant_chunk_point_id(recurso_id, tenant_id, chunk_idx)`, `_inject_chunks_to_qdrant` upsertea N puntos por recurso
- **Cambio sugerido**:
  ```markdown
  **Dos colecciones en Qdrant:**
  - `cerebro_recursos` — UN punto por `(recurso_id, tenant_id)` con el **resumen** (vector del título+resumen). Usado por flujos legacy y por el delete cascade. `point_id = uuid5(ns, "<recurso_id>:<tenant_id>")` (`src/api/main.py:72-73`).
  - `cerebro_chunks` — **N puntos por recurso**, uno por chunk del contenido (~1200 chars con overlap 150). Es la colección que consulta el `/chat` para RAG. `point_id = uuid5(ns, "<recurso_id>:<tenant_id>:chunk:<idx>")` (`src/data/embedder_worker.py:38-39`, chunking en `_chunk_text` en `src/data/embedder_worker.py:42-79`).

  Cuando un segundo tenant reusa una URL, sus chunks se crean **copiando los vectores existentes** del recurso (sin re-embedding) — el embedder hace `scroll filter recurso_id` y reinyecta cambiando solo `payload.tenant_id` (`src/data/embedder_worker.py:171-209`).
  ```

### [CRITICAL] §2.2 — El diagrama del Chat RAG omite que se busca en `cerebro_chunks`
- **Ubicación**: líneas 154-179 (mermaid del flujo RAG)
- **Lo que dice el doc**:
  > "AP->>QD: búsqueda coseno > 0.85 (filtrado por tenant_id)" + nota "Contexto rico construido aquí — el payload de Qdrant solo trae title/url/category, el resumen completo vive en Postgres."
- **Realidad en el código**: la búsqueda real se hace en `cerebro_chunks` y el payload del chunk **sí contiene `chunk_text`** (el texto completo del chunk), no solo title/url/category. Es decir, el "resumen completo" no es lo que llega al LLM — llega el `chunk_text` directamente del payload de Qdrant. Evidencia:
  - `src/api/main.py:1748-1753` → "cerebro_chunks tiene un punto por trozo de ~600 tokens" y POST a `cerebro_chunks/points/search`
  - `src/data/embedder_worker.py:161` → `"chunk_text": chunk_txt` en el payload de cada punto
  - `src/api/main.py:202-203` → staging upsert también guarda `chunk_text` en payload
- **Cambio sugerido**:
  ```markdown
  ```mermaid
  ...
      AP->>QD: búsqueda coseno en `cerebro_chunks` (filtrado payload.tenant_id IN [seed, sub-tenant])
      QD-->>AP: top-K chunks con {recurso_id, chunk_idx, chunk_text, title, url, category}
      AP->>PG: get_resources_for_rag(tenant, recurso_ids) — JOIN recursos+usuario_recursos para enriquecer metadata
      PG-->>AP: titulo, resumen, url, tags, categoría (solo activos del tenant)
      Note over AP: El contexto al LLM se construye con chunk_text de Qdrant<br/>+ metadata de Postgres. NO se usa el resumen como contenido principal.
  ```
  ```

### [HIGH] §3.2 — Tablas `sesiones_chat`/`mensajes_chat` ya no son las únicas para chat
- **Ubicación**: línea 235 (§3.2 Persistencia de Sesiones)
- **Lo que dice el doc**:
  > "Las sesiones y mensajes de chat se persisten en Postgres (tablas `sesiones_chat` y `mensajes_chat`)"
- **Realidad en el código**: las tablas creadas por la baseline son `sesiones_chat` y `mensajes_chat` (`infra/postgres/migrations/0001_baseline.sql:104`, `:118`) — pero la migración 0009 menciona `chat_sessions` y `chat_messages` como destino del cascade del demo (`infra/postgres/migrations/0009_demo_sessions.sql:19-20`). En la práctica las tablas reales siguen siendo `sesiones_chat`/`mensajes_chat`; la referencia en 0009 es inconsistente con la nomenclatura de baseline.
- **Cambio sugerido**: la afirmación del doc es correcta para baseline pero conviene mencionar que existe el cascade del demo y que la migración 0009 usa nomenclatura inconsistente. Mantener el bullet pero añadir nota:
  ```markdown
  Las sesiones y mensajes de chat se persisten en Postgres (tablas `sesiones_chat` y `mensajes_chat`, `infra/postgres/migrations/0001_baseline.sql:104,118`). El cleanup del demo (`src/api/main.py:_cleanup_demo_sessions_loop`) borra en cascada las filas asociadas al sub-tenant junto con sus puntos Qdrant.
  ```
  *[CODE-DOC inconsistency: la migración 0009 (`infra/postgres/migrations/0009_demo_sessions.sql:19-20`) menciona `chat_sessions`/`chat_messages` pero las tablas reales son `sesiones_chat`/`mensajes_chat`. No es un drift del doc audtado, pero conviene flagear al mantenedor.]*

### [HIGH] §2.4 — Curación Nocturna ya no es un workflow n8n puro
- **Ubicación**: líneas 195-204 (mermaid §2.4)
- **Lo que dice el doc**:
  > "Cron->>PG: SELECT id FROM cerebro.recursos WHERE estado='activo' AND fecha_caducidad < NOW()\nCron->>PG: UPDATE recursos SET estado='cuarentena' WHERE id IN (...)" — actor `n8n (Cron)`
- **Realidad en el código**: la curación está implementada en Python (`src/data/audit_cron.py:run_audit_cron`) y se dispara via `POST /admin/audit-cron` con `X-Admin-Token` (`src/api/main.py:1889-1902`). Hace mucho más que un simple UPDATE:
  - Fase A: activos con `fecha_caducidad <= NOW()` → cuarentena con motivo `caducidad` (`src/data/audit_cron.py:121-122`)
  - Emite eventos outbox por tenant (`_emit_outbox_for_tenant` en `src/data/audit_cron.py:17`)
  - Considera `temporal_class`, `valor_archivistico` y `audit_policy` JSONB
  - n8n SIGUE existiendo (`docker-compose.yml:547-549`) pero como disparador del HTTP request hacia `/admin/audit-cron`, no como ejecutor del SQL directo
- **Cambio sugerido**:
  ```markdown
  ### 2.4 Curación Nocturna (sin coste LLM extra)

  ```mermaid
  sequenceDiagram
      participant Cron as n8n (Cron diario)
      participant API as cerebro-api
      participant PG as PostgreSQL
      participant MQ as RabbitMQ

      Cron->>API: POST /admin/audit-cron + X-Admin-Token
      API->>API: run_audit_cron() (src/data/audit_cron.py)
      Note over API: Fase A — recursos activos con fecha_caducidad <= NOW()<br/>se mueven a cuarentena (motivo='caducidad').<br/>Fase B — cuarentenados con >GRACE_PERIOD_DAYS días se expiran.
      API->>PG: UPDATE recursos SET estado=... (filtrado por temporal_class y audit_policy)
      API->>PG: INSERT outbox_eventos 'recurso.cuarentena' / 'recurso.expirado'
      Note over PG, MQ: El outbox-publisher emite a RabbitMQ; el notifier-worker<br/>notifica al usuario por feed in-app + Telegram.
  ```

  La auditoría temporal está implementada en Python (`src/data/audit_cron.py`, autenticada por `AUDIT_CRON_TOKEN`). n8n es solo el disparador HTTP — no ejecuta SQL directo. El motivo `evento_pasado` se decide al ingestar (migración 0006), no aquí.
  ```

### [HIGH] §4 — Faltan los endpoints `/auth/demo-start` y `/auth/refresh` en el flujo de auth
- **Ubicación**: líneas 180-194 (mermaid §2.3 Autenticación) + §4 entero
- **Lo que dice el doc**: el diagrama muestra solo `/auth/login` + login + Set-Cookie. §4 no menciona el flujo demo, ni el refresh, ni el JWT con `tenant_id` sub-tenant `demo_<8hex>`.
- **Realidad en el código**: existen 5 endpoints de auth (`src/api/main.py:801-1086`):
  - `POST /auth/register` (:801)
  - `POST /auth/login` (:814)
  - `POST /auth/demo-start` (:868) — crea sub-tenant `demo_<8hex>` con TTL 15min
  - `POST /auth/refresh` (:1011) — renueva el access token usando refresh cookie + Redis allowlist
  - `POST /auth/logout` (:1081)
  - `GET /auth/me` (:1088)

  El `get_current_user` (`src/api/main.py:455-525`) hace validación adicional contra `demo_sessions` cuando el tenant_id empieza con `demo_`. La cookie de sesión incluye **dos** cookies: access (corta) y refresh (larga, registrada en Redis con TTL).
- **Cambio sugerido**: añadir un sub-apartado §4.5 explicando el flujo demo y el refresh:
  ```markdown
  ### 4.5 Endpoints de Autenticación

  | Endpoint | Función | Notas |
  |---|---|---|
  | `POST /auth/register` | Alta de usuario registered | Email + password (bcrypt). Crea `tenant_id` UUID real. (`src/api/main.py:801`) |
  | `POST /auth/login` | Login | Set-Cookie SESSION + Set-Cookie CSRF. (`src/api/main.py:814`) |
  | `POST /auth/demo-start` | Visita demo anónima | Crea sub-tenant `demo_<8hex>` con TTL 15 min en `cerebro.demo_sessions`. JWT emitido con ese sub-tenant. (`src/api/main.py:868`) |
  | `POST /auth/refresh` | Renueva access token | Lee refresh cookie, valida en Redis allowlist (`refresh:{hash}`). (`src/api/main.py:1011`) |
  | `POST /auth/logout` | Logout | Borra refresh allowlist + clear cookies. (`src/api/main.py:1081`) |
  | `GET /auth/me` | Perfil + estado demo | Devuelve `tenant_id`, `audit_policy`, `demo_session_seconds_remaining` si aplica. (`src/api/main.py:1088`) |

  El middleware `get_current_user` (`src/api/main.py:455-525`) valida adicionalmente las sesiones demo contra `demo_sessions`: si la fila no existe o `expires_at <= NOW()`, responde 401 con `X-Auth-Reason: demo_invalid` / `demo_expired`.
  ```

### [HIGH] §8 — "6 reglas de alerta activas" es incorrecto: hay 9
- **Ubicación**: línea 463 (§8 Alertas Prometheus)
- **Lo que dice el doc**:
  > "El archivo `infra/prometheus/alert.rules.yml` contiene 6 reglas de alerta activas..."
- **Realidad en el código**: hay **9 reglas** en `infra/prometheus/alert.rules.yml`:
  1. `HighLLMLatency` (:6)
  2. `DLQ_Filling_Up` (:16)
  3. `HighErrorRateIngestion` (:26)
  4. `APIHighP99Latency` (:36)
  5. `IngestionQueueBacklog` (:46)
  6. `EmbeddingsDLQAny` (:56)
  7. `PostgresConnectionsHigh` (:66)
  8. `WorkerStuck` (:76)
  9. `VolumeDiskHigh` (:86)

  La descripción del doc enumera 6 bullets que cubren ~5 de las reglas; falta mencionar `HighLLMLatency` (LLM > 20s), `DLQ_Filling_Up` (DLQ ingesta) y `HighErrorRateIngestion` (5xx > 5%).
- **Cambio sugerido**:
  ```markdown
  ### Alertas Prometheus

  El archivo `infra/prometheus/alert.rules.yml` contiene **9 reglas activas** que disparan notificaciones en Grafana cuando:
  - `HighLLMLatency` — latencia promedio LiteLLM > 20s sostenida 2min
  - `DLQ_Filling_Up` — `dlq.url.fallidas` > 10 mensajes 5min
  - `HighErrorRateIngestion` — errores 5xx en API/Traefik > 5% 2min
  - `APIHighP99Latency` — p99 cerebro-api > 2s sostenida 5min
  - `IngestionQueueBacklog` — `q.url.ingesta` > 1000 mensajes 10min
  - `EmbeddingsDLQAny` — cualquier mensaje en `q.embeddings.fallidos` 1min
  - `PostgresConnectionsHigh` — conexiones > 160 (80% de max_connections=200) sostenidas 5min
  - `WorkerStuck` — un worker no responde a scraping de métricas durante 3min
  - `VolumeDiskHigh` — volumen postgres/qdrant > 80% lleno 10min
  ```

### [MEDIUM] §3.1 — Pivote y RLS: aclarar que `outbox_eventos`, `sesiones_chat`, etc. también tienen RLS
- **Ubicación**: línea 222 (§3.1, bullet "Modelo recurso global")
- **Lo que dice el doc**:
  > "la asociación usuario↔recurso vive en `usuario_recursos(tenant_id, recurso_id)`, donde aplica la RLS."
- **Realidad en el código**: la RLS está ENABLE+FORCE en **cinco** tablas, no solo en `usuario_recursos`:
  - `usuario_recursos`, `sesiones_chat`, `mensajes_chat`, `grafo_relaciones`, `outbox_eventos` (`infra/postgres/migrations/0001_baseline.sql:140-183`)
  - Todas con policy `tenant_isolation` USING `tenant_id = current_setting('app.tenant_id')` (`:148-168`)
- **Cambio sugerido**:
  ```markdown
  ...la asociación usuario↔recurso vive en `usuario_recursos(tenant_id, recurso_id)`. La RLS se activa con `FORCE ROW LEVEL SECURITY` en cinco tablas: `usuario_recursos`, `sesiones_chat`, `mensajes_chat`, `grafo_relaciones`, `outbox_eventos` (`infra/postgres/migrations/0001_baseline.sql:140-183`). Todas comparten la policy `tenant_isolation` que lee `current_setting('app.tenant_id')`, fijado por la app con `SELECT set_config('app.tenant_id', $1, true)` antes de cada query crítica (ej. `src/data/db.py:117`, `src/api/main.py:335`).
  ```

### [MEDIUM] §5 — El conector asyncpg no usa `server_settings`, usa una `init=` callback
- **Ubicación**: líneas 350-353 (§5 Aislamiento de Schema)
- **Lo que dice el doc**:
  ```python
  conn = await asyncpg.connect(dsn, server_settings={"search_path": "cerebro,public"})
  ```
- **Realidad en el código**: el pool no se configura con `server_settings`, se usa un callback `init=_init_conn` que ejecuta el SET y registra un codec JSONB:
  - `src/api/database.py:397` → `await conn.execute("SET search_path TO cerebro, public")`
  - `src/api/database.py:393-401` → `_init_conn` también hace `await conn.set_type_codec("jsonb", schema="pg_catalog", encoder=json.dumps, decoder=json.loads)`
  - `src/api/database.py:412-413` → `_pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10, init=_init_conn)`
- **Cambio sugerido**:
  ```markdown
  El pool asyncpg usa un callback `init=` que se ejecuta una vez por conexión: fija el search_path **y** registra el codec JSONB para que asyncpg serialice/deserialice automáticamente:

  ```python
  async def _init_conn(conn):
      await conn.execute("SET search_path TO cerebro, public")
      await conn.set_type_codec("jsonb", schema="pg_catalog",
                                encoder=json.dumps, decoder=json.loads)

  _pool = await asyncpg.create_pool(DSN, min_size=2, max_size=10, init=_init_conn)
  ```

  Evidencia: `src/api/database.py:393-413`.
  ```

### [MEDIUM] §1 — Diagrama de topología omite `cerebro-notifier`
- **Ubicación**: líneas 49-119 (mermaid §1)
- **Lo que dice el doc**: en el subgraph "Workers Asíncronos" aparecen `Scraper`, `Embedder`, `Outbox` — pero no `Notifier`.
- **Realidad en el código**: el servicio existe y está activo:
  - `docker-compose.yml:122-135` → `notifier-worker` / `container_name: cerebro-notifier`
  - `src/notifier/worker.py:42` → consume cola `q.notifications` para eventos `recurso.cuarentena`, `recurso.expirado`, `recurso.rescatado`
  - Persiste filas en `cerebro.notificaciones` y envía Telegram al `telegram_chat_id` del usuario
- **Cambio sugerido**:
  ```markdown
  ```mermaid
  ...
      subgraph Workers["Workers Asíncronos"]
          Scraper["🕷️ cerebro-scraper\nScrapling · Playwright"]:::worker
          Embedder["🧮 cerebro-embedder\nChunking · Qdrant"]:::worker
          Outbox["📤 cerebro-outbox\nOutbox Pattern Publisher"]:::worker
          Notifier["📨 cerebro-notifier\nFeed in-app + Telegram"]:::worker
      end
  ...
      Notifier --> Postgres
      Notifier --> RabbitMQ
      Notifier --> Redis
  ```
  ```

### [MEDIUM] §1 — Embedder citado como "Vectorización · Qdrant" oculta el chunking
- **Ubicación**: línea 62 (subgraph Workers)
- **Lo que dice el doc**:
  > `Embedder["🧮 cerebro-embedder\nVectorización · Qdrant"]:::worker`
- **Realidad en el código**: el embedder hace chunking (~1200 chars, overlap 150) y emite N puntos por recurso a `cerebro_chunks`, no solo un vector:
  - `src/data/embedder_worker.py:42-79` (chunking)
  - `src/data/embedder_worker.py:137-169` (`_inject_chunks_to_qdrant`)
  - También clona chunks entre tenants sin re-embedding (`src/data/embedder_worker.py:171-209`, `:417-419`)
- **Cambio sugerido**:
  ```markdown
  Embedder["🧮 cerebro-embedder\nChunking + Vectorización\ncerebro_chunks"]:::worker
  ```

### [MEDIUM] Gap §2.x — Falta el flujo de "Demo Session Bootstrap" (Slice 6.x)
- **Ubicación**: §2 entera (líneas 60-205)
- **Lo que dice el doc**: §2 documenta Ingesta, Chat RAG, Auth y Curación pero NO el flujo end-to-end del demo onboarding (Slices 6.1-6.6 según los commits recientes: 6.4 staging buscable en RAG, 6.5 cache de embeddings staged, 6.6 nav anónimo).
- **Realidad en el código**: existe un flujo dedicado del demo que toca todas las capas:
  - `POST /auth/demo-start` (`src/api/main.py:868`) crea sub-tenant `demo_<8hex>` con TTL 15 min
  - `_STAGED_RECURSOS` (tres recursos sintéticos) se inyectan en `cerebro_chunks` desde el cache pre-computado (`infra/postgres/migrations/0011_staged_embeddings_cache.sql`)
  - El usuario demo además ve el seed `user_demo_landing` por UNION ALL (`src/api/main.py:_tenant_ids_for`:260-274)
  - `_cleanup_demo_sessions_loop` (`src/api/main.py:350-389`) borra en cascada cada 60s: `demo_sessions` + `usuario_recursos` + `recursos` huérfanos + `chat_sessions` + `chat_messages` + `notificaciones` + Qdrant points (`_qdrant_delete_tenant_points` en :281)
  - Migración `0009_demo_sessions.sql` documenta el modelo
  - Slice 6.6 (commit `8150d7d`) cambió manejo del 429
- **Cambio sugerido**: añadir un §2.5 con un mermaid del demo session bootstrap, citando paths reales. Sección sugerida:
  ```markdown
  ### 2.5 Demo Session Bootstrap (Slices 6.x)

  Cada visitante anónimo recibe un sub-tenant aislado con TTL de 15 minutos. Flujo:

  ```mermaid
  sequenceDiagram
      autonumber
      actor U as Visitante
      participant WB as cerebro-web
      participant AP as cerebro-api
      participant PG as PostgreSQL
      participant QD as Qdrant

      U->>WB: visita landing y pulsa "Probar demo"
      WB->>AP: POST /auth/demo-start
      AP->>PG: INSERT cerebro.demo_sessions (tenant_id="demo_<8hex>", expires_at=NOW()+15min)
      AP->>PG: copia 3 _STAGED_RECURSOS al sub-tenant (recursos + usuario_recursos)
      AP->>PG: SELECT staged_embeddings_cache (vectores pre-computados, sin coste LLM)
      AP->>QD: upsert 3 chunks en cerebro_chunks (payload.tenant_id = sub-tenant)
      AP-->>WB: Set-Cookie SESSION (JWT con tenant_id="demo_<8hex>")

      Note over WB,AP: Las queries del demo hacen UNION con el seed user_demo_landing<br/>(src/api/main.py:_tenant_ids_for:260-274) para incluir los 18 recursos públicos.

      par Cada 60s
          AP->>AP: _cleanup_demo_sessions_loop()
          AP->>PG: SELECT expirados (expires_at < NOW())
          AP->>QD: delete points donde payload.tenant_id = demo_xxx
          AP->>PG: DELETE cascade: demo_sessions + usuario_recursos + recursos huérfanos + chat + notificaciones
      end
  ```

  Referencias: `src/api/main.py:868-1007` (endpoint), `:350-389` (cleanup), `:260-274` (_tenant_ids_for), `infra/postgres/migrations/0009_demo_sessions.sql`, `:0011_staged_embeddings_cache.sql`.
  ```

### [MEDIUM] §6 — Truco base-10 está OK pero falta mencionar la migración 0011
- **Ubicación**: líneas 380-388 (§6 Gestión de Migraciones)
- **Lo que dice el doc**: enumera el formato `NNNN_*.sql` pero no menciona que la última migración es `0011`. El lector podría asumir que hay menos.
- **Realidad en el código**: hay 11 migraciones (0001..0011) en `infra/postgres/migrations/`. La más reciente `0011_staged_embeddings_cache.sql` introduce el cache de embeddings staged (Slice 6.5).
- **Cambio sugerido**: añadir tabla al final de §6 listando las 11 migraciones con propósito (1 línea cada una), para que el lector pueda rastrear qué slice trajo cada cambio sin abrir cada SQL.

### [LOW] §4.4 — `JWT_SECRET_FILE` etc. usan formato distinto al que sugiere el doc
- **Ubicación**: línea 322 (§4.4 Overlay producción)
- **Lo que dice el doc**:
  > "**Docker secrets**: `JWT_SECRET_FILE`, `POSTGRES_PASSWORD_FILE`, etc."
- **Realidad en el código**: UNVERIFIED — no he abierto `docker-compose.prod.yml` para confirmar los nombres exactos de los secrets. Lo dejo en LOW porque la mecánica `*_FILE` es estándar y probablemente correcta, pero el nombre exacto no fue verificado.
- **Cambio sugerido**: ninguno hasta verificar `docker-compose.prod.yml`.

### [LOW] §8 — Mención al "OTel Collector v0.103+" sin la versión actual usada
- **Ubicación**: línea 445 (§8 Corrección de configuración OTel)
- **Lo que dice el doc**: cita la corrección como "v0.103+" pero no menciona qué versión usa hoy el proyecto.
- **Realidad en el código**: la imagen está pinneada en `docker-compose.yml` (no inspeccioné el tag exacto pero `infra/otel/config.yaml` usa la sintaxis nueva, confirmando que la imagen es compatible).
- **Cambio sugerido**: añadir una nota tipo "versión actual: ver `docker-compose.yml` servicio `otel`".

### [UNVERIFIED] §4.4 — Nombres exactos de secrets en `docker-compose.prod.yml`
- **Ubicación**: línea 322
- **Lo que dice el doc**: lista `JWT_SECRET_FILE`, `POSTGRES_PASSWORD_FILE` como ejemplos de docker secrets.
- **Realidad en el código**: no inspeccionado por presupuesto de auditoría — necesitaría `grep -n "secret\|_FILE" docker-compose.prod.yml`.

---

## Aprobado sin cambios

- §1 — La descripción narrativa de Traefik como único entrypoint coincide con `docker-compose.yml:299` (cerebro-traefik) y la red privada `cerebro-net`.
- §3.1 — La separación PostgreSQL/Qdrant es correcta (con la corrección [CRITICAL] sobre Qdrant chunks).
- §3.3 — Lista de volúmenes Docker verificada contra `docker-compose.yml:894+` (qdrant-data, etc.).
- §4.1 — Patrón cookie httpOnly + CSRF doble submit verificado en `src/api/main.py` (cookies SESSION/CSRF y header `X-CSRF-Token`).
- §4.2 — Patrón INCR+EXPIRE atómico verificado en `src/api/main.py:_rate_limit` y aplicado a `/auth/login` (5/min), `/chat` (30/min, `:774`), `/admin/audit-cron` (`:783` audit 5/min).
- §4.3 — Contenedores non-root verificado en `docker-compose.yml` (usuarios `cerebro` uid 1000).
- §5 — La explicación del schema `cerebro` vs `public` (LiteLLM/Prisma) y `n8n` es correcta a nivel narrativo; el detalle técnico difiere en cómo se establece el search_path (ver MEDIUM).
- §6 — El runner shell puro `scripts/migrate.sh` existe y la nota del base-10 es correcta (`scripts/migrate.sh`).
- §7 — Heartbeat Redis + TTL 45s verificado en `src/data/heartbeat.py` y los healthchecks de cada worker en `docker-compose.yml` (outbox-worker `:103`, notifier-worker `:135`, etc.).
- §9 — `scripts/backup.sh` existe; la mecánica `pg_dump --schema=cerebro | gzip` y el snapshot HTTP de Qdrant son razonables (cabecera del script confirma BACKUP_DIR/RETENTION).
