# 🧠 Segundo Cerebro Autónomo — Infraestructura Local

> Plataforma event-driven de gestión de conocimiento personal: captura, procesa y conversa con tu propia base de conocimiento mediante RAG + LLM Gateway + grafo semántico.

---

## 📐 Arquitectura de Servicios

```
┌─────────────────────────────────────────────────────────────────────┐
│                          cerebro-net (Docker)                       │
│                                                                     │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────────┐  │
│  │ Traefik  │───▶│   n8n    │───▶│ LiteLLM  │───▶│   Qdrant     │  │
│  │ Gateway  │    │Workflows │    │ LLM GW   │    │  Vector DB   │  │
│  └──────────┘    └────┬─────┘    └──────────┘    └──────────────┘  │
│       │               │                                             │
│       │          ┌────▼─────┐    ┌──────────┐    ┌──────────────┐  │
│       │          │ RabbitMQ │    │PostgreSQL│    │    Redis     │  │
│       │          │(+DLQ)    │    │Outbox+RLS│    │  Cache+TTL   │  │
│       │          └──────────┘    └──────────┘    └──────────────┘  │
│       │                                                             │
│  ┌────▼─────────────────────────────────────────────────────────┐  │
│  │              Capa de Observabilidad                           │  │
│  │   OTel Collector → Jaeger (trazas) + Prometheus + Grafana    │  │
│  └────────────────────────────────────────────────────────────── ┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### Servicios incluidos

| Servicio | Imagen | Puerto host | Función |
|---|---|---|---|
| **Traefik** | `traefik:v3.1` | `80`, `8080` | API Gateway, rate limiting, Trace-ID |
| **RabbitMQ** | `rabbitmq:3.13-management` | `5672`, `15672` | Cola async de ingesta + Dead Letter Queue |
| **Redis** | `redis:7.4` | `6379` | Caché sub-ms, Bloom Filter, sesiones TTL |
| **PostgreSQL** | `postgres:16` | `5432` | BD relacional, Outbox Pattern, RLS Multi-Tenancy |
| **Qdrant** | `qdrant/qdrant:v1.12` | `6333`, `6334` | Base vectorial para RAG (similitud coseno) |
| **LiteLLM** | `ghcr.io/berriai/litellm` | `4000` | LLM Gateway con fallback automático y circuit breaker |
| **n8n** | `n8nio/n8n:1.71` | `5678` | Orquestador de workflows (Curador Nocturno, pipelines) |
| **Jaeger** | `jaegertracing/all-in-one:1.63` | `16686` | Distributed tracing (Trace-ID por URL) |
| **OTel Collector** | `otel/opentelemetry-collector-contrib` | `4317`, `4318` | Centraliza trazas → Jaeger + Prometheus |
| **Prometheus** | `prom/prometheus:v3.0` | `9090` | Métricas y alertas |
| **Grafana** | `grafana/grafana:11.4` | `3000` | Dashboards de observabilidad |
| **RabbitMQ Exporter** | `kbudde/rabbitmq-exporter` | — | Métricas colas → Prometheus |
| **Redis Exporter** | `oliver006/redis_exporter` | — | Métricas Redis → Prometheus |
| **Postgres Exporter** | `prometheuscommunity/postgres-exporter` | — | Métricas PG → Prometheus |

### Servicios adicionales vs. propuesta original

| Propuesta en `resumen.md` | Implementado | Justificación |
|---|---|---|
| Pinecone | **Qdrant** (self-hosted) | Sin coste cloud, misma API REST/gRPC, filtrado por `tenant_id` |
| SQS / RabbitMQ | **RabbitMQ** | Self-hosted, DLQ nativa, management UI incluida |
| LiteLLM Gateway | **LiteLLM** | Exactamente lo especificado + caché Redis integrada |
| OpenTelemetry | **OTel Collector + Jaeger** | Jaeger añadido para visualización de trazas |
| *(no especificado)* | **Traefik** | API Gateway con rate limiting, routing dinámico y métricas Prometheus nativas |
| *(no especificado)* | **Exporters x3** | Métricas detalladas de Redis, RabbitMQ y PostgreSQL para Grafana |

---

## ⚡ Inicio Rápido

### Prerrequisitos

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) ≥ 4.25 (con Docker Compose v2)
- 8 GB RAM disponibles (recomendado 12 GB)
- Puertos libres: `80, 3000, 4000, 4317-4318, 5432, 5672, 5678, 6333-6334, 6379, 8080, 8888-8889, 9090, 15672, 16686`

### 1. Configurar variables de entorno

```bash
# Copia la plantilla y edita los valores
cp .env.example .env
```

> **Mínimo obligatorio para arrancar:** los valores por defecto en `.env.example` funcionan para desarrollo local sin APIs de LLM reales.
> Para activar LiteLLM con LLMs reales, añade tus claves en `.env`:
> ```
> OPENAI_API_KEY=sk-...
> ANTHROPIC_API_KEY=sk-ant-...
> ```

### 2. Levantar la infraestructura

```bash
# Primera vez (construye y descarga imágenes ~2-4 min)
docker compose up -d

# Ver estado de arranque en tiempo real
docker compose ps
docker compose logs -f --tail=50
```

### 3. Verificar que todo está operativo

```bash
# Script de salud completo (requiere Python 3.9+)
python infra/test_health.py
```

El script verifica:
- ✅ Disponibilidad HTTP/TCP de cada servicio
- ✅ Schema de PostgreSQL (tablas, Outbox, RLS)
- ✅ Colas RabbitMQ (incluyendo DLQs)
- ✅ Conectividad inter-servicio dentro de `cerebro-net`
- ✅ Targets activos en Prometheus
- ✅ APIs de Qdrant y LiteLLM

### 4. Acceder a las interfaces web

| Interfaz | URL | Credenciales |
|---|---|---|
| **Traefik Dashboard** | http://localhost:8080 | — |
| **RabbitMQ Management** | http://localhost:15672 | `cerebro` / `cerebro_pass` |
| **n8n Workflows** | http://localhost:5678 | `admin` / `cerebro_n8n_pass` |
| **Grafana** | http://localhost:3000 | `admin` / `cerebro_grafana_pass` |
| **Prometheus** | http://localhost:9090 | — |
| **Jaeger Tracing** | http://localhost:16686 | — |
| **LiteLLM Gateway** | http://localhost:4000 | Bearer `sk-cerebro-master-key` |
| **Qdrant Dashboard** | http://localhost:6333/dashboard | — |

> **Tip:** Si tienes entradas en `/etc/hosts` (o `C:\Windows\System32\drivers\etc\hosts`), puedes usar los subdominios de Traefik:
> ```
> 127.0.0.1  traefik.localhost rabbitmq.localhost n8n.localhost grafana.localhost llm.localhost qdrant.localhost jaeger.localhost prometheus.localhost
> ```

---

## 🗄️ Estructura de la infraestructura

```
masteria/
├── docker-compose.yml          ← Orquestación de todos los servicios
├── .env.example                ← Plantilla de variables de entorno
├── .env                        ← Secretos locales (NO commitear)
└── infra/
    ├── test_health.py          ← Script de verificación completo
    ├── rabbitmq/
    │   ├── rabbitmq.conf       ← Configuración del broker
    │   └── definitions.json   ← Colas, exchanges y DLQ predefinidos
    ├── postgres/
    │   └── init.sql            ← Schema inicial (Outbox, RLS, grafo semántico)
    ├── qdrant/
    │   └── config.yaml         ← Configuración del servidor vectorial
    ├── litellm/
    │   └── config.yaml         ← Modelos, fallback, caché Redis
    ├── otel/
    │   └── config.yaml         ← Pipelines de trazas y métricas
    ├── prometheus/
    │   └── prometheus.yml      ← Scrape config de todos los servicios
    └── grafana/
        ├── provisioning/
        │   ├── datasources/    ← Prometheus + Jaeger auto-configurados
        │   └── dashboards/     ← Carga automática de dashboards
        └── dashboards/
            └── cerebro-overview.json ← Dashboard principal
```

---

## 🔧 Comandos útiles

```bash
# Ver logs de un servicio específico
docker compose logs -f litellm
docker compose logs -f n8n

# Reiniciar un servicio sin bajar el resto
docker compose restart rabbitmq

# Ejecutar comandos en un contenedor
docker exec -it cerebro-postgres psql -U cerebro -d cerebro_brain
docker exec -it cerebro-redis redis-cli -a cerebro_redis_pass

# Verificar red interna (conectividad entre contenedores)
docker exec cerebro-n8n sh -c "nc -zw3 postgres 5432 && echo OK"
docker exec cerebro-litellm sh -c "nc -zw3 redis 6379 && echo OK"

# Parar todo (preservando datos)
docker compose down

# Parar y ELIMINAR volúmenes (reset completo)
docker compose down -v
```

---

## 🏗️ Detalles de configuración avanzada

### PostgreSQL — Outbox Pattern & Multi-Tenancy

El schema inicial (`infra/postgres/init.sql`) crea:

- **`recursos`** — Tabla principal con índice único `(tenant_id, url_hash)` para deduplicación
- **`outbox_eventos`** — Patrón Outbox para consistencia eventual (n8n lo consume)
- **`grafo_relaciones`** — Aristas semánticas entre recursos (similitud coseno > 0.92)
- **`sesiones_chat` + `mensajes_chat`** — Sesiones con Sliding Window
- **Row-Level Security (RLS)** activado en todas las tablas con política `tenant_id`
- **`curador_marcar_expirados()`** — Función llamada por n8n cron para el Curador Nocturno

### RabbitMQ — Topología de colas

| Cola | Tipo | Propósito |
|---|---|---|
| `q.url.ingesta` | Normal + DLX | Nuevas URLs para procesar |
| `q.url.fallidas` | DLQ | URLs con 3+ fallos (404, timeout) |
| `q.embeddings` | Normal + DLX | Cálculo de vectores en background |
| `q.curador.nocturno` | Normal | Auditoría temporal (Cero-LLM) |

### LiteLLM — Estrategia de Fallback

```
OpenAI GPT-4o → (fallo) → Anthropic Claude → (fallo) → error con 503
```

Configurado con:
- **Circuit Breaker**: 3 fallos → apertura del circuito por 30s
- **Caché Redis**: respuestas en caché 1h para ahorro de tokens
- **Rate Limiting**: máximo 100 peticiones paralelas globales

### Redis — Políticas de memoria

- **`maxmemory 512mb`** con política **`allkeys-lru`**
- TTL por defecto en sesiones: 30 días (configurable en n8n)
- Prefijos de clave: `session:user_{id}:chat_{id}` para Multi-Tenancy

---

## 🔍 Troubleshooting

| Problema | Causa probable | Solución |
|---|---|---|
| `n8n` no arranca | PostgreSQL aún iniciando | Espera 60s, `docker compose restart n8n` |
| `LiteLLM` devuelve 401 | API keys no configuradas | Edita `.env` con claves reales |
| `RabbitMQ` rechaza conexión | Imagen inicializando definitions.json | Espera 30s, las colas se crean automáticamente |
| Qdrant `/healthz` → 404 | Versión de imagen | Usa `curl http://localhost:6333/` (sin `/healthz` en v1.x) |
| Redis `NOAUTH` | Password no configurada en cliente | Usa `-a cerebro_redis_pass` en redis-cli |
| Puerto ya en uso | Otro servicio en el host | Cambia el puerto en `docker-compose.yml` con `"NUEVO:ORIGINAL"` |
| `script test_health.py` falla | `netcat` no instalado en contenedor | Algunas imágenes Alpine requieren `apk add netcat-openbsd` |

---

## 🚀 Roadmap de próximos pasos

1. **Configurar workflows en n8n**: importar pipelines de ingesta URL → scraper → LiteLLM → PostgreSQL + Qdrant
2. **Conectar Telegram Bot**: vía n8n webhook + credencial de Bot Token
3. **Crear colección Qdrant**: `POST http://localhost:6333/collections/cerebro_recursos` con `size: 1536, distance: Cosine`
4. **Activar alertas en Prometheus**: configurar Alertmanager para notificaciones de DLQ saturada
5. **Despliegue en producción**: adaptar a docker-compose con Traefik HTTPS + Let's Encrypt o migrar a Kubernetes

---

## 📚 Referencias

- [Documentación de arquitectura](extractor-requisitos/docs/src/resumen.md)
- [Epics y Features](docs/src/1_epics_and_features.md)
- [Riesgos de arquitectura](docs/src/2_architecture_risks.md)
- [Diagramas C4](docs/src/3_c4_diagrams.md)