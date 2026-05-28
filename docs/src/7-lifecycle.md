<div align="center">
  <img src="/logo-light.png" alt="Logo" width="80" height="80" class="light-only">
  <img src="/logo-dark.png" alt="Logo" width="80" height="80" class="dark-only">


# Ciclo de vida de un recurso — LinkAnvil

</div>

> Referencia canónica del recorrido completo de una URL desde que el usuario la
> añade hasta que desaparece del sistema. Documenta todas las transiciones de
> estado, qué BD se toca en cada paso, y qué controla el usuario vs qué controla
> el sistema.
>
> Para una vista narrativa con ejemplos, ver
> [`9-ejemplo_flujo.md`](./9-ejemplo_flujo.md). Para los prompts
> que el LLM ejecuta en cada fase, ver [`7-prompts.md`](./7-prompts.md).

---

## Tabla de contenidos

1. [Vista general — diagrama de estados](#1-vista-general--diagrama-de-estados)
2. [Fase 1 — Ingesta](#2-fase-1--ingesta)
3. [Fase 2 — Vida activa](#3-fase-2--vida-activa)
4. [Fase 3 — Detección de obsolescencia](#4-fase-3--detección-de-obsolescencia)
   - 4.1 [Camino temporal (cron + botón manual)](#41-camino-temporal-cron--botón-manual)
   - 4.2 [Camino semántico (colisión durante embedding)](#42-camino-semántico-colisión-durante-embedding)
   - 4.3 [Camino manual (usuario manda a cuarentena)](#43-camino-manual-usuario-manda-a-cuarentena)
   - 4.4 [Camino scrape-bloqueado (anti-bot)](#44-camino-scrape-bloqueado-anti-bot)
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
                  │  procesando   │ ◀───── el scraper inserta un placeholder
                  └───────┬───────┘        en el outbox transaccional
                          │
                          │ embedder completa
                          │ (Qdrant + chunks)
                          ├──────────────────────┐
                          │ auto-archivado       │
                          │ desactivado          │ activado
                          ▼                      ▼
                  ┌───────────────┐      ┌───────────────┐
       ┌────────► │    activo     │ ◀──┐ │   expirado    │ ◀──┐
       │          └───────┬───────┘    │ └───────┬───────┘    │
       │                  │            │         │            │
       │                  │ rescate    │         │ rescate    │
       │                  │            │         │            │
       │   ┌──────────────┼────────────┘         │            │
       │   │   audit-cron / audit-now            │            │
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
       │          │ (archivo hist.)│ ← chunks indexados        │
       │          └───────┬───────┘   en Qdrant para Archivo ON│
       │                  │                                    │
       │                  │ DELETE /resources/{id}             │
       │                  ▼                                    │
       │          ┌───────────────┐                            │
       └──────────│   (borrado)   │ ← borrado en PG + cleanup Qdrant
                  └───────────────┘
```

**Cuatro estados válidos** que un recurso puede tener:

| Estado | Significado | Visible en RAG |
|--------|-------------|----------------|
| `procesando` | Recién insertado, el embedder aún no ha terminado | No |
| `activo` | Listo para usar en la base de conocimiento principal | **Sí** (por defecto) |
| `cuarentena` | En período de gracia, recuperable | No |
| `expirado` *(UI: **Archivado**)* | Archivo histórico | Solo con el toggle "Archivo ON" del chat (`include_archive=true`) |

`expirado` significa **archivo histórico** y no descarte (la UI lo etiqueta como **Archivado**; el valor interno de la columna sigue siendo `'expirado'` por compatibilidad con migraciones, eventos y endpoints existentes). Se llega por dos rutas:

- **Auto-archive** del scraper para contenido pasado con valor archivístico
  alto (la política de auditoría del tenant lo decide). Pasa por
  `procesando` para vectorizarse y queda directamente en `expirado`.
- **Expiración tras gracia** (cron temporal, colisión semántica o decisión
  manual). El contenido queda como archivo recuperable.

El toggle "Archivo ON" del chat amplía el RAG para incluir recursos
`expirado` sin penalizar el score, enviando `include_archive=true` en el
payload del chat.

---

## 2. Fase 1 — Ingesta

**Cómo arranca**: `POST /ingest` con la URL y, opcionalmente, un
`tenant_id` (en el caso del bot de Telegram). La API encola el trabajo
en la cola `q.url.ingesta` de RabbitMQ y devuelve `202 Accepted`
inmediatamente — toda la ingesta es asíncrona.

**Pipeline**:

1. **Scraper** (cola `q.url.ingesta`):
   - Descarga la URL con una estrategia HTTP básica; si la página
     bloquea o requiere JS, cae al modo Stealth Playwright.
   - **Pre-extracción determinista (sin LLM)**: dos librerías leen el
     HTML estructurado antes de gastar tokens:
     - `htmldate.find_date(html)` — fecha de publicación (meta-tags,
       OG, JSON-LD, paths `/YYYY/MM/DD/`).
     - `extruct.extract(html)` — JSON-LD (`@type`, `datePublished`,
       `author`, `keywords`), OpenGraph (`og:type`, `og:description`,
       `article:published_time`), Schema.org microdata y Dublin Core.
     - Heurística de coherencia: si la URL delata el año del documento
       (`BOE-A-2010-…`, `/2024/03/`) y `htmldate` da otro año, se
       sobreescribe a `{año_url}-01-01`.
   - Limpia el HTML y extrae texto (≤ 32 000 caracteres). El texto
     limpio puede empezar con dos bloques sintéticos:
     - `[METADATA DEL AUTOR]` (descripción, fecha, autor, categorías,
       tags) cuando el HTML los tiene en `<meta>` o OG.
     - `[OBSOLESCENCIA DETECTADA — extractos del documento]` con
       párrafos del HTML crudo que contienen marcadores de derogación
       (legales, RFCs, lifecycle de proyectos como "Moved to",
       "Project archived"). Filtro anti-ruido evita contaminación con
       blobs JSON de SPAs.
   - Llama a LiteLLM con el prompt de extracción de metadatos (ver
     [`7-prompts.md`](./7-prompts.md) §2.1) **inyectando el bloque
     `[PISTAS ESTRUCTURADAS DEL HTML]`** con los datos deterministas
     como hints (no órdenes). Obtiene `title`, `summary`, `category`,
     `keywords`, `volatility_score`, `estimated_useful_life_days`,
     `expiration_date`, `event_date`, `temporal_class` y
     `valor_archivistico`. Para normativa (BOE/decretos/sentencias/RFCs)
     el prompt instruye explícitamente a extraer la fecha de
     disposición o el año del identificador (p. ej.
     `BOE-A-2010-9269` → 2010-01-01).
   - **Merge defensivo**: si el LLM devuelve `null` en `event_date` o
     un array vacío en `keywords`, el campo se rellena con el valor
     determinista. Si el LLM falla por completo (3 retries), el
     fallback hard-coded también se enriquece con los datos
     pre-extraídos.
   - **Reuso cross-tenant**: si la URL ya existe globalmente como
     `activo` y su caducidad está suficientemente lejos, se omite el
     scrape y el LLM, y se emite un evento `recurso.reusado` para que
     el embedder copie el vector del tenant origen al nuevo tenant.
   - **Placeholder previo**: inserta una fila con `estado='procesando'`
     antes del scrape, para que la UI tenga feedback inmediato.
   - **Persistencia transaccional**: en una sola transacción se insertan
     el recurso, el link tenant ↔ recurso, y el evento
     `recurso.procesado` en el outbox. Atómico.

2. **Decisión al ingestar**:

   El LLM produce tres campos adicionales:
   `temporal_class ∈ {evento, referencia, evergreen}`,
   `valor_archivistico ∈ {alto, medio, nulo}`, y `event_date` (fecha del
   evento descrito). Con esos campos y la `audit_policy` del tenant
   (JSONB con seis claves) se decide el estado inicial:

   - **`evergreen`** o **fecha futura** (no pasada): por defecto
     `procesando → activo` tras el embedder. Para un `evento` futuro se
     calcula `fecha_caducidad` con el `expiration_date` del LLM o, como
     fallback, `today + useful_life_days`. Para `referencia` y
     `evergreen`, `fecha_caducidad` queda `NULL`.
   - **Fecha pasada (no evergreen)**: se compone la clave
     `{evento_pasado|referencia_pasada}_{alto|medio|nulo}` y se lee
     `audit_policy[clave]`. Resultados posibles:
     - `"activo"` → activo en la KB, con caducidad `NULL`.
     - `"cuarentena"` → cuarentena con `quarantine_reason='evento_pasado'`,
       grace period 30 días.
     - `"expirado"` → auto-archivado: el embedder vectoriza y el recurso
       transiciona directamente a `expirado` (archivo histórico).

   **Tres presets canónicos** (la UI los precarga en `/profile`):

   | Preset | evento_pasado: alto/medio/nulo | referencia_pasada: alto/medio/nulo |
   |---|---|---|
   | Estricto | cuarentena / cuarentena / cuarentena | cuarentena / cuarentena / cuarentena |
   | **Equilibrado (default)** | expirado / cuarentena / cuarentena | expirado / cuarentena / cuarentena |
   | Permisivo | expirado / cuarentena / cuarentena | expirado / activo / cuarentena |

   El usuario puede partir de un preset y ajustar celdas individuales —
   no hay diferencia técnica entre "estoy en preset X" y "tengo policy
   custom"; solo se guarda el JSONB resultante.

3. **Outbox publisher**: cada segundo lee los eventos pendientes del
   outbox, los publica al exchange fanout `cerebro.procesamiento` y los
   marca como procesados.

4. **Embedder** (cola `q.recurso.embedder`):
   - Filtro **whitelist** por tipo de evento: solo procesa
     `recurso.procesado` y `recurso.reusado`. Esto evita que el
     embedder reaccione a eventos del ciclo de obsolescencia.
   - Genera el embedding de título + summary + keywords con LiteLLM
     (modelo `cerebro-embeddings`).
   - Inserta el point en la colección Qdrant `cerebro_recursos` con un
     payload que incluye `tenant_id` (usado como filtro de RAG).
   - Hace chunking del contenido y embedding por chunk en la colección
     `cerebro_chunks` (es la colección que consume el RAG).
   - Calcula colisiones semánticas; si encuentra duplicados, dispara el
     [camino semántico](#42-camino-semántico-colisión-durante-embedding).
   - Transiciona el recurso a `activo`, pero **solo si su estado actual
     es `procesando`**. Si el recurso ya estaba en cuarentena o
     expirado, el embedder no lo resucita.

**Resultado**: recurso en `activo`, vectores en dos colecciones de
Qdrant. El embedder emite además un evento `recurso.activado` (rama
normal y rama reused) que el notifier convierte en notificación
in-app + SSE + Telegram con el copy "📚 Tu recurso ... se ha añadido a
tu Base de Conocimiento". Sin este evento, la primera entrada de un
recurso a la BC pasaba silenciosa — solo las transiciones de
cuarentena/archivado/rescate notificaban.

---

## 3. Fase 2 — Vida activa

El estado `activo` significa que el recurso es candidato a RAG:

- **Chat con RAG** (`POST /chat`):
  - Embebe la pregunta del usuario.
  - Busca en `cerebro_chunks` con filtro `tenant_id = $user_tenant`.
  - Filtra los hits resultantes por estado: solo sobreviven los recursos
    cuyo estado es `activo` (o `expirado` si el chat se invoca con
    `include_archive=true`).
  - Inyecta los chunks supervivientes como `context_block` en el system
    prompt (ver [`7-prompts.md`](./7-prompts.md) §3.1).
- **KB UI** (`/kb`):
  - Lista solo recursos `activo` del tenant.
  - Los badges del sidebar `Cuarentena (N)` y `Expirados (N)` se
    actualizan vía SSE cuando hay transiciones.

**Mientras está activo**:

- La `volatilidad` determina cuándo se recalcula la caducidad al
  rescatar (`baja`=365 días, `media`=180, `alta`=60, `dinamica`=30).
- `embedding_version` permite re-embebido masivo si se cambia de modelo.
- La tabla join `usuario_recursos` lleva el track de qué tenants tienen
  linkeado este recurso global.

---

## 4. Fase 3 — Detección de obsolescencia

Cuatro caminos llevan a `cuarentena`. Son **independientes** y pueden
disparar sobre el mismo recurso (idempotente — el primero gana).

### 4.1 Camino temporal (cron + botón manual)

**Mecánica**: el job de auditoría ejecuta dos `UPDATE` SQL atómicos.
Sus filtros son idempotentes: llamarlo N veces produce el mismo
resultado que llamarlo una vez.

```sql
-- Fase A: caducidad → cuarentena
UPDATE recursos
SET estado = 'cuarentena',
    quarantined_at = NOW(),
    quarantine_reason = 'caducidad',
    quarantine_grace_until = (NOW() + OBSOLESCENCE_GRACE_DAYS * INTERVAL '1 day')::DATE,
    updated_at = NOW()
WHERE estado = 'activo'
  AND temporal_class = 'evento'         -- defensa en profundidad
  AND fecha_caducidad IS NOT NULL
  AND fecha_caducidad <= NOW()::DATE;

-- Fase B: gracia agotada → expirado
UPDATE recursos
SET estado = 'expirado', updated_at = NOW()
WHERE estado = 'cuarentena'
  AND quarantine_grace_until IS NOT NULL
  AND quarantine_grace_until <= NOW()::DATE;
```

El filtro `temporal_class = 'evento'` actúa como defensa en
profundidad: si por error una `referencia` o `evergreen` quedara con
`fecha_caducidad` rellena, el cron no la tocaría.

**Disparadores**:

| Disparador | Quién lo invoca | Auth | Rate-limit |
|---|---|---|---|
| Cron nocturno | n8n workflow `linkanvil — audit cron diario` (cron `0 3 * * *`, 03:00 UTC) | `X-Admin-Token: $AUDIT_CRON_TOKEN` | n/a |
| Botón "Revisar caducidades" en `/kb` | Usuario autenticado | JWT del usuario + CSRF | 5/min por tenant (Redis `rl:audit:{tenant_id}`) |
| Llamada CLI / Antigravity | Operador | `X-Admin-Token` | n/a |

**Endpoints**:

- `POST /admin/audit-cron` — interfaz para el cron de n8n (token admin).
- `POST /resources/audit-now` — interfaz para el botón UI (auth de usuario normal).

Ambos ejecutan el mismo pipeline y devuelven
`{trace_id, cuarentenados, expirados}`.

**Demo intra-sesión**: las sesiones demo aceleran el ciclo a 15 minutos
operando con precisión `TIMESTAMPTZ` en lugar de `DATE`. Reusan el mismo
pipeline de outbox y las mismas transiciones (`'activo' → 'cuarentena'`
en Fase A; `IN ('activo','cuarentena') → 'expirado'` en Fase B).

**`fecha_caducidad IS NULL` → invisible para el cron**. Es un escape
hatch del que se aprovechan tres flujos hoy:

- `temporal_class='referencia'` y `temporal_class='evergreen'` siempre
  nacen con `fecha_caducidad = NULL`.
- Cualquier recurso pasado que la `audit_policy` mande a `cuarentena` o
  `expirado` se inserta con `fecha_caducidad = NULL` — el ciclo temporal
  cede el control al ciclo policy-driven.
- El cron sigue sirviendo para el caso clásico: un `evento` futuro cuya
  fecha vence.

### 4.2 Camino semántico (colisión durante embedding)

Cuando se ingesta una URL nueva y el embedder encuentra alta similitud
con un recurso preexistente, llama al prompt **clasificador semántico**
(ver [`7-prompts.md`](./7-prompts.md) §2.2; modelo `cerebro-lite`,
temperatura 0) para tipificar la relación. Si el LLM responde
`VUELVE_OBSOLETO` o `CONTRADICE`, el recurso **antiguo** pasa a
cuarentena con `quarantine_reason='colision_semantica'` y se emite un
evento `recurso.cuarentena`.

Es el caso típico de "LangChain v0.1 → cuarentena cuando llega v0.2",
descrito en [`9-ejemplo_flujo.md`](./9-ejemplo_flujo.md) Fase 3.

### 4.3 Camino manual (usuario manda a cuarentena)

Desde el modal de detalle del recurso en `/kb`, el usuario pulsa
"Mandar a cuarentena":

- Endpoint: `POST /resources/{id}/quarantine`.
- Efecto: `estado='cuarentena'`, `quarantine_reason='manual'`,
  `quarantine_grace_until = today + 30d`.
- Emite un evento `recurso.cuarentena` por cada tenant que tenga
  linkeado el recurso.

### 4.4 Camino scrape-bloqueado (anti-bot)

Si el scraper recibe una página de bloqueo anti-bot y no puede extraer
el contenido, el recurso entra en cuarentena con
`quarantine_reason='manual'` y gracia de 30 días. Se reutiliza el motivo
`manual` porque el `CHECK` actual sobre `quarantine_reason` no contempla
un valor dedicado para scrape bloqueado.

---

## 5. Fase 4 — Cuarentena

**Qué cambia**:

- `estado = 'cuarentena'`.
- `quarantined_at = NOW()`.
- `quarantine_reason ∈ {caducidad, colision_semantica, manual, evento_pasado}`.
- `quarantine_grace_until = today + OBSOLESCENCE_GRACE_DAYS` (default 30).

**Qué NO cambia**:

- **Vectores en Qdrant — siguen ahí**, tanto en `cerebro_recursos` como
  en `cerebro_chunks`.
- `contenido` y `resumen` en Postgres — siguen ahí.

**Qué ve el usuario**:

- La UI `/quarantine` lista los recursos del tenant con su motivo,
  `quarantined_at` y días restantes hasta `quarantine_grace_until`.
- Notificación in-app generada por el notifier al consumir el evento
  `recurso.cuarentena`.
- Notificación de Telegram si el tenant tiene bot configurado y su
  `chat_id` cacheado en Redis.

**Qué puede hacer el usuario**:

| Acción | Endpoint | Efecto |
|--------|----------|--------|
| Rescatar (volver a activo) | `POST /resources/{id}/rescue` | `estado='activo'`, limpia los campos `quarantine_*` y **recalcula `fecha_caducidad` según `volatilidad`** (baja=+365d, media=+180d, alta=+60d, dinamica=+30d). Emite `recurso.rescatado` **sólo para el tenant que rescata** (a diferencia de cuarentena/expire, que emiten un evento por cada tenant linkeado). |
| Expirar ya (saltarse la gracia) | `POST /resources/{id}/expire` | `estado='expirado'`. Útil cuando el usuario sabe que ya no es relevante. |
| Borrar definitivamente | `DELETE /resources/{id}` | Desliga del tenant. Si era el último → borrado global. Ver [Fase 6](#7-fase-6--borrado-definitivo). |
| No hacer nada | — | El cron transicionará a `expirado` cuando `quarantine_grace_until ≤ hoy`. |

**Implicación importante para el RAG**: durante la cuarentena el chat
**no** ve el recurso (se filtra por `estado='activo'`). Pero el vector
sigue ocupando espacio en Qdrant.

---

## 6. Fase 5 — Expirado

**Cómo se llega**:

- Automático: Fase B del cron de auditoría cuando
  `quarantine_grace_until ≤ hoy`.
- Manual: el usuario pulsa "Expirar" en `/quarantine`
  (`POST /resources/{id}/expire`).
- Auto-archive: el embedder transiciona directamente desde `procesando`
  cuando el flag interno de auto-archivado está activo.

**Qué cambia**:

- `estado = 'expirado'`.
- `updated_at = NOW()`.

**Qué NO cambia**:

- `quarantined_at`, `quarantine_reason` y `quarantine_grace_until`
  quedan como auditoría histórica.
- **Vectores en Qdrant — siguen ahí**, igual que en cuarentena.
- `contenido` y `resumen` en Postgres — siguen ahí.

**Qué ve el usuario**:

- La UI `/expired` lista los recursos expirados del tenant.
- Notificación in-app generada por el notifier al consumir
  `recurso.expirado` con motivo `gracia_agotada`, `manual` o
  `auto_archive`.

**Qué puede hacer el usuario**:

| Acción | Endpoint | Efecto |
|--------|----------|--------|
| Rescate fast-track | `POST /resources/{id}/rescue` | Igual que en cuarentena. Permitido para `estado IN ('cuarentena','expirado')` — el usuario puede recuperar incluso un expirado si descubre que aún le interesa. |
| Borrar definitivamente | `DELETE /resources/{id}` | Ver [Fase 6](#7-fase-6--borrado-definitivo). |
| No hacer nada | — | El recurso queda en `expirado` indefinidamente. **El sistema no lo borra automáticamente**; Postgres y Qdrant siguen guardándolo. |

**Política implícita**: la única forma de liberar espacio en Qdrant es
el `DELETE` manual del usuario. No hay GC ni TTL automático. Si la KB
acumula muchos expirados, considera un cleanup periódico (actualmente no
soportado de forma nativa).

---

## 7. Fase 6 — Borrado definitivo

**Endpoint**: `DELETE /resources/{id}`.

Lógica:

1. Se elimina el link de `usuario_recursos` para `(tenant_id, recurso_id)`.
2. Se cuenta cuántos tenants siguen linkeados.
3. Si no queda ninguno → se borra la fila de `recursos`. La cascada de
   claves foráneas limpia automáticamente `grafo_relaciones`,
   `chunks_metadata`, `notificaciones`, etc.
4. La respuesta indica si el borrado fue global (`deleted_globally`) o
   solo per-tenant, para decidir cómo limpiar Qdrant.

**Cleanup de Qdrant** (fuera de la transacción SQL, para no acoplar el
commit a un servicio externo):

| Caso | Acción en `cerebro_recursos` | Acción en `cerebro_chunks` |
|---|---|---|
| `deleted_globally=true` (último tenant) | `POST /collections/cerebro_recursos/points/delete` con filtro `recurso_id=$id` — borra el point del recurso global | Mismo filtro, borra todos los chunks |
| `deleted_globally=false` (solo este tenant) | `POST /collections/cerebro_recursos/points/delete` con `point_id = uuid_v5(recurso_id, tenant_id)` — el point per-tenant | Mismo cálculo por `chunk_idx` |

**Si Qdrant falla durante el cleanup**: el commit SQL ya pasó. El
recurso desaparece de Postgres pero el vector queda huérfano en Qdrant.
No hay GC automático; el vector vivirá hasta que un `DELETE` posterior
active el mismo filtro o hasta una limpieza manual.

**Tras el `DELETE`**:

- UI: el recurso desaparece de `/kb`, `/quarantine` y `/expired`.
- Chat: imposible recuperarlo (no hay rescate desde "borrado").
- Outbox: se emite `recurso.eliminado` para notificar al frontend
  vía SSE.

---

## 8. Anexo A — Tabla "estado vs BDs vs RAG vs notificación"

| Estado | Postgres `recursos` | Qdrant `cerebro_recursos` | Qdrant `cerebro_chunks` | Aparece en RAG | Aparece en KB UI | Notificación emitida |
|---|---|---|---|---|---|---|
| `procesando` | Fila con `estado='procesando'`, sin `contenido` aún | Sin point todavía | Sin chunks | No | Sí (página `/ingest`) | `recurso.procesado` cuando el embedder termina |
| `activo` | Fila completa | Point con payload `tenant_id` | Chunks por documento | **Sí** | Sí (`/kb`) | — |
| `cuarentena` | `estado='cuarentena'` + campos `quarantine_*` | **Sin cambios** (point sigue) | **Sin cambios** | No | Sí (`/quarantine`) | `recurso.cuarentena` con motivo |
| `expirado` (archivo histórico) | `estado='expirado'`, el flag interno de auto-archivado se limpia | **Point inyectado** (auto-archive vectoriza) o sin cambios (expiración tradicional) | **Chunks inyectados** (auto-archive) o sin cambios | Sí con `include_archive=true` en `/chat` | Sí (`/expired`, copy "Archivo histórico") | `recurso.expirado` con `motivo='gracia_agotada'` (cron Fase B), `motivo='manual'` (`expire`) o `motivo='auto_archive'` (embedder tras la transición) |
| (borrado) | Sin fila si era el último tenant; sin link si quedan tenants | Point eliminado (global o per-tenant según caso) | Igual | No | No | `recurso.eliminado` |

**Lectura clave**: hay dos formas de llegar a `expirado`:

- **Auto-archive**: el scraper detecta contenido pasado con valor
  archivístico alto y la `audit_policy` decide archivar directo. El
  recurso pasa por `procesando` (sí se vectoriza) y los chunks quedan
  indexados, por lo que el toggle "Archivo ON" en chat puede
  recuperarlos.
- **Expiración tradicional**: cuarentena agotada o decisión manual. El
  recurso ya tenía sus chunks de la fase activa. La transición es solo
  metadata.

La única transición que toca Qdrant **eliminando** datos sigue siendo
**borrado definitivo**.

---

## 9. Anexo B — Endpoints, comandos y nombres de columna

### Endpoints HTTP relacionados con el ciclo

| Método + Path | Auth | Notas |
|---|---|---|
| `POST /ingest` | JWT user | Devuelve `202`, trabajo en cola |
| `POST /resources/{id}/rescue` | JWT + CSRF | Sirve para cuarentena y expirado |
| `POST /resources/{id}/quarantine` | JWT + CSRF | Solo desde `activo` o `procesando` |
| `POST /resources/{id}/expire` | JWT + CSRF | Salta el período de gracia |
| `DELETE /resources/{id}` | JWT + CSRF | Limpia Qdrant si era el último tenant |
| `POST /resources/audit-now` | JWT + CSRF | Rate-limit 5/min por tenant |
| `POST /admin/audit-cron` | `X-Admin-Token` | Para n8n cron |
| `GET /resources/kb` | JWT | Lista los recursos `activo` del tenant (+ seed en demo). Acepta `?count_only=true` → `{count}` (lo usa el badge "Base de Conocimiento" del sidebar). |
| `GET /resources/quarantine` | JWT | Lista para UI `/quarantine`. Acepta `?count_only=true` → `{count}` (lo usa el badge del sidebar). |
| `GET /resources/expired` | JWT | Lista para UI `/expired`. Acepta `?count_only=true` → `{count}` (lo usa el badge del sidebar). |

### Columnas relevantes de `recursos`

| Columna | Tipo | Propósito |
|---|---|---|
| `id` | UUID | PK |
| `url`, `url_hash` | TEXT, CHAR(64) | Hash sha256 para deduplicación global |
| `estado` | VARCHAR(20) | `activo` / `cuarentena` / `expirado` / `procesando` (CHECK) |
| `volatilidad` | VARCHAR(20) | `baja` / `media` / `alta` / `dinamica` (CHECK) |
| `fecha_caducidad` | DATE | Cuándo vence — alimenta Fase A del cron |
| `quarantined_at` | TIMESTAMPTZ | Cuándo entró en cuarentena |
| `quarantine_reason` | VARCHAR(50) | `caducidad` / `colision_semantica` / `manual` / `evento_pasado` (CHECK) |
| `quarantine_grace_until` | DATE | Fin del período de gracia — alimenta Fase B del cron |
| `contenido` | TEXT | Texto completo scrapeado (fuente del chunking) |
| `resumen` | TEXT | Resumen del LLM (2–3 frases) |
| `embedding_version` | INTEGER | Por si se re-embebe masivamente |
| `temporal_class` | VARCHAR(20) | `evento` / `referencia` / `evergreen` (CHECK) |
| `valor_archivistico` | VARCHAR(20) | `alto` / `medio` / `nulo` (CHECK) |
| `fecha_evento` | DATE | Fecha del evento descrito; puede ser pasada |
| `auto_archive_pending` | BOOLEAN | Si está activo, el embedder transiciona a `expirado` (no `activo`) tras vectorizar |

### Columnas relevantes de `usuarios`

| Columna | Tipo | Propósito |
|---|---|---|
| `audit_policy` | JSONB | Seis claves con la decisión por celda `temporal_class × valor_archivistico` para contenido pasado |

### Variables de entorno

| Variable | Default | Significado |
|---|---|---|
| `OBSOLESCENCE_GRACE_DAYS` | `30` | Días entre cuarentena y expirado |
| `AUDIT_CRON_TOKEN` | (sin default) | Token admin para `POST /admin/audit-cron` |
| `REUSE_FRESHNESS_MARGIN_DAYS` | `7` | Margen mínimo de caducidad para reuso cross-tenant |

### Eventos outbox

| `evento_tipo` | Lo emite | Lo consume |
|---|---|---|
| `recurso.procesado` | La transacción de ingesta tras el `INSERT` | **embedder** (whitelist), notifier (silencioso) |
| `recurso.activado` | El embedder tras la transición `procesando → activo` (rama normal y rama reused) | notifier (in-app + Telegram), frontend (SSE) |
| `recurso.reusado` | El emisor de reuso cuando aplica reuso cross-tenant | **embedder** (whitelist, copia vector) |
| `recurso.cuarentena` | Fase A del cron, cuarentena manual, cuarentena por scrape bloqueado, colisión semántica | notifier (in-app + Telegram), frontend (SSE) |
| `recurso.expirado` (motivos `gracia_agotada` / `manual` / `auto_archive`) | Fase B del cron (`gracia_agotada`), `expire` manual (`manual`), auto-archive del embedder (`auto_archive`) | notifier, frontend |
| `recurso.rescatado` | `rescue` (sólo para el tenant que rescata) | notifier, frontend |
| `recurso.eliminado` | `DELETE /resources/{id}` | frontend (SSE) |

> Nota: `motivo='caducidad'` aparece sólo en `recurso.cuarentena`
> (cuando la Fase A del cron mueve un recurso por vencimiento). **No
> existe** `recurso.expirado` con motivo `caducidad`; cuando la gracia
> se agota, el motivo del `recurso.expirado` es `gracia_agotada`.

### Mapping `motivo` → copy del notifier

El notifier traduce `(evento_tipo, motivo)` a un mensaje humano que va
al feed in-app, al canal Redis `resources:{tenant}` (SSE) y al bot de
Telegram del tenant si está configurado.

| evento_tipo | motivo | Copy humano |
|---|---|---|
| `recurso.cuarentena` | `caducidad` | "ha caducado" |
| `recurso.cuarentena` | `colision_semantica` | "ha sido reemplazado por contenido más reciente" |
| `recurso.cuarentena` | `manual` | "se marcó manualmente" |
| `recurso.cuarentena` | `evento_pasado` | "tiene fecha pasada y requiere revisión" |
| `recurso.expirado` | `gracia_agotada` | "agotó su período de gracia" |
| `recurso.expirado` | `auto_archive` | Etiqueta corta: "tiene fecha pasada y se archivó automáticamente". Copy completo en Telegram: "se archivó automáticamente al detectar valor archivístico alto. Recuperable en el chat con el toggle Archivo ON." |
| `recurso.activado` | — | "se ha añadido a tu Base de Conocimiento" |
| `recurso.rescatado` | — | "vuelve a estar activo" |

El icono en la campana también diferencia: 📚 para `recurso.activado` (entrada nueva a la BC), 📦 para `auto_archive`, ⚠️ para cuarentena, 🗑 para `gracia_agotada`, ♻️ para rescate.

### Pipeline de propagación de la notificación

```
Outbox event (recurso.X)
       │
       ▼
cerebro-outbox  ── fanout exchange `cerebro.procesamiento`
       │                                  │
       │                                  ├─→ embedder (whitelist filtra)
       │                                  │
       ▼                                  ▼
cerebro-notifier (q.notifications)    Otros consumidores
       │
       ├─→ INSERT cerebro.notificaciones (feed in-app)
       ├─→ Redis PUBLISH `resources:{tenant}` (SSE → bell + sidebar badges)
       └─→ Telegram API (si `telegram_bot_active = true` para el tenant)
```

**Doble vía de propagación al frontend**: la API también expone
`GET /notifications?limit=20`, que el bell consulta al montar y cada
5 minutos como red de seguridad. El SSE es la vía instantánea; el
polling es fallback si el `EventSource` se cae sin que el navegador
auto-reconecte.
