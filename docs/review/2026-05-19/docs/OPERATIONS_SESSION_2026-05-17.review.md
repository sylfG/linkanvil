# Reality audit — docs/src/OPERATIONS_SESSION_2026-05-17.md

> Tipo: **log inmutable** de sesión operativa.
> Auditor: docs-reality-auditor.
> Fecha auditoría: 2026-05-19.
> Rama verificada: `develop` @ `7c723f3`.
> Commits posteriores a la sesión que afectan al contenido: ~28 entre `ba405e2` y `7c723f3`.
>
> Política aplicada: **no se propone editar el doc** (es un log, no doctrina viva).
> Se identifican únicamente afirmaciones del log que ya **no reflejan el estado actual** del repo y se propone, al final, una **nota de seguimiento separada** (no una edición del log).

---

## Verdict global

- Núcleo técnico de la sesión (Bug 1-5 + sesión tarde con migraciones 0006/0007 y policy JSONB): **VIGENTE**.
- Pendientes #1, #2 y #5 listados al final del log mañana: **CERRADOS** por commits posteriores — el lector futuro debería saberlo.
- Una afirmación textual del log es contradictoria con la realidad ya en el momento del merge (ver M1 abajo).
- Una ruta de archivo citada repetidamente (`src/frontend/app/(app)/page.tsx`) **fue renombrada** dos días después a `src/frontend/app/(app)/chat/page.tsx` (commit `7439d07`). Cualquier lector que intente abrir esa ruta se va a confundir.
- No se ha encontrado ningún cambio que **revierta o invalide** trabajo técnico descrito en el log.

---

## Hallazgos

### CRITICAL
*(ninguno)*
Ningún trabajo descrito en el log ha sido revertido o invertido sin nota explícita.

### HIGH

#### H1 — Ruta `src/frontend/app/(app)/page.tsx` ya no existe (renombrada a `chat/page.tsx`)

El log la cita en 5 puntos diferentes:
- `docs/src/OPERATIONS_SESSION_2026-05-17.md:53`
- `docs/src/OPERATIONS_SESSION_2026-05-17.md:106`
- `docs/src/OPERATIONS_SESSION_2026-05-17.md:137`
- `docs/src/OPERATIONS_SESSION_2026-05-17.md:394`
- `docs/src/OPERATIONS_SESSION_2026-05-17.md:493`

El rename ocurrió en commit `7439d07 feat(landing): página pública + demo accesible desde /login`:

```
src/frontend/app/(app)/{ => chat}/page.tsx        | 0
```

El **contenido del fix** (parseo del evento `type: error`, `CopyBtn`, toggle "Archivo ON/OFF", `include_archive`) sigue presente en el código:
- `src/frontend/app/(app)/chat/page.tsx:12` — `import { copyToClipboard } from "@/lib/clipboard"`
- `src/frontend/app/(app)/chat/page.tsx:22` — `CopyBtn` usa `copyToClipboard`
- `src/frontend/app/(app)/chat/page.tsx:242` — `include_archive: useArchive` en POST `/chat`
- `src/frontend/app/(app)/chat/page.tsx:488` — copy "Archivo ON" en ámbar

Estado: **VIGENTE en código, ruta obsoleta en doc**. No editar el log — sí mencionar el rename en la nota de seguimiento.

#### H2 — Pendiente #2 ("Queue zombie `q.embeddings` bound sin consumer") cerrado solo a runtime, no en source

El commit posterior `2c7e4a5 fix(auth,hooks,obs): cierra pendientes de la sesión 2026-05-17` afirma textualmente:

> 4) queue zombie q.embeddings eliminada
> Operación de runtime, no código: rabbitmqctl delete_queue q.embeddings […]
> **Sin declarer en source, no se recrea.**

Pero la definición de la cola **sí está declarada en source** y se reaplicaría si RabbitMQ reimporta `definitions.json`:
- `infra/rabbitmq/definitions.json:70` — `"name": "q.embeddings"`
- `infra/rabbitmq/definitions.json:123` — binding `destination: "q.embeddings"`
- Además el test `infra/test_health.py:136` la espera viva (`expected = ["q.url.ingesta", "q.url.fallidas", "q.embeddings", "q.curador.nocturno"]`).

Estado: el pendiente del log se considera resuelto, pero la realidad es que en cualquier rebuild/reimport de RabbitMQ la cola vuelve. **El pendiente sigue abierto en source**. La nota de seguimiento debería decirlo.

### MEDIUM

#### M1 — La frase "Sin commits aún" del log es falsa retroactivamente

`docs/src/OPERATIONS_SESSION_2026-05-17.md:401`:

> Aprox. **+700 / -90** líneas en total. **Sin commits aún** — la copia en `/root/linkanvil/` ya tiene todos los cambios, listos para `git add` + `git commit`.

El propio doc se commiteó **en el mismo commit que contiene los fixes** (`ba405e2`, +432 líneas del propio doc) — lo dice explícitamente el `git show --stat ba405e2`:

```
docs/src/OPERATIONS_SESSION_2026-05-17.md | 432 ++++++++++++++++++++++++++++++
...
12 files changed, 982 insertions(+), 76 deletions(-)
```

No es un cambio del repo posterior — es una incoherencia interna del log respecto a su propia historia. Para un lector futuro es una señal menor pero confusa: "¿hubo o no commit?". Sí lo hubo: `ba405e2`.

#### M2 — Pendiente #1 (logout no llama backend) cerrado en `2c7e4a5`

`docs/src/OPERATIONS_SESSION_2026-05-17.md:417-420` lista como pendiente:

> 1. **Botón logout no llama backend**: `(app)/layout.tsx` hace `clearAuth()` local pero no `POST /api/auth/logout` para revocar el refresh token en Redis.

Resuelto en `2c7e4a5`:
- `src/frontend/app/(app)/layout.tsx:719-721` ahora llama `apiCall("/auth/logout", { method: "POST" }, token)` antes del `clearAuth()`.

Estado: **CERRADO** en `develop`. El pendiente del log ya no aplica.

#### M3 — Pendiente #5 ("filas sucias en `recursos`") cerrado en `2c7e4a5`

`docs/src/OPERATIONS_SESSION_2026-05-17.md:430-438`:

> 4. **`recursos.estado='activo' WITH quarantined_at NOT NULL`**: hay 2 filas con esos campos sucios […]

El commit `2c7e4a5` declara textualmente:

> 5) filas sucias en `recursos` — Verificadas: 0 filas. El fix del embedder ya cubrió el caso […]

Estado: **CERRADO**.

#### M4 — Pendiente #5 del log mañana ("AUDIT_CRON_TOKEN rotación, sin alerta") mitigado en `2c7e4a5`

`docs/src/OPERATIONS_SESSION_2026-05-17.md:439-442` pide alerta si el token diverge entre `.env` y n8n.

`2c7e4a5` añade en `src/api/main.py` log de startup con WARN si falta y INFO con longitud (no valor) si está. No detecta divergencia con n8n, pero da visibilidad.

Estado: **PARCIALMENTE CERRADO**. La detección de divergencia entre n8n y backend sigue siendo manual.

### LOW

#### L1 — Pendiente #2 de la sesión tarde ("Reuso cross-tenant + policy") sin cambios

`docs/src/OPERATIONS_SESSION_2026-05-17.md:541-545` documenta como "por diseño" que un segundo tenant que añade una URL ya conocida hereda el estado global del primero.

Verificado: no hay migración a estado per-tenant en `infra/postgres/migrations/`. **Sigue por diseño**.

#### L2 — Pendiente #4 ("Pre-push hook no entiende `Depends`") parcialmente abordado

`docs/src/OPERATIONS_SESSION_2026-05-17.md:551-554` y `:537-540` (duplicado en el log) piden enseñar al prompt de pre-push a reconocer `Depends(...)`.

`2c7e4a5` arregló LiteLLM 401 en el hook (`ops/cron/litellm_client.py`), no el reconocimiento de `Depends`. Hubo además rondas 14-19 de refactor de hooks (`eb1da66`) pero no he validado si tocan el prompt de pre-push.

Estado: **PROBABLEMENTE ABIERTO**. Fuera de scope para este auditor; mencionar en la nota de seguimiento para que alguien lo confirme.

---

## VIGENTE — trabajo del log que sigue intacto

### Bug 1 — RAG streaming TypeError (variable shadowing `h`)
- `src/api/main.py:1838` — `litellm_headers = {...}`
- `src/api/main.py:1845` — `for hit in hits:` (renombrado)
- `src/api/main.py:1868` — `headers=litellm_headers,`
- Try/except en `_stream` con `data: {"type": "error", ...}` + `[DONE]` presente (`src/api/main.py:1873-1880`).
- Nota: hay otros `for h in hits` no problemáticos en scope distinto (`src/api/main.py:1779`, `:1849`). No reintroducen el bug porque no se solapan con la línea de `httpx.stream`.

### Bug 2 — Auth con refresh tokens
- `src/api/auth.py:27` — `ACCESS_TOKEN_EXPIRE_MINUTES = 30`
- `src/api/auth.py:28` — `REFRESH_TOKEN_EXPIRE_DAYS = 30`
- `src/api/auth.py:33` — `REFRESH_COOKIE = "cerebro_refresh"`
- `src/api/main.py:1011` — `@app.post("/auth/refresh")`
- Headers `X-Auth-Reason: missing|expired|invalid|no_user|no_refresh|refresh_invalid` presentes en `src/api/main.py:469-1071`.
- Reasons adicionales (`demo_invalid`, `demo_expired`) son evolución natural por el trabajo de demo de Slice 5-6, no contradice el log.
- Frontend: `src/frontend/lib/api.ts:21` (`refreshInFlight`), `:73` (`handleAuthFailure`), `:133` (retry on refresh OK).

### Bug 3 — Clipboard fallback
- `src/frontend/lib/clipboard.ts:16` — `copyToClipboard` con fallback `document.execCommand("copy")` (`:41`).
- Call sites migrados: 3 confirmados — `(app)/layout.tsx:228`, `(app)/profile/page.tsx:176`, `(app)/chat/page.tsx:22` (este último era `(app)/page.tsx::CopyBtn` antes del rename del H1).

### Bug 4 — n8n cron URL fix
- `infra/n8n/workflows/audit_cron_daily.json:25` — `"url": "http://cerebro-api:8001/admin/audit-cron"`.
- Endpoint manual: `src/api/main.py:1456` — `@app.post("/resources/audit-now")`.
- Botón en KB: `src/frontend/app/(app)/kb/page.tsx:112` — POST a `/resources/audit-now`.

### Bug 5 — Embedder pisaba estado='activo'
- Whitelist: `src/data/embedder_worker.py:348` — `EMBEDDER_EVENT_TYPES = frozenset({"recurso.procesado", "recurso.reusado"})`.
- Filtro: `src/data/embedder_worker.py:361-366`.
- Guard en DB: `src/data/db.py:459` — `AND estado = 'procesando'` (evolucionado para soportar también `procesando → expirado` con `auto_archive_pending=true`, ver `:476`).
- La ampliación posterior (migración 0007) **endurece** el guard sin debilitarlo.

### Sesión tarde — Clasificación temporal + policy JSONB
- Migraciones presentes: `infra/postgres/migrations/0006_temporal_class_y_strictness.sql`, `infra/postgres/migrations/0007_audit_policy_y_auto_archive.sql`.
- `_get_user_audit_policy` con cache 60s: `src/data/db.py:60`.
- Policy-driven `save_with_outbox`: `src/data/db.py:255-289`.
- Endpoint: `src/api/main.py:1161` — `@app.put("/profile/audit-policy")`.
- `AUDIT_PRESETS`, `matchPreset`, `AuditPolicyKey`: `src/frontend/lib/auth.ts:16-57`.
- `_emit_auto_archive_event`: `src/data/embedder_worker.py:522` + emisión en `:463`.
- Notifier copy: `src/notifier/worker.py:50` (`evento_pasado`) y `:52` (`auto_archive`).
- Toggle "Archivo ON": `src/frontend/app/(app)/chat/page.tsx:242` (`include_archive: useArchive`), `:488` (copy ámbar).
- REASON_META con `evento_pasado` + `CalendarX`: `src/frontend/app/(app)/quarantine/page.tsx:55`.
- `_NotificationsBell` extendido: `src/frontend/app/(app)/_NotificationsBell.tsx:29` y `:37`.

### Commits citados existen y siguen en `develop`
- `021c3ab feat(audit): clasificación temporal del LLM + audit_policy JSONB por celda` ✓
- `41bfd39 feat(profile-modal): card de Auditoría de recursos en el panel lateral` ✓
- `37d4737 fix(notifications): emite evento outbox cuando auto-archive transiciona` ✓
- (No mencionado pero relevante) `ba405e2` empaqueta los 5 bugs reactivos y el propio doc.

---

## Recomendación de follow-up (no edición del log)

Crear un documento separado — sugerencia de path:

```
docs/src/OPERATIONS_FOLLOWUP_2026-05-19_sobre-2026-05-17.md
```

Contenido propuesto (resumen, no draft):

1. **Pendientes del log cerrados** — apuntar a commits `2c7e4a5` (logout backend, AUDIT_CRON_TOKEN log, filas sucias verificadas en 0, LiteLLM 401 del hook) y `eb1da66` (refactor hooks rondas 14-19). Cualquiera que lea el log debería saber que la lista de "Pendientes detectados y NO resueltos" ya no aplica en su mayor parte.
2. **Pendientes que SIGUEN abiertos**:
   - Cola zombie `q.embeddings` está purgada en RabbitMQ pero **se recrea** desde `infra/rabbitmq/definitions.json:70`. Si se quiere eliminar de raíz, hay que quitar la queue + binding del JSON y actualizar `infra/test_health.py:136`.
   - Reuso cross-tenant sigue heredando `estado` global del primer tenant. Por diseño.
   - Pre-push hook reconociendo `Depends()` de FastAPI — confirmar si las rondas de refactor del hook lo abordaron.
3. **Renames de ficheros** que afectan a la lectura del log:
   - `src/frontend/app/(app)/page.tsx` → `src/frontend/app/(app)/chat/page.tsx` (commit `7439d07`).
4. **No revertido**: no se ha encontrado ningún fix técnico del log que haya sido desecho.

Este documento de seguimiento le ahorra a un nuevo lector ~30 min de diff archaeology y deja claro qué del log ya forma parte del estado vigente y qué quedó por cerrar.

---

## Apéndice — comandos usados

```
ssh linkanvil 'cd /root/linkanvil && git log --oneline --since="2026-05-17" develop'
ssh linkanvil 'cd /root/linkanvil && git show 2c7e4a5 --stat'
ssh linkanvil 'cd /root/linkanvil && grep -n "litellm_headers" src/api/main.py'
ssh linkanvil 'cd /root/linkanvil && grep -n "EMBEDDER_EVENT_TYPES" src/data/embedder_worker.py'
ssh linkanvil 'cd /root/linkanvil && grep -n "cerebro-api:8001" infra/n8n/workflows/audit_cron_daily.json'
ssh linkanvil 'cd /root/linkanvil && grep -n "X-Auth-Reason\|/auth/refresh" src/api/main.py'
ssh linkanvil 'cd /root/linkanvil && ls infra/postgres/migrations/'
ssh linkanvil 'cd /root/linkanvil && grep -rn "copyToClipboard" src/frontend/app/'
ssh linkanvil 'cd /root/linkanvil && grep -n "q.embeddings" infra/rabbitmq/definitions.json'
```
