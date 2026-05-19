# Review · 0-resumen · 2026-05-19

**Auditor**: docs-reality-auditor
**Doc revisado**: `docs/src/0-resumen.md`
**Áreas de código verificadas**: `docker-compose.yml`, `src/api/`, `src/ingestion/`, `src/scraper/`, `src/notifier/`, `src/data/`, `src/observability/`, `src/dlq/`, `src/frontend/`, `src/ui/`, `clientes/browser-extension/`, `.claude/agents/`, `docs/src/3-componentes.md`, `infra/postgres/migrations/`
**Versión del repo**: develop @ `7c723f3`

## Resumen
- **0 CRITICAL**, **1 HIGH**, **3 MEDIUM**, **2 LOW**, **3 UNVERIFIED**
- 0 hallazgos [CODE-BUG]
- **Veredicto: YELLOW**

El doc `0-resumen.md` es deliberadamente de alto nivel (audiencia ejecutiva/no técnica), por lo que la mayoría de afirmaciones son abstractas y no enuncian paths, puertos o versiones concretas. Sin embargo, contiene **un número técnico verificable que no está respaldado por código** (HIGH: TTL de sesión de chat de 30 días) y un conjunto de afirmaciones de comportamiento que sólo se pueden validar parcialmente.

---

## Hallazgos

### [HIGH] Afirmación "sesión de chat archivada tras 30 días de inactividad" no está implementada
- **Ubicación**: línea 135
- **Lo que dice el doc**:
  > "Control de Consumo de Memoria: Si un usuario no utiliza su sesión de chat durante 30 días, el sistema la traslada de la memoria rápida al almacenamiento a largo plazo para liberar espacio en el servidor. Si el usuario vuelve a escribir, la sesión se recarga en un instante."
- **Realidad en el código**:
  - Las sesiones de chat viven en la tabla `sesiones_chat` (Postgres). No existe ningún job, migración, cron ni código que mueva sesiones a "cold storage" tras 30 días de inactividad.
  - `grep -rnE "30.*day|days.*30|INACTIVE|archive_session|cold_storage"` sobre `src/` sólo retorna:
    - `src/data/db.py:509`/`audit_cron.py:238` → `quarantine_grace_until = (NOW() + INTERVAL '30 days')` (es la cuarentena de **recursos** caducados, no de sesiones de chat).
    - `src/scraper/worker.py:83,142` y `src/data/db.py:236` → `estimated_useful_life_days` default 30 (vida útil del **recurso**).
    - `src/api/auth.py:28` → `REFRESH_TOKEN_EXPIRE_DAYS = 30` (TTL del refresh token JWT, no de sesiones de chat).
  - El único TTL de sesión que existe es `DEMO_SESSION_TTL_MINUTES = 15` (`src/api/database.py`).
  - `src/api/main.py:1989,2001,2009` exponen list/get/delete de sesiones de chat sin lógica de archivado por inactividad.
- **Cambio sugerido**:
  ```markdown
  * **Cuarentena de Recursos Obsoletos:** Cuando un enlace guardado supera su fecha de caducidad estimada (calculada por la IA), un proceso nocturno lo traslada a una bandeja de "cuarentena" durante 30 días antes de marcarlo como obsoleto. El usuario puede rescatar el recurso en cualquier momento durante ese periodo.
  ```
  (eliminar la afirmación sobre sesiones de chat, o reemplazarla por esta sobre recursos, que sí existe en `src/data/audit_cron.py`).

---

### [MEDIUM] El doc presenta el sistema como "cinco componentes" pero el sistema real tiene 22 servicios
- **Ubicación**: línea 38
- **Lo que dice el doc**:
  > "El sistema está dividido en cinco componentes independientes que trabajan en equipo de forma ordenada."
- **Realidad en el código**:
  - `docker-compose.yml` declara **22 servicios** (líneas 14–861 del compose): `ingestion-api`, `scraper-worker`, `outbox-worker`, `notifier-worker`, `embedder-worker`, `cerebro-migrate`, `cerebro-api`, `cerebro-web`, `traefik`, `rabbitmq`, `redis`, `postgres`, `qdrant`, `litellm`, `n8n`, `n8n-bootstrap`, `jaeger`, `otel-collector`, `prometheus`, `grafana`, `rabbitmq-exporter`, `redis-exporter`, `postgres-exporter`, `tailscale-funnel`.
  - El doc cruzado `docs/src/3-componentes.md:11` ya reconoce explícitamente "22 servicios".
  - Los "cinco componentes" del 0-resumen (A Ingesta / B Procesamiento / C Almacenamiento / D Mantenimiento / E Interfaz) son una agrupación **lógica/pedagógica**, no un mapeo 1-a-1 con servicios reales. Es aceptable como narrativa, pero ningún módulo "Interfaz y Chatbot" engloba al frontend Next.js + la API FastAPI + el chatbot Streamlit (`src/ui/chatbot.py`) como una sola unidad operativa.
- **Cambio sugerido**:
  ```markdown
  El sistema agrupa **22 servicios** desplegados en Docker Compose alrededor de **cinco grandes capas funcionales** que se describen a continuación. Para ver el inventario detallado de servicios consulta [`3-componentes.md`](./3-componentes.md).
  ```

---

### [MEDIUM] El doc no menciona Streamlit como una de las superficies de UI
- **Ubicación**: §E "Interfaz y Chatbot" (líneas 83–89)
- **Lo que dice el doc**:
  > "Es la pantalla y el canal de comunicación con el usuario. Está formado por un panel de control visual y un chat interactivo."
- **Realidad en el código**:
  - Existen tres superficies de UI distintas:
    1. **Next.js** (`src/frontend/`, servicio `cerebro-web` en `docker-compose.yml:264`).
    2. **Streamlit chatbot** (`src/ui/chatbot.py`).
    3. **Browser extension** (`clientes/browser-extension/`) — la propia §A línea 42 la menciona como entrada, pero esta sección §E no la incluye como interfaz.
  - El doc habla en singular ("la pantalla", "el chat") sin distinguir entre las tres superficies, lo que puede llevar al lector a asumir una única SPA.
- **Cambio sugerido**:
  ```markdown
  * **Panel de Control (Aplicación Web):** Interfaz reactiva en Next.js que permite ver estadísticas, consultar los enlaces guardados y revisar el historial de conversaciones.
  * **Chat Conversacional (Streamlit):** Cliente alternativo basado en Streamlit (`src/ui/chatbot.py`) para iterar rápidamente con el motor de chat.
  * **Extensión de Navegador:** Cliente ligero (`clientes/browser-extension/`) que permite enviar enlaces desde Chrome/Firefox sin abrir la app principal.
  ```

---

### [MEDIUM] Falta mencionar SSE / streaming reactivo para ingest y resources en §E "Chat Fluido"
- **Ubicación**: línea 88
- **Lo que dice el doc**:
  > "Chat Fluido: Las respuestas de la IA se muestran palabra por palabra en tiempo real (mientras se van generando)."
- **Realidad en el código**:
  - Confirmado streaming de chat: `src/api/main.py:1860–1879` (`StreamingResponse` con `media_type="text/event-stream"`).
  - **Adicional no mencionado**: existen dos endpoints SSE reactivos para flujos no-chat:
    - `GET /ingest/stream` (`src/api/main.py:1636`) — eventos del pipeline de ingesta en vivo.
    - `GET /resources/stream` (`src/api/main.py:1664`) — transiciones del ciclo de vida del recurso (cuarentena, rescate, expirado).
  - El usuario percibe estos como "actualizaciones en tiempo real" del estado de sus enlaces, pero el doc sólo describe el streaming del chat.
- **Cambio sugerido**:
  ```markdown
  * **Chat Fluido:** Las respuestas de la IA se muestran palabra por palabra en tiempo real mientras se generan. Adicionalmente, la interfaz refleja en directo el estado de cada enlace guardado (procesado, en cuarentena, expirado) mediante un canal de eventos reactivo (SSE), sin necesidad de recargar la página.
  ```

---

### [LOW] Inconsistencia tipográfica: "estan" sin tilde
- **Ubicación**: línea 60
- **Lo que dice el doc**:
  > "promociones que ya no estan vigentes"
- **Realidad en el código**: N/A — typo en el doc.
- **Cambio sugerido**:
  ```markdown
  promociones que ya no están vigentes
  ```

---

### [LOW] Lista numerada de §A se rompe entre el ítem 2 y el ítem 3
- **Ubicación**: líneas 45–50
- **Lo que dice el doc**:
  > Ítem 2 ("Verificación de Duplicados") con dos sub-bullets, seguido de doble salto de línea, y luego ítem 3 ("Extracción Flexible"). En el render, los sub-bullets aparecen separados de su ítem padre.
- **Realidad en el código**: N/A — bug de formato Markdown (los sub-bullets están en columna 1 en lugar de indentados).
- **Cambio sugerido**:
  ```markdown
  2. **Verificación de Duplicados:** El sistema comprueba al instante si el enlace ya existe en la base de datos general.
     * Si el enlace ya se había registrado antes, se reutiliza la información existente para ahorrar energía y costes.
     * Si es un enlace nuevo, se envía a una lista de espera (cola de mensajes) para ser procesado sin retrasar la navegación del usuario.

  3. **Extracción Flexible de Contenido:** ...
  ```

---

### [UNVERIFIED] "Crea un puente de conocimiento de forma automática" entre recursos semánticamente similares
- **Ubicación**: línea 69
- **Lo que dice el doc**:
  > "Si el sistema detecta que un enlace nuevo comparte un tema muy similar con otro guardado hace meses, crea un puente de conocimiento de forma automática"
- **Realidad en el código**:
  - Existe la tabla `grafo_relaciones` (referenciada en `src/data/export_manager.py:42–49`) que persiste relaciones entre recursos.
  - Existe la mecánica de "colisión semántica" mencionada en `src/data/db.py:443` y `src/data/embedder_worker.py:345`, pero la inserción automática de relaciones tras detectar similitud requiere leer la lógica completa del embedder en runtime para confirmar que se dispara sin intervención del usuario. No se pudo verificar de cita única.
- **Cambio sugerido**: requiere validación con un código-walkthrough adicional del embedder_worker antes de afirmar o desmentir.

---

### [UNVERIFIED] "Cookies ultra-protegidas que los virus informáticos comunes no pueden leer del navegador"
- **Ubicación**: línea 89
- **Lo que dice el doc**:
  > "Las cookies utilizadas en el inicio de sesión son ultra-protegidas que los virus informáticos comunes no pueden leer del navegador, y cuenta con un límite de intentos para bloquear accesos no autorizados."
- **Realidad en el código**:
  - `httpOnly=True` confirmado para session/refresh tokens (`src/api/main.py:539`, `:568`) — esto sí impide acceso por JavaScript desde el navegador.
  - `SameSite` configurado vía variable `COOKIE_SAMESITE` (`src/api/main.py:541,553,570`) — el valor concreto depende del despliegue (no es auditable desde código estático).
  - El claim "los virus informáticos comunes no pueden leer" es una simplificación marketing-friendly de `httpOnly`; técnicamente cierto contra XSS, pero no contra malware con acceso al disco o al proceso del navegador. Marcado UNVERIFIED por la subjetividad del lenguaje.
- **Cambio sugerido**:
  ```markdown
  * **Seguridad de Acceso:** El inicio de sesión utiliza cookies `httpOnly` (inaccesibles desde código JavaScript en la página, lo que bloquea ataques XSS comunes) con flag `SameSite` configurable, y cuenta con un límite de intentos para bloquear accesos no autorizados (5 intentos de login/min/IP por defecto).
  ```

---

### [UNVERIFIED] Tono del documento sobre IA: "Si el servicio principal (OpenAI) falla, se conecta automáticamente a un servicio secundario sin que el usuario note la interrupción"
- **Ubicación**: línea 56
- **Lo que dice el doc**:
  > "Si el servicio principal (por ejemplo, OpenAI) falla, el sistema se conecta automáticamente a un servicio secundario sin que el usuario note la interrupción."
- **Realidad en el código**:
  - La integración con LiteLLM existe (`src/api/main.py:59` `LITELLM_URL`, `src/data/embedder_worker.py:25`).
  - LiteLLM permite configurar fallbacks declarativos vía `config.yaml` (carpeta `infra/litellm/`), pero la **política de fallback efectiva** (qué modelo cae sobre qué) depende de esa configuración en runtime y no se puede afirmar desde código Python.
  - El claim "sin que el usuario note la interrupción" no es verificable estáticamente — implica que la latencia/calidad del fallback es indistinguible del primario, algo que sólo se puede demostrar empíricamente.
- **Cambio sugerido**: validar contra `infra/litellm/config.yaml` antes de confirmar el claim; mientras tanto, considerar suavizar a "se intenta automáticamente con un proveedor de respaldo configurado".

---

## Aprobado sin cambios

- §"Características Principales" (líneas 27–32) — claims abstractos verificados:
  - "Organización Automatizada" — clasificación se produce en `src/scraper/worker.py` y embeddings en `src/data/embedder_worker.py`.
  - "Eficiencia en Costes" — deduplicación verificada en `src/ingestion/deduplicator.py` (Bloom filter por tenant).
- §A "Filtro de Entrada" (línea 44) y §A "Verificación de Duplicados" (línea 45) — verificado contra `src/ingestion/main.py` (limpieza de URL + dedup vía Bloom filter en Redis).
- §A "Extracción Flexible" (línea 50, soporte LinkedIn/X con Playwright stealth) — verificado contra `src/scraper/strategy.py` y comentarios en `docs/src/old_/2_resumen_servicios.md:199` ("Playwright/Chromium headless con stealth para SPAs y sitios JS-heavy").
- §A "Bot de Telegram" (línea 42) — verificado: `src/ingestion/main.py:182` (`POST /webhook/telegram/{token_hash}`) y `:230` (`POST /webhook/telegram`).
- §A "Webhooks externos" (línea 42) — verificado: `src/ingestion/main.py:276` (`POST /webhook/external`).
- §A "Extensiones de navegador" (línea 42) — verificado: `clientes/browser-extension/` existe en el repo.
- §B "Formato de Datos Estricto" (líneas 57–60) — verificado: `src/scraper/worker.py:83` enumera el esquema obligatorio (categoria, tags, resumen, estimated_useful_life_days).
- §C "Base de Datos Relacional" — verificado: servicio `postgres:` en `docker-compose.yml:416`, schema en `infra/postgres/init.sql` y `infra/postgres/migrations/`.
- §C "Base de Datos Vectorial" — verificado: servicio `qdrant:` en `docker-compose.yml:463`, integración en `src/data/embedder_worker.py`.
- §C "Exportación para Uso Local" + nota de seguridad (líneas 70–71, "se genera en RAM, no en disco") — verificado: `src/data/export_manager.py:109` usa `io.BytesIO()` en memoria; el ZIP se construye y se sirve sin tocar disco.
- §D "Bandeja de Cuarentena" (línea 81) — verificado: lógica de cuarentena en `src/data/audit_cron.py:238` y `src/data/db.py:509` (`quarantine_grace_until = NOW() + INTERVAL '30 days'`).
- §"Infraestructura — Gestión de Enlaces Rotos" (línea 133, "reintenta 3 veces") — verificado: `src/scraper/_retry.py:12` (`attempts: int = 3`).
- §"Privacidad Total (Multi-Inquilino)" (línea 134) — verificado: aislamiento por `tenant_id` en todo el código (`src/data/db.py`, `src/api/database.py`, RLS bypass controlado para demo en `src/api/database.py:121–124`, payload Telegram con `tenant_id` en `src/ingestion/main.py:221`).
- §"Protección contra Abusos" (línea 136) — verificado: rate limits implementados en `src/api/main.py:645` (`_rate_limit` helper) con políticas por endpoint (`:737` login 5/min/IP, `:741` register 3/hr/IP, `:770` chat 30/min/tenant, `:779` audit 5/min/tenant).
- §"Rastreo de Errores en Cascada" (línea 137, "código de identificación único") — verificado: `trace_id` propagado consistentemente (`src/ingestion/main.py`, `src/scraper/`, `src/data/embedder_worker.py`, `src/ui/chatbot.py:49`, `src/observability/logging.py:8,16`).
