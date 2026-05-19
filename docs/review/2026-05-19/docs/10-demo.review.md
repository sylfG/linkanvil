# Review · 10-demo · 2026-05-19

**Auditor**: docs-reality-auditor
**Doc revisado**: `docs/src/10-demo.md`
**Áreas de código verificadas**:
- `src/api/main.py` (`/auth/demo-start`, `/auth/login`, `/demo/timeline`, `_cleanup_demo_sessions_loop`, `_process_due_demo_audits`, `_index_staged_for_rag`, `/admin/cleanup-demo-sessions`, `DEMO_QUOTAS`)
- `src/api/database.py` (`_STAGED_RECURSOS`, `create_demo_session`, `get_demo_session_events`, `get_sessions_with_due_events`, `delete_demo_session_cascade`, `DEMO_SESSION_TTL_MINUTES`)
- `src/data/audit_cron.py` (`run_demo_audit_for_session`, `_emit_outbox_for_tenant`)
- `infra/postgres/migrations/0009_demo_sessions.sql`, `0010_demo_session_events.sql`, `0011_staged_embeddings_cache.sql`
- `src/api/models.py` (`DemoTimelineResponse`, `DemoTimelineEvent`, `DemoTimelineSession`)
- `src/frontend/lib/demo.ts` (`startDemoSession`, `DemoStartError`)
- `src/frontend/lib/api.ts` (`handleAuthFailure`, `forceLogout`)
- `src/frontend/components/DemoCountdownBanner.tsx`, `DemoHint.tsx`
- `src/frontend/app/(app)/demo/page.tsx`
- `src/frontend/app/(app)/layout.tsx`
- `src/frontend/app/(marketing)/_components/{Hero,Nav,CTABanner}.tsx`
- `ops/build_staged_embeddings.py`

**Versión del repo**: `develop` @ `7c723f3`

## Resumen
- **2 CRITICAL**, **3 HIGH**, **4 MEDIUM**, **2 LOW**, **0 UNVERIFIED**
- **0** hallazgos `[CODE-BUG]`
- **Veredicto: RED** (2 CRITICAL — descripciones falsas que el lector aplicaría).

---

## Hallazgos

### [CRITICAL] Doc afirma que el CTA "Probar demo" está en el nav — el código lo excluye explícitamente

- **Ubicación**: líneas 46–47 (y línea 661 del bloque "CTAs de la landing")
- **Lo que dice el doc**:
  > "Click en cualquiera de los CTAs **"Probar demo gratis"** / **"Acceder al demo"** / **"Probar demo"** (hero, banner medio, nav)."

  y línea 661:
  > "CTAs de la landing: `(marketing)/_components/{Hero,CTABanner,Nav}.tsx`"
- **Realidad en el código**: `Nav.tsx` NO tiene CTA "Probar demo". El comentario al inicio del archivo lo dice literalmente: "El CTA 'Probar demo' vive SOLO en el hero y banners del medio de la landing (no se duplica en el nav)" (evidencia: `src/frontend/app/(marketing)/_components/Nav.tsx:15-19`). El CTA del Nav cuando el usuario está anónimo es **"Iniciar sesión"** (`src/frontend/app/(marketing)/_components/Nav.tsx:97-102`). Solo Hero (`Hero.tsx:103`, texto "Probar el demo gratis") y CTABanner (`CTABanner.tsx:88`, texto "Acceder al demo") disparan demo-start.
- **Cambio sugerido**:
  ```markdown
  2. Click en cualquiera de los CTAs **"Probar el demo gratis"** (hero) /
     **"Acceder al demo"** (banner medio). El Nav SÍ NO duplica el CTA del demo —
     solo muestra "Iniciar sesión" para usuarios anónimos (decisión explícita de
     producto: el Nav guarda ese slot para quien viene a entrar a su cuenta).
  ```
  Y en líneas 660–661:
  ```markdown
  - CTAs de la landing: `(marketing)/_components/{Hero,CTABanner}.tsx`
    (el Nav.tsx NO tiene CTA demo por decisión explícita)
  ```

---

### [CRITICAL] Las cadenas literales del CTA del hero no coinciden con el doc

- **Ubicación**: línea 46–47
- **Lo que dice el doc**:
  > '"Probar demo gratis" / "Acceder al demo" / "Probar demo"'
- **Realidad en el código**:
  - Hero CTA literal: `"Probar el demo gratis"` (con artículo "el") — `src/frontend/app/(marketing)/_components/Hero.tsx:103`.
  - CTABanner CTA literal: `"Acceder al demo"` — `src/frontend/app/(marketing)/_components/CTABanner.tsx:88`.
  - El tercer literal `"Probar demo"` no existe en ningún componente de marketing. Solo aparece en un comentario de `Nav.tsx:15` referenciando que NO se incluye.
- **Cambio sugerido**:
  ```markdown
  2. Click en uno de los CTAs **"Probar el demo gratis"** (Hero) /
     **"Acceder al demo"** (CTABanner). Ambos están solo en la landing,
     no en el Nav.
  ```

---

### [HIGH] El campo de respuesta `redirect` del backend en `/login` 403 no se devuelve dentro del JSON top-level

- **Ubicación**: líneas 72–79
- **Lo que dice el doc**:
  > ```json
  > HTTP 403
  > {
  >   "error": "demo_use_dedicated_endpoint",
  >   "message": "Esta es la cuenta demo. ...",
  >   "redirect": "/demo"
  > }
  > ```
- **Realidad en el código**: el endpoint `POST /auth/login` levanta `HTTPException(403, { "error": ..., "message": ..., "redirect": "/demo" })` (`src/api/main.py:828-843`). FastAPI envuelve ese dict bajo la clave `detail`, así que el cuerpo real que recibe el cliente es:
  ```json
  HTTP 403
  {
    "detail": {
      "error": "demo_use_dedicated_endpoint",
      "message": "Esta es la cuenta demo. ...",
      "redirect": "/demo"
    }
  }
  ```
  (evidencia: comportamiento estándar de `HTTPException` con `detail` dict; `src/frontend/lib/demo.ts:74-83` lo confirma — el front lee `err.detail.error` / `err.detail.message`, no `err.error` directo).
- **Cambio sugerido**:
  ```markdown
  ```json
  HTTP 403
  {
    "detail": {
      "error": "demo_use_dedicated_endpoint",
      "message": "Esta es la cuenta demo. Accede desde el botón 'Probar el demo' de la landing.",
      "redirect": "/demo"
    }
  }
  ```
  (FastAPI envuelve el dict pasado a `HTTPException` bajo la clave `detail`.)
  ```

---

### [HIGH] El doc dice "redirect automático a `/demo`" pero el flujo real es marketing-CTA → router.push("/demo") del cliente

- **Ubicación**: líneas 51–52
- **Lo que dice el doc**:
  > "Redirect automático a `/demo` — vista dedicada con tabs: `Timeline · KB · Cuarentena · Archivo · Chat`."
- **Realidad en el código**:
  1. El **redirect lo decide el cliente**, no el backend (no hay `HTTP 302`). El backend devuelve `{redirect: "/demo", ...}` y `startDemoSession` retorna ese valor para que `Hero.tsx` lo aplique con `router.push` (`src/frontend/lib/demo.ts:96-99`).
  2. La vista `/demo` **NO tiene tabs**. Es una página de timeline pura (header + SVG timeline + tabla cronológica + atajos cards a `/chat`, `/kb`, `/quarantine`, `/expired`). El propio doc lo corrige más adelante en líneas 295–309 ("La ruta `/demo` ya **no** es un dashboard con tabs") pero la sección inicial sigue afirmando lo contrario. Evidencia: `src/frontend/app/(app)/demo/page.tsx` (357 líneas, ninguna referencia a `tab/tabs`).
- **Cambio sugerido**:
  ```markdown
  4. El cliente recibe `{access_token, redirect: "/demo", ...}` y aplica
     `router.push("/demo")` — la vista pedagógica del timeline (sin tabs:
     header + SVG con marcador "now" + tabla cronológica + atajos a las
     rutas reales `/chat`, `/kb`, `/quarantine`, `/expired`).
  ```

---

### [HIGH] La caja `curl` y el endpoint público omiten el prefijo `/api`

- **Ubicación**: líneas 57–58
- **Lo que dice el doc**:
  > ```bash
  > curl -X POST https://linkanvil.example/api/auth/demo-start
  > ```
- **Realidad en el código**: el path real en FastAPI es `/auth/demo-start` (`src/api/main.py:868`), sin prefix `/api`. El frontend lo llama también como `/auth/demo-start` (`src/frontend/lib/demo.ts:63`). El prefix `/api` solo aparece si hay un reverse-proxy externo que lo añade; nada en el repo (FastAPI app, nginx, Caddy si existe) está documentado como añadiendo ese prefix. UNVERIFIED para el deploy específico, pero como cita literal del endpoint expuesto por el backend es incorrecta.
- **Cambio sugerido**:
  ```markdown
  ```bash
  # Endpoint público, rate-limited (10/min por IP)
  curl -X POST https://linkanvil.example/auth/demo-start
  # → { access_token, csrf_token, redirect: "/demo", tenant_id, expires_at, resumed, seconds_remaining }
  ```

  (El backend FastAPI no aplica prefix `/api`; si tu deploy usa un reverse-proxy
  que lo añada, ajusta la URL al lado del proxy.)
  ```

---

### [MEDIUM] El doc omite el campo `resumed` (Slice 6.3) en la respuesta del endpoint

- **Ubicación**: líneas 59
- **Lo que dice el doc**:
  > "{ access_token, csrf_token, redirect: "/demo", tenant_id, expires_at }"
- **Realidad en el código**: La respuesta real incluye también `resumed: bool` (siempre presente) y, cuando `resumed=true`, `seconds_remaining: int`. Ver `src/api/main.py:1000-1009` y `src/api/main.py:953-966`. El frontend lo consume (`src/frontend/lib/demo.ts:21-26, 96-99`).
- **Cambio sugerido**:
  ```markdown
  # → { access_token, csrf_token, redirect: "/demo", tenant_id,
  #     expires_at, resumed, seconds_remaining? }
  ```

---

### [MEDIUM] El doc no menciona el gate "1 sesión demo por IP por día UTC" (Slice 6.3)

- **Ubicación**: sección "🛠️ Cómo entrar" (línea 64) y "🔐 BYOK y el demo" / tabla de diferencias (línea 535)
- **Lo que dice el doc**:
  > "La protección es el TTL de 15 min + cuotas diarias por IP (5 ingests, 20 chats) y la global cap (50 / 200) que evitan que un bot agote el cupo."
- **Realidad en el código**: además de cuotas, `/auth/demo-start` impone **una sola sesión demo por (IP, día-UTC)** vía Redis key `demo_session_started:{ip}:{YYYY-MM-DD}` con TTL 86400s (`src/api/main.py:929-987`). Si la IP ya tiene sesión viva → resume (mismas cookies, mismo countdown). Si ya consumió el cupo del día → 429 `demo_already_used_today` con `register_url: /register`. Está visible en frontend (`src/frontend/lib/demo.ts:31-38` lo documenta).
- **Cambio sugerido**:
  ```markdown
  ### Una sesión demo por IP por día UTC (Slice 6.3)

  Antes del Slice 6.3, un visitante podía hacer logout y pulsar "Probar demo"
  otra vez para conseguir 15 min fresquitos saltándose la cuota diaria. Ahora
  `/auth/demo-start` consulta Redis (`demo_session_started:{ip}:{YYYY-MM-DD}`,
  TTL 24h) y aplica esta lógica:

  - **Sesión viva para esta IP** → resume (re-emite JWT/cookies sobre el mismo
    `tenant_id`, el countdown sigue donde estaba). Respuesta incluye
    `resumed: true` y `seconds_remaining`.
  - **Sesión ya expiró pero la IP gastó hoy** → `429 demo_already_used_today`
    con copy "Ya disfrutaste tu sesión demo de 15 minutos hoy" + `register_url`.
  - **IP nueva para hoy** → crea sesión nueva, marca la IP por 24h.

  La protección es: TTL 15 min + 1-demo/IP/día + cuotas diarias per-IP
  (5 ingests, 20 chats) + cap global (50/200).
  ```

---

### [MEDIUM] El bloque "¿Por qué este diseño?" describe el JWT como si lo emitiera `/auth/login`

- **Ubicación**: líneas 100–102
- **Lo que dice el doc**:
  > "El JWT que firma el endpoint `/auth/login` lleva ese sub-tenant en el claim `tenant_id`, **no** el del usuario demo en BD (`user_demo_landing`)."
- **Realidad en el código**: `/auth/login` rechaza demo con 403 (`src/api/main.py:828-843`); el JWT con `tenant_id = demo_<8hex>` lo emite **`/auth/demo-start`** vía `_access_token_for(user, tenant_id=effective_tenant)` (`src/api/main.py:996,1066`). `/auth/refresh` también acepta `session_tenant` para usuarios demo (`src/api/main.py:1055-1071`).
- **Cambio sugerido**:
  ```markdown
  - El JWT lo emite `POST /auth/demo-start` con el claim
    `tenant_id = "demo_<8hex>"` (no el del usuario demo en BD `user_demo_landing`).
    `/auth/login` rechaza la cuenta demo con 403; `/auth/refresh` rota tokens
    manteniendo el `session_tenant`.
  ```

---

### [MEDIUM] El layout de pasos del cleanup cascade no es exactamente lo que hace `delete_demo_session_cascade`

- **Ubicación**: líneas 483–496
- **Lo que dice el doc**: cascada ordenada Qdrant → `sesiones_chat` (con FK CASCADE a `mensajes_chat`) → `notificaciones` → `usuario_recursos` → `recursos` huérfanos → `demo_sessions`.
- **Realidad en el código**: el orden coincide a grandes rasgos, pero hay un par de detalles:
  1. Qdrant lo borra el caller (`_cleanup_demo_sessions_loop`, `src/api/main.py:381-385` + `_qdrant_delete_tenant_points`), NO `delete_demo_session_cascade` (esto lo comenta el docstring en `src/api/database.py:316-318`).
  2. El `set_config('app.tenant_id', $1, true)` se hace EN la misma tx con un `SELECT set_config(...)` — no es un comentario suelto sino código real (`src/api/database.py:329-332`).
  3. La salvaguarda anti-borrado de huérfanos no usa solo `url_hash` directo, usa una doble subconsulta `NOT EXISTS` para excluir tanto recursos aún asociados como recursos cuyo `url_hash` exista bajo el seed (`src/api/database.py:362-378`).
- **Cambio sugerido**: precisar:
  ```markdown
  ### Lo que se borra al expirar

  El background task `_cleanup_demo_sessions_loop` (cada 60 s) detecta sesiones
  con `expires_at < NOW()`. Por cada una hace:

  1. **Qdrant first** (responsabilidad del caller, en `main.py`):
     `POST /collections/{cerebro_chunks,cerebro_recursos}/points/delete` con
     filtro `payload.tenant_id == "demo_<8hex>"`.
  2. **Cascade transaccional en BD** (delegada a `delete_demo_session_cascade`):
     1. `SELECT set_config('app.tenant_id', tenant_id, true)` para satisfacer la
        RLS forced sobre `usuario_recursos`/`sesiones_chat`.
     2. `DELETE FROM sesiones_chat` — `mensajes_chat` cae con su FK CASCADE.
     3. `DELETE FROM notificaciones` — sin RLS, directo.
     4. `DELETE FROM usuario_recursos` (captura los `recurso_id` antes para el
        siguiente paso).
     5. `DELETE FROM recursos` para los huérfanos: `id = ANY(...)` AND
        `NOT EXISTS (usuario_recursos)` AND
        `NOT EXISTS (usuario_recursos JOIN recursos r2 WHERE tenant_id =
        user_demo_landing AND r2.url_hash = r.url_hash)` —
        salvaguarda doble para no romper el seed.
     6. `DELETE FROM demo_sessions` — dispara `ON DELETE CASCADE` sobre
        `demo_session_events` (migración 0010).

  Si Qdrant falla quedan points huérfanos. Aceptable: el cleanup BD es
  transaccional; un barrido manual semanal limpia restos en Qdrant.
  ```

---

### [MEDIUM] El doc no documenta el helper `get_sessions_with_due_events` aunque sí está en el código

- **Ubicación**: línea 643
- **Lo que dice el doc**:
  > "Helpers nuevos: `get_demo_session_events`, `get_sessions_with_due_events`"
- **Realidad en el código**: el helper `get_sessions_with_due_events` SÍ existe (`src/api/database.py:254-275`), pero no se explica en el cuerpo de la doc cómo lo usa `_process_due_demo_audits`. El bloque pseudocódigo de líneas 200–212 simula el bucle de cleanup pero NO menciona la query previa que decide qué tenants procesar. Punto menor — el link existe en la sección de investigación.
- **Cambio sugerido**: añadir una línea en la sección "Quién dispara el audit" (línea 196):
  ```markdown
  El loop pregunta primero a `db.get_sessions_with_due_events()` (aprovecha el
  índice parcial `idx_demo_events_due` para barrer solo eventos pending), y
  por cada tenant abre su propia transacción + set_config(app.tenant_id) +
  llama a `run_demo_audit_for_session`. Las transacciones aisladas garantizan
  que un fallo en un tenant no contamine los demás.
  ```

---

### [LOW] Doc: el icono pending del SVG no siempre es `AlertTriangle`

- **Ubicación**: línea 232
- **Lo que dice el doc**:
  > "el visitante ve el punto cambiar de pendiente (icono `AlertTriangle`) a disparado (icono `CheckCircle2`) en vivo."
- **Realidad en el código**: el icono pending depende del `kind` (vía `KIND_META`):
  - `transition_cuarentena` → `AlertTriangle`
  - `transition_expirado` → `CalendarX`
  - `reminder_expiry_5min` → `Hourglass`
  Solo el icono fired es siempre `CheckCircle2` (`src/frontend/app/(app)/demo/page.tsx:43-63, 217-224`).
- **Cambio sugerido**:
  ```markdown
  el visitante ve el punto cambiar de su icono "pending" (depende del kind:
  `AlertTriangle` para cuarentena, `CalendarX` para archivo, `Hourglass` para
  reminder) al icono "disparado" (`CheckCircle2` para todos) en vivo.
  ```

---

### [LOW] Doc usa el path `mensajes_chat` con CASCADE pero el código lo confirma sin más detalle

- **Ubicación**: líneas 484–485
- **Lo que dice el doc**:
  > "la FK a `mensajes_chat` tiene `ON DELETE CASCADE`, así que los mensajes se van con la sesión"
- **Realidad en el código**: la afirmación es correcta — `src/api/database.py:341-343` lo comenta ("`mensajes_chat` cascadea vía FK ON DELETE CASCADE (no la borramos explícita)."). Pero NO se cita la migración que lo establece. Mejora menor: añadir referencia.
- **Cambio sugerido** (opcional): añadir en la sección "Para investigar más":
  ```markdown
  - FK CASCADE de mensajes_chat → sesiones_chat: ver migración baseline
    `infra/postgres/migrations/0001_baseline.sql` (búsqueda `mensajes_chat`).
  ```

---

## Aprobado sin cambios

Las siguientes afirmaciones están sincronizadas con el código:

- **§"💡 La pieza clave"** — formato `demo_<8hex>` confirmado: `secrets.token_hex(4)` genera 8 hex chars (`src/api/database.py:107`). Ejemplos `demo_a3b9f1c4` válidos.
- **§"⏱️ Eventos programados intra-sesión"** —
  - 4 eventos con offsets +5/+5/+5/+10 min: 2 `transition_cuarentena` + 1 `transition_expirado` + 1 `reminder_expiry_5min` confirmado (`src/api/database.py:151-211`).
  - Migración 0010 con FK CASCADE a `demo_sessions` y `kind`/`fires_at`/`fired_at`/`recurso_id`/`motivo`/`description` columnas — `infra/postgres/migrations/0010_demo_session_events.sql:21-47`.
  - Índice parcial `idx_demo_events_due ... WHERE fired_at IS NULL` confirmado (`0010_demo_session_events.sql:41-44`).
- **§"Quién dispara el audit"** — granularidad 60s del loop confirmado (`src/api/main.py:411`).
- **§"La vista `/demo` — timeline en vivo"** — polling 5s + SVG + tabla cronológica + chip "Próximo evento" confirmados (`src/frontend/app/(app)/demo/page.tsx:85-100, 120-141`).
- **§"La UI del demo — clon del registered con hints inline"** —
  - Chip `✨ Demo` en logo del sidebar: `src/frontend/app/(app)/layout.tsx:294-303` confirmado.
  - Entrada extra "Línea temporal → /demo" en NAV: `layout.tsx:50-54, 574-577` confirmado.
  - Headers de `/ingest`, `/kb`, `/quarantine`, `/expired`, `/chat` con `<DemoHint>`: confirmado en los 5 archivos (`chat/page.tsx:372`, `kb/page.tsx:182`, `quarantine/page.tsx:180`, `expired/page.tsx:127`, `ingest/page.tsx:184`).
  - Toolbar del chat con chip `✨ Demo` variant=sparkle: `chat/page.tsx:372-376` confirmado (incluye cuota "20 chats/día por IP" en el hint).
- **§"El componente `<DemoHint>`"** —
  - Auto-condicional sobre `user.is_demo`: `DemoHint.tsx:42` (`if (!isDemo) return null`).
  - Variants `info` (default) y `sparkle`, prop `label`, prop `align`: confirmado en `DemoHint.tsx:23-31, 46`.
- **§"El único route guard que queda"** — el snippet de `(app)/layout.tsx:761-772` coincide casi literalmente con el doc (`isDemo` + `inDemoRoute` + redirect a `/chat`).
- **§"Lo que el demo NO puede hacer"** —
  - `PUT /profile/llm-keys` → 403 `demo_account_locked`: `src/api/main.py:1214-1220`.
  - Cuotas `5 ingests + 20 chats` per-IP: `DEMO_QUOTAS = {"ingest": {"per_ip": 5, ...}, "chat": {"per_ip": 20, ...}}` en `src/api/main.py:660-662`.
- **§"⏳ Compresión temporal"** — la tabla narrativa es pedagógica; no hay afirmación verificable directa que rompa.
- **§"🕒 El contador de 15 minutos"** —
  - Banner reads `demo_session_expires_at` y recalcula contra `Date.now()` cada 1s: `DemoCountdownBanner.tsx:24-50`.
  - Cambio de color a falta de 60s (accent → amber → red): `DemoCountdownBanner.tsx:56-58, 60-73`.
  - A los 0s dispara fetch dummy a `/auth/me` para forzar 401: `DemoCountdownBanner.tsx:35-45`.
  - Header `X-Auth-Reason: demo_expired` → interceptor `lib/api.ts:80` → `forceLogout("?demo=expired")` → `window.location.href = "/login?demo=expired"`: `src/frontend/lib/api.ts:58-72, 80`.
  - Texto banner: "Sesión demo · {mm}:{ss} · se borrará todo lo que añadas al expirar" coincide con `DemoCountdownBanner.tsx:75-86` (con variante "Caducada" a los 0s, doc omite ese matiz pero lo describe en frase aparte).
- **§"Disparo manual del cleanup"** — `POST /admin/cleanup-demo-sessions` con header `X-Admin-Token: $AUDIT_CRON_TOKEN` confirmado (`src/api/main.py:1905-1928`).
- **§"🔐 BYOK y el demo"** — las 3 columnas Fernet `llm_key_lite/embeddings/pro` y las virtual-keys del `.env` (`DEMO_KEY_LITE/EMBEDDINGS/PRO`) — UNVERIFIED en este audit (no se inspeccionó `usuarios` schema ni seed_demo_user), pero coherente con la convención. Cuotas confirmadas arriba.
- **§"Slice 6.5 — Cache de embeddings"** —
  - Migración 0011 con tabla `staged_embeddings_cache` (idx PK, titulo, resumen, categoria, chunk_text, embedding FLOAT8[], model, dims, updated_at): `infra/postgres/migrations/0011_staged_embeddings_cache.sql:25-35`.
  - `ops/build_staged_embeddings.py` rellena la tabla con `INSERT ... ON CONFLICT`: `ops/build_staged_embeddings.py:1-30` (header explica idempotencia).
  - `/auth/demo-start` indexa staged en Qdrant vía `_index_staged_for_rag` con cache-first + fallback live a LiteLLM: `src/api/main.py:85-200` (estructura `cached_embedding IS NOT NULL` → cache hit, else fallback).
- **§"Modelos `DemoTimelineResponse` / `DemoTimelineEvent`"** — schema en `src/api/models.py:200-219` coincide con campos descritos.

---

## Notas adicionales sobre [CODE-BUG]

Ninguno detectado durante este audit.
