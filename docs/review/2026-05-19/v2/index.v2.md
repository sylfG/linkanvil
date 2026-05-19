---
layout: home

hero:
  name: "LinkAnvil"
  text: "Plataforma RAG orientada a eventos para extraer y organizar conocimiento."
  tagline: "Ingesta asíncrona, RAG híbrido multi-tenant y Zero-Defect pipeline con despliegue local."
  actions:
    - theme: brand
      text: Empezar
      link: /0-resumen
    - theme: alt
      text: Épicas y Features
      link: /Extractor_de_Requisitos/1_epics_and_features
    - theme: alt
      text: Ver en GitHub
      link: https://github.com/sylfG/linkanvil

features:
  - icon: ⚡
    title: Ingesta Asíncrona Orientada a Eventos
    details: Flujos de trabajo desacoplados basados en RabbitMQ que aseguran la consistencia continua y deduplicación en tiempo real.

  - icon: 🔍
    title: Búsqueda Vectorial Híbrida (RAG)
    details: Análisis veloz gestionado por Qdrant integrado con un diseño Multi-Tenant seguro desde la base.

  - icon: 📦
    title: Respuestas Zero-Defect Pipeline
    details: Estricto control de formato JSON forzado (Zod/Pydantic) a través de un Gateway local de LLMs.

  - icon: 🏗️
    title: Arquitectura Total Local
    details: Total resiliencia y gobernanza de datos bajo Docker Compose con PostgreSQL, Redis y Patrón Outbox transaccional.

  - icon: 🔒
    title: Seguro por Diseño
    details: Análisis STRIDE exhaustivo aplicado a toda la red cerebro-net con componentes aislados mediante Traefik.
---

<!--
================================================================================
Notas de revisión · 2026-05-19 (doc-reviser)
================================================================================

Cambios aplicados respecto a `docs/src/index.md` original:

1. [CRITICAL] CTA "Épicas y Features" enlazaba a `/1_epics_and_features`, path
   que NO existe en `docs/src/` (sólo existe bajo `Extractor_de_Requisitos/`).
   Con `ignoreDeadLinks: true` en `config.mts:100` el build no fallaba, pero el
   botón principal devolvía 404 en producción (GitHub Pages, `base: "/linkanvil/"`).
   → Corregido a `/Extractor_de_Requisitos/1_epics_and_features`, verificado contra
     `ls /tmp/linkanvil-mirror/docs/src/Extractor_de_Requisitos/` (archivo presente)
     y contra `config.mts:143` (sidebar usa exactamente ese path).

2. [MEDIUM] La CTA primaria apuntaba al backlog en vez de a la documentación
   general. La nav (`config.mts:114-116`) trata `/0-resumen` como entrada principal
   del corpus "Documentación", y la portada empujaba al usuario al backlog sin
   pasar por contexto.
   → Reordenadas las `actions`: la CTA `brand` ahora es "Empezar" → `/0-resumen`,
     y "Épicas y Features" pasa a `alt` apuntando al path correcto del backlog.

3. [MEDIUM] La portada no enlazaba el área "Documentación" que el nav promociona
   como primer ciudadano (`config.mts:115`).
   → Resuelto por el cambio (2): la nueva acción `Empezar` → `/0-resumen` da
     entrada visible al árbol `0-resumen / 1-instalacion-configuracion / … / 11-Glosario`.

Sin cambios (aprobados por el review):
- Hero `name`, `text`, `tagline` (líneas 5-7).
- Link a GitHub `https://github.com/sylfG/linkanvil` (verificado contra remote).
- Las 5 features (RabbitMQ, Qdrant, Zero-Defect / LiteLLM, Docker Compose / Outbox,
  cerebro-net / Traefik) — todas verificadas contra `docker-compose.yml` e `infra/`.

Hallazgos no aplicados: ninguno. Se aplicaron los 3 hallazgos del review (1 CRITICAL
+ 2 MEDIUM). No quedan CRITICAL/HIGH/MEDIUM pendientes.
-->
