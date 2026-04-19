# 🧠 Segundo Cerebro Autónomo — Infraestructura Local

> Plataforma event-driven de gestión de conocimiento personal: captura, procesa y conversa con tu propia base de conocimiento mediante RAG + LLM Gateway + grafo semántico.

El repositorio cuenta con un despliegue local dockerizado con un ecosistema completo para operar una IA soberana y personal enlazada a una base de datos relacional orientada a grafos y RAG.

## ⚡ Enlaces Rápidos y Documentación

Toda la arquitectura, registros de diseño, documentación detallada y despliegue del proyecto están unificados a través de [VitePress](https://vitepress.dev/) e integrados mediante GitHub Actions para su publicación automatizada.

* 📖 **[Visita la Documentación Oficial Web (GitHub Pages)](https://silvia.github.io/masteria)** *(Reemplaza la URL según tu repositorio y GitHub Pages configurado)*
* ⚙️ **[Guía de Instalación y Configuración](docs/src/8_instalacion_y_configuracion.md)**
* 🏗️ **[Arquitectura y Diseño de Sistemas](docs/src/6_arquitectura.md)**

---

## 🔑 Integraciones API y Requisitos Externos

Para que el modelo de enrutamiento dinámico, fallbacks automáticos, limitador de tasas y clasificación funcione correctamente, nuestro servicio unificado LLM Gateway (basado en LiteLLM) requiere credenciales de APIs de Inteligencia Artificial externas, las cuales actúan según configuración y fallos jerárquicos (ej: intentar primero OpenAI GPT-4o, si cae, usar Anthropic Claude y luego Local LLM).

A nivel interno existen credenciales o secretos locales entre los contenedores, pero a nivel externo dependemos de:

* **Proveedor OpenAI**: Requiere `OPENAI_API_KEY=sk-...` (Recomendable para GPT-4o y Embedding APIs)
* **Proveedor Anthropic**: Requiere `ANTHROPIC_API_KEY=sk-ant-...` (Recomendado como nodo primario de RAG o fallback)
* **Otros Proveedores**: Azure, Fireworks, etc., configurables directo desde LiteLLM.

Estas variables deben ser ubicadas en tu archivo `.env` configurado localmente a partir de la copia o despliegue inicial en `.env.example`. Además, requerirás asignar configuraciones de seguridad por defecto para tus servicios internos (Contraseñas de RabbitMQ, PostgreSQL, Panel de control UI de N8N y Grafana). Puedes acceder a todos los detalles de los secretos y variables de entorno en la **[Guía de Instalación Detallada](docs/src/8_instalacion_y_configuracion.md)**.

---

## 🗄️ Stack Principal de Servicios y Tecnologías

Todo el ecosistema del Segundo Cerebro se administra y empaqueta detrás de un orquestador local compuesto por:

1. **Traefik Gateway**: API y control de rutas para tus contenedores.
2. **LiteLLM**: Enrutador/Proxy agnóstico para múltiples LLMs externo/local con tolerancias a fallos (Circuit Breakers).
3. **RabbitMQ & Redis**: Motores potentes y comprobados para gestión asíncrona (DLQ) de encolamientos de documentos y caches sub-milisegundo.
4. **PostgreSQL + Outbox + RLS**: Capa relacional para estructurar, auditar, organizar metadatos, y realizar un particionado con multi-tenancy usando *Row-Level Security*.
5. **Qdrant**: Base de datos nativamente vectorial en la que se guardan los "embeddings" de largo contexto.
6. **n8n**: Tu centro de administración gráfico para *workflows*. Todo evento y sub-procesamiento de pipelines se puede orquestar aquí.
7. **Observabilidad Full-Stack**: Integrado con Opentelemetry Collector recogiendo las métricas que viajan hacia **Prometheus**, **Jaeger** (trazas visuales del gateway LLM y BD) y un dashboard final en **Grafana**.

Para empezar e inicializar tu **Segundo Cerebro**: [Documentación de Setup](docs/src/8_instalacion_y_configuracion.md).
