# Ciclo de vida de un recurso en LinkAnvil

> Referencia canónica del recorrido completo de una URL desde que el usuario la
> añade hasta que desaparece del sistema. Documenta todas las transiciones de
> estado, qué BD se toca en cada paso, y qué controla el usuario vs qué controla
> el sistema.
>
> Para una vista narrativa con ejemplos, ver
> [`5_ejemplo_flujo copy.md`](./5_ejemplo_flujo%20copy.md). Para los prompts
> que el LLM ejecuta en cada fase, ver [`prompts.md`](./prompts.md).

---

## Tabla de contenidos

1. [Vista general — diagrama de estados](#1-vista-general--diagrama-de-estados)
2. [Fase 1 — Ingesta](#2-fase-1--ingesta)
3. [Fase 2 — Vida activa](#3-fase-2--vida-activa)
4. [Fase 3 — Detección de obsolescencia](#4-fase-3--detección-de-obsolescencia)
   - 4.1 [Camino temporal (cron + botón manual)](#41-camino-temporal-cron--botón-manual)
   - 4.2 [Camino semántico (colisión durante embedding)](#42-camino-semántico-colisión-durante-embedding)
   - 4.3 [Camino manual (usuario manda a cuarentena)](#43-camino-manual-usuario-manda-a-cuarentena)
5. [Fase 4 — Cuarentena](#5-fase-4--cuarentena)
6. [Fase 5 — Expirado](#6-fase-5--expirado)
7. [Fase 6 — Borrado definitivo](#7-fase-6--borrado-definitivo)
8. [Anexo A — Tabla "estado vs BDs vs RAG vs notificación"](#8-anexo-a--tabla-estado-vs-bds-vs-rag-vs-notificación)
9. [Anexo B — Endpoints, comandos y nombres de columna](#9-anexo-b--endpoints-comandos-y-nombres-de-columna)

---

## 1. Vista general — diagrama de estados

```
                     POST /ingest
                          │
                          ▼
                  ┌───────────────┐
                  │  procesando   │ ◀───── scraper inserta placeholder
                  └───────┬───────┘        en transaction outbox
                          │
                          │ embedder completa
                          │ (Qdrant + chunks)
                          ├──────────────────────┐
                          │ auto_archive_pending │
                          │ = false              │ = true (migración 0007)
                          ▼                      ▼
                  ┌───────────────┐      ┌───────────────┐
       ┌────────► │    activo     │ ◀──┐ │   expirado    │ ◀──┐
       │          └───────┬───────┘    │ └───────┬───────┘    │
       │                  │            │         │            │
       │                  │ rescate    │         │ rescate    │
       │                  │            │         │            │
       │   ┌──────────────┼────────────┘         │            │
       │   │   audit_cron / audit-now            │            │
       │   │   colisión semántica                │            │
       │   │   policy → cuarentena               │            │
       │   │              ▼                      │            │
       │   │      ┌───────────────┐              │            │
       │   │      │  cuarentena   │              │            │
       │   │      └───────┬───────┘              │            │
       │   │              │ gracia expira        │            │
       │   │              │ o decisión manual    │            │
       │   │              ▼                      │            │
       │   │      ┌───────────────┐              │            │
       │   └──────│   expirado    │ ◀────────────┘            │
       │          │ (archivo hist.)│ ←── chunks indexados        │
       │          └───────┬───────┘     en Qdrant para Archivo ON │
       │                  │                                       │
       │                  │ DELETE /resources/{id}                │
       │                  ▼                                       │
       │          ┌───────────────┐                               │
       └──────────│   (borrado)   │  ← borrado en PG + cleanup Qdrant
                  └───────────────┘
```

**Cuatro estados válidos** en `recursos.estado`:

| Estado | Significado | Visible en RAG |
|--------|-------------|----------------|
| `procesando` | Recién insertado, embedder no ha terminado | No |
| `activo` | Listo para usar en KB principal | **Sí** (por defecto) |
| `cuarentena` | En período de gracia, recuperable | No |
| `expirado` | Archivo histórico (migración 0007) | Solo con toggle "Archivo ON" del chat (`include_archive=true`) |

**Cambio semántico de `expirado` (migración 0007)**: ahora significa
"archivo histórico" — no descarte. Engloba dos rutas:

- **Auto-archive** del scraper para contenido pasado con valor archivístico
  alto (la `audit_policy` del tenant lo decidió). Llega a `expirado`
  pasando por `procesando` (sí se vectoriza) gracias al flag
  `auto_archive_pending`.
- **Expiración tras gracia** (audit_cron / colisión / manual). Sigue
  funcionando como antes; el contenido queda como archivo recuperable.

El toggle "Archivo ON" del chat amplía el RAG para incluir recursos
`expirado` sin penalizar score (`get_active_resource_ids` lee
`include_archive` del body del `/chat`).

---

## 2. Fase 1 — Ingesta

**Cómo arranca**: `POST /ingest` con la URL y, opcionalmente, un
`tenant_id` (en el caso del bot de Telegram). El handler en
`src/ingestion/main.py` encola un mensaje en RabbitMQ
(`q.url.ingesta`) y devuelve 202 inmediatamente — toda la ingesta es
asíncrona.

**Pipeline**:

1. **Scraper** (`cerebro-scraper`, queue `q.url.ingesta`):
   - Descarga la URL con `BasicHttpStrategy` (`src/scraper/strategy.py`).
   - Limpia el HTML y extrae texto (≤6000 chars).
   - Llama a LiteLLM con el prompt `_extract_metadata_with_llm`
     (ver `prompts.md` §2.1) para obtener: `title`, `summary`,
     `category`, `keywords`, `volatility_score`,
     `estimated_useful_life_days`, `expiration_date`.
   - **Reuso cross-tenant**: si la URL ya existe globalmente como
     `activo` y `fecha_caducidad` está lejos, salta scrape+LLM y emite
     un evento `recurso.reusado` para que el embedder copie el vector
     del tenant origen al nuevo tenant.
   - **Pre-insert placeholder**: inserta una fila con `estado='procesando'`
     antes del scrape para que la UI tenga feedback inmediato
     (`db.py::insert_placeholder_recurso`).
   - **save_with_outbox** (transaccional, `src/data/db.py:148`):
     - `INSERT INTO recursos` con todos los campos extraídos.
     - `INSERT INTO usuario_recursos` (link tenant ↔ recurso).
     - `INSERT INTO outbox_eventos` con `evento_tipo='recurso.procesado'`.
     - Todo atómico.

2. **Decisión al ingestar** (`src/data/db.py::save_with_outbox`,
   actualizado en migraciones 0006 + 0007):

   El scraper LLM produce 3 campos adicionales:
   `temporal_class ∈ {evento, referencia, evergreen}`,
   `valor_archivistico ∈ {alto, medio, nulo}`, y `event_date` (fecha del
   evento descrito). Con esos campos + la `audit_policy` del tenant
   (JSONB con 6 keys) se decide el estado inicial:

   - **`evergreen`** o **fecha futura** (no pasada): default
     `estado='procesando'` → `'activo'` tras embedder. Para `evento`
     futuro se calcula `fecha_caducidad` con `expiration_date` del LLM
     o fallback `today + useful_life_days`. Para `referencia`/`evergreen`
     queda `NULL`.
   - **Fecha pasada (no evergreen)**: se compone la key
     `{evento_pasado|referencia_pasada}_{alto|medio|nulo}` y se lee
     `usuarios.audit_policy[key]`. Posibles decisiones:
     - `"activo"` → activo en KB con caducidad NULL.
     - `"cuarentena"` → cuarentena con `quarantine_reason='evento_pasado'`,
       grace period 30 días.
     - `"expirado"` → flag `auto_archive_pending=true`, embedder
       vectoriza y transiciona directo a `expirado` (archivo histórico).

   **Tres presets canónicos** (UI los precarga en `/profile`):

   | Preset | evento_pasado: alto/medio/nulo | referencia_pasada: alto/medio/nulo |
   |---|---|---|
   | Estricto | cuarentena / cuarentena / cuarentena | cuarentena / cuarentena / cuarentena |
   | **Equilibrado (default)** | expirado / cuarentena / cuarentena | expirado / cuarentena / cuarentena |
   | Permisivo | expirado / cuarentena / cuarentena | expirado / activo / cuarentena |

   El usuario puede partir de un preset y ajustar celdas individuales —
   no hay diferencia técnica entre "estoy en preset X" y "tengo policy
   custom"; solo se guarda el JSONB resultante.

3. **Outbox publisher** (`cerebro-outbox`, `src/data/outbox_publisher.py`):
   - Poll de `outbox_eventos` cada segundo.
   - Publica al exchange fanout `cerebro.procesamiento`.
   - Marca la fila como `procesado=true`.

4. **Embedder** (`cerebro-embedder`, `q.recurso.embedder`):
   - Filtro **whitelist** por `evento_tipo` — solo procesa
     `recurso.procesado` y `recurso.reusado` (filtro añadido en commit
     `ba405e2` para evitar re-embebido espurio de eventos del ciclo de
     obsolescencia).
   - Genera embedding del título+summary+keywords con LiteLLM
     (modelo `cerebro-embeddings`).
   - Inserta point en colección Qdrant `cerebro_recursos` con payload
     que incluye `tenant_id` (filtro de RAG).
   - Chunking del `contenido` y embedding por chunk → colección
     `cerebro_chunks` (esto es lo que el RAG consume).
   - Llama a `_compute_semantic_collisions` — si encuentra duplicados
     semánticos en Qdrant, dispara el [camino semántico](#42-camino-semántico-colisión-durante-embedding).
   - `update_recurso_estado(recurso_id, "activo")` — pero **solo si el
     estado actual es `procesando`** (guard añadido en commit
     `ba405e2` para que el embedder no resucite cuarentenas).

**Resultado**: recurso en `activo`, vectores en dos colecciones de
Qdrant, evento `recurso.procesado` propagado al notifier (que no hace
nada para este tipo).

---

## 3. Fase 2 — Vida activa

**Estado `activo`** significa que el recurso es candidato a RAG:

- **Chat con RAG** (`POST /chat` en `src/api/main.py`):
  - Embebe la pregunta del usuario.
  - Busca en `cerebro_chunks` con filtro `tenant_id=$user_tenant`.
  - **Filtra hits** por `get_active_resource_ids(tenant_id, recurso_ids)`
    que ejecuta `SELECT id FROM recursos WHERE estado='activo'`
    (`src/api/database.py:121-135`).
  - Inyecta los chunks supervivientes como `context_block` en el system
    prompt (ver `prompts.md` §3.1).
- **KB UI** (`/kb`):
  - Lista solo recursos `activo` del tenant.
  - El badge en el sidebar `Cuarentena (N)` y `Expirados (N)` se actualiza
    vía SSE cuando hay transiciones.

**Mientras está activo**:

- `volatilidad` determina cuándo se le recalcula caducidad al rescatarlo
  (`baja`=365d, `media`=180d, `alta`=60d, `dinamica`=30d).
- `embedding_version` permite re-embebido masivo si se cambia de modelo.
- `usuario_recursos` (tabla join) lleva el track de qué tenants tienen
  linkeado este recurso global.

---

## 4. Fase 3 — Detección de obsolescencia

Tres caminos llevan a `cuarentena`. Son **independientes** y pueden
disparar sobre el mismo recurso (idempotente — el primero gana).

### 4.1 Camino temporal (cron + botón manual)

**Mecánica**: `audit_cron.run_audit_cron()` ejecuta dos UPDATE SQL
atómicas. Filtros idempotentes garantizan que llamarlo N veces produce
las mismas transiciones que llamarlo una.

```sql
-- Fase A: caducidad → cuarentena
UPDATE recursos
SET estado = 'cuarentena',
    quarantined_at = NOW(),
    quarantine_reason = 'caducidad',
    quarantine_grace_until = (NOW() + OBSOLESCENCE_GRACE_DAYS * INTERVAL '1 day')::DATE,
    updated_at = NOW()
WHERE estado = 'activo'
  AND fecha_caducidad IS NOT NULL
  AND fecha_caducidad <= NOW()::DATE;

-- Fase B: gracia agotada → expirado
UPDATE recursos
SET estado = 'expirado', updated_at = NOW()
WHERE estado = 'cuarentena'
  AND quarantine_grace_until IS NOT NULL
  AND quarantine_grace_until <= NOW()::DATE;
```

**Disparadores**:

| Disparador | Quién lo invoca | Auth | Rate-limit |
|---|---|---|---|
| Cron nocturno | n8n workflow `linkanvil — audit cron diario` (cron `0 3 * * *`, ejecuta a las 07:00 UTC en TZ del contenedor) | `X-Admin-Token: $AUDIT_CRON_TOKEN` | n/a |
| Botón "Revisar caducidades" en `/kb` | Usuario autenticado | JWT del usuario + CSRF | 5/min por tenant en Redis (`rl:audit:{tenant_id}`) |
| Llamada CLI / Antigravity | Operador | `X-Admin-Token` | n/a |

**Endpoints**:

- `POST /admin/audit-cron` — interfaz para el cron de n8n (token admin).
- `POST /resources/audit-now` — interfaz para el botón UI (auth user normal).

Ambos llaman a `run_audit_cron()` y devuelven `{trace_id,
cuarentenados, expirados}`.

**fecha_caducidad IS NULL → invisible para el cron**. Esto es un
escape hatch: si un recurso tiene caducidad NULL nunca transiciona por
tiempo. Hoy ningún flujo deja caducidad en NULL (siempre hay fallback
`today + useful_life`); ver `prompts.md` §6 para la propuesta de
contenido histórico/evergreen que sí lo aprovecharía.

### 4.2 Camino semántico (colisión durante embedding)

Cuando se ingesta una URL nueva y el embedder encuentra alta similitud
con un recurso preexistente, llama al prompt **clasificador semántico**
(`prompts.md` §2.2, modelo `cerebro-lite`, temperatura 0) para tipificar
la relación. Si el LLM responde `VUELVE_OBSOLETO` o `CONTRADICE`, el
recurso **antiguo** pasa a cuarentena con
`quarantine_reason='colision_semantica'` y un evento outbox
`recurso.cuarentena` se emite.

Esto es el caso típico de "LangChain v0.1 → cuarentena cuando llega v0.2"
descrito en `5_ejemplo_flujo copy.md` Fase 3.

### 4.3 Camino manual (usuario manda a cuarentena)

Desde `/kb` (modal de detalle del recurso) el usuario puede pulsar
"Mandar a cuarentena":

- Endpoint: `POST /resources/{id}/quarantine`
- Función DB: `quarantine_recurso(tenant_id, recurso_id)`
  (`src/api/database.py:380-420`).
- Sets `estado='cuarentena'`, `quarantine_reason='manual'`,
  `quarantine_grace_until=today + 30d`.
- Emite outbox `recurso.cuarentena` por cada tenant que tenga linkeado
  el recurso.

---

## 5. Fase 4 — Cuarentena

**Qué cambia**:

- `recursos.estado = 'cuarentena'`
- `quarantined_at = NOW()`
- `quarantine_reason` ∈ {`caducidad`, `colision_semantica`, `manual`}
- `quarantine_grace_until = today + OBSOLESCENCE_GRACE_DAYS` (default 30)

**Qué NO cambia**:

- **Vectores en Qdrant — siguen ahí**. Tanto en `cerebro_recursos` como
  en `cerebro_chunks`.
- `contenido` y `resumen` en Postgres — siguen ahí.

**Qué ve el usuario**:

- UI `/quarantine` lista los recursos del tenant con
  `quarantine_reason`, `quarantined_at`, días restantes hasta
  `quarantine_grace_until`.
- Notificación in-app (tabla `notificaciones`) generada por el
  `notifier-worker` al consumir el evento `recurso.cuarentena`.
- Notificación Telegram si el tenant tiene bot configurado y
  `chat_id` cacheado (Redis).

**Qué puede hacer el usuario**:

| Acción | Endpoint | Efecto |
|--------|----------|--------|
| Rescatar (volver a activo) | `POST /resources/{id}/rescue` | `estado='activo'`, limpia `quarantine_*`, **recalcula `fecha_caducidad` según `volatilidad`** (baja=+365d, media=+180d, alta=+60d, dinamica=+30d). Emite outbox `recurso.rescatado`. |
| Expirar ya (saltarse la gracia) | `POST /resources/{id}/expire` | `estado='expirado'`. Útil cuando el usuario sabe que ya no es relevante. |
| Borrar definitivamente | `DELETE /resources/{id}` | Desliga del tenant. Si era el último → borrado global. Ver [Fase 6](#7-fase-6--borrado-definitivo). |
| No hacer nada | — | El cron transicionará a `expirado` cuando `quarantine_grace_until ≤ hoy`. |

**Implicación importante para el RAG**: durante la cuarentena, el
chat **no** ve el recurso (`get_active_resource_ids` filtra por
`estado='activo'`). Pero el vector sigue ocupando espacio en Qdrant.

---

## 6. Fase 5 — Expirado

**Cómo se llega**:

- Automático: `audit_cron` Fase B detecta `quarantine_grace_until ≤ hoy`.
- Manual: usuario pulsa "Expirar" en `/quarantine` (`POST /resources/{id}/expire`).

**Qué cambia**:

- `recursos.estado = 'expirado'`
- `updated_at = NOW()`

**Qué NO cambia**:

- `quarantined_at`, `quarantine_reason`, `quarantine_grace_until` —
  quedan como auditoría histórica.
- **Vectores en Qdrant — siguen ahí**. Igual que en cuarentena.
- `contenido` y `resumen` en Postgres — siguen ahí.

**Qué ve el usuario**:

- UI `/expired` lista los recursos expirados del tenant.
- Notificación in-app generada por el notifier-worker al consumir
  evento `recurso.expirado` con `motivo='gracia_agotada'`.

**Qué puede hacer el usuario**:

| Acción | Endpoint | Efecto |
|--------|----------|--------|
| Rescate fast-track | `POST /resources/{id}/rescue` | Mismo que en cuarentena. Permitido para `estado IN ('cuarentena','expirado')` — el usuario puede recuperar incluso un expirado si descubre que aún le interesa. |
| Borrar definitivamente | `DELETE /resources/{id}` | Ver [Fase 6](#7-fase-6--borrado-definitivo). |
| No hacer nada | — | El recurso queda en `expirado` indefinidamente. **El sistema no lo borra automáticamente**. Postgres + Qdrant siguen guardándolo. |

**Política implícita**: la única forma de liberar espacio en Qdrant es
el DELETE manual del usuario. No hay GC ni TTL automático. Si tu KB tiene
muchos expirados acumulados, considera implementar un cleanup periódico
(no existe hoy).

---

## 7. Fase 6 — Borrado definitivo

**Endpoint**: `DELETE /resources/{id}` (`src/api/main.py:565-602`).

**Función DB**: `delete_recurso_for_tenant(tenant_id, recurso_id)`
(`src/api/database.py:448-490`). Lógica:

1. `DELETE FROM usuario_recursos WHERE tenant_id=$1 AND recurso_id=$2`.
2. `SELECT COUNT(*) FROM usuario_recursos WHERE recurso_id=$2` — cuántos
   tenants siguen linkeados.
3. Si 0 → `DELETE FROM recursos WHERE id=$2` (FK CASCADE limpia también
   `grafo_relaciones`, `chunks_metadata`, `notificaciones`, etc.).
4. Retorna `{deleted_globally: bool}` para que el handler decida cómo
   limpiar Qdrant.

**Cleanup de Qdrant** (`src/api/main.py:578-602`, fuera de la
transacción SQL para no acoplar el commit a un servicio externo):

| Caso | Acción en Qdrant `cerebro_recursos` | Acción en `cerebro_chunks` |
|---|---|---|
| `deleted_globally=true` (último tenant) | `POST /collections/cerebro_recursos/points/delete` con filtro `recurso_id=$id` — borra el point del recurso global | Mismo filtro, borra todos los chunks |
| `deleted_globally=false` (solo este tenant) | `POST /collections/cerebro_recursos/points/delete` con `point_id = uuid_v5(recurso_id, tenant_id)` — el point per-tenant | Mismo cálculo por chunk_idx |

**Si Qdrant falla durante el cleanup**: el commit SQL ya pasó. El
recurso desaparece de Postgres pero el vector queda huérfano en Qdrant.
No hay GC automático. Vivirá hasta el próximo `DELETE` que active el
mismo filtro o hasta una limpieza manual.

**Tras el DELETE**:

- UI: el recurso desaparece de `/kb`, `/quarantine`, `/expired`.
- Chat: imposible recuperarlo (no hay rescate desde "borrado").
- Outbox: emite `recurso.eliminado` para notificar al frontend SSE.

---

## 8. Anexo A — Tabla "estado vs BDs vs RAG vs notificación"

| Estado | Postgres `recursos` | Qdrant `cerebro_recursos` | Qdrant `cerebro_chunks` | Aparece en RAG | Aparece en KB UI | Notificación emitida |
|---|---|---|---|---|---|---|
| `procesando` | Fila con `estado='procesando'`, sin `contenido` aún | Sin point todavía | Sin chunks | No | Sí (página `/ingest`) | `recurso.procesado` cuando embedder termina |
| `activo` | Fila completa | Point con payload tenant_id | Chunks por documento | **Sí** | Sí (`/kb`) | — |
| `cuarentena` | `estado='cuarentena'` + 3 campos quarantine_* | **Sin cambios** (point sigue) | **Sin cambios** | No | Sí (`/quarantine`) | `recurso.cuarentena` con motivo |
| `expirado` (archivo histórico) | `estado='expirado'`, `auto_archive_pending` se limpia | **Point inyectado** (auto-archive sí vectoriza) o sin cambios (expiración tradicional) | **Chunks inyectados** (auto-archive) o sin cambios | Sí con `include_archive=true` en `/chat` | Sí (`/expired`, copy "Archivo histórico") | `recurso.expirado` o `recurso.procesado` (auto-archive) |
| (borrado) | Sin fila si era el último tenant; sin link si quedan tenants | Point eliminado (global o per-tenant según caso) | Igual | No | No | `recurso.eliminado` |

**Lectura clave**: hay dos formas de llegar a `expirado` ahora:

- **Auto-archive** (migración 0007): el scraper detecta contenido pasado
  con valor archivístico alto y la `audit_policy` decide archivar
  directo. El recurso pasa por `procesando` (sí se vectoriza) y la
  ruta única `_build_chunks_from_text` deja chunks indexados → el
  toggle "Archivo ON" en chat puede recuperarlos.
- **Expiración tradicional**: cuarentena agotada o decisión manual. El
  recurso ya tenía sus chunks de la fase activa. La transición es solo
  metadata.

La única transición que toca Qdrant **eliminando** datos sigue siendo
**borrado definitivo**.

---

## 9. Anexo B — Endpoints, comandos y nombres de columna

### Endpoints HTTP relacionados con el ciclo

| Método + Path | Auth | Función DB | Notas |
|---|---|---|---|
| `POST /ingest` | JWT user | scraper async | Devuelve 202, trabajo en cola |
| `POST /resources/{id}/rescue` | JWT + CSRF | `rescue_recurso` | Sirve para cuarentena y expirado |
| `POST /resources/{id}/quarantine` | JWT + CSRF | `quarantine_recurso` | Solo desde `activo` o `procesando` |
| `POST /resources/{id}/expire` | JWT + CSRF | `expire_recurso` | Salta el período de gracia |
| `DELETE /resources/{id}` | JWT + CSRF | `delete_recurso_for_tenant` | Limpia Qdrant si era el último tenant |
| `POST /resources/audit-now` | JWT + CSRF | `run_audit_cron` | Rate-limit 5/min/tenant |
| `POST /admin/audit-cron` | `X-Admin-Token` | `run_audit_cron` | Para n8n cron |
| `GET /resources/quarantine` | JWT | `list_quarantine` | Lista para UI `/quarantine` |
| `GET /resources/expired` | JWT | `list_expired` | Lista para UI `/expired` |

### Columnas relevantes de `recursos`

| Columna | Tipo | Propósito |
|---|---|---|
| `id` | UUID | PK |
| `url`, `url_hash` | TEXT, CHAR(64) | hash sha256 para deduplicación global |
| `estado` | VARCHAR(20) | `activo`/`cuarentena`/`expirado`/`procesando` (CHECK) |
| `volatilidad` | VARCHAR(20) | `baja`/`media`/`alta`/`dinamica` (CHECK) |
| `fecha_caducidad` | DATE | Cuándo vence — alimenta cron Fase A |
| `quarantined_at` | TIMESTAMPTZ | Cuándo entró en cuarentena |
| `quarantine_reason` | VARCHAR(50) | `caducidad`/`colision_semantica`/`manual`/`evento_pasado` (CHECK, migración 0006) |
| `quarantine_grace_until` | DATE | Fin del período de gracia — alimenta cron Fase B |
| `contenido` | TEXT | Texto completo scrapeado (fuente de chunking) |
| `resumen` | TEXT | Resumen del LLM (2-3 frases) |
| `embedding_version` | INTEGER | Por si se re-embebe masivamente |
| `temporal_class` | VARCHAR(20) | `evento`/`referencia`/`evergreen` (CHECK, migración 0006) |
| `valor_archivistico` | VARCHAR(20) | `alto`/`medio`/`nulo` (CHECK, migración 0006) |
| `fecha_evento` | DATE | Fecha del evento descrito; puede ser pasada (migración 0006) |
| `auto_archive_pending` | BOOLEAN | Si true, el embedder transiciona a `expirado` (no `activo`) tras vectorizar (migración 0007) |

### Columnas relevantes de `usuarios`

| Columna | Tipo | Propósito |
|---|---|---|
| `audit_policy` | JSONB | 6 keys con la decisión por celda `temporal_class × valor_archivistico` para contenido pasado. Migración 0007 (sustituye al enum `audit_strictness` previo). |

### Variables de entorno

| Var | Default | Significado |
|---|---|---|
| `OBSOLESCENCE_GRACE_DAYS` | `30` | Días entre cuarentena y expirado |
| `AUDIT_CRON_TOKEN` | (sin default) | Token admin para `/admin/audit-cron` |
| `REUSE_FRESHNESS_MARGIN_DAYS` | `7` | Margen mínimo de caducidad para reuso cross-tenant |

### Eventos outbox

| `evento_tipo` | Lo emite | Lo consume |
|---|---|---|
| `recurso.procesado` | `save_with_outbox` tras INSERT | **embedder** (whitelist), notifier (silencioso) |
| `recurso.reusado` | `emit_reuse_event` cuando reuso cross-tenant | **embedder** (whitelist, copia vector) |
| `recurso.cuarentena` | `audit_cron`, `quarantine_recurso`, colisión semántica | notifier (in-app + Telegram), frontend (SSE) |
| `recurso.expirado` | `audit_cron` Fase B, `expire_recurso` | notifier, frontend |
| `recurso.rescatado` | `rescue_recurso` | notifier, frontend |
| `recurso.eliminado` | `delete_recurso_for_tenant` | frontend (SSE) |
