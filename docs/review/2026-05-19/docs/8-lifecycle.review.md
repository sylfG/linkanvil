# Review · 8-lifecycle · 2026-05-19

**Auditor**: docs-reality-auditor
**Doc revisado**: `docs/src/8-lifecycle.md`
**Áreas de código verificadas**:
- `src/data/audit_cron.py`
- `src/data/db.py`
- `src/api/database.py`
- `src/data/embedder_worker.py`
- `src/api/main.py`
- `src/api/models.py`
- `src/scraper/worker.py`
- `src/notifier/worker.py`
- `src/frontend/lib/auth.ts`
- `infra/postgres/migrations/0006_temporal_class_y_strictness.sql`
- `infra/postgres/migrations/0007_audit_policy_y_auto_archive.sql`

**Versión del repo**: `develop @ 7c723f3`

## Resumen
- 1 CRITICAL, 5 HIGH, 6 MEDIUM, 2 LOW, 3 UNVERIFIED
- 1 hallazgo [CODE-BUG]
- **Veredicto: RED** (CRITICAL en el SQL documentado del audit cron + drift relevante en endpoints/funciones)

---

## Hallazgos

### [CRITICAL] El SQL "Fase A" del cron documentado omite el filtro `temporal_class = 'evento'`

- **Ubicación**: §4.1 — bloque SQL líneas ~219-227 del doc.
- **Lo que dice el doc**:
  > ```sql
  > UPDATE recursos
  > SET estado = 'cuarentena',
  >     quarantined_at = NOW(),
  >     quarantine_reason = 'caducidad',
  >     quarantine_grace_until = (NOW() + OBSOLESCENCE_GRACE_DAYS * INTERVAL '1 day')::DATE,
  >     updated_at = NOW()
  > WHERE estado = 'activo'
  >   AND fecha_caducidad IS NOT NULL
  >   AND fecha_caducidad <= NOW()::DATE;
  > ```
- **Realidad en el código**: el UPDATE real añade un filtro `temporal_class = 'evento'` como defensa en profundidad. Evidencia: `src/data/audit_cron.py:108-121` (lines: `WHERE estado = 'activo' AND temporal_class = 'evento' AND fecha_caducidad IS NOT NULL AND fecha_caducidad <= NOW()::DATE`). El comentario en `:122-130` explica que es defensa en profundidad por si una `referencia` queda con `fecha_caducidad` rellena por error.
- **Cambio sugerido**:
  ```markdown
  ```sql
  -- Fase A: caducidad → cuarentena
  UPDATE recursos
  SET estado = 'cuarentena',
      quarantined_at = NOW(),
      quarantine_reason = 'caducidad',
      quarantine_grace_until = (NOW() + OBSOLESCENCE_GRACE_DAYS * INTERVAL '1 day')::DATE,
      updated_at = NOW()
  WHERE estado = 'activo'
    AND temporal_class = 'evento'         -- defensa en profundidad (migración 0006)
    AND fecha_caducidad IS NOT NULL
    AND fecha_caducidad <= NOW()::DATE;
  ```
  ```

---

### [HIGH] El doc dice que el endpoint admin se llama `/admin/audit-cron`; ese path existe, pero el método real no usa `X-Admin-Token` solamente

- **Ubicación**: §4.1 tabla "Endpoints" y §9 tabla "Endpoints HTTP" (línea aprox. `POST /admin/audit-cron`).
- **Lo que dice el doc**:
  > `POST /admin/audit-cron` — interfaz para el cron de n8n (token admin).
  > `POST /admin/audit-cron` | `X-Admin-Token` | `run_audit_cron` | Para n8n cron
- **Realidad en el código**: endpoint declarado en `src/api/main.py:1889` (`@app.post("/admin/audit-cron")`). El token `AUDIT_CRON_TOKEN` aparece sólo como variable en `src/api/main.py:410` (warning) — UNVERIFIED si el dependency real verifica `X-Admin-Token` o utiliza otro mecanismo (no se ha mostrado la firma de la función).
- **Estado**: parcialmente verificable; el path coincide. Marcar como UNVERIFIED-PARTIAL hasta confirmar el dependency.

---

### [HIGH] El doc afirma "fecha_caducidad IS NULL → invisible para el cron. Hoy ningún flujo deja caducidad en NULL"

- **Ubicación**: §4.1 (último párrafo).
- **Lo que dice el doc**:
  > "Hoy ningún flujo deja caducidad en NULL (siempre hay fallback `today + useful_life`); ver `prompts.md` §6 para la propuesta de contenido histórico/evergreen que sí lo aprovecharía."
- **Realidad en el código**: incorrecto. La lógica de `save_with_outbox` deja `fecha_caducidad = None` en todos los casos en que `temporal_class != 'evento'` (referencia / evergreen) y en todos los casos "pasado" cuando aplica la policy. Evidencia: `src/data/db.py:317-326` (`if temporal_class == "evento": ... else: fecha_caducidad = None`) y `src/data/db.py:355-358` (`fecha_caducidad = None` tras decisión policy-driven).
- **Cambio sugerido**:
  ```markdown
  **fecha_caducidad IS NULL → invisible para el cron**. Esto es un
  escape hatch para tres flujos que hoy ya lo aprovechan:
  - `temporal_class='referencia'` y `temporal_class='evergreen'` siempre
    nacen con caducidad NULL (`src/data/db.py:325`).
  - Cualquier recurso pasado que la policy mande a `cuarentena` o
    `expirado` se limpia su `fecha_caducidad` (`src/data/db.py:357`) —
    el ciclo temporal cede el control al ciclo policy-driven.

  El cron sigue sirviendo para el caso clásico `evento` futuro cuya
  fecha vence.
  ```

---

### [HIGH] El doc cita rangos de líneas para `get_active_resource_ids` y `quarantine_recurso` que no coinciden con el archivo actual

- **Ubicación**: §3 ("Filtra hits"), §4.3 ("Función DB: `quarantine_recurso`"), §7 ("Función DB: `delete_recurso_for_tenant`").
- **Lo que dice el doc**:
  > `get_active_resource_ids(tenant_id, recurso_ids)` (`src/api/database.py:121-135`)
  > `quarantine_recurso(tenant_id, recurso_id)` (`src/api/database.py:380-420`)
  > `delete_recurso_for_tenant(tenant_id, recurso_id)` (`src/api/database.py:448-490`)
- **Realidad en el código**:
  - `get_active_resource_ids` está en `src/api/database.py:538-565` (no 121-135).
  - `quarantine_recurso` está en `src/api/database.py:805-846` (no 380-420).
  - `delete_recurso_for_tenant` está en `src/api/database.py:883-…` (no 448-490).
  - Evidencia: grep `src/api/database.py` líneas 538, 598, 631, 757, 805, 848, 883.
- **Cambio sugerido**:
  ```markdown
  - `get_active_resource_ids` (`src/api/database.py:538`).
  - `quarantine_recurso` (`src/api/database.py:805`).
  - `delete_recurso_for_tenant` (`src/api/database.py:883`).
  ```

---

### [HIGH] El doc cita líneas del endpoint DELETE en `main.py:565-602`/`578-602`; el endpoint real está en `src/api/main.py:1520`

- **Ubicación**: §7, párrafo introductorio.
- **Lo que dice el doc**:
  > **Endpoint**: `DELETE /resources/{id}` (`src/api/main.py:565-602`).
  > **Cleanup de Qdrant** (`src/api/main.py:578-602`, fuera de la transacción SQL …)
- **Realidad en el código**: el handler real está en `src/api/main.py:1520` (`@app.delete("/resources/{recurso_id}")`). El cleanup de Qdrant ocupa aprox. `src/api/main.py:1568-1599`. El rango `565-602` no coincide en absoluto (en esas líneas hay código de auth/refresh).
- **Cambio sugerido**:
  ```markdown
  **Endpoint**: `DELETE /resources/{id}` (`src/api/main.py:1520`).

  …

  **Cleanup de Qdrant** (`src/api/main.py:1568-1599`, fuera de la transacción SQL …)
  ```

---

### [HIGH] El doc dice "rescate fast-track desde `expirado`" emite el mismo evento que desde cuarentena; lo emite, pero el rescate **no** filtra por tenant_id en el outbox

- **Ubicación**: §6 tabla "Qué puede hacer el usuario" (fila Rescate fast-track).
- **Lo que dice el doc**:
  > Rescate fast-track | `POST /resources/{id}/rescue` | Mismo que en cuarentena. Permitido para `estado IN ('cuarentena','expirado')`
- **Realidad en el código**: `rescue_recurso` (`src/api/database.py:757-807`) emite el outbox con `tenant_id = caller` (el rescatador). En cambio, `quarantine_recurso` (`src/api/database.py:805-846`) y `expire_recurso` (`src/api/database.py:848-880`) iteran sobre `SELECT tenant_id FROM usuario_recursos ...` y emiten **uno por tenant linkeado**. El doc afirma que el rescate emite "outbox `recurso.rescatado`" en singular en §4.3 y luego "emite outbox por cada tenant que tenga linkeado el recurso" en §6/Anexo B (línea de la tabla outbox dice "rescue_recurso"). El comportamiento real difiere — el rescate sólo notifica al rescatador, no a los demás tenants.
- **Cambio sugerido**:
  ```markdown
  | Rescatar (volver a activo) | `POST /resources/{id}/rescue` | … Emite outbox `recurso.rescatado` **sólo para el tenant que rescata** (a diferencia de quarantine/expire que iteran sobre todos los tenants linkeados). |
  ```
- **[CODE-BUG]** posible asimetría: `quarantine_recurso` y `expire_recurso` notifican a todos los tenants linkeados, pero `rescue_recurso` sólo notifica al caller. Si es intencional, conviene documentarlo; si no, los demás tenants ven el recurso "rescatado" sin recibir notificación. Flag para revisión.

---

### [MEDIUM] El doc nombra el evento outbox doble `recurso.expirado` con varios motivos en la misma fila de la tabla

- **Ubicación**: §9 tabla "Eventos outbox", fila `recurso.expirado (motivos caducidad/gracia_agotada/manual/auto_archive)`.
- **Lo que dice el doc**:
  > `recurso.expirado` (motivos `caducidad`/`gracia_agotada`/`manual`/`auto_archive`) | `audit_cron` Fase B, `expire_recurso`, embedder (auto-archive) | notifier, frontend
- **Realidad en el código**:
  - `audit_cron` Fase B emite con `motivo='gracia_agotada'` (`src/data/audit_cron.py:152`). No emite con motivo `caducidad` — eso correspondería a Fase A pero allí el evento es `recurso.cuarentena`, no `recurso.expirado`.
  - `expire_recurso` emite con `motivo='manual'` (`src/api/database.py:875`).
  - Embedder auto-archive emite con `motivo='auto_archive'` (`src/data/embedder_worker.py:545`).
  - Por tanto, **`motivo='caducidad'` no se emite jamás como `recurso.expirado`** — es sólo motivo de `recurso.cuarentena`. El doc lista 4 motivos pero sólo existen 3.
- **Cambio sugerido**:
  ```markdown
  | `recurso.expirado` (motivos `gracia_agotada`/`manual`/`auto_archive`) | `audit_cron` Fase B, `expire_recurso`, embedder (auto-archive) | notifier, frontend |
  ```

---

### [MEDIUM] El copy humano del notifier difiere del documentado para `auto_archive`

- **Ubicación**: §9 sub-tabla "Mapping `motivo` → copy del notifier-worker".
- **Lo que dice el doc**:
  > | `recurso.expirado` | `auto_archive` ⭐ | "se archivó automáticamente. Recuperable en chat con toggle Archivo ON" |
- **Realidad en el código**: hay dos copies distintos en el notifier:
  - `REASON_LABELS["auto_archive"] = "tiene fecha pasada y se archivó automáticamente"` (`src/notifier/worker.py:52`).
  - El mensaje completo de Telegram en `_human_message` es: `"📦 Tu recurso \"{label}\" se archivó automáticamente al detectar valor archivístico alto. Recuperable en el chat con el toggle \"Archivo ON\"."` (`src/notifier/worker.py:70-74`).
  - Ninguno coincide bit-a-bit con la cadena del doc. La doc no aclara si cita la etiqueta interna o el copy final.
- **Cambio sugerido**:
  ```markdown
  | `recurso.expirado` | `auto_archive` ⭐ | etiqueta interna: "tiene fecha pasada y se archivó automáticamente"; copy completo Telegram: "se archivó automáticamente al detectar valor archivístico alto. Recuperable en chat con toggle Archivo ON" |
  ```

---

### [MEDIUM] El doc dice que el evento `recurso.expirado` con `motivo='auto_archive'` lo emite el embedder; el embedder usa `_emit_auto_archive_event`, no el path indicado

- **Ubicación**: §8 tabla Anexo A, fila `expirado` columna "Notificación emitida".
- **Lo que dice el doc**:
  > `motivo='auto_archive'` (migración 0007, emitido por el embedder tras la transición)
- **Realidad en el código**: confirmado, lo emite `embedder_worker._emit_auto_archive_event` en `src/data/embedder_worker.py:521-560`. **Sin embargo**, el evento se emite **antes** de que `_build_chunks_from_text` corra (la línea `:466` llama `_emit_auto_archive_event` y luego `:471` llama `_build_chunks_from_text`). El doc afirma que se emite "tras la transición" — verificado parcialmente: tras la transición a `expirado`, sí, pero antes del chunking. Más detalle informativo que crítico.

---

### [MEDIUM] El cron-schedule documentado tiene inconsistencia interna

- **Ubicación**: §4.1 tabla "Disparadores", fila "Cron nocturno".
- **Lo que dice el doc**:
  > Cron nocturno | n8n workflow `linkanvil — audit cron diario` (cron `0 3 * * *`, ejecuta a las 07:00 UTC en TZ del contenedor)
- **Realidad en el código**: el cron es externo (n8n), no verificable directamente desde el repo. La inconsistencia es semántica: `0 3 * * *` se ejecuta a las 03:00 (en la TZ del scheduler), no a las 07:00 UTC. Si el contenedor está en UTC, el cron corre a las 03:00 UTC. Si el cron está expresado en UTC y se quiere ejecutar a las 07:00 UTC, debería ser `0 7 * * *`.
- **Estado**: UNVERIFIED-DRIFT — la afirmación "07:00 UTC" no se puede comprobar sin acceso al workflow n8n; pero el cron `0 3 * * *` no equivale a 07:00 UTC.
- **Cambio sugerido**:
  ```markdown
  Cron nocturno | n8n workflow `linkanvil — audit cron diario` (cron `0 3 * * *` = 03:00 UTC) | …
  ```

---

### [MEDIUM] El doc menciona "El doc cita `quarantine_recurso_blocked` no", pero el código tiene función auxiliar adicional sin documentar

- **Ubicación**: gap — no aparece en el doc.
- **Realidad en el código**: existe `quarantine_recurso_blocked` (`src/data/db.py:497-516`) que cuarentena un recurso cuando el scraper recibe una página de bloqueo anti-bot. Usa motivo `manual` (porque el CHECK constraint no acepta `scrape_bloqueado`) y `quarantine_grace_until = today + 30d`. Es un cuarto camino que lleva a `cuarentena`, no documentado en §4.
- **Cambio sugerido**:
  ```markdown
  ### 4.4 Camino scrape-bloqueado (anti-bot)

  Si el scraper recibe una página de bloqueo anti-bot y no puede extraer
  el contenido, `quarantine_recurso_blocked` (`src/data/db.py:497`)
  cuarentena el recurso con `quarantine_reason='manual'` y gracia 30
  días — el CHECK constraint actual no acepta un motivo
  `scrape_bloqueado` dedicado.
  ```

---

### [MEDIUM] El doc no menciona el flujo demo intra-sesión `run_demo_audit_for_session`

- **Ubicación**: gap — no aparece en el doc.
- **Realidad en el código**: `src/data/audit_cron.py:184-306` define `run_demo_audit_for_session` para sesiones demo Slice 6. Tiene precisión TIMESTAMPTZ (no DATE), lee de `demo_session_events`, y reusa el mismo pipeline outbox. Cambia transiciones de `'activo' → 'cuarentena'` y de `IN ('activo','cuarentena') → 'expirado'`. Esto es relevante para el ciclo de vida en el contexto demo (Slice 6.x mencionado en el prompt del auditor).
- **Cambio sugerido**: añadir nota en §4.1:
  ```markdown
  **Demo intra-sesión**: las sesiones demo (Slice 6) usan
  `run_demo_audit_for_session` (`src/data/audit_cron.py:184`) que opera
  sobre `demo_session_events` con precisión TIMESTAMPTZ en vez de DATE
  para simular el ciclo en 15 minutos. Reusa el mismo outbox/notifier.
  ```

---

### [MEDIUM] El doc afirma que `quarantine_recurso` permite transición desde `procesando`; la implementación cubre `'activo'` y `'procesando'` pero el handler HTTP no lo expone

- **Ubicación**: §9 tabla Endpoints fila "POST /resources/{id}/quarantine".
- **Lo que dice el doc**:
  > `POST /resources/{id}/quarantine` | JWT + CSRF | `quarantine_recurso` | Solo desde `activo` o `procesando`
- **Realidad en el código**: `src/api/database.py:805-846` filtra `WHERE id = $1::uuid AND estado IN ('activo','procesando')` — verificado. ✓
- **Estado**: aprobado (sin cambios).

---

### [LOW] Typo en nombre del archivo de referencia

- **Ubicación**: encabezado del doc, líneas 6-7.
- **Lo que dice el doc**:
  > Para una vista narrativa con ejemplos, ver [`5_ejemplo_flujo copy.md`](./5_ejemplo_flujo%20copy.md).
- **Realidad en el código**: el archivo real es `docs/src/9-ejemplo_flujo.md` (renombrado en commit `57ca84f` y `7c723f3`). El path `5_ejemplo_flujo copy.md` con espacio y "copy" sugiere copia accidental del macOS Finder que no fue limpiada.
- **Cambio sugerido**:
  ```markdown
  Para una vista narrativa con ejemplos, ver [`9-ejemplo_flujo.md`](./9-ejemplo_flujo.md).
  ```

---

### [LOW] Typo en path al prompts en el encabezado

- **Ubicación**: línea 8.
- **Lo que dice el doc**:
  > Para los prompts que el LLM ejecuta en cada fase, ver [`prompts.md`](./prompts.md).
- **Realidad en el código**: el archivo real es `docs/src/7-prompts.md` (commit `57ca84f` renombró `6-prompts.md` → `7-prompts.md`). No existe `prompts.md` plano en `docs/src/`.
- **Cambio sugerido**:
  ```markdown
  ver [`7-prompts.md`](./7-prompts.md).
  ```

---

### [UNVERIFIED] Lista `recursos:{tenant}` Redis pub/sub para SSE en bell + badges sidebar

- **Ubicación**: §9 sección "Pipeline de propagación de la notificación".
- **Lo que dice el doc**:
  > Redis PUBLISH `resources:{tenant}` (SSE → bell + sidebar badges)
- **Realidad en el código**: no he leído `src/notifier/worker.py` completo ni `src/api/main.py` SSE handlers para confirmar el formato exacto del canal. La función `f7a4559 feat(notifier): publicar a Redis pub/sub para SSE en tiempo real` sugiere que sí existe — pero el canal exacto no fue verificado en este audit.

---

### [UNVERIFIED] El endpoint `POST /admin/audit-cron` usa exactamente el header `X-Admin-Token`

- **Ubicación**: §9 tabla "Endpoints HTTP".
- **Lo que dice el doc**:
  > `POST /admin/audit-cron` | `X-Admin-Token` | `run_audit_cron`
- **Realidad en el código**: visible `@app.post("/admin/audit-cron")` en `src/api/main.py:1889` pero no he leído el dependency. Marcar UNVERIFIED hasta confirmar el nombre exacto del header en la lógica de auth admin.

---

### [UNVERIFIED] Endpoint `GET /resources/quarantine` y `GET /resources/expired` permiten `count_only`

- **Ubicación**: §9 tabla.
- **Lo que dice el doc**:
  > `GET /resources/quarantine` | JWT | `list_quarantine` | Lista para UI `/quarantine`
  > `GET /resources/expired` | JWT | `list_expired` | Lista para UI `/expired`
- **Realidad en el código**: ambos handlers (`src/api/main.py:1391`, `:1404`) tienen rama `return {"count": …}` (líneas 1399 y 1412) que el doc no menciona. Es un modo de operación adicional (probable query-param `?count_only=true`); no documentado en la tabla.

---

## [CODE-BUG]

### Asimetría rescate vs cuarentena/expire en notificaciones multi-tenant

- **Síntoma**: `rescue_recurso` (`src/api/database.py:757-807`) emite `recurso.rescatado` sólo para el tenant que rescata. `quarantine_recurso` (`src/api/database.py:805-846`) y `expire_recurso` (`src/api/database.py:848-880`) iteran sobre `SELECT tenant_id FROM usuario_recursos WHERE recurso_id = $1` y emiten un evento por tenant linkeado. Como `recursos` es global (mismo recurso compartido entre N tenants), si un tenant rescata un recurso compartido, los demás tenants que lo tenían linkeado verán que el recurso vuelve a `activo` (porque el estado es global) sin recibir notificación in-app, Telegram o SSE. No es un mismatch con el doc — el doc lo describe en singular pero no es del todo claro — sino una inconsistencia interna del código que vale la pena revisar.
- **Evidencia**:
  - `src/api/database.py:805-816` (quarantine itera tenants).
  - `src/api/database.py:866-878` (expire itera tenants).
  - `src/api/database.py:790-805` (rescue sólo emite para caller).

---

## Aprobado sin cambios

- §1 "Cuatro estados válidos" (procesando/activo/cuarentena/expirado) — verificado contra `infra/postgres/migrations/0006_temporal_class_y_strictness.sql:24-28` (CHECK quarantine_reason), `src/data/db.py:283-289` (DEFAULT_AUDIT_POLICY) y schema base (CHECK estado en migración previa, implícito en defaults).
- §2 "Tres presets canónicos" — los 6 valores de la tabla coinciden bit-a-bit con `src/frontend/lib/auth.ts:24-49` (AUDIT_PRESETS) y con la migración 0007 (`infra/postgres/migrations/0007_audit_policy_y_auto_archive.sql:28-37` default + 64-72 estricto + 76-84 permisivo). El backend acepta cualquier policy con las 6 keys (`src/api/models.py:113-138` AuditPolicyRequest.validate_policy).
- §2 "audit_policy JSONB con 6 keys" — coincide con `DEFAULT_AUDIT_POLICY` en `src/data/db.py:283-290` y `_POLICY_KEYS` en `src/api/models.py` y migración 0007.
- §2 "Decisión policy-driven" para evento_pasado y referencia_pasada — verificado en `src/data/db.py:330-365` (composición de key `{evento_pasado|referencia_pasada}_{alto|medio|nulo}` + lectura de policy.get(key, "cuarentena")).
- §3 "Filtra hits por `get_active_resource_ids(...)` ... ejecuta `SELECT id FROM recursos WHERE estado='activo'`" — verificado funcionalmente en `src/api/database.py:538-565` (filtra `estado = ANY($2::text[])` con `allowed_states = ['activo']` por defecto). El SQL exacto no es literal pero la semántica coincide.
- §3 "Toggle Archivo ON" → coincide con `include_archive: bool = False` en `src/api/models.py:144-150` (ChatRequest) y `req.include_archive` en `src/api/main.py:1768`.
- §4.1 "rate-limit 5/min por tenant en Redis `rl:audit:{tenant_id}`" — UNVERIFIED nombre exacto del key Redis, pero `rate_limit_audit` se usa en `src/api/main.py:1457`. ✓ uso confirmado, key no.
- §5 "Qué cambia / Qué NO cambia" en cuarentena — vectores Qdrant siguen, contenido/resumen siguen: verificado por ausencia en `quarantine_recurso` (`src/api/database.py:805-846`) y en cron Fase A (`src/data/audit_cron.py:108-130`) de cualquier llamada a Qdrant.
- §5 "Rescate recalcula `fecha_caducidad` según `volatilidad`" baja=+365, media=+180, alta=+60, dinamica=+30 — verificado bit-a-bit en `src/api/database.py:770-781` (rescue_recurso) y como mapa estático `_VOLATILITY_DAYS` (`src/api/database.py:602`).
- §5 "El rescate permite estado IN ('cuarentena','expirado')" — verificado en `src/api/database.py:781` (`WHERE id = $1::uuid AND estado IN ('cuarentena','expirado')`).
- §6 "Auto-archive sí vectoriza, transiciona a expirado, chunks indexados" — verificado en `src/data/embedder_worker.py:444-469` (target_estado = "expirado" if auto_archive, _build_chunks_from_text se llama después).
- §7 "Si Qdrant falla durante el cleanup, vector queda huérfano" — verificado: el cleanup vive en bloque `try/except` con `logger.warning` (`src/api/main.py:1577-1599`) fuera de la transacción SQL.
- §9 "auto_archive_pending BOOLEAN" — verificado en `infra/postgres/migrations/0007_audit_policy_y_auto_archive.sql:96-99`.
- §9 "temporal_class CHECK ('evento','referencia','evergreen')" — verificado en `infra/postgres/migrations/0006_temporal_class_y_strictness.sql:35-37`.
- §9 "valor_archivistico CHECK ('alto','medio','nulo')" — verificado en `infra/postgres/migrations/0006_temporal_class_y_strictness.sql:38-40`.
- §9 "quarantine_reason CHECK incluye 'evento_pasado'" — verificado en `infra/postgres/migrations/0006_temporal_class_y_strictness.sql:28-31`.
- §9 "GRACE_PERIOD_DAYS=30 default desde `OBSOLESCENCE_GRACE_DAYS`" — verificado en `src/data/audit_cron.py:14` y `src/data/db.py:11`.
- §9 "evento outbox `recurso.procesado` consumido por whitelist del embedder" — verificado: `EMBEDDER_EVENT_TYPES = frozenset({"recurso.procesado", "recurso.reusado"})` (`src/data/embedder_worker.py:348`).
- §2 "fecha_caducidad fallback `today + useful_life_days`" — verificado en `src/data/db.py:321-324`.
- §2 "`temporal_class` ∈ {evento, referencia, evergreen}", "`valor_archivistico` ∈ {alto, medio, nulo}" — verificado en el prompt del scraper (`src/scraper/worker.py:92-104`) y defaults en `:143-146`.
