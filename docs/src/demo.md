# El demo público de LinkAnvil

> Documentación pedagógica del demo: para qué sirve, cómo está montado,
> qué simula y qué NO simula. Pensada para que un visitante o un nuevo
> colaborador entienda en 5 minutos por qué la cuenta demo es "rara"
> en comparación con una cuenta normal.

---

## 🎯 ¿Para qué existe el demo?

LinkAnvil es un sistema cuyo valor se ve **con el tiempo**: clasificas
URLs, las dejas en tu KB, pasan días o semanas, el cron nocturno
detecta que un evento ya pasó, lo manda a cuarentena, otro lo archiva,
otro entra como `referencia` con valor alto y queda accesible solo si
activas el toggle de Archivo Histórico en el chat.

Eso es maravilloso a 6 meses vista, pero **es invisible en una demo de
5 minutos**. Un visitante que entra por primera vez quiere ver:

- Que el LLM clasifica al ingerir
- Que el chat con RAG funciona y cita fuentes
- Que el sistema distingue evergreen / evento / referencia
- Que la auditoría nocturna gestiona el ciclo de vida
- Que el archivo histórico no pierde nada pero filtra ruido

Pero todo eso pasa en distintos momentos temporales. El demo
**precomprime el tiempo**: trae ya sembrados los 18 recursos
representativos en los estados finales del ciclo de vida, para que el
visitante pueda explorar todos los outcomes a la vez sin tener que
esperar 6 semanas a que el sistema "madure".

---

## 🛠️ Cómo entrar

> Slice 6 separó por completo la entrada del demo de la entrada de
> usuarios registrados. Ya **no hay credenciales visibles en `/login`**
> y la cuenta demo NO acepta password — la entrada es por un endpoint
> dedicado.

### Para el visitante

1. Abrir la landing (`/`).
2. Click en cualquiera de los CTAs **"Probar demo gratis"** /
   **"Acceder al demo"** / **"Probar demo"** (hero, banner medio, nav).
3. El navegador llama a `POST /auth/demo-start` (sin password, sin
   formulario). El backend crea el sub-tenant efímero, stagea 3 recursos
   sintéticos y programa 4 eventos (ver sección siguiente).
4. Redirect automático a `/demo` — vista dedicada con tabs:
   `Timeline · KB · Cuarentena · Archivo · Chat`.

### Para el desarrollador / integraciones

```bash
# Endpoint público, rate-limited (10/min por IP)
curl -X POST https://linkanvil.example/api/auth/demo-start
# → { access_token, csrf_token, redirect: "/demo", tenant_id, expires_at }
```

El endpoint no necesita password porque la cuenta demo es **comunitaria
por diseño**: cualquiera puede pedir una sesión efímera. La protección
es el TTL de 15 min + cuotas diarias por IP (5 ingests, 20 chats) y
la global cap (50 / 200) que evitan que un bot agote el cupo.

### `/login` rechaza el email demo

Si alguien encuentra el email en logs y lo escribe en el formulario
clásico de `/login`, el backend responde:

```json
HTTP 403
{
  "error": "demo_use_dedicated_endpoint",
  "message": "Esta es la cuenta demo. Accede desde el botón 'Probar demo' de la landing.",
  "redirect": "/demo"
}
```

Así garantizamos que el flujo de credenciales reales (registered users)
queda 100% aislado del demo.

---

## 💡 La pieza clave — **sub-tenants efímeros por sesión**

Esta es la diferencia arquitectónica más importante entre el demo y
una cuenta normal:

> **Cada vez que alguien inicia sesión en el demo, el backend crea un
> sub-tenant nuevo y aislado con TTL de 15 minutos.**

### En código

- Tabla `cerebro.demo_sessions` con `(tenant_id, user_id, created_at,
  expires_at, last_seen_at, ip)`.
- El `tenant_id` de la sesión sigue el patrón `demo_<8hex>`
  (ej. `demo_a3b9f1c4`, `demo_e27d1df0`).
- El JWT que firma el endpoint `/auth/login` lleva ese sub-tenant en
  el claim `tenant_id`, **no** el del usuario demo en BD
  (`user_demo_landing`).
- `get_current_user` valida en cada request que la fila en
  `demo_sessions` exista y que `expires_at > NOW()`. Si no, devuelve
  `401 demo_expired`.

### ¿Por qué este diseño?

Sin sub-tenants efímeros, el demo sería un único `tenant_id` compartido
y aparecerían **tres problemas dolorosos**:

1. **Sin aislamiento**: lo que añade Alice a su KB del demo lo ve Bob.
   No es leak de privacidad real (son URLs públicas), pero rompe la
   ilusión de "tu segundo cerebro" — Bob ve cosas que no añadió.
2. **Reset injusto**: si limpiamos el demo cada 15 min con un cron
   global, quien acaba de entrar tiene 15 min completos y quien lleva
   14 min queda con 1 min. No hay forma de hacer "15 min desde el
   login de cada uno" con un único tenant.
3. **Quota compartida**: una persona que ingesta 5 URLs agota la
   cuota del día para toda la humanidad demo. (Cuota per-IP + cap
   global de Slice 4 lo mitiga, pero los sub-tenants lo resuelven
   estructuralmente.)

Con sub-tenants efímeros cada visitante tiene su propia "fotocopia"
del demo, vive sus 15 min, y desaparece sin afectar al resto.

---

## ⏱️ Eventos programados intra-sesión (Slice 6)

El demo no se limita a mostrar los recursos en sus **estados finales**.
También **dispara el ciclo de vida en vivo** dentro de los 15 min de
sesión para que el visitante VEA transiciones, no solo resultados.

### Qué pasa en cada sesión

| Minuto | Evento | Efecto observable |
|---|---|---|
| **+0** | Login vía `POST /auth/demo-start` | Se crean sub-tenant + 3 recursos sintéticos + 4 eventos pending |
| **+5** | `transition_cuarentena` × 2 | Dos recursos `activo` pasan a `cuarentena` con motivo `caducidad` |
| **+5** | `transition_expirado` × 1 | Un recurso `activo` pasa directo a `expirado` (motivo `auto_archive`) |
| **+10** | `reminder_expiry_5min` | Banner pasivo "quedan 5 min" sin modificar recursos |
| **+15** | Cleanup automático | Sub-tenant + sus recursos + sus eventos se borran en cascada |

Las 3 transiciones del minuto 5 **no son ficticias**: usan los mismos
helpers de `recursos`, generan eventos reales en `outbox_eventos` y el
`notifier-worker` crea notificaciones in-app. El visitante ve el bell
de la UI parpadear con 3 nuevas en directo.

### Cómo está montado

Una tabla nueva `cerebro.demo_session_events` (migración 0010)
materializa los eventos programados con precisión `TIMESTAMPTZ`:

```sql
CREATE TABLE cerebro.demo_session_events (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id   TEXT NOT NULL REFERENCES demo_sessions(tenant_id) ON DELETE CASCADE,
    fires_at    TIMESTAMPTZ NOT NULL,
    fired_at    TIMESTAMPTZ,
    kind        VARCHAR(50) NOT NULL,    -- transition_* | reminder_expiry_5min
    recurso_id  UUID,
    motivo      VARCHAR(50),
    description TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

Dos detalles importantes del schema:

- **FK CASCADE a `demo_sessions`**: cuando la sesión expira y la fila
  de `demo_sessions` se borra, los eventos se borran solos. Cero
  limpieza manual.
- **Índice parcial `WHERE fired_at IS NULL`**: el cleanup loop hace
  scans muy baratos buscando solo eventos pending.

### Por qué una tabla aparte y no `fecha_caducidad`

La columna `recursos.fecha_caducidad` es `DATE` (precisión 1 día). El
cron de producción (`run_audit_cron`) compara con `NOW()::DATE` para
mover recursos vencidos a cuarentena.

Esto no sirve para el demo:
- Necesitamos precisión de **minutos** (evento al minuto 5 exacto).
- Necesitamos **scoping por tenant** (no contaminar otros tenants).

La solución: una función paralela
`run_demo_audit_for_session(tenant_id, conn)` en `audit_cron.py` que
trabaja sobre `demo_session_events` con `TIMESTAMPTZ`, scoped al
tenant, y reutiliza el mismo helper de outbox que el cron de prod —
así las notificaciones llegan al bell con el mismo `evento_tipo` y
schema. Quien recibe la notificación no distingue el origen.

### Quién dispara el audit

El mismo background task que ya limpia sesiones expiradas
(`_cleanup_demo_sessions_loop` en `main.py`, tick cada 60s). Se le
añadió un paso al inicio del bucle:

```python
while True:
    # 1. Audits intra-sesión — procesa eventos con fires_at <= NOW()
    await _process_due_demo_audits()

    # 2. Cleanup de sesiones expiradas (paso original de Slice 5)
    expired = await db.get_expired_demo_sessions()
    for s in expired:
        await _qdrant_delete_tenant_points(s["tenant_id"])
        await db.delete_demo_session_cascade(s["tenant_id"])

    await asyncio.sleep(60)
```

Granularidad de 60s implica que un evento programado a +5:00 puede
dispararse entre +5:00 y +5:59. Aceptable — el visitante percibe la
ventana como "alrededor del minuto 5".

### La vista `/demo` — timeline en vivo

El endpoint `GET /demo/timeline` (gated a `is_demo`) devuelve la
sesión + sus 4 eventos con `fired_at`. La página `/demo` la consume
con polling cada 5s y pinta:

- **Línea horizontal SVG** con un marcador móvil (now) + puntos por
  evento, coloreados según kind. Tooltip con descripción al hover.
- **Tabla cronológica** debajo con hora, evento, motivo, descripción,
  y estado (Pendiente / Disparado).
- **Chip "Próximo evento"** en el header con countdown relativo.

Cuando el audit del backend dispara un evento, el polling lo refleja
en los 5s siguientes — el visitante ve el punto cambiar de pendiente
(icono `AlertTriangle`) a disparado (icono `CheckCircle2`) en vivo.

---

## 🪟 La ruta `/demo` y la separación con `/chat`

Slice 6 también limpió la deuda visual del Slice 5: el banner de
countdown ya no se renderiza globalmente condicionado a `is_demo`
en cada ruta de `(app)/`. En su lugar:

- **`/demo`** es la única ruta donde el demo opera. Tabs internas
  (Timeline / KB / Cuarentena / Archivo / Chat) — todo el demo cabe
  en una sola URL.
- **Route guards client-side** en `(app)/layout.tsx`:
  - Demo session en `/chat`, `/kb`, `/quarantine`, `/expired` → redirect
    a `/demo`.
  - Registered session en `/demo` → redirect a `/chat`.
- **El sidebar habitual** (Ingestar / KB / Cuarentena / Expirados) NO
  se renderiza en `/demo` — esta vista trae su propio chrome con
  tabs y header sticky.
- **`ProfileModal`** (telegram bot, BYOK, audit policy) sigue
  accesible solo desde el sidebar `(app)/`, así que los demo users
  nunca llegan a él — perfecto, porque sus claves vienen
  pre-configuradas y no se pueden cambiar (defendido a nivel
  backend con `403 demo_account_locked` en `PUT /profile/llm-keys`).

Resultado: las vistas reales de `/chat`, `/kb`, `/quarantine`, `/expired`
ya **no tienen ningún condicional `is_demo`** ni instrumentación
demo-específica. Quedan idénticas a antes, solo para registered.

---

## 📚 Recursos pre-sembrados — los 18 ejemplos

El seed (`ops/seed_demo_user.py`) puebla **un tenant compartido**
inmutable, `user_demo_landing`, con 18 recursos cuidadosamente
escogidos para cubrir todas las combinaciones interesantes de
`temporal_class × valor_archivistico × estado`. Los sub-tenants
efímeros hacen `UNION ALL` con este tenant en todas las queries de
lectura, así que cada visitante ve esos 18 ejemplos compartidos
**sin duplicarlos en BD ni en Qdrant**.

### Distribución por categoría

| Categoría    | Cantidad | Ejemplos canónicos |
|--------------|----------|---|
| Recetas      | 2 | Menú semanal saludable, paella valenciana |
| Repos de IA  | 5 | whisper, transformers, langchain, anthropics/skills, linkanvil |
| Papers arXiv | 3 | Attention Is All You Need, Mistral 7B, Llama 2 |
| Eventos futuros | 2 | Primavera Sound 2026, NeurIPS 2026 CFP |
| Eventos pasados archivados | 2 | AEMET verano 2020, WWDC 2023 Vision Pro |
| Cuarentena por evento_pasado | 1 | ExpoJove 2024 |
| Documentación atemporal | 3 | Docker overview, K8s concepts, Python tutorial |

### Distribución por estado del ciclo de vida

| Estado | Cantidad | Qué representa |
|---|---|---|
| `activo` | 15 | URLs en uso normal, visibles en `/kb` |
| `cuarentena` | 1 | Triaje pendiente — el usuario decide rescatar o expirar |
| `expirado` | 2 | Archivo histórico — visibles solo con toggle Archivo ON |

### Distribución por `temporal_class`

| Clase | Cantidad | Significado |
|---|---|---|
| `evergreen` | 4 | Tutorial / docs que no caducan (Docker, K8s, Python tutorial, paella) |
| `evento` | 2 | Tienen fecha concreta y `fecha_caducidad` (Primavera Sound, NeurIPS) |
| `referencia` | 12 | Artículos descriptivos, papers, repos — pueden quedar como histórico o seguir siendo útiles |

---

## ⏳ Compresión temporal — qué simula el demo

Aquí está la clave pedagógica que solicitó este documento. En una
cuenta real, **estos estados aparecerían con el paso del tiempo**:

| Estado del recurso | Cuándo aparece en cuenta normal | En el demo |
|---|---|---|
| `procesando` | 2-30 s tras ingestar (mientras scraper + embedder corren) | No visible — todos los seed están ya activos |
| `activo` | Tras embedding completado | 15 recursos preseed en este estado |
| `cuarentena` por `evento_pasado` | Cuando el cron nocturno detecta que un evento ya pasó (puede ser semanas tras la ingesta) | 1 preseed (ExpoJove 2024) |
| `cuarentena` por `caducidad` | Días/meses tras `fecha_caducidad` (con período de gracia configurable) | No preseed — para verlo añade una URL con fecha próxima y espera el cron |
| `expirado` (auto_archive) | Cuando un recurso de valor alto pasa de `procesando` directamente a archivo histórico | 2 preseed (AEMET 2020, WWDC 2023) |
| `expirado` (manual) | Cuando el usuario rescata o archiva desde `/quarantine` o `/expired` | Puedes provocarlo tú: ve a `/quarantine`, click en "Expirar" sobre ExpoJove |
| Notificaciones del lifecycle | Llegan vía outbox → fanout cuando ocurre cada transición | Cada visitante tiene su bandeja vacía (el seed no genera notificaciones para sub-tenants) |

### En lenguaje de producto

> El demo **muestra los resultados finales del ciclo de vida sin
> obligarte a esperar el tiempo natural**. Es como un museo de
> ejemplos curados que ilustra qué hace LinkAnvil tras semanas de
> operación, comprimido en lo que un visitante puede recorrer en
> 15 minutos.

### Lo que SÍ es real-time en el demo

- **Ingestar una URL**: el flujo completo (Bloom filter → scraper →
  embedder → outbox → notifier → SSE) ocurre tal cual en producción.
  En 10-30 s ves la URL pasar de "Procesando" a "Activo" en `/kb`.
- **Clasificación LLM al ingerir**: el scraper le pregunta a
  `cerebro-lite` por `temporal_class`, `valor_archivistico`,
  `fecha_evento`, etc. Tú ves el resultado en la fila correspondiente.
- **Chat con RAG**: cada mensaje dispara un embedding de la query,
  búsqueda en Qdrant, recuperación de chunks, inyección en el prompt,
  streaming de la respuesta con cita de fuentes.
- **Cuotas diarias**: el límite per-IP (5 ingests + 20 chats / día UTC)
  es vivo y real.

### Lo que NO podrás ver en 15 min

- El cron nocturno de auditoría (transición automática
  `activo → cuarentena → expirado` por `fecha_caducidad`).
- Notificaciones del lifecycle propias (las del seed pertenecen a
  `user_demo_landing` y no a tu sub-tenant; en tu sub-tenant la
  bandeja arranca vacía).
- Re-ingesta del mismo recurso tras corrección de scrape.
- Auditoría exhaustiva semanal (`ops/cron/weekly_audit.py`).

Si quieres ver esto en directo: regístrate con tu email, configura
tus claves de LLM (BYOK) en `/profile` y úsalo durante varios días.

---

## 🕒 El contador de 15 minutos

Tras login, en la cabecera de toda la app aparece un banner sticky:

```
🕒 Sesión demo · 14:59 · se borrará todo lo que añadas al expirar
```

El countdown:

- **Es absoluto, no relativo**: el componente lee
  `demo_session_expires_at` (timestamp ISO del backend) y recalcula
  los segundos restantes contra `Date.now()` cada 1 s. Resiste pestañas
  dormidas, cambios de hora del sistema, recargas de página.
- **Cambia de color a falta de 60 s**: pasa de morado (accent) a
  ámbar con icono `Hourglass` pulsando.
- **A los 0 s**: se vuelve rojo con texto "Caducada".
- **Tras 0 s**: el siguiente request a la API responde
  `401 X-Auth-Reason: demo_expired`. El interceptor de `lib/api.ts`
  redirige a `/login?demo=expired`.

### Lo que se borra al expirar

Un background task dentro de `cerebro-api` corre cada **60 s** y
detecta sesiones con `expires_at < NOW()`. Por cada una hace cascada:

1. **Qdrant** — `POST /collections/{cerebro_chunks,cerebro_recursos}/points/delete`
   con filtro `payload.tenant_id == "demo_<uuid>"`.
2. **`sesiones_chat`** — la FK a `mensajes_chat` tiene `ON DELETE
   CASCADE`, así que los mensajes se van con la sesión.
3. **`notificaciones`** — sin RLS, delete directo.
4. **`usuario_recursos`** — RLS forzada con policy `tenant_isolation`;
   primero `SELECT set_config('app.tenant_id', $1, true)` para poder
   borrar las filas del tenant.
5. **`recursos`** huérfanos — los que quedan sin asociaciones en
   `usuario_recursos`, EXCEPTO si comparten `url_hash` con un recurso
   del seed canónico (salvaguarda anti-borrado accidental).
6. **`demo_sessions`** — la fila del sub-tenant.

Lo que **NO se borra nunca**: los 18 recursos del seed
(`user_demo_landing`), ni sus chunks en Qdrant, ni la fila del usuario
demo en `usuarios`. Esos son la "memoria muscular" del demo y son
inmutables.

### Disparo manual del cleanup

```bash
curl -X POST http://192.168.1.19:8001/admin/cleanup-demo-sessions \
  -H "X-Admin-Token: $AUDIT_CRON_TOKEN"
```

Devuelve un JSON con los detalles de cada cascada. Útil para:

- Verificación post-deploy (ver el cleanup en acción sin esperar al
  tick de 60 s).
- Disaster recovery si el background task fallase silenciosamente.
- Hookearlo desde n8n como backup del cron interno.

---

## 🔐 BYOK y el demo

El demo tiene 3 columnas cifradas con Fernet en `usuarios`:
`llm_key_lite`, `llm_key_embeddings`, `llm_key_pro`. Vienen pobladas
por el seed con las virtual-keys que pone el owner en `.env`
(`DEMO_KEY_LITE`, `DEMO_KEY_EMBEDDINGS`, `DEMO_KEY_PRO`). Por defecto
caen a `LITELLM_MASTER_KEY` si no se rellenan — útil out-of-the-box,
pero recomendable cambiarlas a virtual-keys reales de free-tier
(Groq, Mistral free, Gemini Flash AI Studio) para acotar el coste.

### Diferencias con un usuario registrado

| Acción | Demo | Registrado |
|---|---|---|
| Ver el formulario BYOK en `/profile` | NO (muestra info-box "cuenta compartida") | SÍ |
| `PUT /profile/llm-keys` | 403 `demo_account_locked` | OK (valida key contra LiteLLM y cifra) |
| Cuota diaria | 5 ingests + 20 chats / día (per-IP) | Sin cuota diaria (solo rate-limit por minuto) |
| Cap global de seguridad | 50 ingests + 200 chats / día (para todos los demos juntos) | N/A |
| Visibilidad del seed | SÍ (`UNION` con `user_demo_landing`) | NO |

---

## 🗺️ Mapa mental rápido

```
┌────────────────────────────────────────────────────────────────┐
│                    SISTEMA REAL                                │
│  (cuenta registrada, tenant fijo, sin TTL, sin seed compartido)│
│                                                                │
│   ingesta → scraper → embedder → outbox → activo               │
│                                          ↓ (cron nocturno)     │
│   activo  → cuarentena (motivo) → expirado o rescatado         │
│                  ↑                                             │
│         actions usuario (UI / Telegram)                        │
└────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────┐
│                       DEMO                                     │
│  (sub-tenant demo_xxx efímero TTL 15min + UNION con seed)      │
│                                                                │
│   Login → crea demo_xxx con expires_at = NOW + 15min           │
│       ↓                                                        │
│   /kb muestra UNION(demo_xxx, user_demo_landing) = 18 + tuyos  │
│       ↓                                                        │
│   Ingest URL → va a demo_xxx (sub-tenant aislado)              │
│   Chat → resuelve key del USER demo, RAG sobre UNION           │
│       ↓                                                        │
│   Cuota diaria per-IP enforced (5 ingests, 20 chats)           │
│       ↓                                                        │
│   A los 15min: cleanup task borra demo_xxx y todo su contenido │
│   (Qdrant + sesiones_chat + notificaciones + usuario_recursos  │
│   + recursos huérfanos + fila demo_sessions)                   │
│       ↓                                                        │
│   user_demo_landing (los 18 seed) queda intacto                │
└────────────────────────────────────────────────────────────────┘
```

---

## 📚 Glosario rápido

- **Sub-tenant efímero**: tenant_id `demo_<8hex>` creado en cada login
  del demo. Vive 15 min y se borra con todo su contenido al expirar.
- **Seed tenant**: `user_demo_landing`, contiene los 18 recursos
  canónicos del demo. Inmutable. Cada sub-tenant lo une en queries
  de lectura.
- **Compresión temporal**: el truco de tener recursos pre-sembrados
  en estados del lifecycle que en producción tardarían semanas en
  alcanzarse.
- **Cleanup task**: corutina asyncio dentro de `cerebro-api` que
  cada 60 s borra sesiones expiradas (BD + Qdrant en cascada).
- **`demo_expired`**: razón devuelta en el header `X-Auth-Reason`
  cuando un request llega tras `expires_at`. El frontend lo mapea a
  un redirect a `/login?demo=expired`.
- **BYOK** (Bring Your Own Key): trae tu propia virtual-key de
  LiteLLM. El demo NO permite cambiar la suya; los registrados sí.
- **Quota per-IP**: cuota diaria del demo escopada por la IP del
  visitante (5 ingests + 20 chats / día UTC).
- **Cap global**: tope diario sumado de todos los visitantes del
  demo (50 ingests + 200 chats / día UTC) como red de seguridad.

---

## 🔍 Para investigar más

- Migración SQL del schema: `infra/postgres/migrations/0009_demo_sessions.sql`
- Lógica del sub-tenant: `src/api/database.py::create_demo_session`
- Validación TTL en cada request: `src/api/main.py::get_current_user`
- Cleanup background task: `src/api/main.py::_cleanup_demo_sessions_loop`
- Endpoint admin: `POST /admin/cleanup-demo-sessions`
- Banner countdown frontend: `src/frontend/app/(app)/layout.tsx::DemoCountdownBanner`
- Catálogo de los 18 seed: `ops/seed_demo_user.py::SEED_RESOURCES`
