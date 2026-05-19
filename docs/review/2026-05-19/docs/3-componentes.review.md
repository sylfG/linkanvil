# Review · 3-componentes · 2026-05-19

**Auditor**: docs-reality-auditor
**Doc revisado**: `docs/src/3-componentes.md`
**Áreas de código verificadas**: `src/api/`, `src/data/`, `src/scraper/`, `src/frontend/`, `src/ingestion/`, `src/notifier/`, `src/observability/`, `src/dlq/`, `src/ui/`, `docker-compose.yml`, `infra/litellm/`, `infra/n8n/`, `infra/tailscale/`, `infra/postgres/`, `clientes/browser-extension/`
**Versión del repo**: `develop` @ `7c723f3`

## Resumen
- 2 CRITICAL, 3 HIGH, 6 MEDIUM, 2 LOW, 2 UNVERIFIED
- 0 hallazgos [CODE-BUG]
- **Veredicto: RED** (presencia de CRITICAL)

## Hallazgos

### [CRITICAL] Count de servicios desactualizado: doc dice 22, el compose tiene 24
- **Ubicación**: línea 11
- **Lo que dice el doc**:
  > "Este documento describe cada uno de los 22 servicios que componen LinkAnvil…"
- **Realidad en el código**: `docker-compose.yml` declara 24 servicios (evidencia: `docker-compose.yml:14-861`):
  `ingestion-api, scraper-worker, outbox-worker, notifier-worker, embedder-worker, cerebro-migrate, cerebro-api, cerebro-web, traefik, rabbitmq, redis, postgres, qdrant, litellm, n8n, n8n-bootstrap, jaeger, otel-collector, prometheus, grafana, rabbitmq-exporter, redis-exporter, postgres-exporter, tailscale-funnel`.
  Además, el doc solo describe explícitamente ~21 de ellos (faltan `notifier-worker` y `cerebro-migrate` — ver hallazgos siguientes).
- **Cambio sugerido**:
  ```markdown
  Este documento describe cada uno de los 24 servicios que componen LinkAnvil con una **analogía pedagógica**, un bloque *¿Qué hace?* (responsabilidades en lenguaje claro) y un bloque *¿Por qué se tomó esta decisión?* (motivación de la elección).
  ```

### [CRITICAL] `notifier-worker` no existe en la documentación
- **Ubicación**: §3 "Workers Asíncronos" (líneas 144-195) — solo describe scraper, embedder y outbox
- **Lo que dice el doc**:
  > (no menciona `notifier-worker` en ninguna parte)
- **Realidad en el código**: Existe un cuarto worker async, declarado en `docker-compose.yml:122-152` como `notifier-worker` (`container_name: cerebro-notifier`) ejecutando `python -m src.notifier.worker`. Su propósito es consumir `q.notifications` (fanout `cerebro.procesamiento`) para crear filas en `notificaciones` y enviar mensajes a Telegram cuando un recurso pasa a `cuarentena`/`expirado` (evidencia: `src/notifier/worker.py:1-15`). Tiene heartbeat propio en Redis `worker:notifier:heartbeat` (`docker-compose.yml:135`).
- **Cambio sugerido** (añadir nueva subsección en §3 después de "cerebro-outbox"):
  ```markdown
  ### 🔔 cerebro-notifier — El Mensajero de Avisos

  *Analogía:* Es el cartero que avisa al usuario cuando uno de sus enlaces guardados fue puesto en cuarentena (no se pudo leer) o ha caducado por obsolescencia. Si el usuario tiene un bot de Telegram vinculado, además le envía un mensaje directo a su chat.

  **Código:** `src/notifier/worker.py`

  **¿Qué hace?**

  - **Consumo de Eventos:** Escucha la cola `q.notifications` (fanout `cerebro.procesamiento`) en RabbitMQ, donde llegan los eventos `recurso.cuarentena` y `recurso.expirado`.
  - **Feed In-App:** Crea una fila en la tabla `notificaciones` para que aparezca en el panel del usuario.
  - **Notificación Telegram:** Si el tenant tiene bot configurado y un `chat_id` capturado (cacheado en Redis `telegram_chat:{tenant_id}` y persistido en `usuarios.telegram_chat_id`), envía un mensaje directo al chat.

  **¿Por qué se tomó esta decisión?**

  Separar el envío de notificaciones del scraper y del embedder mantiene esos workers enfocados en su tarea principal y permite que las notificaciones se reintenten de forma independiente si Telegram está caído o si la BD bloquea.
  ```

### [HIGH] `cerebro-migrate` no aparece en el doc
- **Ubicación**: §2 o §5 — no aparece
- **Lo que dice el doc**:
  > (silencio)
- **Realidad en el código**: `docker-compose.yml:194-215` declara el contenedor one-shot `cerebro-migrate` (`postgres:16-alpine`, ejecuta `bash /migrate.sh`) que aplica las migraciones SQL pendientes de `infra/postgres/migrations/` antes de levantar `cerebro-api`. Es idempotente vía `cerebro.schema_migrations(version)`. Tiene comentario explicativo en `docker-compose.yml:189-193` y existen 10 migraciones (`infra/postgres/migrations/0001_baseline.sql` … `0010_demo_session_events.sql`).
- **Cambio sugerido** (añadir subsección, idealmente en §5 "Almacenamiento y Mensajería" o crear §3.5):
  ```markdown
  ### 🗃️ cerebro-migrate — Migrador One-Shot

  *Analogía:* Es el albañil que llega antes de que abra la oficina, comprueba qué reformas hay pendientes en el plano y las aplica una sola vez. Si todas las reformas ya están hechas, no hace nada y se va.

  **¿Qué hace?**

  Es un contenedor `postgres:16-alpine` con `restart: "no"` que se ejecuta una sola vez al levantar el stack. Aplica las migraciones SQL pendientes de `infra/postgres/migrations/` (numeradas `0001_…` a `00NN_…`) contra la base de datos. Es idempotente: lleva registro en `cerebro.schema_migrations(version)` para no re-aplicar lo ya aplicado.

  **¿Por qué se tomó esta decisión?**

  Garantiza que el schema de `cerebro` esté actualizado antes de que `cerebro-api` arranque, evitando errores 500 por columnas inexistentes en releases nuevas. Es un patrón clásico de migración declarativa para `docker compose up -d`.
  ```

### [HIGH] Frecuencia del Heartbeat: doc dice 45s, el default es 15s
- **Ubicación**: líneas 146 y 279
- **Lo que dice el doc**:
  > "envían una señal cada 45 segundos para demostrar que siguen vivos y trabajando"
  > "Los workers dejan aquí su firma cada 45 segundos para avisarle al sistema que siguen vivos"
- **Realidad en el código**: el valor `45` corresponde al **TTL** de la clave Redis, no al intervalo de escritura. El intervalo real (frecuencia con la que el worker hace `SETEX`) es 15s por defecto (evidencia: `src/data/heartbeat.py:17-18`):
  ```python
  DEFAULT_INTERVAL = int(os.getenv("WORKER_HEARTBEAT_INTERVAL_SEC", "15"))
  DEFAULT_TTL = int(os.getenv("WORKER_HEARTBEAT_TTL_SEC", "45"))
  ```
- **Cambio sugerido**:
  ```markdown
  El sistema usa "trabajadores" silenciosos: son independientes, pueden tomarse su tiempo para leer páginas complejas sin que la aplicación web se quede congelada. Cada uno tiene un sistema de "latidos de corazón" (Heartbeat): escriben una señal en Redis cada 15 segundos con un TTL de 45 segundos para demostrar que siguen vivos y trabajando; si la señal expira (3 ciclos perdidos) el sistema detecta que se han quedado atascados (ver el detalle en [`4-arquitectura.md`](./4-arquitectura.md), sección de Heartbeat).
  ```
  Y en línea 279:
  ```markdown
  3. **Monitor de Vida (Heartbeat):** Los workers dejan aquí su firma cada 15 segundos (con TTL de 45 s) para avisarle al sistema que siguen vivos (ver Heartbeat en [`4-arquitectura.md`](./4-arquitectura.md)).
  ```

### [HIGH] Links internos rotos: usan `_` cuando los archivos reales usan `-`
- **Ubicación**: líneas 13, 14, 73, 146, 220, 230, 267, 279, 338, 370
- **Lo que dice el doc** (muestra):
  > `[catálogo de contenedores](./2_resumen_servicios.md)`
  > `` [`4_arquitectura.md`](./4_arquitectura.md) ``
  > `` [`1_instalacion_y_configuracion.md`](./1_instalacion_y_configuracion.md) ``
- **Realidad en el código**: los archivos reales son `docs/src/2-resumen-servicios.md`, `docs/src/4-arquitectura.md`, `docs/src/1-instalacion-configuracion.md` (evidencia: `ls docs/src/`). Todos los links del doc apuntan a archivos inexistentes.
- **Cambio sugerido**: reemplazar globalmente:
  ```markdown
  - `./2_resumen_servicios.md` → `./2-resumen-servicios.md`
  - `./4_arquitectura.md`      → `./4-arquitectura.md`
  - `./1_instalacion_y_configuracion.md` → `./1-instalacion-configuracion.md`
  ```

### [MEDIUM] Frontend: claim de "Error Boundaries" sin evidencia en el código
- **Ubicación**: línea 133
- **Lo que dice el doc**:
  > "**Diseño Antifragilidad (Límites de Error):** La pantalla está dividida en piezas independientes. Si un bloque falla, el sistema aísla el error para que el resto siga funcionando."
- **Realidad en el código**: no hay ningún `ErrorBoundary` propio en `src/frontend/app/` ni `src/frontend/components/`. Búsqueda `grep -rnE "ErrorBoundary|error.boundary" src/frontend/{app,components}` no retorna resultados (solo coincidencias dentro de `node_modules`). Tampoco existen archivos `error.tsx` (convención de Next.js App Router para boundaries).
- **Cambio sugerido**: o bien implementar los `error.tsx` y mantener el bullet, o eliminarlo:
  ```markdown
  - **Punto de Acceso:** Una pantalla segura para iniciar y cerrar sesión.
  - **Chat Interactivo:** Conversación con la IA con respuestas en streaming palabra por palabra (SSE).
  - **Panel de Control:** Espacio para ver todos los enlaces guardados y revisar el historial de conversaciones.
  ```
  (eliminar el bullet "Diseño Antifragilidad" hasta que existan los Error Boundaries).

### [MEDIUM] `src/ui/chatbot.py` (Streamlit) sigue en el repo, doc dice que fue reemplazado
- **Ubicación**: líneas 137-140
- **Lo que dice el doc**:
  > "Se reemplazó la tecnología anterior (Streamlit) porque era demasiado rígida."
- **Realidad en el código**: el archivo Streamlit aún vive en `src/ui/chatbot.py:6` (`import streamlit as st`). No está enlazado en `docker-compose.yml` (ningún servicio lo arranca), por lo que es código legacy. La afirmación del doc es correcta en intención (Streamlit ya no se usa) pero el lector que mire el repo verá `src/ui/` y se confundirá.
- **Cambio sugerido**: añadir nota o eliminar `src/ui/`. Si la decisión es mantenerlo como referencia histórica, añadir esta nota tras el bullet de "Mayor Seguridad y Control":
  ```markdown
  > Nota: `src/ui/chatbot.py` (Streamlit) se conserva como referencia histórica pero NO está cableado en `docker-compose.yml`. El frontend operativo es exclusivamente `src/frontend/` (Next.js).
  ```

### [MEDIUM] Doc no describe explícitamente `redis-stack-server` (módulos de Redis)
- **Ubicación**: líneas 271-282
- **Lo que dice el doc**:
  > "Para garantizar estabilidad. Obligamos al sistema a no utilizar versiones 'más recientes' de Redis con sorpresas, sino una versión probada para que cosas vitales como el Bloom Filter no se rompan por actualizaciones silenciosas."
- **Realidad en el código**: la imagen es `redis/redis-stack-server:latest@sha256:798ab84d9f266936b034ab11c4d04a2b8e4b441884c5aa7d17ac951eefdf742a` (evidencia: `docker-compose.yml:389`). El tag es `:latest` con SHA-pinning — *no* es un tag versionado fijo como `:7.2.x`. El Bloom Filter funciona porque `redis-stack` incluye RedisBloom como módulo. El doc da a entender una versión "probada" pero el pinning real es por digest de la imagen `latest`.
- **Cambio sugerido**:
  ```markdown
  Para garantizar estabilidad. Usamos `redis/redis-stack-server` (incluye el módulo RedisBloom necesario para el deduplicator) pinneado por SHA256 (no por tag), para que el Bloom Filter no se rompa por actualizaciones silenciosas de `:latest`.
  ```

### [MEDIUM] Doc no menciona explícitamente la extensión de navegador como cliente
- **Ubicación**: §1 / §2 — el doc nombra "la extensión de tu navegador" pero no le dedica una sección
- **Lo que dice el doc**:
  > "Es un servicio ligero dedicado exclusivamente a recibir enlaces nuevos (ya sea desde la extensión de tu navegador, Telegram u otras aplicaciones)" (línea 87)
- **Realidad en el código**: existe `clientes/browser-extension/` con `background.js`, `manifest.json`, `popup.html`, `popup.js`, `options.html`, `options.js`. Es un cliente real, no "una de tantas apps". El scope del doc es servidores+contenedores, así que omitirlo podría justificarse, pero conviene mencionarlo (al menos como link) ya que es el flujo principal de ingesta de URLs.
- **Cambio sugerido**: tras el primer párrafo de cerebro-ingestion, añadir:
  ```markdown
  > El cliente principal que dispara `POST /ingest` es la extensión de navegador (`clientes/browser-extension/`); también hay flujo Telegram (`POST /webhook/telegram/{token_hash}`).
  ```

### [MEDIUM] Doc no menciona `cerebro-litellm` como contenedor con DB Postgres (store_model_in_db)
- **Ubicación**: §4 "cerebro-litellm" (líneas 201-222)
- **Lo que dice el doc**:
  > Describe LiteLLM como proxy con fallback, circuit breaker y caché.
- **Realidad en el código**: además LiteLLM almacena modelos en Postgres (`store_model_in_db: true`, `infra/litellm/config.yaml:64`) y aplica `global_max_parallel_requests: 100` + `max_budget: 50` (líneas 65-66). El "circuit breaker" del doc se materializa como `allowed_fails: 1 + cooldown_time: 15` (líneas 46-47 y 75-76). Vale la pena citar los números reales para que el lector no busque a ciegas.
- **Cambio sugerido**: añadir tras el bullet "Interruptor de Seguridad":
  ```markdown
  - **Interruptor de Seguridad (Circuit Breaker):** Si un proveedor falla `allowed_fails: 1` vez, deja de enviarle peticiones durante `cooldown_time: 15` segundos (configurado en `infra/litellm/config.yaml`).
  - **Persistencia de Modelos:** Mantiene el catálogo de modelos en Postgres (`store_model_in_db: true`) — por eso depende de la BD principal aunque la limpie Prisma en el schema `public`.
  ```

### [MEDIUM] `cerebro-outbox` no usa el schema cualificado en la query
- **Ubicación**: línea 191
- **Lo que dice el doc**:
  > "Este trabajador revisa constantemente la tabla `cerebro.outbox_eventos` en Postgres…"
- **Realidad en el código**: la query SQL referencia la tabla sin prefijo `cerebro.`: `FROM outbox_eventos` (evidencia: `src/data/outbox_publisher.py:54, 97, 114`). El acceso depende del `search_path` (configurado a `cerebro, public` en `infra/postgres/init.sql:20`). El doc no es técnicamente falso (la tabla vive en el schema `cerebro`) pero el snippet "literal" confunde al lector que haga `grep cerebro.outbox_eventos` en el código.
- **Cambio sugerido**:
  ```markdown
  Utiliza el **Patrón Outbox**. Este trabajador revisa constantemente la tabla `outbox_eventos` (en el schema `cerebro` vía `search_path`) en Postgres buscando tareas recién terminadas por el scraper que necesitan ser enviadas al embedder. Cuando encuentra una, la entrega de forma segura a RabbitMQ (cola `q.embeddings`).
  ```

### [LOW] Doc dice "100 por segundo por usuario" sin precisar `burst`
- **Ubicación**: línea 33
- **Lo que dice el doc**:
  > "bloquea automáticamente los excesos impidiendo que entren demasiadas peticiones de golpe (el máximo promedio es de 100 por segundo por usuario)"
- **Realidad en el código**: `docker-compose.yml:330-331`:
  ```yaml
  - "traefik.http.middlewares.global-ratelimit.ratelimit.average=100"
  - "traefik.http.middlewares.global-ratelimit.ratelimit.burst=50"
  ```
  Existe un `burst=50` adicional sobre el `average=100/s`. La unidad/identidad se basa en `sourceCriterion` default de Traefik (IP del request).
- **Cambio sugerido**:
  ```markdown
  - **Control de Multitudes (Rate Limiting):** Para prevenir sobrecargas o ataques, bloquea automáticamente los excesos. El máximo promedio es 100 req/s por IP, con `burst` de 50 (config: `traefik.http.middlewares.global-ratelimit` en `docker-compose.yml`).
  ```

### [LOW] Doc dice "infra/litellm/config.yaml" sin precisar la duración de cache TTL
- **Ubicación**: línea 212
- **Lo que dice el doc**:
  > "**Memoria de Ahorro (Caché):** Recuerda las preguntas frecuentes para responder al instante y ahorrar costos (caché en Redis)."
- **Realidad en el código**: el TTL del caché en Redis es 1 hora (`ttl: 3600`, `infra/litellm/config.yaml:60`) y solo aplica a `completion, embedding` (líneas 56-58).
- **Cambio sugerido**:
  ```markdown
  - **Memoria de Ahorro (Caché):** Recuerda las respuestas de `completion` y `embedding` en Redis con TTL de 1 hora (`infra/litellm/config.yaml`: `cache_params.ttl: 3600`).
  ```

### [UNVERIFIED] Trace-ID inyectado por Traefik
- **Ubicación**: línea 35
- **Lo que dice el doc**:
  > "**Etiqueta de Seguimiento (Trace-ID):** Le coloca un identificador único (como un gafete de visitante numerado) a cada conexión."
- **Realidad en el código**: en `docker-compose.yml:297-340` Traefik tiene `--tracing.otlp.http.endpoint=http://otel-collector:4318/v1/traces` (línea 316) pero no se encontró configuración explícita de inyección de header `X-Trace-Id` ni `X-Request-Id` propagado a backend en los labels. Puede que sea funcionalidad implícita del tracing OTLP de Traefik 3.x; requiere validar en runtime con un curl al gateway y mirar headers que llegan al backend.
- **Cambio sugerido**: confirmar comportamiento real con `curl -v https://ingest.localhost/...` y, si Traefik solo emite el span OTLP pero no inyecta header, reformular:
  ```markdown
  - **Trazas distribuidas:** Traefik emite spans a OTel Collector vía OTLP (`--tracing.otlp.http.endpoint`). El trace-id se propaga a backends que respeten W3C Trace Context.
  ```

### [UNVERIFIED] Bloom Filter "es un hint, no un veto — idempotencia real aguas abajo"
- **Ubicación**: línea 89
- **Lo que dice el doc**:
  > "El bloom es un *hint*, no un veto — la idempotencia real se resuelve aguas abajo."
- **Realidad en el código**: `src/ingestion/deduplicator.py:31-51` implementa `BF.RESERVE` + `BF.ADD`. La afirmación de que es "hint" requiere ver el call-site en `src/ingestion/main.py` para confirmar si el 202 se devuelve incluso ante hit de Bloom o si se corta ahí. No se inspeccionó esa lógica con suficiente profundidad para confirmar/desmentir.
- **Cambio sugerido**: confirmar el comportamiento del call-site en `src/ingestion/main.py` (alrededor del manejo de duplicados) y precisar:
  ```markdown
  - **Filtro de Duplicados:** Utiliza un Bloom Filter en Redis (RedisBloom `BF.ADD`) como pre-filtro probabilístico. La deduplicación definitiva ocurre aguas abajo en `recursos.url_hash` (UNIQUE) en Postgres.
  ```

## Aprobado sin cambios

- §1 "Tailscale Funnel" — profile `telegram`, `serve.json` proxy a `ingestion-api:8000`, volumen `tailscale-state`, `AllowFunnel: true` — verificado contra `docker-compose.yml:861-887` e `infra/tailscale/serve.json`.
- §2 cerebro-ingestion — `INCR + EXPIRE atómico` y `202 Accepted` — verificado contra `src/ingestion/main.py:123-125` (comentario `F-06.4 Noisy Neighbor Defense — INCR atómico evita race TOCTOU`).
- §2 cerebro-api — JWT en cookie httpOnly + CSRF double-submit + `httpx.AsyncClient` compartido — verificado contra `src/api/main.py:395, 402, 533-557, 615-629`.
- §2 cerebro-api — `setWebhook` de Telegram desde el backend — verificado contra `src/api/main.py:1147-1150`.
- §2 cerebro-web — store Zustand — verificado contra `src/frontend/package.json:22` (`"zustand": "^5.0.3"`).
- §3 cerebro-scraper — `_looks_blocked()`, guard de 300 chars, rewrite `medium.com → readmedium.com` — verificado contra `src/scraper/strategy.py:41-48, 118, 158-165, 180-205` y `src/scraper/worker.py:229-290`.
- §3 cerebro-scraper — `shm_size: 1gb` para Chromium — verificado contra `docker-compose.yml:59`.
- §3 cerebro-embedder — flujo `reused=True` para reutilizar embeddings entre tenants — verificado contra `src/data/embedder_worker.py:370-409`.
- §3 cerebro-embedder — `point_id = uuid5(ns, "<recurso_id>:<tenant_id>")` — verificado contra `src/data/embedder_worker.py:34-39, 199`.
- §4 cerebro-litellm — fallback + retries + caché Redis — verificado contra `infra/litellm/config.yaml:45-60, 69-76` (`num_retries: 3`, `cache: true`, `type: redis`).
- §4 cerebro-litellm — schema isolation Prisma → `cerebro` — verificado contra `infra/postgres/init.sql:13-20`.
- §4 cerebro-n8n — schema `n8n` aislado — verificado contra `docker-compose.yml:563` (`DB_POSTGRESDB_SCHEMA: n8n`).
- §4 cerebro-n8n-bootstrap — one-shot generador de API key — verificado contra `infra/n8n/bootstrap-apikey.sh` e `infra/n8n/bootstrap-apikey.py`.
- §5 cerebro-rabbitmq — DLQ + colas `q.url.ingesta` / `q.embeddings` — verificado contra `src/ingestion/main.py`, `src/data/outbox_publisher.py` y `src/dlq/dlq_manager.py`.
- §5 cerebro-qdrant — multi-tenant via `point_id` uuid5 + HNSW — verificado contra `src/data/embedder_worker.py:140-169, 198-209, 298-341`.
- §6 Exporters — los tres exporters con imagen pinneada por SHA (rabbitmq-exporter, redis-exporter, postgres-exporter) — verificado contra `docker-compose.yml:780, 809, 836`.
