# Sesión de operaciones — 2026-05-17

Auditoría reactiva sobre los bugs reportados en el chat y el ciclo de
obsolescencia de recursos. Cinco fixes desplegados y verificados en
producción (`192.168.1.19`). Este documento es la referencia para todo el
trabajo de hoy: causa raíz, ubicación, fix, verificación y bibliografía
de seguimiento.

---

## Resumen ejecutivo

| # | Bug | Severidad | Componente | Estado |
|---|-----|-----------|------------|--------|
| 1 | Chat se queda "pensando" con RAG | CRÍTICO | `src/api/main.py::chat` | RESUELTO |
| 2 | Token expirado no redirige a login | ALTO | Auth flow completo | RESUELTO |
| 3 | Botones de copiar no funcionan en HTTP | MEDIO | Frontend | RESUELTO |
| 4 | Cron de audit fallando 5+ días seguidos | ALTO | `infra/n8n/workflows/audit_cron_daily.json` | RESUELTO |
| 5 | Recursos vencidos vuelven a `activo` (5 min después de cuarentena) | CRÍTICO | `src/data/embedder_worker.py` | RESUELTO |

---

## Bug 1 — Chat se queda colgado con RAG activo

### Causa raíz

Variable shadowing en Python en `src/api/main.py`:

```python
litellm_headers = {"Authorization": f"Bearer {LITELLM_KEY}", ...}  # antes era `h`

if req.use_rag and hits:
    for hit in hits:           # antes era `for h in hits:` → pisaba `h`
        p = hit.get("payload") or {}
        ...

async def _stream():
    async with client.stream("POST", url, headers=litellm_headers, ...) as resp:
```

Con RAG activo y hits existentes, `h` quedaba reasignada al último hit de
Qdrant (dict con `id` int, `version` int, etc.). httpx lanzaba
`TypeError: Header value must be str or bytes, not <class 'int'>` antes del
primer `yield` al LLM. El cliente recibía 200 + content-type SSE pero
nunca contenido, y `reader.read()` terminaba con `done=true` sin error
→ bubble vacío.

### Fix

- Rename `h → litellm_headers` y `for h in hits → for hit in hits`.
- Try/except en `_stream()` que emite `data: {"type": "error", ...}` +
  `[DONE]` cuando el upstream falla. Visible en UI en vez de silencio.
- Frontend (`src/frontend/app/(app)/page.tsx`) parsea el evento `type: error`
  y lanza excepción para que el catch escriba el mensaje al usuario.

### Verificación

- `RAG=false`: streaming completo ("Hola no es una palabra…") ✓
- `RAG=true`: streaming completo ("Mi base de conocimiento actual es limit…") ✓
- Sin TypeErrors nuevos en logs.

---

## Bug 2 — Token expirado no redirige a login

### Causa raíz

- `src/frontend/lib/auth.ts` usaba `zustand/persist` (`name: cerebro-auth`):
  token guardado en localStorage **sin TTL**.
- `src/frontend/app/(app)/layout.tsx` solo redirige si `!token`, así que
  el token persistido sobrevivía a la expiración del JWT (24h).
- `src/frontend/lib/api.ts::apiCall` lanzaba en `!res.ok` con mensaje
  genérico, sin detectar 401 ni hacer logout.
- Backend: JWT 24h + cookie 24h, sin refresh-token flow → re-login cada
  día como única salida.

### Fix

**Backend (`src/api/main.py` + `src/api/auth.py`):**

- Access JWT recortado a `ACCESS_TOKEN_EXPIRE_MINUTES=30` (env-overridable).
- Refresh token opaco (48 bytes random) almacenado en Redis con SHA-256,
  TTL `REFRESH_TOKEN_EXPIRE_DAYS=30`. Clave: `refresh:{sha256}` →
  JSON `{user_id, tenant_id, email}`.
- Cookie `cerebro_refresh` httpOnly añadida en login/register.
- Nuevo endpoint `POST /auth/refresh`: valida cookie, **rota**
  (DELETE old + SET new), reemite access JWT y CSRF.
- `/auth/logout` revoca el refresh en Redis y borra los 3 cookies.
- `get_current_user` ahora emite header `X-Auth-Reason` en respuestas 401:
  - `missing` — sin cookie ni Bearer.
  - `expired` — JWT estructuralmente válido pero `exp` vencido.
  - `invalid` — JWT corrupto/firma inválida.
  - `no_user` — JWT válido pero el usuario fue borrado.
  - `no_refresh` / `refresh_invalid` — en `/auth/refresh`.

**Frontend (`src/frontend/lib/api.ts`):**

- `handleAuthFailure(res)` exportada. Para `X-Auth-Reason=expired`:
  - Llama `POST /api/auth/refresh` con mutex `refreshInFlight` (evita N
    refreshes paralelos compitiendo por la rotación).
  - Si refresh OK: sincroniza Zustand con el `access_token` nuevo.
  - Retorna `"refreshed"`. Llamador reintenta una vez.
- Para cualquier otro `X-Auth-Reason`: `clearAuth()` + redirect a `/login`.
- `apiCall<T>` retry-once on 401-expired.

**Frontend chat (`src/frontend/app/(app)/page.tsx`):**

- `send()` ahora reintenta el streaming con el JWT rotado al recibir 401.

### Verificación

- `/auth/refresh` sin cookie → 401 + `X-Auth-Reason: no_refresh` ✓
- Register → 3 cookies (session 30min, csrf 30d, refresh 30d) + key en Redis ✓
- `/auth/refresh` con cookie válida → 200, hash en Redis cambia ✓
- Reuso del refresh viejo → 401 + `X-Auth-Reason: refresh_invalid` ✓

---

## Bug 3 — Botones de copiar no funcionan

### Causa raíz

`navigator.clipboard.writeText` solo está disponible en
contextos seguros (HTTPS, localhost). La app se accede por
`http://192.168.1.19:3001` → API undefined → `TypeError`.

### Fix

Nuevo util `src/frontend/lib/clipboard.ts::copyToClipboard(text)`:

1. Intenta `navigator.clipboard.writeText`.
2. Si no existe o falla, cae a la técnica legacy: crear `<textarea>`
   off-screen, seleccionarlo, `document.execCommand("copy")`, removerlo.
3. Retorna `boolean` para que el llamador decida si mostrar tick / toast.

Tres call sites migrados:
- `app/(app)/page.tsx::CopyBtn`
- `app/(app)/layout.tsx::ProfileModal` (tenant_id)
- `app/(app)/profile/page.tsx::copyTenantId`

### Verificación

Bundle minificado contiene `document.execCommand("copy")` en los 3
chunks que usan el util.

---

## Bug 4 — Cron de audit fallando todos los días desde hace 5+

### Causa raíz

Workflow `linkanvil — audit cron diario` (id `M6Qwm9rKXRew2tFu`)
apuntaba a `http://api:8000/admin/audit-cron`, pero el alias real en la
red Docker es `cerebro-api:8001`. El nodo HTTP fallaba con
`bad address 'api:8000'`. Historial en `n8n.execution_entity`:

```
id |  workflowId      |  mode   | status |        startedAt
 6 | M6Qwm9rKXRew2tFu | trigger | error  | 2026-05-16 07:00:00 UTC
 5 | M6Qwm9rKXRew2tFu | trigger | error  | 2026-05-15 07:00:00 UTC
 4 | M6Qwm9rKXRew2tFu | trigger | error  | 2026-05-14 07:00:00 UTC
 3 | M6Qwm9rKXRew2tFu | trigger | error  | 2026-05-13 07:00:00 UTC
 2 | M6Qwm9rKXRew2tFu | trigger | error  | 2026-05-12 07:00:00 UTC
```

(`startedAt` en UTC: el cron declara `0 3 * * *` y se ejecuta a las 07:00
UTC, lo que indica que la TZ de n8n es UTC-4.)

### Fix

- `infra/n8n/workflows/audit_cron_daily.json`: URL corregida.
- `n8n.workflow_entity` (BD live de n8n): nodes JSONB actualizado con
  `REPLACE(nodes::text, 'http://api:8000/...', 'http://cerebro-api:8001/...')::jsonb`.
- `cerebro-n8n` reiniciado para repoblar el scheduler en memoria.

### Verificación

```
docker exec cerebro-n8n wget http://api:8000/health         → bad address
docker exec cerebro-n8n wget http://cerebro-api:8001/health → {"status":"ok"}
```

Backlog drenado manualmente vía `POST /admin/audit-cron` con
`X-Admin-Token`: 2 recursos `activo → cuarentena`.

### Nuevo: botón manual `/resources/audit-now`

Como complemento al cron, se añadió un endpoint user-facing:

**Backend (`src/api/main.py`):**
```
POST /resources/audit-now
  Auth:      Depends(get_current_user)
  CSRF:      Depends(verify_csrf)
  Rate-limit: 5/min por tenant en Redis (rl:audit:{tenant_id})
  Body:      none
  Response:  { status, trace_id, cuarentenados, expirados }
```

Reusa `run_audit_cron()` tal cual — idempotente, sin admin token, sin
divergir entre cron y manual.

**Frontend (`src/frontend/app/(app)/kb/page.tsx`):**

Botón "Revisar caducidades" junto al refresh, con `Loader2` mientras
corre y toast (verde/rojo, 5s) con `cuarentenados` + `expirados`. Recarga
la lista al terminar para que los badges del sidebar se actualicen vía
SSE.

---

## Bug 5 — Recursos vuelven a `activo` después del audit

### Causa raíz

**Diagnóstico paso a paso:**

1. `cerebro.procesamiento` es un exchange **fanout** en RabbitMQ.
2. El embedder bind-ea su queue `q.recurso.embedder` a este exchange con
   `routing_key=""`. En fanout el routing key es irrelevante: la queue
   recibe **todos** los eventos publicados al exchange.
3. El outbox publisher (`src/data/outbox_publisher.py`) inyecta
   `payload['evento_tipo']` y publica al fanout cada evento de
   `outbox_eventos`, incluidos:
   - `recurso.procesado` (scraper) ← legítimo para embedder
   - `recurso.reusado` (scraper, reuse path) ← legítimo
   - `recurso.cuarentena` (audit_cron, colisión semántica) ← NO debería
     llegar al embedder
   - `recurso.expirado` (audit_cron) ← NO
   - `recurso.rescatado` (rescue endpoint) ← NO
4. El embedder `process_message` no filtraba por `evento_tipo`. Recibía
   un payload del audit como `{event_origin: "audit_cron", recurso_id,
   url, motivo}` sin `extracted_info` ni `contenido`. Caía en la rama
   "nuevo recurso" → generaba embedding desde `"" | "" | Tags: "" ` →
   `_inject_to_qdrant` con vector basura → `update_recurso_estado(
   recurso_id, "activo")`.

**Evidencia DB:**

```
quarantined_at = 2026-05-17 10:45:49.483  (audit_cron emite cuarentena)
updated_at     = 2026-05-17 10:45:53.784  (embedder pisa estado='activo'
                                            ~4 s después)
```

Cada vez que el audit movía un recurso a cuarentena, el embedder lo
re-activaba inmediatamente, dejando los campos `quarantine_*` sucios y
el `estado` mentiroso.

**Síntoma colateral:** queue `q.embeddings` con 108 mensajes ready y 0
consumers (también bound al fanout pero nadie la lee — herencia de una
arquitectura previa).

### Fix

**A. Whitelist en el embedder (`src/data/embedder_worker.py`):**

```python
EMBEDDER_EVENT_TYPES = frozenset({"recurso.procesado", "recurso.reusado"})

async def process_message(self, message):
    async with message.process(...):
        payload = json.loads(message.body.decode())
        evento_tipo = payload.get("evento_tipo") or (
            (message.headers or {}).get("evento_tipo") if message.headers else None
        )
        if evento_tipo and evento_tipo not in self.EMBEDDER_EVENT_TYPES:
            logger.debug(f"[{trace_id}] Embedder ignora evento_tipo={evento_tipo}")
            return
        ...
```

**B. Defensa en profundidad en `src/data/db.py::update_recurso_estado`:**

```python
if estado == "activo":
    await conn.execute(
        """UPDATE recursos
           SET estado = 'activo', updated_at = NOW()
           WHERE id = $1::uuid AND estado = 'procesando'""",
        recurso_id,
    )
else:
    await conn.execute(
        "UPDATE recursos SET estado = $1, updated_at = NOW() WHERE id = $2::uuid",
        estado, recurso_id,
    )
```

Si en el futuro otro consumidor cae en la trampa de "finalizar = activo",
no podrá pisar transiciones de cuarentena/expirado. Solo procesando→activo
está permitido por esta función.

**C. Queue zombie purgada:** `rabbitmqctl purge_queue q.embeddings`
(108 mensajes basura eliminados).

### Verificación

Test reproducible:

```
1. /resources/audit-now → {"cuarentenados":2,"expirados":0}
2. sleep 6
3. SELECT id, estado, quarantined_at, updated_at FROM recursos
   WHERE id IN ('5bdefd3e...','f4db97f3...');
```

Resultado:

```
estado=cuarentena, quarantined_at = updated_at = 10:57:44 (sin segundo update)
```

Antes del fix: `estado=activo, updated_at = quarantined_at + ~4s`.

---

## Limpieza de disco

`docker system prune -f` recuperó **4 GB** (sobre todo build cache).

```
Antes:  /dev/mapper/pve-vm--119--disk--0   40G   27G   11G  72%
Después: /dev/mapper/pve-vm--119--disk--0  40G   22G   17G  58%
```

Eso resolvió los warnings `MISCONF Errors writing to the AOF file: No space
left on device` que aparecían en el worker outbox. Redis responde PONG
normalmente.

---

## Operación del cron de obsolescencia (referencia)

**Pipeline:**

```
n8n (cerebro-n8n)  →  POST /admin/audit-cron  →  src/data/audit_cron.py::run_audit_cron()
   ↑ cron diario        ↑ src/api/main.py             ↑ dos UPDATE en `recursos`
```

| Pieza | Detalle |
|-------|---------|
| Definición | `infra/n8n/workflows/audit_cron_daily.json` — `cronExpression: "0 3 * * *"`. |
| Hora real | 07:00 UTC (n8n corre en UTC-4). |
| Endpoint | `POST /admin/audit-cron` con header `X-Admin-Token: $AUDIT_CRON_TOKEN`. |
| Lógica fase A | `activo` con `fecha_caducidad <= hoy` → `cuarentena`, `quarantine_grace_until = hoy + OBSOLESCENCE_GRACE_DAYS (default 30)`. |
| Lógica fase B | `cuarentena` con `quarantine_grace_until <= hoy` → `expirado`. |
| Idempotencia | Sí: ambas fases filtran por `estado` actual. |
| Notificación | Outbox events `recurso.cuarentena` / `recurso.expirado` por tenant → notifier-worker → in-app feed (`notificaciones`) + Telegram si está configurado. |
| Disparo manual | `POST /resources/audit-now` (auth normal de usuario, rate-limited 5/min/tenant) o botón "Revisar caducidades" en `/kb`. |

### Estados del ciclo

```
              ┌───────────┐
              │procesando │ ← insertado por scraper (placeholder/post-scrape)
              └─────┬─────┘
                    │ embedder OK
                    ▼
              ┌───────────┐
       ┌────  │  activo   │  ←──┐
       │      └─────┬─────┘     │ rescate (UI o API)
       │            │ audit_cron│
       │            │ o col.sem.│
       │            ▼           │
       │      ┌───────────┐     │
       │      │cuarentena │ ────┘
       │      └─────┬─────┘
       │ delete     │ grace_until vencido
       │            ▼
       │      ┌───────────┐
       │      │ expirado  │
       │      └─────┬─────┘
       │            │ delete o rescate fast-track
       │            ▼
       │      ┌───────────┐
       └────► │ (borrado) │
              └───────────┘
```

---

## Archivos tocados

```
infra/n8n/workflows/audit_cron_daily.json
src/api/auth.py
src/api/main.py
src/data/db.py
src/data/embedder_worker.py
src/frontend/lib/api.ts
src/frontend/lib/clipboard.ts            (nuevo)
src/frontend/app/(app)/page.tsx
src/frontend/app/(app)/layout.tsx
src/frontend/app/(app)/profile/page.tsx
src/frontend/app/(app)/kb/page.tsx
```

Aprox. **+700 / -90** líneas en total. Sin commits aún — la copia en
`/root/linkanvil/` ya tiene todos los cambios, listos para `git add` + `git commit`.

Imágenes Docker reconstruidas y recreadas:
`linkanvil-cerebro-api`, `linkanvil-cerebro-web`, `linkanvil-embedder-worker`,
`linkanvil-scraper-worker`, `linkanvil-outbox-worker`, `linkanvil-notifier-worker`.

---

## Pendientes detectados y NO resueltos

1. **Botón logout no llama backend**: `(app)/layout.tsx` hace `clearAuth()`
   local pero no `POST /api/auth/logout` para revocar el refresh token en
   Redis. Con TTL de 30 días se autocura, pero conviene cerrar el bucle.
2. **Queue zombie `q.embeddings` bound sin consumer**: la purgué pero la
   binding sigue. Conviene desbindarla del exchange (o eliminar el queue)
   en una próxima sesión para que no acumule más mensajes.
3. **`tenant_id` en payloads de audit-cron**: los outbox events
   emitidos por `_emit_outbox_per_tenant` van bien dirigidos por tenant,
   pero el embedder solo veía el `tenant_id` del primer destinatario
   (otra razón para filtrar por `evento_tipo`).
4. **`recursos.estado='activo' WITH quarantined_at NOT NULL`**: hay
   2 filas con esos campos sucios (residuo del bug ahora resuelto).
   No es crítico — el próximo audit las re-evaluará — pero un cleanup
   one-shot SQL las normalizaría:
   ```sql
   UPDATE recursos SET quarantined_at=NULL, quarantine_reason=NULL,
                       quarantine_grace_until=NULL
   WHERE estado='activo' AND quarantined_at IS NOT NULL;
   ```
5. **`AUDIT_CRON_TOKEN` rotación**: el token está en `.env` y en n8n env.
   Si se rota, hay que actualizar ambos sitios. No hay alerta si
   divergen.

---

# Sesión tarde 2026-05-17 — Clasificación temporal + policy JSONB + auto-archive

## Origen de la sesión

Tras documentar `prompts.md` y `lifecycle.md`, detectaste que recursos
como Expojove 2024 y AEMET 2020 NO se trataban como contenido pasado:
el LLM no extraía `expiration_date` (el prompt original solo pedía
"deadline o fin de oferta futura"), caía al fallback `today + 30 días`
y los recursos vivían como `activo` con caducidad sintética.

## Cambios estructurales aplicados

### Migración 0006 — clasificación del LLM
- `recursos.temporal_class` VARCHAR(20) — `evento`/`referencia`/`evergreen`.
- `recursos.valor_archivistico` VARCHAR(20) — `alto`/`medio`/`nulo`.
- `recursos.fecha_evento` DATE — fecha del evento descrito (puede ser pasada).
- `recursos_quarantine_reason_check` extendido con `'evento_pasado'`.
- `usuarios.audit_strictness` (enum) — luego sustituido por migración 0007.

### Migración 0007 — policy por celda + auto-archive
- `usuarios.audit_policy` JSONB con 6 keys (matriz `temporal_class ×
  valor_archivistico` para contenido pasado). Cada celda es
  `activo`/`cuarentena`/`expirado`.
- `recursos.auto_archive_pending` BOOLEAN — señal al embedder para
  transicionar a `expirado` (no `activo`) tras vectorizar.
- `usuarios.audit_strictness` eliminada. La migración es idempotente
  (DO block con check de existencia) tras un fallo inicial del
  `cerebro-migrate` por aplicación manual previa.

### Backend
- **Scraper prompt** extendido con 3 campos nuevos (incluyendo hint del
  path `YYYY/MM/DD` de la URL para fechas).
- **`db.py::save_with_outbox`** ahora es policy-driven: lookup
  `policy[clave]` reemplaza el árbol if/elif anterior. Helper
  `_get_user_audit_policy(tenant_id)` con cache in-process 60s.
- **`db.py::update_recurso_estado` guard ampliado**: permite
  `procesando → expirado` solo cuando `auto_archive_pending=true`,
  preserva la defensa contra reverts a `activo` ya transicionados.
- **`embedder_worker.py`** lee el flag al terminar y transiciona al
  destino correcto. Tras auto-archive emite `recurso.expirado` con
  `motivo='auto_archive'` para que el notifier avise al usuario.
- **`notifier/worker.py`** mapea `motivo='auto_archive'` → copy 📦
  "se archivó automáticamente. Recuperable en chat con Archivo ON".
  También copy específico para `motivo='evento_pasado'` en cuarentena.
- **`api/main.py`**: nuevo `PUT /profile/audit-policy` con validador
  estricto de 6 keys. `GET /auth/me` devuelve `audit_policy`.
  `POST /chat` acepta `include_archive: bool` para incluir `expirado`
  en RAG (toggle "Archivo ON").

### Frontend
- **`lib/auth.ts`**: tipo `AuditPolicy`, constante `AUDIT_PRESETS` con
  los 3 presets canónicos, helper `matchPreset()` para detectar
  client-side si la policy actual coincide con un preset.
- **`/profile` y panel lateral `ProfileModal`**: card "Auditoría de
  recursos" con 3 botones preset (1-click) + 6 selects para ajuste fino.
  Auto-save al cambiar cualquier celda. Badge dinámico "Basado en X" o
  "Personalizada".
- **Chat (`(app)/page.tsx`)**: toggle "Archivo ON/OFF" en ámbar junto
  al botón "RAG ON". Pasa `include_archive` en el body de POST `/chat`.
- **`/quarantine`**: REASON_META con entrada `evento_pasado`
  (icono `CalendarX`, badge azul).
- **`/expired`**: copy actualizado a "Archivo histórico" (no descarte).
- **`_NotificationsBell.tsx`**: REASON_LABEL extendido con
  `evento_pasado` y `auto_archive`.

## Matriz de comportamiento (presets canónicos)

| Preset | evento_pasado_{alto,medio,nulo} | referencia_pasada_{alto,medio,nulo} |
|---|---|---|
| Estricto | cuarentena / cuarentena / cuarentena | cuarentena / cuarentena / cuarentena |
| **Equilibrado (default)** | expirado / cuarentena / cuarentena | expirado / cuarentena / cuarentena |
| Permisivo | expirado / cuarentena / cuarentena | expirado / activo / cuarentena |

## Bug detectado y resuelto durante la sesión

**Síntoma**: el bell no se actualizaba aunque hubiera auto-archives.

**Causa**: el embedder transicionaba `procesando → expirado` por SQL
directo via `update_recurso_estado` pero NO emitía outbox event. El
notifier-worker (whitelist: `cuarentena|expirado|rescatado`) nunca veía
el cambio.

**Fix**: helper `_emit_auto_archive_event` en el embedder que inserta
`recurso.expirado` con motivo `auto_archive` tras la transición.
Backfill manual de los 2 recursos pre-fix (Expojove + AEMET) vía
`INSERT INTO outbox_eventos` con `SET LOCAL app.tenant_id` para
respetar la RLS forzada.

## Commits de la sesión

| Hash | Asunto |
|---|---|
| `021c3ab` | feat(audit): clasificación temporal del LLM + audit_policy JSONB por celda |
| `41bfd39` | feat(profile-modal): card de Auditoría de recursos en el panel lateral |
| `37d4737` | fix(notifications): emite evento outbox cuando auto-archive transiciona |

Publicados en `origin/develop`.

## Pendientes y notas de operación

1. **Pre-push hook con FP**: el LLM auditor de `ops/prompts/pre-push.txt`
   reporta CRITICAL en `/auth/me` ignorando que `Depends(get_current_user)`
   ES la validación JWT. Push usó `--no-verify` con autorización
   explícita del usuario. Convendría enseñar al prompt a reconocer
   `Depends(...)` de FastAPI.
2. **Reuso cross-tenant + policy**: cuando un segundo tenant añade una
   URL ya conocida (rama `reused`), hereda el `estado` global decidido
   por el primer tenant — NO se re-evalúa la policy del nuevo tenant.
   Es por diseño (estado global, sin per-tenant estados) pero conviene
   documentarlo. Si lo cambias, requiere migración a estado per-tenant.
3. **Backfill masivo**: rows pre-migración 0006 tienen
   `temporal_class='evento'` por default. Para reclasificar URLs ya
   ingestadas, re-ingéstalas manualmente — no hay cron de
   reclasificación.
4. **Pre-push hook no entiende `Depends`**: se podría añadir excepción
   en el prompt para que pase los endpoints que usan `Depends(verify_csrf)`
   o `Depends(get_current_user)` sin marcarlos CRITICAL.

---

## 📌 Post-sesión — drift acumulado a 2026-05-19

> **Naturaleza de esta sección**: este log es un documento **inmutable**.
> El cuerpo de arriba describe la sesión del 2026-05-17 tal como ocurrió y
> NO se modifica. Esta sección añade, sin reescribir la historia, una capa
> de anotaciones con lo que ha cambiado en los ~2 días posteriores
> (rango verificado: `develop` @ `7c723f3`, ~28 commits entre `ba405e2`
> y `7c723f3`). Generada por `doc-reviser` a partir del review report
> `docs/review/2026-05-19/docs/OPERATIONS_SESSION_2026-05-17.review.md`.

### Afirmaciones que SIGUEN vigentes

El núcleo técnico de la sesión está intacto en `develop`. Ningún fix
descrito en el log ha sido revertido. En particular:

- **Bug 1 (RAG streaming TypeError)**: `litellm_headers` y `for hit in
  hits` siguen en `src/api/main.py` (líneas ~1838, 1845, 1868). El
  try/except de `_stream` con `data: {"type":"error",...}` + `[DONE]`
  sigue en su sitio.
- **Bug 2 (Auth + refresh tokens)**: `ACCESS_TOKEN_EXPIRE_MINUTES=30`,
  `REFRESH_TOKEN_EXPIRE_DAYS=30`, cookie `cerebro_refresh`, endpoint
  `POST /auth/refresh` con rotación, y los headers `X-Auth-Reason:
  missing|expired|invalid|no_user|no_refresh|refresh_invalid` siguen
  exactamente como se describen. Han aparecido reasons adicionales
  (`demo_invalid`, `demo_expired`) por el trabajo posterior de demo,
  pero no contradicen el log.
- **Bug 3 (Clipboard fallback)**: `src/frontend/lib/clipboard.ts` y los
  3 call sites siguen migrados (el de chat ahora cuelga de `chat/page.tsx`
  por el rename — ver "Renames" abajo).
- **Bug 4 (n8n cron URL)**: `infra/n8n/workflows/audit_cron_daily.json`
  apunta a `http://cerebro-api:8001/admin/audit-cron`. Endpoint manual
  `POST /resources/audit-now` y botón en `/kb` operativos.
- **Bug 5 (Embedder pisaba `activo`)**: whitelist
  `EMBEDDER_EVENT_TYPES = frozenset({"recurso.procesado",
  "recurso.reusado"})` en `src/data/embedder_worker.py`. El guard en
  `src/data/db.py::update_recurso_estado` se **endurece** con la
  migración 0007 (acepta también `procesando → expirado` cuando
  `auto_archive_pending=true`) sin debilitar la defensa contra reverts
  a `activo`.
- **Sesión tarde (clasificación temporal + policy JSONB)**:
  migraciones `0006_temporal_class_y_strictness.sql` y
  `0007_audit_policy_y_auto_archive.sql` presentes en
  `infra/postgres/migrations/`. `_get_user_audit_policy` con cache 60s,
  `save_with_outbox` policy-driven, `PUT /profile/audit-policy`,
  `AUDIT_PRESETS`/`matchPreset` en frontend, `_emit_auto_archive_event`
  en embedder, copies de notifier (`evento_pasado`, `auto_archive`),
  toggle "Archivo ON", REASON_META con `evento_pasado` — todo verificado
  en su sitio.
- **Commits citados**: `021c3ab`, `41bfd39`, `37d4737` siguen en
  `develop`. El propio doc llegó al repo en `ba405e2` (ver nota M1 en
  "Incoherencias internas" abajo).

### Afirmaciones que YA NO son válidas (drift acumulado)

#### Rutas de archivo obsoletas — rename a `chat/page.tsx`

El log cita repetidamente `src/frontend/app/(app)/page.tsx` (líneas 53,
106, 137, 394, 493 del log). Ese archivo **fue renombrado** a
`src/frontend/app/(app)/chat/page.tsx` en el commit
`7439d07 feat(landing): página pública + demo accesible desde /login`:

```
src/frontend/app/(app)/{ => chat}/page.tsx        | 0
```

El **contenido** del fix (parseo de `type: error`, `CopyBtn`, toggle
"Archivo ON/OFF", `include_archive: useArchive`) sigue presente, solo en
otra ruta. Un lector que intente abrir `src/frontend/app/(app)/page.tsx`
no encontrará el archivo.

#### Pendientes del log que YA NO aplican (cerrados por commits posteriores)

Los siguientes ítems de la sección "Pendientes detectados y NO
resueltos" han sido cerrados — total o parcialmente — en commits
posteriores:

| Pendiente del log | Estado a 2026-05-19 | Commit |
|---|---|---|
| #1 — Botón logout no llama backend | **CERRADO**: `(app)/layout.tsx:719-721` ahora hace `apiCall("/auth/logout", {method:"POST"}, token)` antes del `clearAuth()`. | `2c7e4a5` |
| #4 — `recursos.estado='activo' WITH quarantined_at NOT NULL` (2 filas sucias) | **CERRADO**: verificadas 0 filas en `develop`; el fix del embedder ya cubría el caso sin necesidad del UPDATE SQL one-shot. | `2c7e4a5` |
| #5 — `AUDIT_CRON_TOKEN` rotación sin alerta | **PARCIALMENTE CERRADO**: `src/api/main.py` añade log de startup (WARN si falta, INFO con longitud si está). La detección de divergencia con n8n sigue siendo manual. | `2c7e4a5` |
| Sesión tarde #1 / #4 (duplicado) — Pre-push hook reconociendo `Depends()` | **PROBABLEMENTE ABIERTO**: `2c7e4a5` arregló LiteLLM 401 del hook (`ops/cron/litellm_client.py`); rondas 14-19 de refactor de hooks en `eb1da66` no se han verificado contra el prompt de pre-push. Confirmar manualmente. | `2c7e4a5`, `eb1da66` |

#### Pendientes del log que SIGUEN abiertos (con matiz)

- **Pendiente #2 — Queue zombie `q.embeddings` bound sin consumer**: el
  commit `2c7e4a5` declara la queue "eliminada" como operación de
  runtime (`rabbitmqctl delete_queue q.embeddings`) y afirma "Sin
  declarer en source, no se recrea". **Eso es incorrecto**: la cola
  sigue declarada en source —
  - `infra/rabbitmq/definitions.json:70` — `"name": "q.embeddings"`
  - `infra/rabbitmq/definitions.json:123` — binding
    `destination: "q.embeddings"`
  - `infra/test_health.py:136` — el test la espera viva en la lista
    `["q.url.ingesta", "q.url.fallidas", "q.embeddings",
    "q.curador.nocturno"]`.
  - En cualquier rebuild/reimport de RabbitMQ desde `definitions.json`
    la cola vuelve. Para cerrar este pendiente de raíz hay que quitar
    queue + binding del JSON y actualizar `infra/test_health.py:136`.
- **Sesión tarde #2 — Reuso cross-tenant + policy**: sin cambios. No
  hay migración a estado per-tenant en `infra/postgres/migrations/`.
  Sigue por diseño tal como el log lo documenta.

### Incoherencias internas del log (no son drift, son notas para el lector)

- **M1 — "Sin commits aún" no es cierto retroactivamente**: el log dice
  en su línea 401 _"Sin commits aún — la copia en `/root/linkanvil/` ya
  tiene todos los cambios, listos para `git add` + `git commit`"_. El
  propio doc llegó al repo dentro del commit `ba405e2`
  (`docs/src/OPERATIONS_SESSION_2026-05-17.md | 432 +++`, 12 archivos,
  +982/-76 en total). Para un lector futuro: sí hubo commit, fue
  `ba405e2`.

### Commits que invalidaron partes del log

| Commit | Qué cambió respecto al log |
|---|---|
| `ba405e2` | Empaqueta los 5 bugs reactivos y el propio doc (contradice "Sin commits aún" del log). |
| `7439d07 feat(landing): página pública + demo accesible desde /login` | Rename de `src/frontend/app/(app)/page.tsx` → `src/frontend/app/(app)/chat/page.tsx`. Invalida las 5 referencias a esa ruta. |
| `2c7e4a5 fix(auth,hooks,obs): cierra pendientes de la sesión 2026-05-17` | Cierra pendientes #1, #4 y parcialmente #5. Purga la queue `q.embeddings` en runtime pero **no en source** (ver pendiente arriba). |
| `eb1da66` | Refactor de hooks rondas 14-19. Posiblemente toca el prompt de pre-push (sin verificar). |

---

## 📋 Notas del v2 (generado por doc-reviser · 2026-05-19)

**Origen**: `/tmp/linkanvil-mirror/docs/src/OPERATIONS_SESSION_2026-05-17.md` · branch `develop` @ `7c723f3`
**Review aplicado**: `/tmp/linkanvil-staging/docs/review/2026-05-19/docs/OPERATIONS_SESSION_2026-05-17.review.md`

### Política especial aplicada

Este documento es un **log operativo inmutable** de la sesión del
2026-05-17. Por instrucción explícita del caller y de la propia
recomendación del review (sección "Recomendación de follow-up — no
edición del log"), **no se ha modificado el cuerpo del documento**.
Las correcciones del review se han transformado en **anotaciones de
drift** en la sección "📌 Post-sesión" añadida al final.

### Cambios aplicados

- 0 CRITICAL · 2 HIGH · 4 MEDIUM · 2 LOW (de 8 hallazgos del review)
- Todos los HIGH y MEDIUM del review se reflejan como entradas en la
  sección "Post-sesión — drift acumulado":
  - **H1** (rename `(app)/page.tsx` → `(app)/chat/page.tsx`) →
    subsección "Rutas de archivo obsoletas".
  - **H2** (queue zombie cerrada en runtime pero no en source) →
    subsección "Pendientes del log que SIGUEN abiertos".
  - **M1** (frase "Sin commits aún" inválida retroactivamente) →
    subsección "Incoherencias internas del log".
  - **M2** (pendiente #1 logout backend) → tabla "Pendientes del log
    que YA NO aplican".
  - **M3** (pendiente #4 filas sucias) → misma tabla.
  - **M4** (pendiente #5 `AUDIT_CRON_TOKEN`) → misma tabla,
    parcialmente cerrado.
  - **L1** (reuso cross-tenant sin cambios) → subsección "Pendientes
    del log que SIGUEN abiertos".
  - **L2** (pre-push hook + `Depends`) → tabla "Pendientes del log
    que YA NO aplican", marcado como "PROBABLEMENTE ABIERTO".

### Pendientes (no aplicados en este v2)

- Ninguno. No hay UNVERIFIED en el review.
- El propio review L2 (pre-push hook + `Depends`) queda flaggeado en
  la sección Post-sesión como "PROBABLEMENTE ABIERTO" porque el
  auditor no validó si las rondas 14-19 del refactor de hooks
  (`eb1da66`) tocan el prompt de pre-push. Requiere confirmación
  manual aparte.

### Bugs de código flaggeados (no son drift de doc)

- **[CODE-BUG] Cola `q.embeddings` declarada en source pese a la
  intención de eliminarla**:
  `infra/rabbitmq/definitions.json:70`, `:123` +
  `infra/test_health.py:136`. La purga vía `rabbitmqctl` no es
  suficiente — en cualquier reimport de `definitions.json` la cola
  vuelve. Cerrar requiere editar JSON + actualizar el test.
