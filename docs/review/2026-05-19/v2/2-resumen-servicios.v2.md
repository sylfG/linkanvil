<div align="center">
  <img src="/logo-light.png" alt="Logo" width="80" height="80" class="light-only">
  <img src="/logo-dark.png" alt="Logo" width="80" height="80" class="dark-only">


# 📋 Resumen de Contenedores y Topología de Red

</div>


El clúster del **LinkAnvil** está compuesto por **23 contenedores** que operan dentro de la red privada `cerebro-net`, más un sidecar opcional (`tailscale-funnel`, profile `telegram`) que expone públicamente el endpoint de webhooks de Telegram cuando se necesita. Se dividen en seis capas funcionales: entrada y API, interfaz web, workers asíncronos, almacenamiento, orquestación/IA y observabilidad.

Este documento es el **catálogo operativo** del sistema: puertos, imágenes, recursos y propósito en una línea por servicio. Para entender el *porqué* de cada componente, las analogías pedagógicas y los flujos completos, consulta [3_arquitectura.md](./3_arquitectura.md).

---

## Tabla de contenidos

1. [🗺️ Diagrama de Conexiones entre Contenedores](#️-diagrama-de-conexiones-entre-contenedores)
2. [🗂️ Catálogo de Contenedores](#️-catálogo-de-contenedores)
3. [📊 Resumen de Límites por Contenedor](#-resumen-de-límites-por-contenedor)

---

## 🗺️ Diagrama de Conexiones entre Contenedores

```mermaid
graph TD
    classDef gateway fill:#2b3c5a,stroke:#3b82f6,color:#fff
    classDef api fill:#1f3a2a,stroke:#10b981,color:#fff
    classDef worker fill:#2d2050,stroke:#a78bfa,color:#fff
    classDef ai fill:#3b1f4a,stroke:#d946ef,color:#fff
    classDef db fill:#374151,stroke:#f59e0b,color:#fff
    classDef obs fill:#1e3a8a,stroke:#8b5cf6,color:#fff
    classDef exporter fill:#4c1d95,stroke:#c4b5fd,color:#fff

    User((Usuario HTTPS))

    Traefik[🔀 cerebro-traefik<br/>Port: 80, 8080]:::gateway
    Ingestion[📥 cerebro-ingestion<br/>Port interno: 8000]:::api
    API[⚙️ cerebro-api<br/>Port: 8001]:::api
    Web[🌐 cerebro-web<br/>Port: 3001]:::api

    n8n[🔄 cerebro-n8n<br/>Port: 5678]:::ai
    LiteLLM[🤖 cerebro-litellm<br/>Port: 4000]:::ai
    Scraper[🕷️ cerebro-scraper]:::worker
    Embedder[🧮 cerebro-embedder]:::worker
    Outbox[📤 cerebro-outbox]:::worker
    Notifier[📢 cerebro-notifier]:::worker

    Migrate[🗃️ cerebro-migrate<br/>one-shot]:::db
    Postgres[🗄️ cerebro-postgres<br/>Port: 5432]:::db
    Redis[⚡ cerebro-redis<br/>Port: 6379]:::db
    RabbitMQ[📨 cerebro-rabbitmq<br/>Port: 5672/15672]:::db
    Qdrant[🧠 cerebro-qdrant<br/>Ports: 6333/6334]:::db

    OTel[📡 cerebro-otel<br/>Ports: 4317/4318]:::obs
    Prometheus[📊 cerebro-prometheus<br/>Port: 9090]:::obs
    Jaeger[🔭 cerebro-jaeger<br/>Port: 16686]:::obs
    Grafana[📈 cerebro-grafana<br/>Port: 3000]:::obs
    PG_Exp[📦 cerebro-postgres-exporter]:::exporter
    RMQ_Exp[📦 cerebro-rabbitmq-exporter]:::exporter
    Red_Exp[📦 cerebro-redis-exporter]:::exporter

    User -->|HTTPS| Traefik
    Traefik ==>|ingest.localhost o /ingest| Ingestion
    Traefik ==>|api.*| API
    Traefik ==>|n8n.*| n8n
    Traefik ==>|grafana.*| Grafana

    Web -->|proxy server-side| API
    API -->|JWT + sesiones| Postgres
    API -->|rate limit + caché| Redis
    API -->|embeddings + RAG| LiteLLM
    API -->|búsqueda vectorial| Qdrant

    Migrate -.->|service_completed_successfully| API

    Ingestion -->|Bloom Filter| Redis
    Ingestion -->|publica URL| RabbitMQ

    Scraper -->|consume q.url.ingesta| RabbitMQ
    Scraper -->|guarda recurso| Postgres
    Scraper -->|heartbeat| Redis
    Scraper -->|analiza texto| LiteLLM

    Outbox -->|lee outbox_eventos| Postgres
    Outbox -->|publica eventos (embedding, notify, ...)| RabbitMQ
    Outbox -->|heartbeat| Redis

    Embedder -->|consume q.embeddings| RabbitMQ
    Embedder -->|genera embedding| LiteLLM
    Embedder -->|inserta vector| Qdrant
    Embedder -->|heartbeat| Redis

    Notifier -->|consume eventos| RabbitMQ
    Notifier -->|heartbeat| Redis

    n8n -->|flujos| Postgres
    n8n -->|flujos| RabbitMQ
    LiteLLM -->|caché prompts| Redis
    LiteLLM -->|metadata| Postgres

    OTel -->|trazas| Jaeger
    OTel -->|métricas| Prometheus
    Traefik -.->|OTLP traces| OTel
    API -.->|OTLP traces| OTel

    PG_Exp -.->|scrape| Postgres
    RMQ_Exp -.->|scrape| RabbitMQ
    Red_Exp -.->|scrape| Redis
    Prometheus -->|scrape| PG_Exp
    Prometheus -->|scrape| RMQ_Exp
    Prometheus -->|scrape| Red_Exp
    Prometheus -->|scrape| OTel
    Grafana -->|query| Prometheus
    Grafana -->|query| Jaeger
```

> `cerebro-web` se expone directamente vía host port `3001` (no hay routing Traefik a la Web).

---

## 🗂️ Catálogo de Contenedores

Una fila por servicio. `RAM/CPU` indica el límite asignado en `docker-compose.yml`. Los servicios marcados como **sidecar** sólo arrancan con un profile específico.

| Contenedor | Capa | Imagen / Código | Puerto(s) | RAM / CPU | Propósito (1 línea) |
|---|---|---|---|---|---|
| `cerebro-tailscale` | Gateway (sidecar `telegram`) | `tailscale/tailscale:stable` (sin digest pin) | 443 vía Funnel (no mapeo Docker) | — | Túnel HTTPS público fijo para webhook de Telegram → `ingestion-api:8000`. |
| `cerebro-traefik` | Gateway | `traefik:v3.6.14` | 80, 8080 (443 declarado pero no publicado; TLS público se sirve vía `cerebro-tailscale` Funnel) | 256 MB / 0.5 | Único punto de entrada: routing por labels Docker, rate-limit global, retries, Trace-ID OTel y TLS Let's Encrypt en producción. |
| `cerebro-ingestion` | Ingesta | `infra/ingestion.Dockerfile` · `src/ingestion/main.py` | 8000 (interno) | 512 MB / 1.0 | Recibe URLs, aplica Bloom Filter + rate-limit atómico en Redis y publica a `q.url.ingesta`. Responde `202` al instante. |
| `cerebro-api` | API | `infra/api.Dockerfile` · `src/api/main.py` | 8001 | 768 MB / 1.0 | Backend FastAPI: auth JWT (cookie httpOnly + CSRF), chat RAG con SSE, CRUD de sesiones/mensajes, integración LiteLLM + Qdrant. |
| `cerebro-web` | Frontend | `infra/frontend.Dockerfile` · `src/frontend/` | 3001 | 384 MB / 0.5 | Next.js 15 + Zustand API-backed: login, chat SSE, listado de recursos. Proxy server-side hacia `cerebro-api`. |
| `cerebro-scraper` | Worker | `src/scraper/worker.py` | — | 1.5 GB / 2.0 (shm 1 GB) | Consume `q.url.ingesta`, scrapea con Basic/Stealth Playwright, valida bloqueos, llama a LiteLLM y persiste recurso + evento Outbox (healthcheck por heartbeat en Redis: clave `worker:scraper:heartbeat`). |
| `cerebro-embedder` | Worker | `src/data/embedder_worker.py` | — | 768 MB / 1.0 | Consume `q.embeddings`, genera vector vía LiteLLM e inserta en Qdrant. Copia vectores existentes en flujo `reused` (healthcheck por heartbeat en Redis: clave `worker:embedder:heartbeat`). |
| `cerebro-outbox` | Worker | `src/data/outbox_publisher.py` | — | 384 MB / 0.5 | Polling de `cerebro.outbox_eventos` → publica en RabbitMQ. Garantiza consistencia eventual sin Dual-Write (healthcheck por heartbeat en Redis: clave `worker:outbox:heartbeat`). |
| `cerebro-notifier` | Worker | `src/notifier/worker.py` | — | 256 MB / 0.3 | Consume eventos de notificación desde RabbitMQ y entrega vía canales configurados (Telegram, etc.). Healthcheck por heartbeat en Redis (clave `worker:notifier:heartbeat`). |
| `cerebro-litellm` | Motor LLM | `ghcr.io/berriai/litellm:main-latest` (pinned por digest) · config: `infra/litellm/config.yaml` | 4000 | 1 GB / 1.0 | Proxy multi-proveedor con Circuit Breaker, fallback automático y caché de prompts en Redis. |
| `cerebro-n8n` | Orquestación | `n8nio/n8n:1.123.37` | 5678 | 768 MB / 1.0 | Orquestador visual: webhooks de Telegram, scraping ligero y curación nocturna. Usa schema `n8n`. |
| `cerebro-n8n-bootstrap` | Orquestación | one-shot (`python:3.12-alpine`) | — | — | Espera a `n8n`, genera la API key inicial y la inyecta en `.env`. Se ejecuta una sola vez. |
| `cerebro-migrate` | Almacenamiento | `postgres:16-alpine` · `scripts/migrate.sh` | — | — | One-shot: aplica migraciones SQL pendientes de `infra/postgres/migrations/`. Idempotente vía `cerebro.schema_migrations(version)`. `cerebro-api` depende de su `service_completed_successfully`. |
| `cerebro-postgres` | Almacenamiento | `postgres:16-alpine` | 5432 | 2 GB / 2.0 | Base de datos relacional. Schemas: `cerebro` (LinkAnvil), `n8n` (orquestador), `public` (LiteLLM/Prisma). |
| `cerebro-redis` | Almacenamiento | `redis/redis-stack-server:latest` (pinned por digest) | 6379 | 768 MB / 1.0 | Bloom Filter de dedupe (módulo RedisBloom), rate-limiters atómicos, heartbeats de workers y caché LiteLLM. |
| `cerebro-rabbitmq` | Mensajería | `rabbitmq:3.13-management-alpine` | 5672, 15672 | 768 MB / 1.0 | Broker con vhost `cerebro`. Colas `q.url.ingesta`, `q.embeddings` y DLQs asociadas. |
| `cerebro-qdrant` | Vector DB | `qdrant/qdrant:v1.17.1` | 6333 (REST), 6334 (gRPC) | 2 GB / 2.0 | Vectores HNSW. Colecciones `cerebro_recursos` (doc-level) y `cerebro_chunks` (RAG), filtrado por `tenant_id` en payload. |
| `cerebro-otel` | Observabilidad | `otel/opentelemetry-collector-contrib:0.150.1` | 4317, 4318, 8888, 8889 | 384 MB / 0.5 | Recolector OTLP: enruta trazas a Jaeger y métricas a Prometheus. |
| `cerebro-prometheus` | Observabilidad | `prom/prometheus:v3.11.2` | 9090 | 1 GB / 1.0 | TSDB de métricas + 9 reglas de alerta activas (latencia, colas, DLQ, heartbeats, disco). |
| `cerebro-jaeger` | Observabilidad | `jaegertracing/all-in-one` (pinned por digest) | 16686 (UI), 14317 (OTLP gRPC), 14318 (OTLP HTTP) | 384 MB / 0.5 | Distributed tracing: visualización de la cascada de spans por Trace-ID. |
| `cerebro-grafana` | Observabilidad | `grafana/grafana:11.4.0` | 3000 | 384 MB / 0.5 | Dashboards y alertas sobre Prometheus + Jaeger. |
| `cerebro-postgres-exporter` | Exporter | `prometheuscommunity/postgres-exporter:v0.19.1` | 9187 (interno) | 128 MB / 0.25 | Métricas Prometheus de PostgreSQL (conexiones, locks, tamaño). |
| `cerebro-redis-exporter` | Exporter | `oliver006/redis_exporter:v1.82.0-alpine` | 9121 (interno) | 128 MB / 0.25 | Métricas Prometheus de Redis (memoria, hit rate, clientes). |
| `cerebro-rabbitmq-exporter` | Exporter | `kbudde/rabbitmq-exporter` (pinned por digest) | 9419 (interno) | 128 MB / 0.25 | Métricas Prometheus de RabbitMQ (cola, consumers, mensajes). Versión congelada para evitar regresiones. |

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

---

## 📊 Resumen de Límites por Contenedor

Repartimos los recursos para que el stack quepa en una sola máquina sólida sin interferencias. Almacenamiento y scraper ocupan los tanques más grandes; exporters y observabilidad son mínimos.

| Contenedor | RAM Límite | CPU Límite | Tipo |
|---|---|---|---|
| cerebro-postgres | 2 GB | 2.0 | Almacenamiento |
| cerebro-qdrant | 2 GB | 2.0 | Vector DB |
| cerebro-scraper | 1.5 GB | 2.0 | Worker |
| cerebro-litellm | 1 GB | 1.0 | Motor LLM |
| cerebro-prometheus | 1 GB | 1.0 | Observabilidad |
| cerebro-api | 768 MB | 1.0 | API |
| cerebro-embedder | 768 MB | 1.0 | Worker |
| cerebro-rabbitmq | 768 MB | 1.0 | Mensajería |
| cerebro-n8n | 768 MB | 1.0 | Orquestación |
| cerebro-redis | 768 MB | 1.0 | Almacenamiento |
| cerebro-ingestion | 512 MB | 1.0 | API |
| cerebro-outbox | 384 MB | 0.5 | Worker |
| cerebro-web | 384 MB | 0.5 | Frontend |
| cerebro-otel | 384 MB | 0.5 | Observabilidad |
| cerebro-jaeger | 384 MB | 0.5 | Observabilidad |
| cerebro-grafana | 384 MB | 0.5 | Observabilidad |
| cerebro-traefik | 256 MB | 0.5 | Gateway |
| cerebro-notifier | 256 MB | 0.3 | Worker |
| exporters (×3) | 128 MB c/u | 0.25 c/u | Exporters |

---

> Para decisiones de diseño, flujos de secuencia (ingesta, chat RAG, auth, curación nocturna), patrón Outbox, dual-DB Postgres+Qdrant, aislamiento de schema, migraciones, heartbeat y backup, consulta **[3_arquitectura.md](./3_arquitectura.md)**.

---

## 📋 Notas del v2 (generado por doc-reviser · 2026-05-19)

**Origen**: `docs/src/2-resumen-servicios.md` · branch `develop` @ `7c723f3`
**Review aplicado**: `docs/review/2026-05-19/docs/2-resumen-servicios.review.md`

### Cambios aplicados
- 0 CRITICAL · 11 HIGH · 14 MEDIUM · 0 LOW (de 27 hallazgos del review)
- Secciones tocadas: encabezado/conteo de contenedores (§intro), diagrama Mermaid (§1), tabla del catálogo (§2), nueva subsección "Volúmenes persistentes" (§2), tabla de límites (§3)
- HIGH aplicados: imágenes pinneadas (postgres, redis, rabbitmq, qdrant, otel, prometheus, jaeger, grafana, n8n, litellm) + CPU Redis corregida a `1.0`
- MEDIUM aplicados: conteo `23 contenedores` (no 21), filas nuevas `cerebro-notifier` y `cerebro-migrate`, nodos y aristas en el diagrama (Notifier, Migrate, dependencia migrate→api), Qdrant gRPC `6334`, Traefik publica sólo `80, 8080` (eliminada arista `cerebro.*→Web`), reclasificación n8n/LiteLLM como `classDef ai`, etiqueta Traefik ingestion clarificada, nota sobre digest pin ausente en tailscale, etiqueta Outbox→RabbitMQ generalizada, sidecar tailscale puerto vía Funnel, sección de volúmenes persistentes añadida tras el catálogo
- Corrección de exactitud no presente en el review: el número real de reglas de alerta activas en `infra/prometheus/alert.rules.yml` es **9** (no 6) — verificado directamente (`HighLLMLatency`, `DLQ_Filling_Up`, `HighErrorRateIngestion`, `APIHighP99Latency`, `IngestionQueueBacklog`, `EmbeddingsDLQAny`, `PostgresConnectionsHigh`, `WorkerStuck`, `VolumeDiskHigh`); el review marcaba este punto como MEDIUM "no verificado", aquí se aplica la cifra real

### Pendientes (no aplicados en este v2)
- **[MEDIUM] Filtrado por `tenant_id` en Qdrant** (review §"filtrado por tenant_id" no verificado): el detalle de runtime no se auditó contra `src/data/embedder_worker.py` ni `src/api/` en el review original. El v2 mantiene la afirmación del original porque ningún hallazgo concreto la contradice; pendiente verificar manualmente leyendo el código de inserción/búsqueda en Qdrant.
- **[LOW] Typo de capitalización en TOC** (anchor con U+FE0F variation selector huérfano): no aplicado; es un detalle estilístico que requiere cambiar el plugin de markdown-it-anchor de VitePress, fuera del alcance de un fix quirúrgico al doc. TODO opcional.
- **[LOW] Catálogo lista 22 filas vs cifra de la intro**: resuelto implícitamente al subir la cifra a 23 contenedores y añadir las dos filas faltantes (`cerebro-notifier`, `cerebro-migrate`) — la tabla pasa a tener 24 filas (incluye `cerebro-tailscale` sidecar).

### Bugs de código flaggeados (no son drift de doc, requieren acción aparte)
- _Ninguno. El review reporta 0 [CODE-BUG]._
