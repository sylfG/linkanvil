---
layout: home

hero:
  name: "LinkAnvil"
  text: "Plataforma RAG orientada a eventos para extraer y organizar conocimiento."
  tagline: "Ingesta asíncrona, RAG híbrido multi-tenant y Zero-Defect pipeline con despliegue local."
  actions:
    - theme: brand
      text: Épicas y Features
      link: /1_epics_and_features
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
