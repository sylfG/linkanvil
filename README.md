<div align="center">
  <img src="./docs/public/logo-dark.png" alt="Logo" width="80" height="80">

  <h1 align="center">🧠 LinkAnvil: Autonomous Knowledge Extractor</h1>

  <p align="center">
    Plataforma orientada al procesamiento ágil y desatendido de URLs para construir grafos semánticos privados.
    <br />
    <a href="https://sylfg.github.io/linkanvil"><strong>Explora la Documentación »</strong></a>
    <br />
    <br />
    <a href="docs/src/1-instalacion-configuracion.md">Ver Instalación</a>
    ·
    <a href="https://github.com/sylfG/linkanvil/issues/new">Reportar un Bug</a>
    ·
    <a href="docs/src/Extractor_de_Requisitos/1_epics_and_features.md">Roadmap</a>
  </p>

  [![VitePress](https://img.shields.io/badge/docs-VitePress-blue)](https://sylfg.github.io/linkanvil)
  [![Docker](https://img.shields.io/badge/docker-compose-2496ED?logo=docker&logoColor=white)](#-tecnologias-y-servicios)
  [![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
</div>

---

## 🎯 Sobre el Proyecto

LinkAnvil no es únicamente un "cerebro digital" genérico; es una **plataforma analítica diseñada para el procesamiento asíncrono de URLs**.

El objetivo principal es proporcionar un cauce estructurado donde puedas "enviar y olvidar" enlaces (artículos, documentación, foros). LinkAnvil se encarga de extraer el contenido, procesarlo mediante LLMs, vectorizarlo (RAG), y establecer **colisiones semánticas** (relacionar automáticamente conceptos similares) mediante su grafo de conocimiento interno.

### ✨ Ventajas y Características Principales

* **Ingesta Desatendida de URLs**: Uso de colas (RabbitMQ) para procesar información web en segundo plano, sin bloqueos ni latencia para el usuario final.
* **Colisión Semántica Vectorial**: Interconexión autónoma de recursos utilizando similitud del coseno en Qdrant, desvelando relaciones ocultas entre tus documentos guardados.
* **Proxy LLM Resiliente y Privado**: Fallbacks automatizados (ej: OpenAI → Anthropic → Local) usando LiteLLM. Además, es **100% compatible con Ollama**, permitiendo ejecutar modelos de IA de forma totalmente privada y desconectada si tu hardware lo permite.
* **Pipeline Zero-Defect**: Aislamiento de fallos mediante Dead Letter Queues (DLQ). Si el scraping de una URL falla, el ecosistema sigue funcionando y el error se audita.
* **Observabilidad Completa**: Telemetría, métricas y trazas nativas con OpenTelemetry, Jaeger, Prometheus y Grafana.

---

## 🛠️ Tecnologías y Servicios

El backend de LinkAnvil está desacoplado y funciona mediante una orquestación de contenedores.

* **API Gateway**: Traefik
* **Message Broker**: RabbitMQ
* **Bases de Datos**: PostgreSQL (Relacional + RLS) y Qdrant (Vectorial)
* **Caché Temporal**: Redis
* **Lógica y Orquestación**: LiteLLM (Gateway de IA) y n8n (Workflows)
* **Observabilidad**: OpenTelemetry, Jaeger, Prometheus, Grafana

---

## 💻 Requisitos del Sistema

LinkAnvil está compuesto por una arquitectura de microservicios ligera que puede desplegarse en cualquier entorno compatible con Docker (Servidor VPS, NAS, Nube o Local). Los siguientes requisitos contemplan **únicamente la ejecución de los servicios base** del sistema (bases de datos, orquestador, colas y telemetría), excluyendo el host (SO) y excluyendo la ejecución de Modelos de Lenguaje (IA).

| Recurso | Mínimos | Recomendados |
| :--- | :--- | :--- |
| **CPU** | 2 Cores (x86_64 o ARM64) | 4+ Cores (x86_64 o ARM64) |
| **Memoria RAM (Docker)**| 4 GB asignados a los contenedores | 8 GB asignados a los contenedores |
| **Dependencias** | Docker Engine v24+, Compose v2 | Docker Engine v24+, Compose v2 |
| **Almacenamiento** | 10 GB (Imágenes y volúmenes base) | 20 GB+ (Persistencia a largo plazo) |

> **Aceleración y Modelos Privados (Ollama)**: El sistema envía y delega todo el cómputo de inteligencia artificial a través de LiteLLM. Puedes usar APIs externas (OpenAI, Anthropic) sin un aumento en el uso del hardware, o si lo prefieres, LinkAnvil es compatible directamente para conectar con motores locales como **[Ollama](https://ollama.com/)** permitiendo un ecosistema 100% privado y sin red.
>
> *Nota: Si decides alojar modelos privados mediante Ollama en esa misma máquina, deberás sumarle al sistema los requisitos proporcionales del LLM seleccionado (p. ej. sumar +8GB extra de RAM/VRAM para correr un Llama 3 de 8B parámetros).*

---

## 🚀 Quick Start (servidor limpio Debian 12 / Ubuntu 22.04+)

```bash
# 1. Clonar
git clone https://github.com/sylfG/linkanvil && cd linkanvil

# 2. Dependencias del SO (una vez por máquina, requiere sudo)
sudo bash install-host.sh

# 3. Arrancar la app (interactivo: te pregunta qué proveedor(es) LLM activar)
bash up.sh
```

`up.sh` te dejará elegir 1 o varios proveedores LLM en orden de prioridad (NVIDIA, OpenAI, Anthropic, Gemini, Mistral, Cohere, Groq, xAI, OpenRouter). El primero es el primario; el resto entra en la cadena de fallback de LiteLLM. Detalles en [`infra/litellm/providers.yaml`](infra/litellm/providers.yaml).

Tras `up.sh`:

| Servicio | URL |
|---|---|
| Frontend | http://localhost:3001  *(demo: `demo@linkanvil.io` / `linkanvil-demo`)* |
| API docs | http://localhost:8001/docs |
| n8n | http://localhost:5678 |
| Grafana | http://localhost:3000 |
| Jaeger | http://localhost:16686 |

**Opciones:**
- `bash up.sh --with-telegram` — incluye Tailscale Funnel para webhooks Telegram (pide `TS_AUTHKEY`).
- `bash up.sh --no-build` — salta el build de imágenes locales (más rápido en re-arranques).
- `bash up.sh --reconfigure-llm` — reabre el prompt para cambiar la lista/orden de proveedores LLM.
- `bash reset.sh` — reset destructivo (borra volúmenes + reconstruye todo).
- `make health` — comprobación rápida de healthchecks.

Para una guía detallada, ver **[Guía de Instalación](docs/src/1-instalacion-configuracion.md)**.

---

## 📚 Documentación Técnica Interna

Toda la arquitectura, diagramas e hitos de desarrollo residen en [VitePress](https://vitepress.dev/) y GitHub Pages. Si eres desarrollador, te sugerimos leer:

* 🏛️ **[Arquitectura y Diseño de Sistemas](docs/src/4-arquitectura.md)**
* 📐 **[Diagramas C4 de Componentes](docs/src/Extractor_de_Requisitos/3_c4_diagrams.md)**
* 📋 **[Planificación y Registro de Épicas](docs/src/Extractor_de_Requisitos/1_epics_and_features.md)**

---

## 🤝 Contribución

¡Las contribuciones hacen que la comunidad de código abierto sea un lugar increíble para aprender, inspirar y crear! Cualquier contribución que hagas será **muy apreciada**.

1. Haz un Fork del proyecto
2. Crea tu rama para la nueva Feature (`git checkout -b feature/IncreibleFeature`)
3. Haz commit de tus cambios (`git commit -m 'Add some IncreibleFeature'`)
4. Sube la rama (`git push origin feature/IncreibleFeature`)
5. Abre un Pull Request

---

## 📄 Licencia

Distribuido bajo la Licencia MIT. Consulta el archivo `LICENSE` para más información.
