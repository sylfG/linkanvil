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

La entrada del demo está separada por completo de la entrada de
usuarios registrados. **No hay credenciales visibles en `/login`** y la
cuenta demo NO acepta password — la entrada es por un endpoint
dedicado.

### Para el visitante

1. Abrir la landing (`/`).
2. Click en uno de los CTAs **"Probar el demo gratis"** (Hero) /
   **"Acceder al demo"** (banner medio). Ambos están solo en la
   landing, no en el Nav. El Nav anónimo guarda su slot CTA para
   **"Iniciar sesión"** por decisión explícita de producto: ese botón
   es para quien ya viene a entrar a su cuenta, no para descubrir el
   demo.
3. El navegador llama a `POST /auth/demo-start` (sin password, sin
   formulario). El backend crea el sub-tenant efímero, stagea 3
   recursos sintéticos y programa 4 eventos (ver sección siguiente).
4. El cliente recibe `{access_token, redirect: "/demo", ...}` y
   redirige a `/demo` — la vista pedagógica del timeline (sin tabs:
   header + SVG con marcador "now" + tabla cronológica + atajos a las
   rutas reales `/chat`, `/kb`, `/quarantine`, `/expired`).

### Para el desarrollador / integraciones

```bash
# Endpoint público, rate-limited (10/min por IP)
curl -X POST https://linkanvil.example/auth/demo-start
# → { access_token, csrf_token, redirect: "/demo", tenant_id,
#     expires_at, resumed, seconds_remaining? }
```

(El backend no aplica prefix `/api`; si tu deploy usa un reverse-proxy
que lo añada, ajusta la URL al lado del proxy.)

El endpoint no necesita password porque la cuenta demo es **comunitaria
por diseño**: cualquiera puede pedir una sesión efímera. La protección
es el TTL de 15 min + el gate "1 sesión por IP / día UTC" (ver más
abajo) + cuotas diarias por IP (5 ingests, 20 chats) + cap global
(50 / 200) que evitan que un bot agote el cupo.

### Una sesión demo por IP por día UTC

Sin este gate, un visitante podría hacer logout y pulsar "Probar el
demo gratis" otra vez para conseguir 15 min fresquitos saltándose la
cuota diaria. `/auth/demo-start` consulta Redis
(`demo_session_started:{ip}:{YYYY-MM-DD}`, TTL 24h) y aplica esta
lógica:

- **Sesión viva para esta IP** → resume (re-emite JWT/cookies sobre el
  mismo `tenant_id`, el countdown sigue donde estaba). Respuesta
  incluye `resumed: true` y `seconds_remaining`.
- **Sesión ya expiró pero la IP gastó hoy** →
  `429 demo_already_used_today` con copy "Ya disfrutaste tu sesión
  demo de 15 minutos hoy" + `register_url: /register`.
- **IP nueva para hoy** → crea sesión nueva, marca la IP por 24h.

La defensa total es: TTL 15 min + 1-demo/IP/día + cuotas diarias
per-IP (5 ingests, 20 chats) + cap global (50/200).

### `/login` rechaza el email demo

Si alguien encuentra el email en logs y lo escribe en el formulario
clásico de `/login`, el backend responde:

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

El cuerpo viene siempre bajo la clave `detail` (comportamiento estándar
del framework cuando se devuelve un dict). El front lee
`err.detail.error` / `err.detail.message` / `err.detail.redirect`.

Así garantizamos que el flujo de credenciales reales (registered users)
queda 100% aislado del demo.

---

## 💡 La pieza clave — **sub-tenants efímeros por sesión**

Esta es la diferencia arquitectónica más importante entre el demo y
una cuenta normal:

> **Cada vez que alguien inicia sesión en el demo, el backend crea un
> sub-tenant nuevo y aislado con TTL de 15 minutos.**

### En la base de datos

- Tabla `cerebro.demo_sessions` con `(tenant_id, user_id, created_at,
  expires_at, last_seen_at, ip)`.
- El `tenant_id` de la sesión sigue el patrón `demo_<8hex>`
  (ej. `demo_a3b9f1c4`, `demo_e27d1df0`).
- El JWT lo emite `POST /auth/demo-start` con el claim
  `tenant_id = "demo_<8hex>"` (no el del usuario demo persistente en
  BD). `/auth/login` rechaza la cuenta demo con 403; `/auth/refresh`
  rota tokens manteniendo el `session_tenant`.
- Cada request valida que la fila en `demo_sessions` exista y que
  `expires_at > NOW()`. Si no, devuelve `401 demo_expired`.

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
   global lo mitigan, pero los sub-tenants lo resuelven
   estructuralmente.)

Con sub-tenants efímeros cada visitante tiene su propia "fotocopia"
del demo, vive sus 15 min, y desaparece sin afectar al resto.

---

## ⏱️ Eventos programados intra-sesión

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
notifier crea notificaciones in-app. El visitante ve el bell de la UI
parpadear con 3 nuevas en directo.

### Cómo está montado

Una tabla `cerebro.demo_session_events` materializa los eventos
programados con precisión `TIMESTAMPTZ`:

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
cron de producción compara con `NOW()::DATE` para mover recursos
vencidos a cuarentena.

Esto no sirve para el demo:
- Necesitamos precisión de **minutos** (evento al minuto 5 exacto).
- Necesitamos **scoping por tenant** (no contaminar otros tenants).

La solución: una función paralela de auditoría intra-sesión que trabaja
sobre `demo_session_events` con `TIMESTAMPTZ`, scoped al tenant, y
reutiliza el mismo helper de outbox que el cron de prod — así las
notificaciones llegan al bell con el mismo `evento_tipo` y schema.
Quien recibe la notificación no distingue el origen.

### Quién dispara el audit

El mismo background task que limpia sesiones expiradas (tick cada
60 s). Se le añadió un paso al inicio del bucle:

```text
while True:
    # 1. Audits intra-sesión — procesa eventos con fires_at <= NOW()
    process_due_demo_audits()

    # 2. Cleanup de sesiones expiradas
    expired = get_expired_demo_sessions()
    for s in expired:
        qdrant_delete_tenant_points(s.tenant_id)
        delete_demo_session_cascade(s.tenant_id)

    sleep(60s)
```

El loop pregunta primero por las sesiones con eventos vencidos
(aprovecha el índice parcial para barrer solo eventos pending), y por
cada tenant abre su propia transacción + `set_config(app.tenant_id,
...)` + ejecuta el audit. Las transacciones aisladas garantizan que un
fallo en un tenant no contamine los demás.

Granularidad de 60 s implica que un evento programado a +5:00 puede
dispararse entre +5:00 y +5:59. Aceptable — el visitante percibe la
ventana como "alrededor del minuto 5".

### La vista `/demo` — timeline en vivo

El endpoint `GET /demo/timeline` (gated a `is_demo`) devuelve la
sesión + sus 4 eventos con `fired_at`. La página `/demo` la consume
con polling cada 5 s y pinta:

- **Línea horizontal SVG** con un marcador móvil (now) + puntos por
  evento, coloreados según kind. Tooltip con descripción al hover.
- **Tabla cronológica** debajo con hora, evento, motivo, descripción,
  y estado (Pendiente / Disparado).
- **Chip "Próximo evento"** en el header con countdown relativo.

Cuando el audit del backend dispara un evento, el polling lo refleja
en los 5 s siguientes — el visitante ve el punto cambiar de su icono
"pending" (depende del kind: alerta para cuarentena, calendario X para
archivo, reloj de arena para reminder) al icono "disparado" (check) en
vivo.

---

## 🪟 La UI del demo — clon del registered con hints inline

El principio: demo y registered comparten **toda** la app. Solo cambia
información contextual añadida (un chip, unos tooltips), no estructura.

### El principio

Demo y registered comparten **todo** el cromo:

- Mismo layout (sidebar + nav + countdown banner top).
- Mismas rutas reales: `/chat`, `/kb`, `/quarantine`, `/expired`,
  `/ingest`.
- Mismos componentes de página — sin ramas de lógica condicional por
  tipo de usuario en la lógica de negocio del frontend.

Lo único que se añade al demo es **información**, no estructura:

| Lugar | Solo para demo |
|---|---|
| Top del layout | Banner countdown con TTL 15:00 → 00:00 |
| Logo del sidebar | Chip `✨ Demo` con tooltip "se borra al expirar" |
| Sidebar nav | Entrada extra al inicio: `Línea temporal → /demo` |
| Headers de `/ingest`, `/kb`, `/quarantine`, `/expired` | Tooltip inline con copy contextual |
| Toolbar del chat | Chip `✨ Demo` con cuota y tooltip |

### El componente de hint inline

El tooltip contextual es auto-condicional: si el usuario actual es
demo, renderiza un icono `Info` con tooltip on hover/focus/tap; si no,
renderiza nada (cero footprint visual para registered).

Variantes:
- `variant="info"` (defecto) → icono pequeño discreto.
- `variant="sparkle"` + `label="Demo"` → chip completo con badge.
- `align="right"` → tooltip a la derecha cuando el componente está
  cerca del borde.

Esto permite **sembrar el componente en cualquier sitio** sin tocar la
lógica de la página.

### La ruta `/demo` — solo timeline

`/demo` no es un dashboard con tabs. Es una vista pedagógica con:

1. Header explicativo + chip "Próximo evento" con countdown relativo.
2. **Línea horizontal SVG** con marcador móvil (now) y los 4 eventos
   posicionados proporcionalmente entre login y expiración.
3. **Tabla cronológica** con hora, evento, motivo, descripción y
   estado (Pendiente / Disparado).
4. **Atajos cards** a `/chat`, `/kb`, `/quarantine`, `/expired` para
   que el visitante salte a ver el efecto real del audit.

Polling cada 5 s a `GET /demo/timeline` para actualizar `fired_at` en
vivo cuando el cleanup loop dispara los eventos.

### Route guard

Demo accede libremente a TODAS las rutas. La única restricción es que
un usuario registered no debería ver la línea temporal `/demo` (no le
aporta nada): si pisa esa ruta, el layout lo redirige a `/chat`.

### Lo que el demo NO puede hacer

Las limitaciones del demo viven en el **backend**, no en el frontend:

- `PUT /profile/llm-keys` → 403 `demo_account_locked` (claves
  pre-configuradas).
- `POST /ingest` / `POST /chat` → 429 cuando se alcanzan los topes
  diarios per-IP (5 ingests, 20 chats).
- La `audit_policy` del tenant SÍ es editable desde el modal de
  perfil — es solo configuración del tenant, y al expirar la sesión la
  fila se borra junto con el sub-tenant, así que es un cambio efímero.
  No daña ningún seed.

El frontend NO oculta ni desactiva nada visualmente — todo se intenta,
y si el backend rechaza, los componentes manejan los 403 y 429 con
mensajes legibles.

---

## 📚 Recursos pre-sembrados — los 18 ejemplos

El seed inicial puebla **un tenant compartido** inmutable,
`user_demo_landing`, con 18 recursos cuidadosamente escogidos para
cubrir todas las combinaciones interesantes de
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

En una cuenta real, **estos estados aparecerían con el paso del
tiempo**:

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

- El cron nocturno de auditoría real que opera sobre `fecha_caducidad`
  con precisión DATE. El demo te enseña **una versión comprimida y
  scoped** vía la auditoría intra-sesión, pero el cron de prod global
  (todos los tenants, una vez al día) no corre dentro de la sesión.
- Re-ingesta del mismo recurso tras corrección de scrape.
- Auditoría exhaustiva semanal de código.
- El ciclo de vida largo (caducidad real → gracia 30 días → archivo)
  con días entre cada paso. El demo comprime las transiciones del
  minuto 5 sintetizándolas con `transition_cuarentena` y
  `transition_expirado`, pero un usuario real las verá repartidas en
  semanas.

### Lo que SÍ ves del lifecycle

- **Tus 3 recursos efímeros** sembrados al login pasarán por
  transiciones reales en vivo al minuto 5 — verás cómo aparecen en
  `/quarantine` y `/expired`.
- **Tres notificaciones in-app** en el bell (icono notif del sidebar)
  con `evento_tipo = recurso.cuarentena | recurso.expirado` — el
  mismo formato que recibe un tenant registered cuando su cron
  diario corre. Las emite el notifier consumiendo el outbox que
  escribió la auditoría intra-sesión.
- **El timeline en `/demo`** te muestra cuándo va a pasar y, tras el
  audit, refleja `fired_at` en vivo (polling 5 s).

Si quieres ver el ciclo natural sin compresión: regístrate con tu email,
configura tus claves de LLM (BYOK) en `/profile` y úsalo durante varios
días.

---

## 🕒 El contador de 15 minutos

Tras login, en la cabecera de toda la app aparece un banner sticky:

```
🕒 Sesión demo · 14:59 · se borrará todo lo que añadas al expirar
```

El countdown:

- **Es absoluto, no relativo**: el componente lee
  `demo_session_expires_at` (timestamp ISO del backend) y recalcula
  los segundos restantes contra la hora actual cada 1 s. Resiste
  pestañas dormidas, cambios de hora del sistema, recargas de página.
- **Cambia de color a falta de 60 s**: pasa de morado (accent) a
  ámbar con icono de reloj de arena pulsando.
- **A los 0 s**: se vuelve rojo con texto "Caducada".
- **Tras 0 s**: el siguiente request a la API responde
  `401 X-Auth-Reason: demo_expired`. El interceptor del cliente
  redirige a `/login?demo=expired`.

### Lo que se borra al expirar

El background task de cleanup (cada 60 s) detecta sesiones con
`expires_at < NOW()`. Por cada una hace:

1. **Qdrant first**:
   `POST /collections/{cerebro_chunks,cerebro_recursos}/points/delete`
   con filtro `payload.tenant_id == "demo_<8hex>"`.
2. **Cascade transaccional en BD**:
   1. `SELECT set_config('app.tenant_id', tenant_id, true)` para
      satisfacer la RLS forzada sobre `usuario_recursos` /
      `sesiones_chat`.
   2. `DELETE FROM sesiones_chat` — `mensajes_chat` cae con su
      `FK ON DELETE CASCADE`.
   3. `DELETE FROM notificaciones` — sin RLS, directo.
   4. `DELETE FROM usuario_recursos` (captura los `recurso_id` antes
      para el siguiente paso).
   5. `DELETE FROM recursos` para los huérfanos: `id = ANY(...)` AND
      `NOT EXISTS (usuario_recursos)` AND `NOT EXISTS (usuario_recursos
      JOIN recursos r2 WHERE tenant_id = user_demo_landing AND
      r2.url_hash = r.url_hash)` — salvaguarda doble para no romper el
      seed (ni recurso aún asociado a alguien, ni recurso que comparta
      `url_hash` con el seed canónico).
   6. `DELETE FROM demo_sessions` — dispara `ON DELETE CASCADE` sobre
      `demo_session_events`, así que los 4 eventos programados
      desaparecen solos. Cero limpieza manual de la tabla de eventos.

Si Qdrant falla quedan points huérfanos. Aceptable: el cleanup BD es
transaccional; un barrido manual semanal limpia restos en Qdrant.

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
| Cuota diaria | 5 ingests + 20 chats / día (per-IP) + 1 sesión/IP/día UTC | Sin cuota diaria (solo rate-limit por minuto) |
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
│   Landing CTA (Hero / banner) → POST /auth/demo-start          │
│       ↓                                                        │
│   create_demo_session():                                       │
│     · INSERT demo_sessions (expires_at = NOW + 15min)          │
│     · stagea 3 recursos efímeros (URLs sintéticas)             │
│     · programa 4 eventos en demo_session_events                │
│       ↓                                                        │
│   Frontend redirige a /demo (timeline pedagógica)              │
│       ↓                                                        │
│   Visitante navega libremente: /chat /kb /ingest /quarantine   │
│   /expired (MISMA app que registered) + /demo (extra)          │
│       ↓                                                        │
│   /kb muestra UNION(demo_xxx, user_demo_landing) = 18+3 staged │
│   Ingest URL → va a demo_xxx aislado                           │
│   Chat → keys pre-configuradas del demo, RAG sobre UNION       │
│       ↓                                                        │
│   ⏱️ +5min — cleanup loop dispara la auditoría intra-sesión:   │
│     · 2 staged → cuarentena (motivo caducidad)                 │
│     · 1 staged → expirado    (motivo auto_archive)             │
│     · 3 notificaciones via outbox → notifier → bell del UI     │
│   ⏱️ +10min — banner reminder "quedan 5min"                    │
│       ↓                                                        │
│   Cuota diaria per-IP (5 ingests, 20 chats) + cap global       │
│   + gate "1 sesión / IP / día UTC" (Redis)                     │
│       ↓                                                        │
│   ⏱️ +15min — cleanup task borra demo_xxx en cascada           │
│   (Qdrant + sesiones_chat + notificaciones + usuario_recursos  │
│   + recursos huérfanos + demo_sessions → demo_session_events)  │
│       ↓                                                        │
│   user_demo_landing (los 18 seed) queda intacto                │
└────────────────────────────────────────────────────────────────┘
```
