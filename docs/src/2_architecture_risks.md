# 🏗️ Arquitectura y Riesgos (Fase 2) — LinkAnvil

Este documento define los Requisitos No Funcionales (NFRs) y el modelado de amenazas (STRIDE) basados en la arquitectura orientada a eventos del proyecto LinkAnvil.

---

## 1. Requisitos No Funcionales (NFRs)

| NFR | Descripción | Categoría | Componentes Involucrados |
| --- | --- | --- | --- |
| **Latencia Sub-milisegundo (Ingesta)** | El sistema debe validar y rechazar URLs duplicadas en menos de 1ms para no bloquear la experiencia del usuario y evitar gasto inútil de procesamiento. | `Infrastructure`, `Data` | Redis (Bloom Filter), Traefik |
| **Resiliencia Cognitiva (High Availability)** | El procesamiento IA no debe depender de un único proveedor (*Vendor Lock-in*). Debe existir *Fallback Automático* bajo demanda si el LLM principal falla. | `Integration`, `Infrastructure` | LiteLLM Gateway |
| **Consistencia Eventual Estricta** | El flujo de base relacional a grafos y vectores debe completarse íntegramente tras su publicación. Ningún dato debe perderse en silos separados (*Dual-Write problem*). | `Data`, `Logic / Business` | PostgreSQL (Patrón Outbox), RabbitMQ, Qdrant |
| **Aislamiento Multi-Tenant** | Total privacidad entre datos de diferentes usuarios. Un Inquilino no puede, bajo ninguna circunstancia, recuperar "embeddings" o filas transaccionales de otro. | `Security`, `Data` | PostgreSQL (RLS), Qdrant (`tenant_id`) |
| **Observabilidad Integral (Zero-Blindness)** | Debe existir un rastro absoluto para cada evento en el clúster a través de un `Trace-ID` único que acompañe la acción desde origen a destino. | `Observability` | OTel Collector, Jaeger |

---

## 2. Decisiones de Arquitectura (ADRs Resumidos)

* **PostgreSQL sobre MongoDB:** Se requiere el **Patrón Outbox** transaccional para garantizar la consistencia relacional y publicar posteriormente los eventos en RabbitMQ de manera atómica, algo fundamental en una arquitectura *Event-Driven* pura. Se integran además políticas locales RLS (*Row-Level Security*).
* **Docker Compose (Standalone) sobre Cloud Administrado:** Restricción de coste y filosofía del producto. El Segundo Cerebro debe poder vivir en *localhost* o en una única VPS, garantizando privacidad absoluta (sin *Vendor Lock-in* a herramientas SaaS propietarias) mediante red virtual interna aislada (`cerebro-net`).
* **LiteLLM Proxy + Zod (Zero-Defect):** Obligatorio obligar a los LLMs a estructurar respuestas tabulares JSON en la salida para alimentar Qdrant/PostgreSQL, rechazando explícitamente contenido malformado antes de contaminar la base de conocimiento.

---

## 3. Modelado de Amenazas (STRIDE)

| Riesgo (STRIDE) | Vector de Ataque | Mitigación Arquitectónica | Categoría Afectada |
| --- | --- | --- | --- |
| **(S) Spoofing** | Suplantación de identidad en el enrutamiento interno entre servicios locales. | Los servicios solo exponen puertos dentro de la red Docker (`cerebro-net`). Traefik es el único canal hacia internet. | `Infrastructure`, `Security` |
| **(T) Tampering** | Manipulación de la base de conocimiento o vectorización maliciosa interceptando mensajes. | Salidas estructuradas forzosas (Zod/Pydantic) en LiteLLM, y firma de integridad en la mensajería interna. | `Integration`, `Security` |
| **(R) Repudiation** | Un proceso falla o se elimina un dato y no hay forma de saber qué componente lo ocasionó. | Trazabilidad distribuida obligatoria mediante OpenTelemetry (`Trace-ID`) visualizada en Jaeger (Event Sourcing Logging). | `Observability` |
| **(I) Info Disclosure** | Cruce de información o "embeddings" mostrados al usuario B pero pertenecientes al usuario A. | Filtro mandatario `tenant_id` en Qdrant y Row-Level Security (RLS) en PostgreSQL. | `Data`, `Security` |
| **(D) DoS** | *Denial of Service* / Abuso de API: Un usuario satura la cola de ingesta agotando RAM y cuotas del LLM. | Rate Limiting rígido en Traefik, validación ultrarrápida redundante en Redis y *Throttling/Noisy Neighbor Defense*. | `Infrastructure`, `Security` |
| **(E) Elevation of Privilege** | Bypass del flujo de red para inyectar *Prompts* directamente al LLM abusando de la facturación Cloud. | LiteLLM Gateway actúa bajo cuotas máximas pre-acordadas, con control de facturación local e independiente de la tarjeta de crédito global. | `Integration`, `Security` |
