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

1. Abrir `/login`.
2. Bloque "Probar sin registro" debajo del formulario: copia las
   credenciales públicas con un click.
3. Click en "Entrar".
4. Redirect a `/chat` con la sesión activa.

Credenciales públicas (también en `ops/seed_demo_user.py`):

```
demo@linkanvil.io
linkanvil-demo
```

⚠️ Estas credenciales son fijas y públicas. Cualquiera puede usarlas.
Es deliberado — el visitante curioso quiere probar sin fricción.

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
