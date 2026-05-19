# Review · 9-ejemplo_flujo · 2026-05-19

**Auditor**: docs-reality-auditor
**Doc revisado**: `/tmp/linkanvil-mirror/docs/src/9-ejemplo_flujo.md`
**Áreas de código verificadas**:
- `src/scraper/worker.py`, `src/scraper/strategy.py`
- `src/ingestion/main.py`, `src/ingestion/deduplicator.py`, `src/ingestion/publisher.py`
- `src/data/db.py` (save_with_outbox, save_semantic_collisions, emit_reuse_event)
- `src/data/embedder_worker.py`
- `src/data/audit_cron.py` (run_audit_cron, run_demo_audit_for_session)
- `src/data/outbox_publisher.py`, `src/data/export_manager.py`
- `src/api/main.py` (chat, SSE, admin endpoints), `src/api/database.py`
- `src/notifier/worker.py`
- `src/observability/`, `src/telemetry.py`
- `infra/rabbitmq/definitions.json`, `infra/postgres/migrations/0001..0011`
- `infra/n8n/workflows/audit_cron_daily.json`, `infra/otel/config.yaml`
- `docker-compose.yml`, `ops/cron/`

**Versión del repo**: mirror local (no es git repo); migraciones 0001–0011 presentes.

## Resumen
- **2 CRITICAL**, **5 HIGH**, **6 MEDIUM**, **5 LOW**, **2 UNVERIFIED**
- 0 hallazgos [CODE-BUG]
- **Veredicto: RED** (hay CRITICAL — afirmaciones reproducibles que no coinciden con el codigo)

---

## Hallazgos

### [CRITICAL] Umbral de similitud coseno es 0.92, no 0.88 (mencionado 3 veces en el doc)

- **Ubicacion**: lineas 344, 364, 366, 803
- **Lo que dice el doc**:
  > "Encuentra alta similitud (cosine > 0.88) con el UUID del recurso \"LangChain v0.1\"."
  > "El umbral 0.88 es **alto a proposito**..."
  > "Solo por encima de 0.88 (un threshold calibrado empiricamente)..."
  > "LinkAnvil usa umbral 0.88 para detectar colisiones semanticas." (glosario)
- **Realidad en el codigo**: El umbral hard-coded en el clasificador es **0.92**, no 0.88 (evidencia: `src/data/embedder_worker.py:307` `"score_threshold": 0.92`, y `src/data/embedder_worker.py:337` log `Sin colisiones semanticas > 0.92`). No hay configuracion externa; el valor esta fijo.
- **Cambio sugerido**:
  ```markdown
  Encuentra alta similitud (cosine > 0.92) con el UUID del recurso
  "LangChain v0.1".
  ```
  Y en el glosario:
  ```markdown
  **Similitud coseno** - medida entre 0 y 1 que compara dos vectores.
  1 = identicos, 0 = sin relacion. LinkAnvil usa umbral 0.92 para
  detectar colisiones semanticas (`embedder_worker.py:307`).
  ```

### [CRITICAL] El clasificador de relacion semantica lo invoca el **embedder**, no el **scraper**

- **Ubicacion**: lineas 346-353
- **Lo que dice el doc**:
  > "**`cerebro-scraper`** envia ambos resumenes a **`cerebro-litellm`** con el **prompt clasificador de relacion semantica**"
- **Realidad en el codigo**: La clasificacion la hace el **embedder**, no el scraper. La funcion `_classify_collision_type` vive en `src/data/embedder_worker.py:246-296` y se llama desde `_compute_semantic_collisions` (`src/data/embedder_worker.py:328`), que a su vez se invoca tras vectorizar el recurso. El scraper (`src/scraper/worker.py`) jamas llama al clasificador.
- **Cambio sugerido**:
  ```markdown
  3. **`cerebro-embedder`** envia ambos resumenes a **`cerebro-litellm`**
     con el **prompt clasificador de relacion semantica** (ver
     [`7-prompts.md` §2.2](./7-prompts.md#22-clasificador-de-relacion-semantica-embedder)):
     pide tipificar la relacion con UNA palabra del enum
     `{ES_UN, CONTRADICE, EXTIENDE, VUELVE_OBSOLETO, ASOCIACION_GENERAL}`.
  ```

---

### [HIGH] El mensaje NO se marca con flag `relink`; el scraper resuelve idempotencia por su cuenta

- **Ubicacion**: lineas 113-115
- **Lo que dice el doc**:
  > "Si la URL parece duplicada, el mensaje se marca con flag `relink` para que el scraper resuelva la idempotencia rio abajo (ver paso 1.3 punto 1)."
- **Realidad en el codigo**: El payload del mensaje se publica intacto (`src/ingestion/main.py:151-156` -- `payload = request.model_dump()` sin anadir flag). El string `"Accepted (relink)"` aparece **solo** en la respuesta HTTP (`src/ingestion/main.py:159`), no en el cuerpo del mensaje a RabbitMQ. El scraper resuelve idempotencia consultando Postgres via `find_existing_recurso_by_url` (`src/scraper/worker.py:191`), sin leer ningun flag.
- **Cambio sugerido**:
  ```markdown
  - **Publica SIEMPRE** al queue, sin importar lo que diga el bloom -
    el filtro es solo un hint *best-effort*, no un veto. El payload
    del mensaje es siempre el mismo (no se anade ningun flag de
    duplicado); el scraper resuelve la idempotencia rio abajo
    consultando `recursos` por `url_hash` antes de scrapear
    (ver paso 1.3 punto 1).
  ```

### [HIGH] La cola consumida por el embedder es `q.recurso.embedder`, no `q.embeddings`

- **Ubicacion**: linea 52, 207, diagrama linea 304
- **Lo que dice el doc**:
  > "el embedder consume `q.embeddings`"
  > "**`cerebro-embedder`** (worker que genera vectores): consume del fanout via su cola `q.embeddings`."
  > Mermaid: `EM->>RMQ: consume q.embeddings`
- **Realidad en el codigo**: La cola que declara y consume el embedder esta hard-coded como `q.recurso.embedder` (`src/data/embedder_worker.py:82` `QUEUE_NAME = "q.recurso.embedder"`; bind en `src/data/embedder_worker.py:108-117`). `q.embeddings` si esta pre-declarada en `infra/rabbitmq/definitions.json:70`, pero nadie la consume desde el codigo del embedder; queda como queue huerfana de la definicion declarativa.
- **Cambio sugerido**:
  ```markdown
  el embedder consume `q.recurso.embedder` (la cola esta bound al
  fanout `cerebro.procesamiento` con routing key vacia).
  ```
  Y actualizar el mermaid:
  ```
  EM->>RMQ: consume q.recurso.embedder
  ```
  *Nota separada para el equipo: la definicion declarativa
  `infra/rabbitmq/definitions.json` pre-declara `q.embeddings` pero
  no se usa - considerar limpieza.*

### [HIGH] El worker relay del outbox vive en `outbox_publisher.py`, no `outbox_worker.py`

- **Ubicacion**: linea 259
- **Lo que dice el doc**:
  > "- `src/data/outbox_worker.py` - relay Postgres -> RabbitMQ."
- **Realidad en el codigo**: El archivo es `src/data/outbox_publisher.py` (clase `OutboxPublisher`, evidencia: `src/data/outbox_publisher.py:19`). No existe `src/data/outbox_worker.py`.
- **Cambio sugerido**:
  ```markdown
  - `src/data/outbox_publisher.py` - relay Postgres -> RabbitMQ
    (clase `OutboxPublisher`).
  ```

### [HIGH] La seccion "Exportador LLM Wiki / Gemelo Markdown" no existe como se describe

- **Ubicacion**: lineas 699-719, 726
- **Lo que dice el doc**:
  > "Un script de cron (`audit_cron` o similar, tambien guiado por eventos) activa al **Exportador LLM Wiki**."
  > "extrae el grafo de **Postgres** y materializa carpetas y archivos locales en formato Markdown (`.md`)"
  > "Crea un archivo con *frontmatter* YAML... inserta links al estilo Obsidian (`[[Tutorial Bot LangChain]]`) y mueve la nota de v0.1 a un subdirectorio de archivo o la marca con metadata `obsolete: true`."
  > "Adicionalmente agrupa las variables activas en `hot.md` para rapida carga..."
  > "`ops/cron/` - scripts del exportador LLM Wiki."
- **Realidad en el codigo**:
  1. Existe `src/data/export_manager.py::VaultExporter` (`src/data/export_manager.py:10`) que genera un ZIP con frontmatter YAML, `hot.md`, `index.md`, etc.
  2. **NO esta cableado a ningun cron ni a outbox**: una busqueda global de `VaultExporter` / `export_manager` en el codigo solo arroja la propia definicion. No hay endpoint API, ni worker, ni evento de outbox que lo dispare.
  3. `ops/cron/` **no contiene** scripts de exportacion a Markdown - es un sistema de auditoria de codigo basado en LiteLLM (`ops/cron/weekly_audit.py`, `.githooks/pre-push`, ver `ops/cron/README.md:1-13`). Genera reportes de **auditoria de codigo** en `ops/sessions/audit-YYYY-MM-DD.md`, no exporta la KB del usuario.
  4. No se detecta proceso "obsolete: true" para mover v0.1 al subdirectorio "archivo".
- **Cambio sugerido**: re-escribir la subseccion entera para reflejar que (a) existe `VaultExporter` como exportador on-demand (probablemente via endpoint API si se cablease) y (b) `ops/cron/` es la auditoria de codigo semanal, no el exportador de la KB. O bien marcar la seccion con un disclaimer "diseno aspiracional, no implementado".

### [HIGH] El doc afirma "los 21 contenedores", el cluster real tiene 22-24

- **Ubicacion**: linea 11
- **Lo que dice el doc**:
  > "Para ilustrar como los 21 contenedores de **LinkAnvil** colaboran en tiempo real..."
- **Realidad en el codigo**: `docker-compose.yml` declara 24 `container_name: cerebro-*` (api, embedder, grafana, ingestion, jaeger, litellm, migrate, n8n, n8n-bootstrap, notifier, otel, outbox, postgres, postgres-exporter, prometheus, qdrant, rabbitmq, rabbitmq-exporter, redis, redis-exporter, scraper, tailscale, traefik, web). Quitando los one-shot (`cerebro-migrate`, `cerebro-n8n-bootstrap`): **22 contenedores activos en runtime**, no 21.
- **Cambio sugerido**:
  ```markdown
  Para ilustrar como los ~22 contenedores de **LinkAnvil** colaboran
  en tiempo real, seguimos un escenario realista de uso diario.
  ```

---

### [MEDIUM] Fase 3.d ignora el camino "Slice 6" - auditoria intra-sesion del demo

- **Ubicacion**: lineas 391-404, 405-456
- **Lo que dice el doc**: Solo describe cuatro caminos a `cuarentena/expirado`: 3.a (cron temporal), 3.b (semantico), 3.c (manual), 3.d (policy al ingestar).
- **Realidad en el codigo**: Existe un quinto camino exclusivo del demo, ya implementado: `src/data/audit_cron.py:186-298` `run_demo_audit_for_session` ("Slice 6 - Auditoria intra-sesion para un sub-tenant demo"). Procesa eventos pre-programados en `demo_session_events` con precision TIMESTAMPTZ y dispara transiciones cuarentena/expirado durante la sesion demo (orquestado por `_cleanup_demo_sessions_loop` en `src/api/main.py:308-347`, `_process_due_demo_audits`). Reutiliza outbox+notifier, por lo que el bell del frontend funciona identicamente al cron de prod.
- **Cambio sugerido**: anadir un **3.f Camino demo - auditoria intra-sesion** que mencione `demo_session_events`, `run_demo_audit_for_session`, sub-tenants efimeros y la pipeline outbox/notifier compartida con prod. Migraciones relevantes: `0009_demo_sessions.sql`, `0010_demo_session_events.sql`.

### [MEDIUM] El Bloom Filter es **por-tenant**, no global; el doc lo presenta como un cache global

- **Ubicacion**: lineas 108-112, 743-745 (glosario)
- **Lo que dice el doc**:
  > "Consulta un **Bloom Filter** en Redis (estructura de datos probabilistica... que responde \"definitivamente NO he visto esto antes\" o \"quizas si lo he visto\";)"
- **Realidad en el codigo**: La clave del bloom filter es **por tenant**: `bf:tenant:{tenant_id}:ingestion` (`src/ingestion/deduplicator.py:29`). Esto significa que dos tenants distintos siempre veran "nuevo" para la misma URL (consistente con el reuso cross-tenant descrito en 1.b, pero no es lo que el doc sugiere).
- **Cambio sugerido**:
  ```markdown
  - Consulta un **Bloom Filter** en Redis **por tenant**
    (estructura de datos probabilistica muy compacta que responde
    "definitivamente NO he visto esto antes" o "quizas si lo he visto"
    *para este tenant*; usar `BF.ADD` devuelve tambien si la URL era
    nueva para el tenant en cuestion). El Bloom es solo un hint local;
    la deduplicacion global cross-tenant la hace el scraper consultando
    `recursos.url_hash` en Postgres.
  ```

### [MEDIUM] El endpoint manual de cuarentena fija `motivo='manual'` server-side; el doc dice que el frontend lo envia

- **Ubicacion**: lineas 491-495
- **Lo que dice el doc**:
  > "Frontend llama a `POST /resources/{id}/quarantine` con `motivo='manual'`."
- **Realidad en el codigo**: El endpoint no acepta `motivo` en el body (`src/api/main.py:1491-1505`). El motivo se inyecta dentro de `quarantine_recurso`: `quarantine_reason = 'manual'` (`src/api/database.py:822`).
- **Cambio sugerido**:
  ```markdown
  Frontend llama a `POST /resources/{id}/quarantine` (sin body
  especifico). El backend fija internamente `quarantine_reason='manual'`
  (`src/api/database.py:822`) y emite outbox.
  ```

### [MEDIUM] El embedder NO procesa `recurso.cuarentena`; el doc justifica mal por que Expojove no se vectoriza

- **Ubicacion**: lineas 542-548
- **Lo que dice el doc**:
  > "el outbox emitio `recurso.cuarentena`. El embedder lo ignora (whitelist solo acepta `recurso.procesado` / `recurso.reusado`)."
- **Realidad en el codigo**: la afirmacion sobre la whitelist es **correcta** (`src/data/embedder_worker.py:348` `EMBEDDER_EVENT_TYPES = frozenset({"recurso.procesado", "recurso.reusado"})` y filter en linea 364). **Pero**: el doc dice "Expojove **NO se vectoriza**". En realidad, **`save_with_outbox` ya decidio `evento_tipo='recurso.cuarentena'` (no `procesado`) cuando determino cuarentena (`src/data/db.py:281, 302`)**, asi que el embedder nunca recibe un evento "procesado" sobre Expojove. La whitelist es defensa en profundidad, pero el flujo principal es que Expojove ni siquiera entra al embedder en primer lugar.
- **Cambio sugerido**: aclarar que el outbox emite **`recurso.cuarentena`** directamente cuando la policy decide cuarentena (no un evento "procesado" que luego se filtre); la whitelist del embedder es defensa en profundidad por si se emiten otros eventos por colision/cron sobre el mismo recurso.

### [MEDIUM] Formato exacto de `tenant_id`: `user_<32 hex>`, no `user_<uuid>`

- **Ubicacion**: linea 41, 813 (glosario)
- **Lo que dice el doc**:
  > "Se identifica por un `tenant_id` (`user_<uuid>`)."
- **Realidad en el codigo**: El default en la columna `usuarios.tenant_id` es `'user_' || replace(uuid_generate_v4()::text, '-', '')` (`infra/postgres/migrations/0008_byok_y_demo_flag.sql`), es decir 32 chars hex SIN guiones. Para demo: `demo_<8 hex>` (`src/api/database.py:107`).
- **Cambio sugerido**:
  ```markdown
  Se identifica por un `tenant_id` con formato `user_<32 hex>` para
  cuentas registered (default SQL en `usuarios.tenant_id`) o
  `demo_<8 hex>` para sub-tenants efimeros del demo
  (`src/api/database.py:107`).
  ```

### [MEDIUM] Los chunks van a la coleccion Qdrant `cerebro_chunks` con overlap de 150 chars; el doc omite ambos detalles

- **Ubicacion**: lineas 549-554
- **Lo que dice el doc**:
  > "construye chunks (fragmentos del texto, normalmente ~1200 caracteres, para que el RAG pueda recuperar pasajes especificos en vez del documento entero), transiciona directo a `'expirado'`"
- **Realidad en el codigo**: el chunking usa `target_chars=1200` **y `overlap_chars=150`** (`src/data/embedder_worker.py:42`). Los chunks se inyectan en la **coleccion Qdrant separada `cerebro_chunks`** (`src/data/embedder_worker.py:165`), distinta de `cerebro_recursos` (donde vive el vector "head" del recurso). El doc dice solo "~1200 caracteres" sin estos dos detalles importantes.
- **Cambio sugerido**:
  ```markdown
  ...construye chunks (~1200 caracteres con overlap de 150 chars,
  `_chunk_text` en `embedder_worker.py:42`), los inyecta en la
  coleccion Qdrant `cerebro_chunks` (separada del recurso "head"
  en `cerebro_recursos`), transiciona directo a `'expirado'`...
  ```

---

### [LOW] Links rotos a `prompts.md` y `lifecycle.md` (los archivos llevan prefijo numerico)

- **Ubicacion**: lineas 163, 348, 381
- **Lo que dice el doc**:
  > "Ver [`prompts.md` §2.1](./prompts.md#21-extraccion-de-metadata-scraper)"
  > "[`prompts.md` §2.2](./prompts.md#22-clasificador-de-relacion-semantica-embedder)"
  > "[`lifecycle.md`](./lifecycle.md)"
- **Realidad en el codigo**: en `/tmp/linkanvil-mirror/docs/src/` los archivos son `7-prompts.md` y `8-lifecycle.md`. Los links relativos fallaran al render.
- **Cambio sugerido**: cambiar los hrefs a `./7-prompts.md...` y `./8-lifecycle.md`.

### [LOW] Horario del cron diario: doc dice "03:00 locales (07:00 UTC)" pero el cron es `0 3 * * *` sin TZ

- **Ubicacion**: lineas 414-416
- **Lo que dice el doc**:
  > "A las 03:00 locales (07:00 UTC) **`cerebro-n8n`** dispara el workflow"
- **Realidad en el codigo**: `infra/n8n/workflows/audit_cron_daily.json` define `cronExpression: "0 3 * * *"`. No hay `TZ` configurado en el `docker-compose.yml` del contenedor n8n, asi que correra segun la TZ del runtime del contenedor (default UTC). Ademas, 03:00 local (Espana UTC+1/+2) seria 02:00 UTC o 01:00 UTC, **no** 07:00 UTC. La conversion del doc esta rota independientemente de la TZ.
- **Cambio sugerido**:
  ```markdown
  A las 03:00 UTC (default del contenedor n8n) **`cerebro-n8n`**
  dispara el workflow...
  ```
  o documentar el ajuste explicito de TZ si se quiere otra hora.

### [LOW] El escenario "LangChain v0.1 -> tutorial -> v0.2" es narrativo, no reproducible end-to-end

- **Ubicacion**: linea 11-22
- **Lo que dice el doc**: presenta el escenario como si fuera ejecutable paso a paso.
- **Realidad en el codigo**: los pasos individuales (ingest, embedder, colision, audit) si estan implementados, pero el escenario concreto depende de que el LLM clasifique `EXTIENDE` y `VUELVE_OBSOLETO`, lo cual es no-determinista (depende de la corrida del modelo). Reproducible **conceptualmente**, no de forma bit-exacta. Adicionalmente, langchain.com/v0.1 y langchain.com/v0.2 son URLs reales pero el sistema scrape-LLM-clasifica las clasifica probabilisticamente.
- **Cambio sugerido**: anadir nota inicial:
  ```markdown
  > Nota: el escenario LangChain v0.1 -> tutorial -> v0.2 es
  > **ilustrativo**, no un test reproducible. Las clasificaciones
  > (`EXTIENDE`, `VUELVE_OBSOLETO`) dependen del LLM y pueden variar
  > entre corridas; lo que esta deterministico son los **estados de
  > las tablas y eventos del outbox**, no las palabras exactas que
  > devuelve el modelo.
  ```

### [LOW] El doc se refiere a `cerebro-tailscale` como "receptor inicial de webhooks de Telegram"; el receptor real es `cerebro-ingestion`

- **Ubicacion**: lineas 101-103
- **Lo que dice el doc**:
  > "Si la URL entra por Telegram en vez de la web, el receptor inicial es **`cerebro-tailscale`** (red privada VPN para recibir webhooks de Telegram sin exponer la API a internet)."
- **Realidad en el codigo**: `cerebro-tailscale` esta en `docker-compose.yml`, pero el webhook de Telegram lo atiende directamente `cerebro-ingestion` en `/webhook/telegram/{token_hash}` (`src/ingestion/main.py:182`). Tailscale provee la red de transporte, no es el "receptor" del webhook.
- **Cambio sugerido**:
  ```markdown
  Si la URL entra por Telegram, **`cerebro-tailscale`** expone
  `cerebro-ingestion` al webhook de Telegram a traves de una red
  privada VPN sin exponer la API a internet; el endpoint real que
  procesa el payload sigue siendo `cerebro-ingestion`
  (`/webhook/telegram/{token_hash}`).
  ```

### [LOW] Migracion 0006 - el doc atribuye correctamente las columnas, pero omite que introdujo `audit_strictness` (luego reemplazado en 0007)

- **Ubicacion**: lineas 426-430 (recuadro), 738, 758, 818
- **Lo que dice el doc**: atribuye `temporal_class`, `valor_archivistico`, `evento_pasado` a la migracion 0006 - correcto. Pero no menciona que **0006 tambien introdujo `audit_strictness`** (`infra/postgres/migrations/0006_temporal_class_y_strictness.sql:5`), reemplazado en 0007 por `audit_policy`. Lectores que tracen el git history pueden confundirse.
- **Cambio sugerido**: nota en glosario `audit_policy`: "Reemplaza al enum `audit_strictness` (introducido en 0006, eliminado en 0007). Migracion 0007 hace UPSERT de los valores antiguos al nuevo JSONB."

---

### [UNVERIFIED] OTel trace propagation entre ingestion -> scraper -> embedder -> litellm

- **Ubicacion**: lineas 660-676
- **Lo que dice el doc**: describe propagacion de Trace ID via headers OTel y visualizacion en Jaeger.
- **Realidad en el codigo**: `src/telemetry.py:11-50` configura OTLP exporter por servicio y `set_global_textmap(TraceContextTextMapPropagator())`. La decoracion `@trace_operation` se usa en todos los servicios (`scraper/worker.py:174`, `embedder_worker.py:350`, `ingestion/main.py:111`, `api/main.py`). No verificado en runtime que la cascada Jaeger se forme correctamente entre los 4 servicios (requiere tirar Jaeger y mirar la UI). Diseno plausible; ejecucion UNVERIFIED.

### [UNVERIFIED] El reescritor de dominios anti-bot real (medium.com -> readmedium.com) funciona end-to-end

- **Ubicacion**: lineas 130-138
- **Lo que dice el doc**: describe `_rewrite_for_scrape` y la transformacion.
- **Realidad en el codigo**: `src/scraper/strategy.py:38-48` implementa el rewrite (`medium.com` y `*.medium.com` -> `readmedium.com/{url_original}`). UNVERIFIED si Medium/Datadome bloquea Stealth Playwright en runtime; depende de las defensas del sitio.

---

## Aprobado sin cambios

- §1.1 punto 2 - rate limiting atomico Redis: verificado contra `src/ingestion/main.py:125-139` (INCR + EXPIRE 60s + 429).
- §1.2 punto 6 - validacion post-scraping: verificado contra `src/scraper/strategy.py:118-150` (markers `cf-mitigated`, `verifica que usted no es un bot`, `failed to render this page`; NO usa `cloudflare` o `captcha` solos).
- §1.2 - guard de calidad `<300 chars`: verificado contra `src/scraper/worker.py:247`.
- §1.3 punto 9 - outbox transaccional (3 inserts en misma TX): verificado contra `src/data/db.py:319-399` (`async with conn.transaction()` envuelve los 3 INSERT/UPSERT).
- §1.3 punto 10 - `cerebro.procesamiento` fanout exchange: verificado contra `infra/rabbitmq/definitions.json:44-49`.
- §1.3 punto 11 - embedder whitelist `recurso.procesado/recurso.reusado`: verificado contra `embedder_worker.py:348`.
- §1.3 punto 12 - UUID v5 deterministico para `point_id`: verificado contra `embedder_worker.py:31-39` (`_QDRANT_POINT_NS` namespace fijo, `uuid5(ns, "<recurso_id>:<tenant_id>")`). El UUID v5 se usa tanto para recursos (`_qdrant_point_id`) como para chunks (`_qdrant_chunk_point_id`).
- §1.b - reuso cross-tenant via `recurso.reusado` y copia de vector: verificado contra `src/scraper/worker.py:191-209` (con guard adicional `has_contenido` que el doc omite) y `src/data/embedder_worker.py:382-403` (`_fetch_existing_vector_for_recurso`).
- §2 paso 5 - `grafo_relaciones` bidireccional con tipo inverso: verificado contra `src/data/db.py:537-555` (`EXTENDIDO_POR`, `OBSOLECIDO_POR`).
- §3.a - filtro `temporal_class='evento' AND fecha_caducidad <= NOW()::DATE`: verificado contra `src/data/audit_cron.py:113-126`.
- §3.a - gracia 30 dias por defecto via `OBSOLESCENCE_GRACE_DAYS`: verificado contra `src/data/audit_cron.py:15` y `src/data/db.py:563`.
- §3.a punto 5 - n8n dispara `POST /admin/audit-cron` con `X-Admin-Token`: verificado contra `infra/n8n/workflows/audit_cron_daily.json` y `src/api/main.py:1889-1902`.
- §3.a variante manual - endpoint `/resources/audit-now` con rate-limit 5/min: verificado contra `src/api/main.py:1456-1475` (sin admin token, requiere user auth + `rate_limit_audit`).
- §3.b - `save_semantic_collisions` aplica cuarentena al recurso destino con `quarantine_reason='colision_semantica'`: verificado contra `src/data/db.py:562-575`.
- §3.d - `audit_policy` con 6 keys + presets Estricto/Equilibrado/Permisivo: verificado contra `infra/postgres/migrations/0007_audit_policy_y_auto_archive.sql:23-77` y la tabla resumen de la doc cuadra celda a celda con el JSONB de la migracion (Estricto = todo cuarentena; Equilibrado default = alto->expirado, resto cuarentena; Permisivo = referencia_medio->activo).
- §3.d - cache in-process de `audit_policy` a 60s: verificado contra `src/data/db.py:51` `_POLICY_TTL_SEC = 60.0`.
- §3.d - `_emit_auto_archive_event` y `_fetch_auto_archive_flag` defensa-en-profundidad: verificado contra `src/data/embedder_worker.py:444-520`.
- §3.d - SSE `/resources/stream` reenviando Redis pub/sub `resources:{tenant_id}`: verificado contra `src/api/main.py:1663-1690` y `src/notifier/worker.py:247-264`.
- §3.d punto 6 - `get_active_resource_ids(..., include_archive=True)` amplia a `estado IN ('activo','expirado')`: verificado contra `src/api/database.py:538-560`.
- §3.e - periodo de gracia, endpoints `/resources/{id}/rescue`, `/resources/{id}/expire`, DELETE `/resources/{id}`: verificado contra `src/api/main.py:1478-1525` (endpoints existen; la tabla de volatilidades baja=+365d etc. se delega a `lifecycle.md`).
- §4 Tracing - `cerebro-otel` y `cerebro-jaeger` existen (`docker-compose.yml` services); endpoint OTLP `http://otel-collector:4318/v1/traces` configurado (`src/telemetry.py:9`).
- §4 Metrics - exporters Prometheus existen para Postgres/Redis/RabbitMQ: verificado contra `docker-compose.yml:779-848` y `infra/prometheus/prometheus.yml:35-45`.
- §4 - `infra/grafana/dashboards/` con `cerebro-overview.json`: existe.
- §4 - `infra/prometheus/alert.rules.yml` con alerta `q.url.ingesta > 1000`: verificado contra `infra/prometheus/alert.rules.yml:46-51`.
