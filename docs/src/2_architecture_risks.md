<div align="center">
  <img src="../public/logo-light.png" alt="Logo" width="80" height="80" class="light-only">
  <img src="../public/logo-dark.png" alt="Logo" width="80" height="80" class="dark-only">


# 🏗️ Arquitectura y Riesgos (Fase 2) — LinkAnvil

</div>


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

### ADR-001: PostgreSQL sobre MongoDB
**Contexto:** Necesitamos persistencia relacional con consistencia transaccional para el Patrón Outbox y aislamiento multi-tenant.
**Decisión:** PostgreSQL con Patrón Outbox (tabla `outbox_eventos`) para publicar eventos en RabbitMQ de forma atómica, y Row-Level Security (RLS) para aislamiento de tenants.
**Ventaja:** Garantías ACID. La transacción que crea el recurso y el evento Outbox nunca queda en estado inconsistente, incluso si RabbitMQ está caído en ese momento.

### ADR-002: Docker Compose Standalone sobre Cloud Administrado
**Contexto:** El producto debe poder vivir en `localhost` o una VPS sin depender de servicios cloud propietarios.
**Decisión:** Docker Compose con red privada `cerebro-net`. Todo el stack se levanta con un único `docker compose up -d`.
**Ventaja:** Privacidad absoluta (ningún dato sale del host), sin costes de cloud, portabilidad total.

### ADR-003: LiteLLM Proxy + Pydantic Zero-Defect Pipeline
**Contexto:** Las respuestas de LLMs son texto libre y pueden llegar malformadas, contaminando Qdrant/Postgres con datos incorrectos.
**Decisión:** LiteLLM como proxy multi-proveedor con Circuit Breaker y Fallback; todas las respuestas validadas con Pydantic antes de persistir.
**Ventaja:** Un proveedor que cae no interrumpe el servicio. Las respuestas malformadas se rechazan antes de llegar a la base de datos.

### ADR-004: Schema `cerebro` Aislado en PostgreSQL
**Contexto:** LiteLLM usa Prisma internamente. Prisma ejecuta `schema_sync` al arrancar y **elimina cualquier tabla en `public` que no reconozca**. Las tablas de LinkAnvil en `public` se destruían en cada restart de LiteLLM.
**Decisión:** Mover todas las tablas propias al schema `cerebro`. Configurar asyncpg con `SET search_path TO cerebro, public`. El `init.sql` crea el schema explícitamente antes que las tablas.
**Ventaja:** Las migraciones de LiteLLM/Prisma son completamente invisibles para el schema `cerebro`. Los tres schemas coexisten sin interferencia: `public` (LiteLLM), `cerebro` (LinkAnvil), `n8n` (orquestador).

### ADR-005: httpOnly Cookie + CSRF Doble Submit
**Contexto:** El JWT de sesión estaba en `localStorage`. Cualquier XSS en el frontend podía robar el token y suplantar al usuario indefinidamente.
**Decisión:** JWT en cookie `SESSION_COOKIE` con `httponly=True` (JS no puede leerla). Adicionalmente, cookie `CSRF_COOKIE` legible por JS + header `X-CSRF-Token` en cada request que modifica estado. La API verifica que header == cookie (doble submit pattern). Se mantiene `Authorization: Bearer` como fallback para bots/scripts.
**Ventaja:** Elimina el vector XSS para robo de token. El doble submit CSRF no requiere estado server-side (sin tabla de tokens). Tradeoff: el cliente debe enviar explícitamente el header `X-CSRF-Token` y configurar `credentials: "include"` en fetch.

### ADR-006: Heartbeat Redis + TTL para Liveness de Workers
**Contexto:** Los workers Python (scraper, embedder, outbox) pueden bloquearse internamente (esperando conexión, procesando mensaje muy grande) mientras el proceso sigue "vivo" para Docker. El healthcheck basado en `CMD` no detecta esta condición.
**Decisión:** Cada worker ejecuta una tarea asyncio que escribe `worker:<name>:heartbeat` en Redis con TTL de 45 segundos. El healthcheck de Docker lee esa clave — si no existe, el contenedor se marca `unhealthy`.
**Ventaja:** Detecta workers zombi con latencia máxima de 45s. No requiere exponer un puerto HTTP adicional por worker. Si el worker se cuelga, Docker puede reiniciarlo automáticamente según la política `restart: unless-stopped`.

### ADR-007: Runner de Migraciones Shell sin Alembic
**Contexto:** Necesitamos aplicar migraciones SQL idempotentes sin añadir dependencias Python extra ni un runtime de migración separado.
**Decisión:** `scripts/migrate.sh` — script Bash que invoca `psql` (disponible en `postgres:16-alpine`). Usa la tabla `cerebro.schema_migrations` para bookkeeping. Cada migración corre en una transacción; un fallo revierte solo esa migración y para la ejecución.
**Ventaja:** Zero dependencias adicionales. Reproducible en cualquier entorno con `psql`. Idempotente y seguro de ejecutar en CI/CD. Nota técnica: los nombres de archivo usan `0001`, `0002`, etc. — Bash interpreta estos como octal en aritmética. Se usa `$((10#${version}))` para forzar base-10 y evitar bugs silenciosos.

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
