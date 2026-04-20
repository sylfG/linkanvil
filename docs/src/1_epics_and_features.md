# 📋 Épicas y Features — LinkAnvil

**Proyecto:** LinkAnvil
**Fecha:** 2026-04-09
**Stack:** Traefik, n8n, LiteLLM, RabbitMQ, Redis, PostgreSQL, Qdrant, OpenTelemetry, Prometheus, Jaeger, Grafana
**Estado:** FASE 1 Completada

---

## EPIC-00: Setup e Infraestructura Base
>
> Fundamentos técnicos y despliegue del ecosistema local orientado a eventos.

| Feature ID | Feature | Prioridad MoSCoW |
| --- | --- | --- |
| F-00.1 | Configuración de Docker Compose y red privada (cerebro-net) | MUST |
| F-00.2 | Despliegue de API Gateway y proxy reverso (Traefik) | MUST |
| F-00.3 | Configuración y despliegue del motor orquestador (n8n) | MUST |
| F-00.4 | Esquemas de base de datos relacional y configuración inicial (PostgreSQL) | MUST |
| F-00.5 | Despliegue de almacenamiento en caché (Redis) y bus de mensajes (RabbitMQ) | MUST |
| F-00.6 | Despliegue de base de datos vectorial con colecciones iniciales (Qdrant) | MUST |

---

## EPIC-01: Inclusión Omnicanal y Captura Asíncrona
>
> El Recolector: Puerta de entrada para ingestión de URLs desde múltiples orígenes, protección contra colisiones en sub-milisegundo.

| Feature ID | Feature | Prioridad MoSCoW |
| --- | --- | --- |
| F-01.1 | Filtro Deduplicador en Tiempo Real (Bloom Filter en Redis) para evitar múltiples ingestas idénticas | MUST |
| F-01.2 | Endpoint unificado de Ingesta Asíncrona (producción a cola RabbitMQ) protegido por Rate Limiting | MUST |
| F-01.3 | Soporte para captura mediante Bot de Telegram | MUST |
| F-01.4 | Soporte para captura mediante extensiones de navegador y webhooks externos | SHOULD |
| F-01.5 | Cola de Mensajes Muertos (DLQ) para tolerancia a fallos crónicos en la extracción | MUST |

---

## EPIC-02: Extracción Dinámica y Procesamiento IA Estructurado
>
> El Analista: Ruteo resiliente para scraping de origen y análisis de información a través del LLM Gateway (LiteLLM).

| Feature ID | Feature | Prioridad MoSCoW |
| --- | --- | --- |
| F-02.1 | Scraper de Ruteo Dinámico (Patrón Strategy) adaptable según origen (básico, Scrapling/Playwright, IA proxy) | MUST |
| F-02.2 | LLM Gateway con Circuit Breaker, Fallback Automático entre proveedores y caché local | MUST |
| F-02.3 | Pipeline Zero-Defect: Forzar Salidas Estructuradas del LLM validando JSON inquebrantable mediante Zod/Pydantic | MUST |
| F-02.4 | Clasificación inteligente de contenido y estimación lógica de la fecha útil (Volatilidad) para futuro | MUST |

---

## EPIC-03: Almacenamiento Centralizado y Auto-descubrimiento RAG
>
> La Memoria RAG: Consistencia de estado, prevención de Dual-Write problem y cruce de datos inteligente.

| Feature ID | Feature | Prioridad MoSCoW |
| --- | --- | --- |
| F-03.1 | Implementación de Patrón Outbox en PostgreSQL para consistencia transaccional a largo plazo | MUST |
| F-03.2 | Generación paralela de embeddings base e inyección vectorial asíncrona hacia Qdrant particionada por Tenant | MUST |
| F-03.3 | Colisionador Semántico en Background (cruces automáticos en SQL por Similitud Distanciada del vector superior a 0.92) | SHOULD |
| F-03.4 | Multi-Tenancy Estrutural con Aislamiento (Row Level Security local) de base relacional | MUST |
| F-03.5 | Soporte nativo y rápido de exportación masiva local en Standalone sin Vendor Lock-In (Markdown) | COULD |

---

## EPIC-04: Interacción, Memoria Híbrida y Control
>
> El Asistente Personal: Consumo dual entre Chatbot y panel métrico global.

| Feature ID | Feature | Prioridad MoSCoW |
| --- | --- | --- |
| F-04.1 | Chatbot RAG Conversacional Interactivo alojado en panel visual web | MUST |
| F-04.2 | Persistencia Multi-sesión ultra rápida cross-platform apoyada en Redis (reanudaciones sub-milibegundo) e Inyección TTL | MUST |
| F-04.3 | Panel de Control web administrativo unificado (Dashboard general con métricas locales) | SHOULD |
| F-04.4 | Compactación de Largo Contexto del Historial (Sliding Window relacional) para preservar rentabilidad del Tokenizado | SHOULD |
| F-04.5 | Function Calling Activo y Soberano del LLM al histórico RAG crudo almacenado para rebatir ambigüedad a petición expresa | COULD |

---

## EPIC-05: Curación Defensiva e Higiene Documental
>
> El Curador: Mantenimiento automatizado que no dispara rentabilidad IA o LLM.

| Feature ID | Feature | Prioridad MoSCoW |
| --- | --- | --- |
| F-05.1 | Auditoría Temporal Relacional (Cron SQL ultrarrápido contra cruce de volatilidad sin gastar LLM) | MUST |
| F-05.2 | Interfaz en Dashboard para Bandeja de Cuarentena pre-borrado absoluto del estado expirable | MUST |
| F-05.3 | Auditoría Exhaustiva Basada en IA por encargo puntual del Dueño a petición proactiva manual del sistema general | SHOULD |

---

## EPIC-06: Observabilidad Integral del Clúster
>
> Trace ID completo de extremo a extremo, medición general y aislamiento para equidad de rendimiento.

| Feature ID | Feature | Prioridad MoSCoW |
| --- | --- | --- |
| F-06.1 | Instaciación de OpenTelemetry (OTel Collector) como colector unificado propagando un único `Trace ID` en perimetral | MUST |
| F-06.2 | Exportación y despliegue del registro y rastreo Inter-Servicios general y distribuido a una interfaz Jaeger central | MUST |
| F-06.3 | Setup monitor activo Prometheus acoplado vía alertas al panel unificado de Grafana en el cerebro-net | MUST |
| F-06.4 | Límite Automático / Estrangulamiento individual y Cuota Equitativa (Throttling local / Noisy Neighbor Defense) | COULD |

---

## EPIC-07: Gemelo Digital Offline y Ecosistema Local LLM Wiki
>
> Bóveda auto-contenida offline (Exportador) orquestada como un LLM Wiki nativo (Obsidian/Cursor) con grafos bidireccionales y hot cache cognitiva. Todo el proceso sucede íntegramente en memoria RAM y nunca se almacena en disco para total privacidad por Tenant.

| Feature ID | Feature | Prioridad MoSCoW |
| --- | --- | --- |
| F-07.1 | Exportación Estructurada de Bóveda Offline (Formato LLM Wiki: raw/, wiki/, CLAUDE.md) | SHOULD |
| F-07.2 | Traducción Recursiva de Aristas (relaciones validadas SQL/Vector) a Enlaces Nativos (Obsidian `[[ ]]`) | SHOULD |
| F-07.3 | Generador de Caché Caliente Dinámica (`hot.md`) para sincronización del Sliding Window conversacional | COULD |

---

## EPIC-08: Identidad y Control de Acceso
>
> Gestión de usuarios, autenticación y asignación estricta de tenencia.

| Feature ID | Feature | Prioridad MoSCoW |
| --- | --- | --- |
| F-08.1 | Sistema de login unificado para acceso a la plataforma | MUST |
| F-08.2 | Sistema de roles y Tenant único por usuario (eliminación de selector de Tenant) | MUST |

---

## EPIC-09: Experiencia de Usuario e Internacionalización
>
> Adaptación del sistema para uso global y pautas de accesibilidad para todos los perfiles de usuario.

| Feature ID | Feature | Prioridad MoSCoW |
| --- | --- | --- |
| F-09.1 | Soporte Multilenguaje fluido (ES/ENG) en toda la interfaz de usuario | SHOULD |
| F-09.2 | Integración de estándares de Accesibilidad (WCAG, contrastes, soporte lectores) | SHOULD |

---

## Resumen de Prioridades

| Prioridad | Cantidad de Features |
| --- | --- |
| MUST | 25 |
| SHOULD | 10 |
| COULD | 4 |
| WON'T | 0 |

# 📋 Épicas y Features — [NOMBRE DEL PROYECTO]

<!--
  INSTRUCCIONES PARA LA IA (FASE 1 — Descubrimiento y Desglose)
  ──────────────────────────────────────────────────────────────
  Este archivo es el OUTPUT de la FASE 1 del workflow.
  Sustitúye TODO el contenido de ejemplo por el desglose real del proyecto.

  Estructura obligatoria:
  - Una sección H2 por Epic (## EPIC-XX: Nombre)
  - Descripción breve del Epic en blockquote (>)
  - Tabla de Features con columnas: Feature ID | Feature | Prioridad MoSCoW
  - Sección de resumen al final con totales por prioridad

  IDs de Feature: F-XX.Y (Epic-Número.Subnúmero), empezando por F-00 para Setup.
  Prioridades: MUST | SHOULD | COULD | WON'T
-->

**Proyecto:** [NOMBRE DEL PROYECTO]
**Fecha:** [FECHA]
**Stack:** [STACK TECNOLÓGICO]
**Estado:** FASE 1 Completada

---

## EPIC-00: Setup e Infraestructura Base

> Fundamentos técnicos necesarios antes de cualquier funcionalidad de negocio. Orden obligatorio de implementación.

| Feature ID | Feature | Prioridad MoSCoW |
| --- | --- | --- |
| F-00.1 | [Setup inicial del proyecto: instalación de dependencias, configuración de entorno] | MUST |
| F-00.2 | [Esquema de base de datos: migraciones y modelos principales] | MUST |

---

## EPIC-01: [Nombre del Epic principal]

> [Descripción breve del Epic: qué problema de negocio resuelve.]

| Feature ID | Feature | Prioridad MoSCoW |
| --- | --- | --- |
| F-01.1 | [Feature clave del Epic, la más importante para el MVP] | MUST |
| F-01.2 | [Segunda feature del Epic] | MUST |
| F-01.3 | [Feature importante pero no bloqueante para el día 1] | SHOULD |
| F-01.4 | [Feature deseable pero no esencial] | COULD |

---

## EPIC-02: [Nombre del segundo Epic]

> [Descripción breve.]

| Feature ID | Feature | Prioridad MoSCoW |
| --- | --- | --- |
| F-02.1 | [Feature clave] | MUST |
| F-02.2 | [Feature secundaria] | SHOULD |

---

## Resumen de Prioridades

| Prioridad | Cantidad de Features |
| --- | --- |
| MUST | [N] |
| SHOULD | [N] |
| COULD | [N] |
| WON'T | [N] |
