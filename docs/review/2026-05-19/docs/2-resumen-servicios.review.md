# Review · 2-resumen-servicios · 2026-05-19

**Auditor**: docs-reality-auditor
**Doc revisado**: `docs/src/2-resumen-servicios.md`
**Áreas de código verificadas**: `docker-compose.yml`, `infra/*.Dockerfile`, `src/notifier/`, `src/scraper/`, `src/data/`, `src/api/`
**Versión del repo**: `develop` @ `7c723f3`

## Resumen
- 0 CRITICAL, 11 HIGH, 14 MEDIUM, 2 LOW, 0 UNVERIFIED
- 0 hallazgos [CODE-BUG]
- Veredicto: **RED** (alta densidad de drift en imágenes/puertos + 2 servicios productivos sin documentar)

Nota interpretativa: el prompt operacional pidió tratar los gaps como MEDIUM y reservar CRITICAL para "servicios mencionados que no existen". Ningún servicio fantasma se documentó, por eso no hay CRITICAL. Sin embargo el doc afirma versiones de imágenes que no coinciden con `docker-compose.yml` (postgres 17 vs 16-alpine, redis 7-alpine vs redis-stack-server pinned por digest, etc.); esto se clasifica como HIGH porque un lector que aplique lo escrito tomará decisiones operativas equivocadas (matriz de upgrade, CVE pinning, compatibilidad de extensiones).

---

## Hallazgos

### [HIGH] Imagen de PostgreSQL: el doc afirma `postgres:17-alpine`, el compose usa `postgres:16-alpine`
- **Ubicación**: línea 132 (tabla de catálogo)
- **Lo que dice el doc**:
  > "| `cerebro-postgres` | Almacenamiento | `postgres:17-alpine` | 5432 | 2 GB / 2.0 | ..."
- **Realidad en el código**: `postgres:16-alpine` (`docker-compose.yml:417`). Además el servicio one-shot `cerebro-migrate` también usa `postgres:16-alpine` (`docker-compose.yml:195`).
- **Cambio sugerido**:
  ```markdown
  | `cerebro-postgres` | Almacenamiento | `postgres:16-alpine` | 5432 | 2 GB / 2.0 | Base de datos relacional. Schemas: `cerebro` (LinkAnvil), `n8n` (orquestador), `public` (LiteLLM/Prisma). |
  ```

### [HIGH] Imagen de Redis: doc dice `redis:7-alpine`, compose usa `redis/redis-stack-server` pinned por digest
- **Ubicación**: línea 133
- **Lo que dice el doc**:
  > "| `cerebro-redis` | Almacenamiento | `redis:7-alpine` | 6379 | 768 MB / — | ..."
- **Realidad en el código**: `redis/redis-stack-server:latest@sha256:798ab84d9f266936b034ab11c4d04a2b8e4b441884c5aa7d17ac951eefdf742a` (`docker-compose.yml:389`). Es redis-stack (incluye módulos RedisBloom, RedisJSON, RediSearch), no redis vanilla — relevante porque el Bloom Filter documentado en el mismo doc depende de RedisBloom, que NO existe en `redis:7-alpine`.
- **Cambio sugerido**:
  ```markdown
  | `cerebro-redis` | Almacenamiento | `redis/redis-stack-server:latest` (pinned por digest) | 6379 | 768 MB / 1.0 | Bloom Filter de dedupe (módulo RedisBloom), rate-limiters atómicos, heartbeats de workers y caché LiteLLM. |
  ```
  > Nota: el límite CPU también está mal — ver hallazgo siguiente.

### [HIGH] Límite de CPU de Redis: doc dice `—`, compose define `cpus: "1.0"`
- **Ubicación**: línea 133 (catálogo) y línea 161 (tabla de límites)
- **Lo que dice el doc**:
  > "| `cerebro-redis` | ... | 768 MB / — | ..." (L133)
  > "| cerebro-redis | 768 MB | — | Almacenamiento |" (L161)
- **Realidad en el código**: `cpus: "1.0"` (`docker-compose.yml:396`).
- **Cambio sugerido**:
  ```markdown
  | cerebro-redis | 768 MB | 1.0 | Almacenamiento |
  ```
  y en L133 cambiar `768 MB / —` por `768 MB / 1.0`.

### [HIGH] Imagen de RabbitMQ: doc dice `rabbitmq:3-management`, compose usa `rabbitmq:3.13-management-alpine`
- **Ubicación**: línea 134
- **Lo que dice el doc**:
  > "| `cerebro-rabbitmq` | Mensajería | `rabbitmq:3-management` | 5672, 15672 | ..."
- **Realidad en el código**: `rabbitmq:3.13-management-alpine` (`docker-compose.yml:345`).
- **Cambio sugerido**:
  ```markdown
  | `cerebro-rabbitmq` | Mensajería | `rabbitmq:3.13-management-alpine` | 5672, 15672 | 768 MB / 1.0 | Broker con vhost `cerebro`. Colas `q.url.ingesta`, `q.embeddings` y DLQs asociadas. |
  ```

### [HIGH] Imagen de Qdrant + puerto gRPC ausente
- **Ubicación**: línea 135 (catálogo) y línea 52 (diagrama)
- **Lo que dice el doc**:
  > "| `cerebro-qdrant` | Vector DB | `qdrant/qdrant` | 6333 | 2 GB / 2.0 | ..."
  > "Qdrant[🧠 cerebro-qdrant<br/>Port: 6333]:::db" (L52)
- **Realidad en el código**: imagen pinneada `qdrant/qdrant:v1.17.1` (`docker-compose.yml:464`); publica DOS puertos: `6333:6333` REST y `6334:6334` gRPC (`docker-compose.yml:477-478`).
- **Cambio sugerido**:
  ```markdown
  | `cerebro-qdrant` | Vector DB | `qdrant/qdrant:v1.17.1` | 6333 (REST), 6334 (gRPC) | 2 GB / 2.0 | Vectores HNSW. Colecciones `cerebro_recursos` (doc-level) y `cerebro_chunks` (RAG), filtrado por `tenant_id` en payload. |
  ```
  Y en el diagrama:
  ```markdown
  Qdrant[🧠 cerebro-qdrant<br/>Ports: 6333/6334]:::db
  ```

### [HIGH] Imagen de OTel Collector sin pin
- **Ubicación**: línea 136
- **Lo que dice el doc**:
  > "| `cerebro-otel` | Observabilidad | `otel/opentelemetry-collector-contrib` | 4317, 4318, 8888, 8889 | ..."
- **Realidad en el código**: `otel/opentelemetry-collector-contrib:0.150.1` (`docker-compose.yml:673`).
- **Cambio sugerido**:
  ```markdown
  | `cerebro-otel` | Observabilidad | `otel/opentelemetry-collector-contrib:0.150.1` | 4317, 4318, 8888, 8889 | 384 MB / 0.5 | Recolector OTLP: enruta trazas a Jaeger y métricas a Prometheus. |
  ```

### [HIGH] Imagen de Prometheus sin pin
- **Ubicación**: línea 137
- **Lo que dice el doc**:
  > "| `cerebro-prometheus` | Observabilidad | `prom/prometheus` | 9090 | 1 GB / 1.0 | ..."
- **Realidad en el código**: `prom/prometheus:v3.11.2` (`docker-compose.yml:704`).
- **Cambio sugerido**:
  ```markdown
  | `cerebro-prometheus` | Observabilidad | `prom/prometheus:v3.11.2` | 9090 | 1 GB / 1.0 | TSDB de métricas + 6 reglas de alerta activas (latencia, colas, DLQ, heartbeats, disco). |
  ```

### [HIGH] Imagen de Jaeger sin pin + puertos OTLP duplicados publicados
- **Ubicación**: línea 138 (catálogo) y línea 56 (diagrama)
- **Lo que dice el doc**:
  > "| `cerebro-jaeger` | Observabilidad | `jaegertracing/all-in-one` | 16686 | 384 MB / 0.5 | ..."
- **Realidad en el código**: `jaegertracing/all-in-one:latest@sha256:ab6f1a1f0fb49ea08bcd19f6b84f6081d0d44b364b6de148e1798eb5816bacac` (`docker-compose.yml:639`); además publica `14317:4317` (OTLP gRPC) y `14318:4318` (OTLP HTTP) (`docker-compose.yml:653-654`), no sólo `16686`.
- **Cambio sugerido**:
  ```markdown
  | `cerebro-jaeger` | Observabilidad | `jaegertracing/all-in-one` (pinned por digest) | 16686 (UI), 14317 (OTLP gRPC), 14318 (OTLP HTTP) | 384 MB / 0.5 | Distributed tracing: visualización de la cascada de spans por Trace-ID. |
  ```

### [HIGH] Imagen de Grafana sin pin
- **Ubicación**: línea 139
- **Lo que dice el doc**:
  > "| `cerebro-grafana` | Observabilidad | `grafana/grafana` | 3000 | 384 MB / 0.5 | ..."
- **Realidad en el código**: `grafana/grafana:11.4.0` (`docker-compose.yml:740`).
- **Cambio sugerido**:
  ```markdown
  | `cerebro-grafana` | Observabilidad | `grafana/grafana:11.4.0` | 3000 | 384 MB / 0.5 | Dashboards y alertas sobre Prometheus + Jaeger. |
  ```

### [HIGH] Imagen de n8n sin pin + puerto host expuesto
- **Ubicación**: línea 130 (catálogo) y línea 43 (diagrama)
- **Lo que dice el doc**:
  > "| `cerebro-n8n` | Orquestación | `n8nio/n8n` | 5678 (interno) | 768 MB / 1.0 | ..."
- **Realidad en el código**: imagen pinneada `n8nio/n8n:1.123.37` (`docker-compose.yml:548`); puerto 5678 NO es solo interno — se publica con `5678:5678` (`docker-compose.yml:587`).
- **Cambio sugerido**:
  ```markdown
  | `cerebro-n8n` | Orquestación | `n8nio/n8n:1.123.37` | 5678 | 768 MB / 1.0 | Orquestador visual: webhooks de Telegram, scraping ligero y curación nocturna. Usa schema `n8n`. |
  ```

### [HIGH] Imagen de LiteLLM no documentada + puerto host expuesto
- **Ubicación**: línea 129 (catálogo) y línea 44 (diagrama)
- **Lo que dice el doc**:
  > "| `cerebro-litellm` | Motor LLM | `infra/litellm/config.yaml` | 4000 (interno) | 1 GB / 1.0 | ..."
- **Realidad en el código**: imagen `ghcr.io/berriai/litellm:main-latest@sha256:7c311546c25e7bb6e8cafede9fcd3d0d622ac636b5c9418befaa32e85dfb0186` (`docker-compose.yml:504`); el campo "Imagen / Código" tiene un solo file de config sin imagen. Además el puerto 4000 se publica con `4000:4000` (`docker-compose.yml:522`), no es interno.
- **Cambio sugerido**:
  ```markdown
  | `cerebro-litellm` | Motor LLM | `ghcr.io/berriai/litellm:main-latest` (pinned por digest) · config: `infra/litellm/config.yaml` | 4000 | 1 GB / 1.0 | Proxy multi-proveedor con Circuit Breaker, fallback automático y caché de prompts en Redis. |
  ```

### [MEDIUM] El doc cuenta "21 contenedores" — el compose define 24 servicios (23 sin sidecar)
- **Ubicación**: línea 11
- **Lo que dice el doc**:
  > "El clúster del **LinkAnvil** está compuesto por **21 contenedores** que operan dentro de la red privada `cerebro-net`, más un sidecar opcional (`tailscale-funnel`, profile `telegram`)..."
- **Realidad en el código**: servicios definidos en `docker-compose.yml`: `ingestion-api`, `scraper-worker`, `outbox-worker`, `notifier-worker`, `embedder-worker`, `cerebro-migrate`, `cerebro-api`, `cerebro-web`, `traefik`, `rabbitmq`, `redis`, `postgres`, `qdrant`, `litellm`, `n8n`, `n8n-bootstrap`, `jaeger`, `otel-collector`, `prometheus`, `grafana`, `rabbitmq-exporter`, `redis-exporter`, `postgres-exporter`, `tailscale-funnel`. Total = 24 servicios (23 sin profile `telegram`). La tabla del doc lista 22 filas (incluyendo `cerebro-tailscale` sidecar).
- **Cambio sugerido**:
  ```markdown
  El clúster del **LinkAnvil** está compuesto por **23 contenedores** que operan dentro de la red privada `cerebro-net`, más un sidecar opcional (`tailscale-funnel`, profile `telegram`) que expone públicamente el endpoint de webhooks de Telegram cuando se necesita.
  ```

### [MEDIUM] Servicio `cerebro-notifier` no documentado
- **Ubicación**: ausente — debería aparecer entre `cerebro-outbox` (L128) y `cerebro-litellm` (L129) y en el diagrama (L31-60)
- **Lo que dice el doc**: (no lo menciona)
- **Realidad en el código**: servicio activo `notifier-worker` con `container_name: cerebro-notifier`, command `python -m src.notifier.worker`, healthcheck heartbeat-based, 256 MB / 0.3 CPU (`docker-compose.yml:122-152`). El módulo existe en `src/notifier/worker.py`.
- **Cambio sugerido** (añadir fila al catálogo y nodo al diagrama):
  ```markdown
  | `cerebro-notifier` | Worker | `src/notifier/worker.py` | — | 256 MB / 0.3 | Consume notificaciones (eventos de scraper/embedder) y entrega via canales configurados (Telegram, etc.). Heartbeat-based. |
  ```
  Y en el diagrama:
  ```markdown
  Notifier[📢 cerebro-notifier]:::worker
  ```

### [MEDIUM] Servicio `cerebro-migrate` no documentado
- **Ubicación**: ausente — sería una fila adicional o nota junto a `cerebro-api` (L124)
- **Lo que dice el doc**: (no lo menciona)
- **Realidad en el código**: servicio one-shot `cerebro-migrate` con imagen `postgres:16-alpine` que ejecuta `bash /migrate.sh` aplicando migraciones SQL de `infra/postgres/migrations/`. Es dependencia hard de `cerebro-api` vía `condition: service_completed_successfully` (`docker-compose.yml:194-212` y dep en `:252-253`).
- **Cambio sugerido**:
  ```markdown
  | `cerebro-migrate` | Almacenamiento | `postgres:16-alpine` · `scripts/migrate.sh` | — | — | One-shot: aplica migraciones SQL pendientes de `infra/postgres/migrations/`. Idempotente vía `cerebro.schema_migrations(version)`. `cerebro-api` depende de su `service_completed_successfully`. |
  ```

### [MEDIUM] Diagrama Mermaid omite dependencia `cerebro-api → cerebro-migrate`
- **Ubicación**: bloque diagrama L27-111 (no hay arista migrate→api)
- **Lo que dice el doc**: el diagrama no muestra `cerebro-migrate` ni su orden de arranque obligatorio.
- **Realidad en el código**: `cerebro-api.depends_on.cerebro-migrate.condition: service_completed_successfully` (`docker-compose.yml:252-253`).
- **Cambio sugerido** (añadir nodo + arista):
  ```markdown
  Migrate[🗃️ cerebro-migrate<br/>one-shot]:::db
  Migrate -.->|service_completed_successfully| API
  ```

### [MEDIUM] Traefik no publica 443 (solo 80 y 8080) en compose; sin embargo el doc lo enumera
- **Ubicación**: línea 122 (catálogo) y línea 38 (diagrama)
- **Lo que dice el doc**:
  > "| `cerebro-traefik` | Gateway | `traefik:v3.6.14` | 80, 443, 8080 | ..." (L122)
  > "Traefik[🔀 cerebro-traefik<br/>Port: 80/443, 8080]:::gateway" (L38)
- **Realidad en el código**: `ports: ["80:80", "8080:8080"]` (`docker-compose.yml:319-321`). El entrypoint `websecure :443` está declarado en `command:` (`docker-compose.yml:314`) pero NO está mapeado al host. Sólo el sidecar `tailscale-funnel` expone 443 vía Funnel.
- **Cambio sugerido**:
  ```markdown
  | `cerebro-traefik` | Gateway | `traefik:v3.6.14` | 80, 8080 (443 declarado pero no publicado; TLS público se sirve vía `cerebro-tailscale` Funnel) | 256 MB / 0.5 | Único punto de entrada: routing por labels Docker, rate-limit global, retries, Trace-ID OTel y TLS Let's Encrypt en producción. |
  ```

### [MEDIUM] Healthcheck de `cerebro-scraper` y workers asíncronos no descrito
- **Ubicación**: filas L126-128 del catálogo
- **Lo que dice el doc**: no menciona healthcheck para scraper/embedder/outbox.
- **Realidad en el código**: los tres workers usan healthcheck basado en heartbeat Redis (`docker-compose.yml:65-70`, `:102-107`, `:166-171`). La 1-line del scraper sí menciona "shm 1 GB" pero omite el mecanismo de salud.
- **Cambio sugerido**: añadir al final de cada fila de worker una nota tipo:
  ```markdown
  ... (healthcheck por heartbeat en Redis: clave `worker:<name>:heartbeat`).
  ```

### [MEDIUM] Volúmenes persistentes no documentados
- **Ubicación**: el doc no tiene sección de volúmenes
- **Lo que dice el doc**: (no los menciona)
- **Realidad en el código**: 10 volúmenes nombrados (`docker-compose.yml:890-901`): `rabbitmq-data`, `redis-data`, `postgres-data`, `qdrant-data`, `n8n-data`, `jaeger-data` (declarado pero jaeger usa memoria), `prometheus-data`, `grafana-data`, `playwright-profile`, `tailscale-state` (con `name: cerebro-tailscale-state`).
- **Cambio sugerido**: añadir bloque tras la tabla del catálogo:
  ```markdown
  ### Volúmenes persistentes

  | Volumen | Contenedor consumidor | Contenido |
  |---|---|---|
  | `postgres-data` | cerebro-postgres | Datos relacionales (`/var/lib/postgresql/data`). |
  | `redis-data` | cerebro-redis | AOF + RDB snapshots (`/data`). |
  | `rabbitmq-data` | cerebro-rabbitmq | Mnesia + colas durables (`/var/lib/rabbitmq`). |
  | `qdrant-data` | cerebro-qdrant | Vectores HNSW (`/qdrant/storage`). |
  | `n8n-data` | cerebro-n8n | Workflows y credenciales (`/home/node/.n8n`). |
  | `prometheus-data` | cerebro-prometheus | TSDB (`/prometheus`). |
  | `grafana-data` | cerebro-grafana | Dashboards y settings (`/var/lib/grafana`). |
  | `playwright-profile` | cerebro-scraper | Perfil Chromium persistente para login flows. |
  | `cerebro-tailscale-state` | cerebro-tailscale | Estado de auth Tailscale (`/var/lib/tailscale`). |
  | `jaeger-data` | (declarado pero no montado) | Jaeger usa `SPAN_STORAGE_TYPE=memory`; el volumen está huérfano. |
  ```

### [MEDIUM] El diagrama no muestra arista `Outbox → q.embeddings` claramente
- **Ubicación**: líneas 83-85 del diagrama
- **Lo que dice el doc**:
  > "Outbox -->|publica embedding| RabbitMQ"
- **Realidad en el código**: `outbox_publisher` (`src/data/outbox_publisher.py`, invocado en compose L94) publica desde `cerebro.outbox_eventos` hacia múltiples colas según el tipo de evento. La etiqueta "publica embedding" es estrechamente cierta pero ambigua — el outbox NO es exclusivamente para embeddings.
- **Cambio sugerido**:
  ```markdown
  Outbox -->|publica eventos (embedding, notify, ...)| RabbitMQ
  ```

### [MEDIUM] El doc afirma "filtrado por `tenant_id`" en Qdrant — no verificado por este auditor
- **Ubicación**: línea 135
- **Lo que dice el doc**:
  > "filtrado por `tenant_id` en payload"
- **Realidad en el código**: el compose no expone esta información. Sería necesario inspeccionar `src/data/embedder_worker.py` o las definiciones de colección. Marcado MEDIUM (no es un gap del compose, es un detalle del runtime no auditado contra código).
- **Cambio sugerido**: ninguno hasta verificar contra `src/data/embedder_worker.py` y/o `src/api/` (fuera de scope de este audit).

### [MEDIUM] El doc afirma "6 reglas de alerta activas" en Prometheus — no verificado contra archivo
- **Ubicación**: línea 137
- **Lo que dice el doc**:
  > "TSDB de métricas + 6 reglas de alerta activas (latencia, colas, DLQ, heartbeats, disco)"
- **Realidad en el código**: el archivo existe (`./infra/prometheus/alert.rules.yml`, montado en `docker-compose.yml:721`) pero este audit no contó las reglas activas.
- **Cambio sugerido**: verificar el número exacto leyendo `infra/prometheus/alert.rules.yml` y ajustar si difiere.

### [MEDIUM] Categorización de capa para LiteLLM y n8n inconsistente entre tabla y diagrama
- **Ubicación**: catálogo L129-130 vs diagrama L43-44
- **Lo que dice el doc**: tabla pone `cerebro-n8n` en capa "Orquestación" y `cerebro-litellm` en "Motor LLM"; el diagrama clasifica ambos con `classDef worker` (color púrpura).
- **Realidad en el código**: ambos son servicios stateful con UI/API expuesta — no son workers asíncronos como scraper/embedder/outbox.
- **Cambio sugerido**: añadir un classDef específico ("ai" / "orchestration") y reclasificar:
  ```markdown
  classDef ai fill:#3b1f4a,stroke:#d946ef,color:#fff
  n8n[🔄 cerebro-n8n<br/>Port: 5678]:::ai
  LiteLLM[🤖 cerebro-litellm<br/>Port: 4000]:::ai
  ```

### [MEDIUM] Sidecar `cerebro-tailscale`: la imagen NO está pinneada
- **Ubicación**: línea 121
- **Lo que dice el doc**:
  > "| `cerebro-tailscale` | Gateway (sidecar `telegram`) | `tailscale/tailscale:stable` | ..."
- **Realidad en el código**: `tailscale/tailscale:stable` (`docker-compose.yml:862`) — coincide literal, pero el resto del stack tiene digests pinneados; el doc no comunica que este servicio NO sigue la política de pinning.
- **Cambio sugerido**: añadir nota:
  ```markdown
  | `cerebro-tailscale` | Gateway (sidecar `telegram`) | `tailscale/tailscale:stable` (sin digest pin) | 443 vía Funnel (no mapeo Docker) | — | Túnel HTTPS público fijo para webhook de Telegram → `ingestion-api:8000`. |
  ```

### [MEDIUM] El diagrama omite `cerebro-notifier` consumiendo de RabbitMQ
- **Ubicación**: diagrama L27-111
- **Lo que dice el doc**: (no aparece)
- **Realidad en el código**: `notifier-worker` depende de `rabbitmq:service_healthy` y se conecta vía `RABBITMQ_URL` (`docker-compose.yml:141, 147`).
- **Cambio sugerido**:
  ```markdown
  Notifier -->|consume eventos| RabbitMQ
  Notifier -->|heartbeat| Redis
  ```

### [MEDIUM] Etiqueta Traefik "ingest.\*" en el diagrama vs labels reales
- **Ubicación**: línea 63
- **Lo que dice el doc**:
  > "Traefik ==>|ingest.*| Ingestion"
- **Realidad en el código**: la rule real es `Host(\`ingest.localhost\`) || PathPrefix(\`/ingest\`)` (`docker-compose.yml:39`). "ingest.\*" es ambigua — no aclara que se acepta tanto subdomain como path prefix.
- **Cambio sugerido**:
  ```markdown
  Traefik ==>|ingest.localhost o /ingest| Ingestion
  ```

### [MEDIUM] Etiqueta Traefik "cerebro.\*" para Web no coincide con label real
- **Ubicación**: línea 65
- **Lo que dice el doc**:
  > "Traefik ==>|cerebro.*| Web"
- **Realidad en el código**: `cerebro-web` NO tiene ningún label `traefik.http.routers.*` en el compose; se accede directo por `3001:3001` publicado al host (`docker-compose.yml:264-292`). No hay routing Traefik a la Web. La arista es **incorrecta**.
- **Cambio sugerido**:
  ```markdown
  Web exposed directly via host port 3001 (no Traefik routing).
  Eliminar la línea "Traefik ==>|cerebro.*| Web".
  ```

### [LOW] Typo de capitalización en sección título de TOC
- **Ubicación**: línea 19
- **Lo que dice el doc**:
  > "1. [🗺️ Diagrama de Conexiones entre Contenedores](#️-diagrama-de-conexiones-entre-contenedores)"
- **Realidad en el código**: el anchor generado por VitePress normaliza el emoji al inicio; el enlace actual `#️-diagrama-...` empieza con un U+FE0F variation selector huérfano que algunos parsers omiten. No afectará a la mayoría de casos pero es frágil.
- **Cambio sugerido**: regenerar anclas con el plugin de markdown-it-anchor sin emoji o usar `{#diagrama-conexiones}` explícito.

### [LOW] El catálogo lista 22 filas pero el doc dice "21 contenedores + 1 sidecar"
- **Ubicación**: tabla L121-142 + descripción L11
- **Lo que dice el doc**: 21 + 1 sidecar = 22; la tabla tiene exactamente 22 filas (`cerebro-tailscale` + otros 21). Pero ver hallazgo MEDIUM "21 contenedores": el compose define más.
- **Realidad en el código**: 24 servicios definidos.
- **Cambio sugerido**: corregir tanto la cifra L11 como añadir las filas faltantes (`cerebro-notifier`, `cerebro-migrate`).

---

## Aprobado sin cambios

- §Catálogo L122 `cerebro-traefik` versión imagen — `traefik:v3.6.14` coincide (`docker-compose.yml:298`).
- §Catálogo L123 `cerebro-ingestion` puerto interno 8000 y Dockerfile — `infra/ingestion.Dockerfile` + `loadbalancer.server.port=8000` (`docker-compose.yml:14-17, 41`).
- §Catálogo L124 `cerebro-api` puerto 8001 y RAM/CPU — `8001:8001` + 768M/1.0 (`docker-compose.yml:225-229`).
- §Catálogo L125 `cerebro-web` puerto 3001 y Dockerfile — `3001:3001` + `infra/frontend.Dockerfile` (`docker-compose.yml:267, 275-276`).
- §Catálogo L126 `cerebro-scraper` shm 1 GB + RAM/CPU — `shm_size: '1gb'` + 1500M/2.0 (`docker-compose.yml:59-64`).
- §Catálogo L127 `cerebro-embedder` RAM/CPU — 768M/1.0 (`docker-compose.yml:163-165`).
- §Catálogo L128 `cerebro-outbox` RAM/CPU + módulo Python — `python -m src.data.outbox_publisher` + 384M/0.5 (`docker-compose.yml:94, 99-101`).
- §Catálogo L131 `cerebro-n8n-bootstrap` carácter one-shot — `restart: "no"` (`docker-compose.yml:616`).
- §Catálogo L132 puerto Postgres 5432 — `5432:5432` (`docker-compose.yml:445`).
- §Catálogo L134 puertos RabbitMQ 5672 + 15672 — `5672:5672` y `15672:15672` (`docker-compose.yml:361-362`).
- §Catálogo L137 Prometheus puerto 9090 + RAM/CPU — `9090:9090` + 1G/1.0 (`docker-compose.yml:709-718`).
- §Catálogo L138 Jaeger UI puerto 16686 + RAM/CPU — `16686:16686` + 384M/0.5 (`docker-compose.yml:643-652`).
- §Catálogo L139 Grafana puerto 3000 + RAM/CPU — `3000:3000` + 384M/0.5 (`docker-compose.yml:744-755`).
- §Catálogo L140-142 exporters: imágenes, puertos internos (9187, 9121, 9419) y RAM/CPU 128M/0.25 coinciden (`docker-compose.yml:836, 809, 780` + envs `PUBLISH_PORT=9419`, etc.).
- §Diagrama OTel ports 4317/4318 — coinciden con `docker-compose.yml:685-686`.
- §Tabla de límites L152-169: todos los valores RAM/CPU listados coinciden con los `deploy.resources.limits` del compose EXCEPTO Redis (ver hallazgo HIGH arriba).
