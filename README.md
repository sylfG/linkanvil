<div align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="./docs/src/public/logo-dark.png">
    <img src="./docs/src/public/logo-light.png" alt="LinkAnvil logo" width="80" height="80">
  </picture>

  <h1 align="center">🧠 LinkAnvil: Autonomous Knowledge Extractor</h1>

  <p align="center">
    Plataforma orientada al procesamiento ágil y desatendido de URLs para construir grafos semánticos privados.
    <br />
    <a href="https://sylfg.github.io/linkanvil"><strong>Explora la Documentación »</strong></a>
    <br />
    <br />
    <a href="https://sylfg.github.io/linkanvil/1-instalacion-configuracion">Ver Instalación</a>
    ·
    <a href="https://github.com/sylfG/linkanvil/issues/new">Reportar un Bug</a>
    ·
    <a href="https://sylfg.github.io/linkanvil/Extractor_de_Requisitos/1_epics_and_features">Roadmap</a>
  </p>

  [![VitePress](https://img.shields.io/badge/docs-VitePress-blue)](https://sylfg.github.io/linkanvil)
  [![Docker](https://img.shields.io/badge/docker-compose-2496ED?logo=docker&logoColor=white)](#-stack-tecnologico)
  [![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
</div>

---

## 📑 Contenido

- [a. Descripción general](#-descripcion-general) · [b. Stack tecnológico](#-stack-tecnologico) · [c. Instalación y ejecución](#-instalacion-y-ejecucion) · [d. Estructura del proyecto](#-estructura-del-proyecto) · [e. Funcionalidades principales](#-funcionalidades-principales)

---

## 🎯 Descripción general

LinkAnvil es una **plataforma analítica para el procesamiento asíncrono de URLs**. Funciona como un cauce estructurado donde puedes "enviar y olvidar" enlaces (artículos, documentación, foros): el sistema extrae el contenido, lo procesa con LLMs, lo vectoriza (RAG) y detecta **colisiones semánticas** para construir automáticamente un grafo privado de tu conocimiento.

> 📖 Visión completa, decisiones de diseño y modelo de datos:
> **[Resumen ejecutivo](https://sylfg.github.io/linkanvil/0-resumen)** · **[Arquitectura](https://sylfg.github.io/linkanvil/4-arquitectura)** · **[Ciclo de vida de un recurso](https://sylfg.github.io/linkanvil/7-lifecycle)**

---

## 🛠️ Stack tecnológico

El backend de LinkAnvil está desacoplado en ~22 servicios contenedorizados orquestados con Docker Compose.

| Capa | Tecnología |
|---|---|
| API Gateway | Traefik |
| API + workers | Python 3.12 (FastAPI, asyncio) |
| Frontend | Next.js 15 + React 19 + TypeScript |
| Message Broker | RabbitMQ 3 |
| BD relacional | PostgreSQL 17 (con RLS) |
| BD vectorial | Qdrant |
| Caché / colas SSE | Redis 7 |
| Gateway LLM | LiteLLM (BYOK + fallback chain) |
| Workflows | n8n |
| Observabilidad | OpenTelemetry · Jaeger · Prometheus · Grafana |
| Acceso público (opt-in) | Tailscale Funnel |

> 📖 Catálogo completo de servicios con puertos, healthchecks y dependencias:
> **[2 · Catálogo de servicios](https://sylfg.github.io/linkanvil/2-resumen-servicios)** · **[3 · Componentes](https://sylfg.github.io/linkanvil/3-componentes)** · **[5 · Herramientas IA](https://sylfg.github.io/linkanvil/5-herramientas-ia)**

---

## 🚀 Instalación y ejecución

### Requisitos mínimos

| Recurso | Mínimo | Recomendado |
|---|---|---|
| CPU | 2 cores (x86_64 / ARM64) | 4+ cores |
| RAM (Docker) | 4 GB | 8 GB |
| Disco | 10 GB | 20 GB+ |
| Dependencias | Docker Engine 24+ y Compose v2 | idem |

> Aceleración LLM y modelos privados con **[Ollama](https://ollama.com/)** son compatibles vía LiteLLM. Si alojas el modelo en la misma máquina, añade su requisito de RAM/VRAM.

### Quick start (Debian 12 / Ubuntu 22.04+)

```bash
# 1. Clonar
git clone https://github.com/sylfG/linkanvil && cd linkanvil

# 2. Dependencias del SO (una vez por máquina, requiere sudo)
sudo bash install-host.sh

# 3. Arrancar (interactivo: te pregunta proveedores LLM y si lo expones público)
bash up.sh
```

`up.sh` genera secretos aleatorios (`POSTGRES_PASSWORD`, `JWT_SECRET`, `LITELLM_MASTER_KEY`, etc.) en `.env` y los registra en `.secrets-generated.txt` (chmod 600, en `.gitignore`).

**Flags útiles:**

| Flag | Efecto |
|---|---|
| `--public` / `--private` | Modo público (Tailscale Funnel) o privado (localhost) |
| `--with-telegram` | Activa el sidecar Funnel para webhooks Telegram |
| `--reconfigure-llm` | Reabre el prompt de proveedores LLM |
| `--print-secrets` | Imprime los secretos generados en pantalla (acepta riesgo de scrollback) |
| `--no-build` / `--no-wait` | Salta build / healthcheck |

**Endpoints tras `up.sh`** (todos sobre `localhost`, no expuestos a 0.0.0.0):
`Frontend :3001` · `API docs :8001/docs` · `n8n :5678` · `Grafana :3000` · `Jaeger :16686` · `RabbitMQ :15672` · `Qdrant :6333/dashboard`

> 📖 Guía paso a paso (instalación en limpio, `.env` por variable, troubleshooting):
> **[1 · Instalación y configuración](https://sylfg.github.io/linkanvil/1-instalacion-configuracion)**
> 📖 Despliegue seguro y hardening (UFW, anti-SSRF, containers, Funnel ACL):
> **[11 · Seguridad](https://sylfg.github.io/linkanvil/11-Seguridad)**

---

## 📁 Estructura del proyecto

```
linkanvil/
├── src/                  Código de los servicios Python + frontend
│   ├── api/                cerebro-api (FastAPI, auth, RAG, SSE)
│   ├── ingestion/          endpoint /ingest + validación anti-SSRF
│   ├── scraper/            BasicHTTP + Playwright stealth
│   ├── notifier/           fan-out de eventos vía SSE/Telegram
│   ├── dlq/                dead-letter queue handlers
│   ├── observability/      OpenTelemetry instrumentation
│   ├── data/               schemas Pydantic + repositorios PG/Qdrant
│   └── frontend/           Next.js 15 (app router, RSC, Tailwind)
├── infra/                Configuración de los servicios externos
│   ├── postgres/           migraciones SQL versionadas (0001…)
│   ├── litellm/            providers.yaml + render dinámico
│   ├── qdrant/             init de colecciones
│   ├── rabbitmq/           definitions.json (exchanges, queues, DLQ)
│   ├── grafana/            dashboards y datasources
│   ├── prometheus/         scrape config
│   ├── otel/ jaeger/       collector y backends de trazas
│   ├── n8n/                workflows exportados
│   └── tailscale/          serve-web.json (Funnel sidecar)
├── ops/                  Operaciones (seed, backups, scripts cron)
├── scripts/              bootstrap-env, wait-healthy, render-litellm
├── tests/                pytest (unit + integration con testcontainers)
├── docs/                 VitePress (publicado en GitHub Pages)
├── docker-compose.yml    Stack runtime
├── docker-compose.prod.yml  Overrides producción
├── up.sh                 Bootstrap idempotente del stack
├── install-host.sh       Dependencias del host (una vez)
└── reset.sh              Reset destructivo (borra volúmenes)
```

> 📖 Detalle por componente (responsabilidades, contratos, eventos AMQP):
> **[3 · Componentes](https://sylfg.github.io/linkanvil/3-componentes)** · **[4 · Arquitectura](https://sylfg.github.io/linkanvil/4-arquitectura)**

---

## ✨ Funcionalidades principales

- **Ingesta desatendida** — manda una URL y sigue trabajando; el pipeline asíncrono se encarga del resto.
- **Colisión semántica vectorial** — relaciona automáticamente recursos con similitud coseno ≥ 0.92 en Qdrant.
- **Multi-LLM con fallback** — LiteLLM enruta entre NVIDIA, OpenAI, Anthropic, Gemini, Mistral, Cohere, Groq, xAI, OpenRouter u Ollama local con cadena estricta de prioridades.
- **BYOK per-tenant** — cada usuario aporta sus propias virtual-keys de LiteLLM (cifradas en BD con Fernet).
- **Ciclo de vida automático** — los recursos transicionan `activo → cuarentena → expirado` según `temporal_class × valor_archivistico` con cron de auditoría.
- **RAG dual mode** — el chat consulta solo KB activa o también el archivo (`expirado` con valor archivístico alto).
- **Notificaciones en tiempo real** — fan-out Outbox → RabbitMQ → notifier → Redis pub/sub → SSE al frontend en ≤ 1 segundo.
- **Observabilidad nativa** — trazas distribuidas (OpenTelemetry → Jaeger), métricas (Prometheus) y dashboards (Grafana) precargados.
- **Despliegue público opcional** — frontend accesible vía Tailscale Funnel (`https://<host>.<tailnet>.ts.net`) sin abrir puertos en el host.

> 📖 Cómo se materializa cada funcionalidad:
> **[5 · Herramientas IA](https://sylfg.github.io/linkanvil/5-herramientas-ia)** · **[7 · Lifecycle](https://sylfg.github.io/linkanvil/7-lifecycle)** · **[8 · Flujo end-to-end](https://sylfg.github.io/linkanvil/8-ejemplo_flujo)** · **[9 · Demo público](https://sylfg.github.io/linkanvil/9-demo)** · **[10 · Glosario](https://sylfg.github.io/linkanvil/10-Glosario)**

---

## 🤝 Contribución

1. Haz un fork del proyecto
2. Crea tu rama (`git checkout -b feature/IncreibleFeature`)
3. Commit (`git commit -m 'feat: add IncreibleFeature'` — Conventional Commits)
4. Push (`git push origin feature/IncreibleFeature`)
5. Abre un Pull Request

> 📖 Roadmap y épicas: **[Extracción de requisitos](https://sylfg.github.io/linkanvil/Extractor_de_Requisitos/1_epics_and_features)**

---

## 📄 Licencia

Distribuido bajo la Licencia MIT. Consulta el archivo `LICENSE` para más información.
