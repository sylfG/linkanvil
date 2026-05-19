# Review: docs/src/11-Glosario.md

**Target**: `/tmp/linkanvil-mirror/docs/src/11-Glosario.md` (35 términos)
**Fecha auditoría**: 2026-05-19
**Auditor**: docs-reality-auditor
**Repo access**: local mirror (`/tmp/linkanvil-mirror/`)

---

## Resumen ejecutivo

- **35 términos** en glosario.
- **Hallazgos CRITICAL**: 2 — definiciones que mienten sobre el modelo real del proyecto (tenant simplificado a 1 nivel cuando el código tiene 2; RAG ignora el toggle Archivo).
- **Hallazgos HIGH**: 9 — términos LinkAnvil-específicos AUSENTES del glosario pese a aparecer en otras docs y en código de producción (BYOK, audit_policy, temporal_class, valor_archivistico, evento_pasado, auto_archive_pending, DLQ, JSONB, JWT).
- **Hallazgos MEDIUM**: 6 — gaps menores, definiciones genéricas, términos obsoletos no documentados.
- **Hallazgos LOW**: 5 — typos, ortografía, tipografía.
- **Verdict**: el glosario describe un proyecto **genérico**, no LinkAnvil. La mitad de los términos de dominio (los que realmente importan para entender la arquitectura) no están definidos. Términos como `tenant`, `RAG` y `outbox` se definen en forma de "diccionario para principiantes" sin reflejar el modelo concreto del repo.

---

## CRITICAL

### CRIT-1 — `Tenant` oculta el modelo de 2 niveles (tenant + sub-tenant demo)

**Glosario** (`docs/src/11-Glosario.md:12`):
> "**Tenant (Inquilino / Cuenta):** Un espacio de usuario aislado y seguro dentro de un sistema compartido por muchas personas o empresas."

**Realidad en código** — el proyecto tiene **dos clases de tenant** muy diferentes:

1. **Tenant persistente** (registro normal): fila en `usuarios`, `tenant_id` estable.
2. **Sub-tenant efímero demo** (TTL 15 min, formato `demo_<8hex>`):
   - `src/api/database.py:15` — *"Los sub-tenants efímeros del demo (demo_<8hex>) hacen UNION con este..."*
   - `src/api/database.py:93` — *"Crea un sub-tenant efímero (TTL 15min) para una nueva sesión demo."*
   - `infra/postgres/migrations/0009_demo_sessions.sql:3` — *"Sesiones efímeras del demo (sub-tenants con TTL de 15 min)."*
   - `infra/postgres/migrations/0010_demo_session_events.sql:5` — *"Cada login del demo (vía POST /auth/demo-start) crea su sub-tenant"*
   - `src/api/main.py:248` — *"sub-tenants efímeros del demo no tienen fila en `usuarios`."*
   - `src/api/llm_keys.py:4` — *"`tenant_id` a keyear por `user_id`. El motivo: los sub-tenants..."*
   - `src/data/audit_cron.py:187` — *"Auditoría intra-sesión para un sub-tenant demo."*

**Impacto**: cualquier desarrollador nuevo lee el glosario y NO sabe que existe un segundo nivel de aislamiento (`sub-tenant`) que cambia el comportamiento de auth, LLM keys, audit cron, cleanup, y queries con `UNION`. La FAQ marketing (`src/frontend/app/(marketing)/_components/FAQ.tsx:16`) tampoco lo menciona y describe solo el tenant persistente.

**Acción**: redefinir `Tenant` para incluir:
- Tenant persistente (cuenta de usuario registrada).
- Sub-tenant efímero demo (sesión TTL 15 min sin fila en `usuarios`, identificado por `demo_<8hex>`).
Y añadir entrada separada **"Sub-tenant demo"**.

---

### CRIT-2 — `RAG` ignora la dualidad activo/archivo histórico

**Glosario** (`docs/src/11-Glosario.md:9`):
> "**RAG (Generación Aumentada por Recuperación):** Una técnica que permite a una Inteligencia Artificial responder preguntas basándose exclusivamente en los documentos y enlaces aportados por el usuario, evitando que invente información."

**Realidad** — el RAG de LinkAnvil tiene **dos modos de recuperación**:

- `src/frontend/app/(marketing)/_components/FAQ.tsx:24` — *"contenido pasado con valor archivístico alto se manda al archivo histórico — sigue indexado y recuperable en el chat con el toggle 'Archivo ON'."*
- `infra/postgres/migrations/0007_audit_policy_y_auto_archive.sql:82-85` — *"los chunks queden indexados en Qdrant para el toggle Archivo ON en chat, pero el recurso aparezca como 'archivo histórico' en /expired (no en KB activo)."*
- `src/api/main.py:85-90` — pipeline `_index_staged_for_rag` (demo) con embeddings staged.

**Impacto**: la definición genérica esconde que el sistema:
1. Discrimina recursos `activo` vs `expirado` con un toggle UI.
2. Tiene una pipeline **staged embeddings** para demo (`ops/build_staged_embeddings.py`).
3. Soporta colisión global de recursos (`src/data/embedder_worker.py:384` "(otro tenant) en vez de re-embeber").

La definición debe mencionar el toggle "Archivo ON" y/o el staged path. Como está, es indistinguible del RAG de cualquier producto.

---

## HIGH

### HIGH-1 — `BYOK` ausente del glosario

Aparece **decenas de veces** en código y docs pero no está definido. Es un término propio del proyecto (Bring Your Own Key — para LiteLLM).

Evidencia:
- `src/frontend/app/(app)/layout.tsx:144` — *"BYOK (migración 0008): 3 virtual-keys de LiteLLM por tenant."*
- `src/frontend/lib/api.ts:162-166` — *"(ej: { error, op, message } en 402/429 BYOK/quota) ... `byok_required` vs `demo_daily_quota_exceeded`"*
- `src/frontend/app/(app)/chat/page.tsx:257-267` — manejo del 402 BYOK.
- `infra/postgres/migrations/0008_byok_y_demo_flag.sql` — migración explícita.
- También citado en `docs/src/2-resumen-servicios.md` y `docs/src/3-componentes.md` (assumed, grep `BYOK` en docs/src devuelve hits).

**Acción**: añadir entrada **BYOK (Bring Your Own Key)** explicando que cada usuario registrado puede aportar sus 3 virtual-keys de LiteLLM, y que el demo está exento.

---

### HIGH-2 — `audit_policy` no documentado pese a ser eje del producto

Evidencia:
- `src/frontend/lib/auth.ts:7` define `AUDIT_POLICY_KEYS` con 6 claves.
- `src/data/db.py:30` `DEFAULT_AUDIT_POLICY`.
- `infra/postgres/migrations/0007_audit_policy_y_auto_archive.sql:20` — *"usuarios.audit_policy JSONB (sustituto de audit_strictness)"*.
- El JSONB tiene 6 claves: `evento_pasado_alto/medio/nulo`, `referencia_pasada_alto/medio/nulo`.

**Acción**: añadir definición que aclare que es un JSONB con 6 claves resultado de la matriz `temporal_class × valor_archivistico`, y que **reemplazó** al antiguo `audit_strictness`.

---

### HIGH-3 — `temporal_class` no documentado

Evidencia:
- `infra/postgres/migrations/0006_temporal_class_y_strictness.sql:36-37` — CHECK constraint con valores `'evento', 'referencia', 'evergreen'`.
- `src/frontend/app/(marketing)/_components/RealExamples.tsx:15,28,40,52,64` — UI marketing lo usa.
- `src/frontend/app/(app)/profile/page.tsx:35,425` — UI app lo agrupa.
- `src/data/audit_cron.py:120,127` — query SQL.

Es un campo definitorio del modelo de datos. Los tres valores (`evento` / `referencia` / `evergreen`) deberían listarse explícitamente.

---

### HIGH-4 — `valor_archivistico` no documentado

Evidencia:
- `infra/postgres/migrations/0006_temporal_class_y_strictness.sql:38-39` — CHECK con `'alto', 'medio', 'nulo'`.
- `src/frontend/app/(marketing)/_components/RealExamples.tsx:7` — *"LLM extraería (temporal_class + valor_archivistico)"*.

Tres valores: `alto`, `medio`, `nulo`. Define una de las dos dimensiones de la matriz de `audit_policy`. Debe documentarse.

---

### HIGH-5 — `evento_pasado` / `referencia_pasada` (claves del JSONB) no documentadas

Evidencia:
- `src/notifier/worker.py:50` — `"evento_pasado": "tiene fecha pasada y requiere revisión"`.
- `src/frontend/app/(app)/_NotificationsBell.tsx:29` — `evento_pasado: "fecha pasada"`.
- `infra/postgres/migrations/0007_audit_policy_y_auto_archive.sql:26-31` — keys del JSONB.

Son los `evento_tipo` emitidos por el audit_cron y consumidos por el notifier. Aparecen en UI traducidos al usuario final.

---

### HIGH-6 — `auto_archive_pending` no documentado

Evidencia:
- `infra/postgres/migrations/0007_audit_policy_y_auto_archive.sql:80-87` — flag en `recursos`.
- `src/data/embedder_worker.py:438,444,510-520` — el embedder lo lee y transiciona a `expirado`.
- `src/data/audit_cron.py:260` — el cron lo limpia tras transición.

Flag clave del pipeline auto-archive. Sin él, el flujo "alto-archivo → expirado" del FAQ no funciona.

---

### HIGH-7 — `DLQ` ausente pese a ser usado

Evidencia:
- `src/data/embedder_worker.py:83` — `DLQ_ROUTING_KEY = "dlq.url.fallidas"`.
- `src/data/embedder_worker.py:113` — `"x-dead-letter-routing-key": DLQ_ROUTING_KEY`.
- Aparece en `docs/src/2-resumen-servicios.md` (grep confirma).

Definición esperada: Dead-Letter Queue — cola de RabbitMQ a la que van mensajes que fallaron el procesamiento normal después de N reintentos.

---

### HIGH-8 — `JSONB` ausente, mencionado por nombre en otras docs

Evidencia: el tipo JSONB es central en `audit_policy` y en `outbox_eventos.payload`. Aparece en `infra/postgres/migrations/0007` y `0010`, en `src/data/db.py:46`, y en otras páginas de docs.

(El usuario solicitó verificar tipografía: dice "json b" → "JSONB" — no encontré ningún "json b" malformado en el glosario actual; el problema es que **no aparece**.)

---

### HIGH-9 — `JWT` ausente del glosario

Evidencia:
- `src/api/auth.py:8,20,23-28,66,71,74` — implementación con `jose.jwt`.
- `src/frontend/lib/auth.ts:87` y `src/frontend/components/DemoCountdownBanner.tsx:39` — UI decodifica el JWT.

(Verificación de tipografía: el código usa **JWT** consistentemente, NO JWS. No hay confusión nombre-implementación.)

`refresh token` (también listado por el usuario): existe (`src/api/auth.py:24,28,46,50`) pero no está en glosario. Es un token **opaque random**, NO un JWT — distinción importante que el glosario debería preservar.

---

## MEDIUM

### MED-1 — Términos obsoletos no marcados

`audit_strictness` ya **NO existe** en `usuarios` (DROP en `infra/postgres/migrations/0007_audit_policy_y_auto_archive.sql:74`). Sin embargo:
- `src/data/audit_cron.py:134` — comentario stale: *"respetando el strictness del tenant"*.
- `infra/postgres/migrations/0006_temporal_class_y_strictness.sql` — nombre del archivo migración mantiene `strictness`.

El glosario debería **mencionar el término obsoleto** y apuntar a `audit_policy` como sustituto, para que devs leyendo PRs viejos o ese comentario no se confundan.

(El usuario preguntó específicamente por este término — confirmado: `audit_strictness` fue reemplazado por `audit_policy` en migración 0007.)

---

### MED-2 — `outbox` definición demasiado genérica

**Glosario** (`docs/src/11-Glosario.md:8`):
> "**Patrón Outbox:** Un método de diseño de software que asegura que los datos se guarden correctamente en la base de datos principal antes de avisar o enviar copias a otros componentes del sistema..."

**Realidad** (`src/frontend/lib/resource_stream.tsx:23`):
> "outbox → RabbitMQ → notifier → Redis → SSE"

La cadena específica de LinkAnvil tiene **5 saltos** definidos. La definición debería mencionar al menos la tabla `outbox_eventos` y los consumidores reales.

Tablas afectadas:
- `src/data/audit_cron.py:45` — `INSERT INTO outbox_eventos`
- `src/data/export_manager.py:77` — `FROM outbox_eventos`

---

### MED-3 — `SSE` definición no menciona el path

**Glosario** (`docs/src/11-Glosario.md:11`): definición genérica de streaming.

**Realidad**: SSE en LinkAnvil tiene canales Redis pub/sub específicos:
- `src/notifier/worker.py:247` — *"Fan-out a SSE: cualquier UI suscrita a `resources:{tenant_id}`"*.
- `src/frontend/lib/api.ts:184-188` — función `sseUrl` con cookies same-origin.
- `src/frontend/lib/sse.ts` (módulo dedicado).

Debería mencionar el canal `resources:{tenant_id}` y el endpoint SSE concreto.

---

### MED-4 — `Bloom Filter` definición OK pero falta contexto LinkAnvil

**Glosario** (`docs/src/11-Glosario.md:23`): definición correcta a nivel concepto.

**Falta**: contexto del proyecto.
- `src/ingestion/deduplicator.py:14` — *"Filtro Deduplicador en Tiempo Real basado en Bloom Filters (RedisBloom)."*
- `src/ingestion/deduplicator.py:28` — key per-tenant: `_get_bloom_key(tenant_id)`.

Debería decir "RedisBloom per-tenant, usado para deduplicar URLs en ingesta".

---

### MED-5 — `Cola de Mensajes (RabbitMQ)` cita producto pero no exchange

**Glosario** (`docs/src/11-Glosario.md:32`): definición OK.

**Falta**: en LinkAnvil hay un **fanout exchange** específico:
- `src/data/embedder_worker.py:343,356` — *"El exchange `cerebro.procesamiento` es fanout: cada queue bound..."*
- `src/notifier/worker.py:4` — *"Consume de la fanout `cerebro.procesamiento`"*.

El término **"fanout exchange"** (pedido específico del usuario) NO está en glosario y es central a la arquitectura event-driven.

---

### MED-6 — `Embedding` no menciona modelo ni dimensiones

**Glosario** (`docs/src/11-Glosario.md:7`): definición conceptual correcta.

**Falta**:
- Modelo: `cerebro-embeddings` vía LiteLLM (`src/data/embedder_worker.py:121,131`).
- Endpoint: `LITELLM_EMBEDDINGS_URL = .../v1/embeddings`.
- Dimensión: 1536 (`infra/qdrant/init_qdrant.sh:13` y `:24` — `"size": 1536`).
- Idempotencia upserts: `src/data/embedder_worker.py:30` — *"el mismo par siempre genere el mismo id (idempotencia en upserts)"*.

---

## LOW

### LOW-1 — Typo en línea 18 (Webhook)

`docs/src/11-Glosario.md:18`:
> "...enviándole **nuevosiem** que ha ocurrido un evento nuevo."

`nuevosiem` no es palabra. Probablemente "nuevos siempre" o fragmento de duplicación. La frase entera repite "que ha sucedido un evento" / "que ha ocurrido un evento nuevo" — limpiar.

### LOW-2 — Duplicación "web" en Host Header

`docs/src/11-Glosario.md:20`:
> "Una sección invisible en tu petición **web web**..."

Doble "web". Eliminar uno.

### LOW-3 — Inconsistencia de viñetas

Líneas 4-12 usan `* ` y 13-38 usan `*   ` (tres espacios). Aunque Markdown lo tolera, los renderers no siempre lo hacen idéntico — unificar a un solo estilo.

### LOW-4 — `Streaming SSE` — definición no resuelve el acrónimo

Dice "Streaming SSE" pero no aclara "Server-Sent Events". Añadir.

### LOW-5 — `Similitud coseno` no aparece como entrada

Aunque "Embedding" lo insinúa ("medir qué tan similar"), no hay entrada explícita. El código usa `"distance": "Cosine"` (`infra/qdrant/init_qdrant.sh:16,26`). El usuario pidió verificar este término — está presente en el código, ausente del glosario. Clasificación: MEDIUM si se quiere ser estricto, LOW si se considera implícito.

---

## Términos en código sin entrada en glosario (gap inventory)

Términos que aparecen en código de producción y/o otras docs, **no listados**:

| Término | Origen evidencia |
|---|---|
| BYOK | `src/api/llm_keys.py`, migración 0008, FAQ marketing |
| audit_policy / DEFAULT_AUDIT_POLICY | `src/data/db.py:30-32`, `src/frontend/lib/auth.ts:7-16` |
| temporal_class | migración 0006, embedder, UI |
| valor_archivistico | migración 0006 |
| evento_pasado / referencia_pasada | notifier worker, NotificationsBell |
| auto_archive_pending | migración 0007, embedder, audit_cron |
| sub-tenant demo | `src/api/database.py:15,93`, migraciones 0009/0010 |
| Qdrant | usado en >20 archivos, colecciones `cerebro_recursos` y `cerebro_chunks` |
| LiteLLM | virtual keys per-tenant, embeddings y chat completions |
| Redis pub/sub | canal `resources:{tenant_id}` para SSE |
| outbox_eventos (tabla) | tabla concreta del patrón outbox |
| DLQ | `dlq.url.fallidas` en embedder |
| JSONB | tipo PG para `audit_policy` y `outbox_eventos.payload` |
| JWT / Refresh token / CSRF token | `src/api/auth.py` — 3 tokens, 3 roles distintos |
| fanout exchange (`cerebro.procesamiento`) | embedder, notifier |
| Trace-ID está pero falta **OpenTelemetry / OTLP** | `src/telemetry.py:9`, `infra/otel/config.yaml` |
| chunk (chunk_idx, chunk_text) | `src/api/main.py:76-105`, cache `staged_embeddings` |
| RabbitMQ ya está pero falta **routing_key** | `src/ingestion/publisher.py:29` |
| litellm virtual key / alias | `src/api/llm_keys.py:21,93` |
| `recursos.estado` (activo / expirado / cuarentena) | aparece en migraciones y FAQ |
| cerebro_recursos / cerebro_chunks (colecciones Qdrant) | `infra/qdrant/init_qdrant.sh:11,21` |
| staged_embeddings (cache para demo) | migración 0011, `ops/build_staged_embeddings.py` |
| Telegram webhook por usuario | `src/api/main.py:1148`, `src/ingestion/main.py:182-230` |

Total: **~22 términos faltantes** vs **35 presentes** = el glosario cubre ~60% del vocabulario real.

---

## Resumen por categorías

| Categoría | Estado |
|---|---|
| Términos de infra genérica (Docker, HTTPS, NAT, Proxy, Puerto) | OK, definiciones correctas. |
| Términos de seguridad (CSRF, XSS, Rate Limiting) | Definiciones genéricas OK. Falta contexto del proyecto (rate limits concretos: 5/min login, 30/min chat). |
| Términos de dominio LinkAnvil | **DÉFICIT GRAVE** — falta lo esencial: BYOK, audit_policy, temporal_class, valor_archivistico, sub-tenant. |
| Términos de stack (RabbitMQ, Qdrant, Redis, LiteLLM) | RabbitMQ está pero genérico. Qdrant, Redis y LiteLLM ausentes pese a ser nombres propios del stack. |
| Términos de observabilidad | OK (Trazas, Métricas, Exporter, Observabilidad). |

---

## Recomendaciones (priorizadas)

1. **CRITICAL**: refundir `Tenant` y añadir `Sub-tenant demo` como entrada separada.
2. **CRITICAL**: enriquecer `RAG` con el toggle "Archivo ON" y la dualidad activo/archivo histórico.
3. **HIGH**: añadir 9 entradas nuevas: BYOK, audit_policy, temporal_class, valor_archivistico, evento_pasado, auto_archive_pending, DLQ, JSONB, JWT (+ Refresh Token + CSRF Token diferenciados).
4. **MEDIUM**: añadir nota histórica sobre `audit_strictness` (obsoleto, reemplazado en migración 0007).
5. **MEDIUM**: enriquecer outbox, SSE, Bloom Filter, RabbitMQ con detalles concretos del proyecto (nombres de exchanges, tablas, canales).
6. **MEDIUM**: añadir `fanout exchange`, `similitud coseno`, `OpenTelemetry`, `Qdrant`, `LiteLLM`.
7. **LOW**: corregir typos (`nuevosiem`, `web web`), unificar viñetas, expandir acrónimos.

---

## Métricas

- **Términos totales en glosario**: 35
- **Términos LinkAnvil-específicos críticos faltantes**: 9 (HIGH)
- **Definiciones engañosas vs realidad código**: 2 (CRITICAL — tenant, RAG)
- **Términos obsoletos no documentados**: 1 (`audit_strictness`)
- **Typos**: 2 (LOW)
- **Cobertura estimada**: ~60% del vocabulario técnico real del repo.
