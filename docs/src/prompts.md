# Prompts del sistema LinkAnvil

> Referencia canónica de TODOS los puntos donde LinkAnvil llama a un LLM:
> qué prompt envía, qué intenta extraer y dónde se invoca.
>
> Última actualización: 2026-05-17. Si modificas un prompt en código, actualiza
> este archivo en el mismo commit para que no se desincronicen.

---

## Tabla de contenidos

1. [Mapa general de la pipeline](#1-mapa-general-de-la-pipeline)
2. [Prompts de ingesta](#2-prompts-de-ingesta)
   - 2.1 [Extracción de metadata (scraper)](#21-extracción-de-metadata-scraper)
   - 2.2 [Clasificador de relación semántica (embedder)](#22-clasificador-de-relación-semántica-embedder)
3. [Prompts de consulta (chat)](#3-prompts-de-consulta-chat)
   - 3.1 [Chat con RAG](#31-chat-con-rag)
   - 3.2 [Chat sin RAG (fallback)](#32-chat-sin-rag-fallback)
   - 3.3 [Chat legacy Streamlit (deprecated)](#33-chat-legacy-streamlit-deprecated)
4. [Prompts de auditoría / seguridad](#4-prompts-de-auditoría--seguridad)
   - 4.1 [Pre-push hook](#41-pre-push-hook)
   - 4.2 [Weekly audit cron](#42-weekly-audit-cron)
5. [Cliente LiteLLM compartido](#5-cliente-litellm-compartido)
6. [Gap conocido — clasificación temporal del contenido](#6-gap-conocido--clasificación-temporal-del-contenido)

---

## 1. Mapa general de la pipeline

```
                     ┌──────────────────────────────────────────┐
   USUARIO ─▶ /ingest │  RabbitMQ q.url.ingesta                  │
                     │            │                              │
                     │            ▼                              │
                     │  ┌─────────────────────┐                  │
                     │  │ scraper-worker      │                  │
                     │  │  └─ Prompt #1       │ ← extrae metadata│
                     │  │     (cerebro-lite)  │   incl. caducidad│
                     │  └────────┬────────────┘                  │
                     │           │ outbox: recurso.procesado     │
                     │           ▼                               │
                     │  ┌─────────────────────┐                  │
                     │  │ embedder-worker     │                  │
                     │  │  ├─ Embeddings API  │ ← vectorización  │
                     │  │  └─ Prompt #4       │ ← tipifica       │
                     │  │     (cerebro-lite)  │   relaciones     │
                     │  └────────┬────────────┘                  │
                     │           │ vectores en Qdrant            │
                     └───────────┼──────────────────────────────-┘
                                 │
                                 ▼
   USUARIO ─▶ /chat   ┌─────────────────────────┐
                      │ cerebro-api             │
                      │  ├─ Embeddings query    │
                      │  ├─ Qdrant search       │
                      │  ├─ Prompt #2 (con RAG) │ ← system prompt
                      │  └─ Prompt #3 (sin RAG) │   según hits
                      └─────────────────────────┘

   DESARROLLADOR ──▶ git push ──▶ Prompt #6 (pre-push, seguridad del diff)
                   ──▶ cron lunes ─▶ Prompt #7 (weekly-audit, código completo)

   LEGACY (en repo, no en pipeline live):
                  Prompt #5 (Streamlit chatbot, en `src/ui/chatbot.py`)
```

**Servicio dorsal**: todos los prompts pasan por
[LiteLLM](http://localhost:4000) (`cerebro-litellm` container). El proxy
LiteLLM expone modelos lógicos `cerebro-lite` y `cerebro-pro` que mapean a
proveedores configurados en su `config.yaml`.

---

## 2. Prompts de ingesta

### 2.1 Extracción de metadata (scraper)

- **Ubicación**: `src/scraper/worker.py:73-91` (función `_extract_metadata_with_llm`)
- **Disparador**: cada mensaje en la cola `q.url.ingesta`. El scraper baja la URL,
  limpia el HTML, y llama a este prompt con los primeros 6000 caracteres del texto.
- **Modelo**: `cerebro-lite`
- **Temperatura**: `0.1` (cuasi-determinista — queremos estabilidad en la salida JSON)
- **Inputs interpolados**: `url`, `title` (HTML `<title>`), `clean_text[:6000]`
- **Outputs esperados**: JSON estricto con 10 campos (los 7 originales +
  3 añadidos en migración 0006: `event_date`, `temporal_class`,
  `valor_archivistico`).
- **Qué intenta conseguir**: transformar HTML scrappeado en estructura
  consumible aguas abajo — categoría, palabras clave, volatilidad estimada,
  caducidad del recurso, y desde la migración 0006 también la **clasificación
  temporal del contenido** (¿es un evento concreto, una referencia
  descriptiva o evergreen?) y su **valor archivístico** (¿merece guardarse
  si su fecha es pasada?). El cruce policy × class × valor decide el
  destino del recurso al ingestar — ver `lifecycle.md` §2.

**Texto literal del prompt (post-migración 0006)**:

El prompt actual en `src/scraper/worker.py` solicita los 7 campos
originales más los 3 nuevos. Para el texto exacto del prompt consulta el
código fuente — varía con la fase de prompt-engineering. Lo crucial es
el **schema de salida** (ver tabla siguiente).

**Schema del output**:

| Campo | Tipo | Mapeo en DB | Restricciones |
|-------|------|-------------|---------------|
| `title` | str | `recursos.titulo` | libre |
| `summary` | str | `recursos.resumen` | 2-3 frases en español |
| `category` | enum | `recursos.categoria` | 8 valores en inglés |
| `keywords` | list\[str\] | `recursos.tags` (JSONB) | 3-5 items |
| `volatility_score` | enum | `recursos.volatilidad` | `baja`/`media`/`alta`/`dinamica` |
| `estimated_useful_life_days` | int | fallback de `fecha_caducidad` solo para `temporal_class='evento'` | 30-365 |
| `expiration_date` | str ISO o null | `recursos.fecha_caducidad` directo si no null | YYYY-MM-DD |
| **`event_date`** ⭐ | str ISO o null | `recursos.fecha_evento` | Fecha del evento descrito (puede ser pasada). El LLM extrae también del PATH de la URL (`YYYY/MM/DD`) como hint si no hay fecha en el texto. |
| **`temporal_class`** ⭐ | enum | `recursos.temporal_class` | `evento` (deadline/oferta/cita), `referencia` (crónica descriptiva), `evergreen` (tutorial/doc estable) |
| **`valor_archivistico`** ⭐ | enum | `recursos.valor_archivistico` | `alto` (papers, post-mortems, informes oficiales), `medio` (prensa estándar), `nulo` (anuncios caducados sin valor) |

⭐ = campos añadidos por la migración 0006.

**Cómo se usa cada campo aguas abajo** (`src/data/db.py::save_with_outbox`):

- `temporal_class='evergreen'` o evento/referencia con **fecha futura** →
  `estado='procesando'` → `'activo'` tras embedder.
- `temporal_class != 'evergreen'` con **fecha pasada**: se compone la
  key `{evento_pasado|referencia_pasada}_{alto|medio|nulo}` y se lee la
  decisión de `usuarios.audit_policy[key]`:
  - `"activo"` → activo en KB (caducidad NULL).
  - `"cuarentena"` → cuarentena con motivo `evento_pasado`.
  - `"expirado"` → flag `auto_archive_pending=true`, embedder vectoriza
    igualmente y transiciona a `expirado` (archivo histórico).

**Manejo de errores**: `with_retries(_call)` (en `src/scraper/_retry.py`)
reintenta. Si tras retries falla, **fail-open** con valores por defecto
seguros (`worker.py:115-123`): título = URL, summary = primeros 400 chars,
`volatility="media"`, `useful_life=30`, `expiration_date=None`.

**Observaciones**:

- El prompt **no** pide al LLM que clasifique la naturaleza temporal del
  contenido (evento vs referencia vs evergreen). Solo pide
  `expiration_date` para casos de "evento, deadline, fin de oferta o
  caducidad explícita". Para artículos descriptivos sobre el pasado
  (p.ej. el blog AEMET 2020 que motivó este documento), el LLM tiende a
  responder `null` → cae al fallback `today + useful_life` → el recurso
  queda con caducidad sintética futura que no refleja la naturaleza
  histórica del contenido. Ver [sección 6](#6-gap-conocido--clasificación-temporal-del-contenido).
- `temperature=0.1` (no 0.0) es un compromiso: la salida es JSON
  estructurado pero algunos campos (`summary`, `keywords`) se benefician
  de un poco de variabilidad estilística.
- Trunca el texto a 6000 chars — páginas largas pierden contexto. No hay
  estrategia de chunking en esta fase (el chunking para RAG ocurre
  después, en el embedder, sobre el `contenido` completo guardado en BD).

---

### 2.2 Clasificador de relación semántica (embedder)

- **Ubicación**: `src/data/embedder_worker.py:260-275` (dentro de
  `_classify_relation` u operación equivalente — método privado dentro del
  cómputo de colisiones semánticas)
- **Disparador**: tras generar el embedding de un recurso, cuando Qdrant
  detecta uno preexistente con alta similitud (`_compute_semantic_collisions`).
  Se invoca por cada par (nuevo, antiguo) cuya similitud supere el umbral.
- **Modelo**: `cerebro-lite`
- **Temperatura**: `0.0` (determinismo absoluto — la salida es un enum de 5 valores)
- **Tokens máximos**: `max_tokens: 10` (limitación dura — el LLM solo debe
  responder UNA palabra)
- **Inputs interpolados**: `new_info.title`, `new_info.summary`,
  `old_info.title`, `old_info.summary`
- **Outputs esperados**: una sola palabra del enum
  `{ES_UN, CONTRADICE, EXTIENDE, VUELVE_OBSOLETO, ASOCIACION_GENERAL}`
- **Qué intenta conseguir**: tipificar la relación entre dos recursos
  similares para alimentar el grafo (`grafo_relaciones` tabla) y disparar el
  colisionador semántico (F-03.3). Si la relación es `VUELVE_OBSOLETO` o
  `CONTRADICE`, el recurso antiguo se manda a cuarentena con
  `quarantine_reason='colision_semantica'`.

**Texto literal del prompt:**

```text
Como un evaluador experto, compara el nuevo documento con el antiguo.
Documento Nuevo (ID Reciente):
Título: {new_info.get('title', '')}
Resumen: {new_info.get('summary', '')}

Documento Antiguo (ID Existente):
Título: {old_info.get('title', '')}
Resumen: {old_info.get('summary', '')}

Tipifica la relación como UNA ÚNICA PALABRA: 'ES_UN', 'CONTRADICE', 'EXTIENDE', 'VUELVE_OBSOLETO' o 'ASOCIACION_GENERAL'.
```

**Manejo de errores**: try/except. Si LiteLLM falla, retorna
`"ASOCIACION_GENERAL"` (la relación más conservadora — no dispara
transición de cuarentena). El parser busca substrings del enum en la
respuesta tolerando ruido (`for t in [...]: if t in tipo: return t`).

**Observaciones**:

- Patrón **enum-classification** muy reusable: temperatura 0.0 + max_tokens
  bajo + parser tolerante a ruido. Si en el futuro se quiere clasificar
  `temporal_class` del contenido (evento/referencia/evergreen), este es el
  template a copiar.
- El prompt es **monolingüe en español** mientras que el enum es
  mayúsculas-snake-case. No genera confusión empíricamente, pero es un
  detalle de estilo a refinar si se internacionaliza.
- Solo se ejecuta cuando hay un "match" en Qdrant — no en toda ingesta. Eso
  limita el coste pero también significa que el grafo no se construye para
  recursos completamente nuevos.

---

## 3. Prompts de consulta (chat)

### 3.1 Chat con RAG

- **Ubicación**: `src/api/main.py:779-794` (función `chat` dentro de
  `@app.post("/chat")`)
- **Disparador**: cada `POST /chat` con `use_rag=true` y al menos un hit
  válido en Qdrant cuyo recurso esté `activo` para el tenant.
- **Modelo**: dinámico — viene en el campo `req.model` del body, típicamente
  `cerebro-lite` o `cerebro-pro`.
- **Streaming**: sí (`stream: true`), respuesta SSE.
- **Inputs interpolados**: `context_block` (fragmentos de chunks del RAG
  formateados como markdown). Los chunks vienen de la colección
  `cerebro_chunks` en Qdrant, ordenados por score descendente.
- **Outputs**: respuesta libre en lenguaje natural. El streaming devuelve
  deltas `{choices: [{delta: {content: "..."}}]}`.
- **Qué intenta conseguir**: respuestas que prioricen la base de
  conocimiento del usuario sobre el conocimiento general del LLM, con
  citas textuales y distinción explícita entre fuentes.

**Texto literal del prompt (system role):**

```text
Eres un asistente experto. Tienes acceso al contexto extraído de la base
de conocimiento del usuario, delimitado más abajo.

REGLAS ESTRICTAS:
1. Si la respuesta a la pregunta del usuario está total o parcialmente en
el contexto, úsala como fuente principal y cita los datos textualmente
(fechas, nombres, cifras) tal y como aparecen.
2. NO digas que 'no hay información específica' si el dato aparece en el
contexto, aunque esté de forma resumida o implícita.
3. NO mezcles tu conocimiento general con el contexto a menos que el
usuario lo pida explícitamente; si lo haces, distingue claramente qué
viene del contexto y qué de tu conocimiento previo.
4. Si tras leer el contexto sigues sin tener la respuesta, dilo de forma
directa y ofrece tu conocimiento general indicándolo.

{context_block}
```

**Construcción del `context_block`**: cada hit de Qdrant se formatea como
(`src/api/main.py:572-589`):

```text
## Contexto recuperado de tu base de conocimiento:

### {title}
URL: {url}
Fragmento (chunk {chunk_idx}):
{chunk_text}

---

### {title 2}
URL: {url 2}
...
```

**Manejo de errores**: try/except que captura cualquier fallo del RAG y
deja `context_block=""`. Si el bloque queda vacío, se ramifica al prompt
**3.2** (sin RAG). Recientemente añadido (commit `ba405e2`): try/except
también en `_stream()` que emite `data: {"type": "error", ...}` para que
el frontend muestre el error al usuario en lugar de un bubble vacío.

**Observaciones**:

- El prompt incluye solo los **10 últimos mensajes** del historial
  (`req.messages[-10:]`), no toda la conversación. Sliding window para
  controlar contexto.
- No hay límite explícito a `context_block`. Si Qdrant devuelve muchos
  chunks largos, el system prompt puede llegar a decenas de miles de
  tokens. Confiar en el rate limit de LiteLLM y la ventana del modelo.

---

### 3.2 Chat sin RAG (fallback)

- **Ubicación**: `src/api/main.py:797-801` (rama `else` del `if context_block`)
- **Disparador**: `POST /chat` con `use_rag=false` o con `use_rag=true` pero
  sin hits relevantes (Qdrant vacío o todos los hits filtrados por estado).
- **Modelo / temperatura / streaming**: igual que 3.1.
- **Inputs**: ninguno (prompt estático).
- **Outputs**: respuesta libre.
- **Qué intenta conseguir**: dejar claro al usuario que la respuesta NO
  viene de su KB, para que no asuma que tiene cobertura sobre la pregunta.

**Texto literal del prompt (system role):**

```text
Eres un asistente experto. La base de conocimiento del usuario no ha
devuelto resultados relevantes para esta pregunta. Responde con tu
conocimiento general e indícalo explícitamente.
```

**Observaciones**:

- Es el camino de salida más débil del sistema — el usuario podría no
  notar la diferencia con 3.1 si el LLM no acompaña la respuesta con la
  cláusula "según mi conocimiento general". Vigilar: si la calidad
  percibida del chat baja, este prompt es el primer sospechoso.
- En la métrica de `logger.info("CHAT model=%s use_rag=%s hits=%d ...")`
  se ve cuándo se dispara (línea `src/api/main.py:803`): `hits=0`.

---

### 3.3 Chat legacy Streamlit (deprecated)

- **Ubicación**: `src/ui/chatbot.py:136-142`
- **Disparador**: solo si alguien arranca `streamlit run src/ui/chatbot.py`
  manualmente. **NO está en docker-compose**, no se ejecuta en producción.
- **Modelo**: dinámico (selectbox de Streamlit).
- **Inputs interpolados**: `context_block` (lista de URLs+similitud, NO
  chunks reales).
- **Outputs**: texto en bloque (no streaming).
- **Qué intenta conseguir**: legado de pre-Next.js — chatbot embebido
  Streamlit para debugging local.

**Texto literal del prompt (system role):**

```text
Eres un asistente experto que responde usando el contexto de la base de
conocimiento del usuario. Si no hay contexto relevante, responde con tu
conocimiento general e indícalo.
```

**Observaciones**:

- Está **deprecated** desde la migración a Next.js. Mantenerlo o
  eliminarlo es decisión de producto pendiente. Si se elimina, asegurar
  que tampoco quede en `docker-compose.yml` como servicio (verificado:
  no aparece).
- Su `context_block` es muy pobre (solo `title — url [similitud: 0.XX]`),
  no incluye el texto del chunk. Diferencia clave vs 3.1 — el LLM no
  puede citar datos textualmente.

---

## 4. Prompts de auditoría / seguridad

### 4.1 Pre-push hook

- **Ubicación**: `ops/prompts/pre-push.txt` (template externo)
- **Disparador**: hook git `.githooks/pre-push` antes de cada `git push`.
  El hook envía el diff a través de `litellm_client.send_prompt`.
- **Modelo**: `cerebro-lite` (default de `litellm_client.py`, env
  `LITELLM_MODEL` puede sobreescribir).
- **Temperatura**: `0` (audit determinista).
- **`max_tokens`**: `600` (default de `send_prompt`).
- **Inputs interpolados**: `{diff}` (diff completo de `git diff
  origin/<branch>..HEAD`, truncado a `MAX_DIFF_CHARS` — actualmente
  8000 — con aviso `"Diff truncado a 8000 chars"`).
- **Outputs esperados**: una de dos formas:
  - `CLEAN` (single line) si no hay hallazgos.
  - Lista de líneas `CRITICAL|HIGH|MEDIUM: archivo:línea descripción` si
    hay hallazgos.
- **Qué intenta conseguir**: cazar 6 categorías clásicas de vulnerabilidad
  específicas de LinkAnvil antes de subir a GitHub. Bloquea el push solo
  si encuentra `CRITICAL`; `HIGH`/`MEDIUM` son warnings que no bloquean.

**Texto literal del prompt:**

```text
Eres un revisor de seguridad para linkanvil (FastAPI multi-tenant RAG).
Analiza este diff. Busca SOLO hallazgos reales con alta confianza (>80%):

1. JWT sin validación tenant_id en endpoints protegidos
2. Queries asyncpg con f-strings o concatenación de strings (SQL injection)
3. SSRF: URLs de usuario que llegan al scraper sin validación
4. Secrets hardcodeados (claves, tokens, contraseñas literales)
5. Notificaciones directas que saltan el outbox pattern (outbox_eventos)
6. Campos Pydantic sin validación que llegan a la DB

Formato de respuesta:
- Si hay hallazgos: una línea por hallazgo con prefijo CRITICAL/HIGH/MEDIUM, archivo:línea, descripción breve
- Si no hay hallazgos: una línea "CLEAN"

No expliques metodología. Solo lista hallazgos reales o CLEAN.

Diff:
{diff}
```

**Manejo de errores**: `litellm_client.send_prompt` retorna `None` si LiteLLM
no responde — el hook trata `None` como fail-open (`warning LiteLLM HTTP
... — push continua sin analisis`). Push **no se bloquea** si LiteLLM cae.

**Observaciones**:

- Las 6 categorías son **fijas y específicas del dominio**. Si añades una
  nueva práctica de seguridad (p.ej. auth0/OAuth), edita este archivo,
  no el código del hook.
- Cuidado con el truncado a 8000 chars en PRs grandes — análisis parcial.
  Ver `pre_push.py::_collect_diff` para el algoritmo de truncado.
- Asume que el repo respeta el patrón outbox: si un día se añade un
  servicio nuevo con su propia ruta de eventos, este prompt empezará a
  generar falsos positivos en la categoría 5.

---

### 4.2 Weekly audit cron

- **Ubicación**: `ops/prompts/weekly-audit.txt` (template externo)
- **Disparador**: cron semanal (`ops/cron/weekly_audit.py` invocado por
  Antigravity / systemd timer / etc. según despliegue).
- **Modelo**: `cerebro-lite` (default).
- **Temperatura**: `0`.
- **`max_tokens`**: `1200` (más generoso que pre-push porque el output es
  un reporte estructurado).
- **`timeout`**: 60s.
- **Inputs interpolados**: `{code}` — concatenación de archivos críticos
  (típicamente `src/api/main.py`, `src/api/auth.py`, `src/scraper/worker.py`).
- **Outputs esperados**: markdown con 3 secciones fijas:
  - `## Resumen Ejecutivo`
  - `## Hallazgos (CRITICAL/HIGH/MEDIUM)`
  - `## Acciones recomendadas`
- **Qué intenta conseguir**: auditoría más profunda y reflexiva que el
  pre-push. No mira un diff, mira el código entero de archivos sensibles
  y produce un informe legible que se archiva en `ops/sessions/`.

**Texto literal del prompt:**

```text
Eres el security-reviewer de linkanvil (FastAPI multi-tenant RAG).
Audita estos archivos críticos:

{code}

Busca:
1. JWT: ¿se valida tenant_id en todos los endpoints? ¿endpoints sin auth?
2. asyncpg: ¿todas las queries usan $1, $2...? ¿f-strings con datos de usuario?
3. SSRF: ¿URLs de usuario pasan validación antes de ser scrapeadas?
4. Pydantic: ¿campos sin validación que llegan a la DB?
5. Rate limiting: ¿endpoints POST sin rate limit?
6. Outbox: ¿notificaciones directas que saltan outbox_eventos?

Formato de respuesta: markdown con las secciones:
## Resumen Ejecutivo
## Hallazgos (CRITICAL/HIGH/MEDIUM)
## Acciones recomendadas

Solo hallazgos reales con >80% de confianza. Si no hay hallazgos, indicar
explícitamente "Sin hallazgos" en cada sección.
```

**Manejo de errores**: como en 4.1, fail-open via `litellm_client`. Si la
ejecución cron falla, no rompe nada; al lunes siguiente vuelve a intentar.

**Observaciones**:

- Las **6 categorías son casi idénticas a 4.1** con una addición: "Rate
  limiting" (categoría 5 aquí). Conviene mantener ambos prompts
  alineados — si añades una categoría, hazlo en los dos sitios.
- Output en markdown es legible para humanos. El cron suele guardar el
  reporte en `ops/sessions/security-audit-<fecha>.md`.
- Si los archivos auditados crecen, el prompt puede superar el contexto
  de `cerebro-lite`. En ese caso, considerar dividir en múltiples
  llamadas (por archivo) o pasar a `cerebro-pro`.

---

## 5. Cliente LiteLLM compartido

- **Ubicación**: `ops/cron/litellm_client.py` (módulo Python ~220 líneas)
- **API pública**: `send_prompt(prompt, max_tokens=600, timeout=30, ...)` →
  `Optional[str]`.
- **Quién lo usa**: prompts #6 y #7 (los hooks/cron). Los prompts #1-#5
  llaman directamente a httpx desde sus propios módulos.
- **Resolución de credenciales** (orden de precedencia):
  1. Variable de entorno `LITELLM_KEY` (exportada en el shell).
  2. Variable de entorno `LITELLM_MASTER_KEY` (alias usado por
     docker-compose).
  3. Fallback: `_load_dotenv_fallback()` parsea `.env` del root del
     repo y puebla `os.environ` con `setdefault` (no pisa overrides
     manuales).
- **Resolución de URL**: `LITELLM_URL` env → default
  `http://localhost:4000`. Validada con `_validate_url` para evitar
  esquemas no-http.
- **Resolución de modelo**: `LITELLM_MODEL` env → default `cerebro-lite`.
- **Comportamiento de errores**: nunca lanza. Captura `HTTPError`,
  `URLError`, parsing errors → imprime warning a stdout y retorna `None`.
- **Headers que envía**:
  - `Content-Type: application/json`
  - `Authorization: Bearer <key>` (si hay key resuelta — añadido en
    commit `2c7e4a5` tras detectar HTTP 401 en pre-push).

**Por qué los prompts #1-#5 NO usan este cliente**:

- Son código de runtime (workers / API) que ya tienen `httpx.AsyncClient`
  abierto en el lifespan del proceso. Reusan el pool de conexiones.
- Necesitan streaming (chat) o headers extra (Authorization ya está
  hardcodeado con `LITELLM_KEY` de container env).
- Histórico — `litellm_client.py` se introdujo para hooks/cron donde
  no había httpx ni event loop. Si en el futuro se quiere centralizar
  todo en un solo cliente, hay refactor pendiente.

---

## 6. Resuelto en migraciones 0006 + 0007 — clasificación temporal y policy por celda

> **Estado**: gap cerrado. Esta sección queda como referencia histórica.
> El comportamiento descrito abajo es el del prompt #1 ANTES de la
> migración 0006; el comportamiento actual se documenta en
> §2.1 ("Output esperado") y en `lifecycle.md` (Anexo A).

### Resumen del cierre

1. **Migración 0006**: el prompt #1 ahora extrae tres campos adicionales —
   `temporal_class` (evento/referencia/evergreen), `valor_archivistico`
   (alto/medio/nulo), `event_date` (fecha del evento, posiblemente
   pasada). Las columnas equivalentes existen en `recursos`.
2. **Migración 0007**: la decisión "qué hacer con un recurso de fecha
   pasada" se pasó de un enum `audit_strictness` (estricto/equilibrado/
   permisivo) a una `audit_policy` JSONB con 6 keys (una por celda
   `temporal_class × valor_archivistico`). El frontend ofrece 3 presets
   (Estricto/Equilibrado/Permisivo) que rellenan las 6 celdas + 6 selects
   para ajuste fino. Decisiones posibles por celda: `activo`,
   `cuarentena`, `expirado`.
3. **Auto-archive**: cuando la policy decide `expirado` para un recurso
   de fecha pasada, el scraper marca `auto_archive_pending=true` y el
   embedder transiciona a `'expirado'` tras vectorizar (en vez del
   default `'activo'`). Los chunks quedan disponibles para recuperación
   vía toggle "Archivo ON" en el chat (campo `include_archive` del
   `/chat`).

### Trazas con el comportamiento nuevo (preset Equilibrado, default)

| URL | LLM clasifica | Destino |
|-----|---------------|---------|
| Expojove 2024 (artículo de prensa) | `referencia`, valor `medio` | cuarentena/`evento_pasado` |
| AEMET 2020 (informe oficial) | `referencia`, valor `alto` | auto-archive → `expirado` |
| Tutorial de Docker (evergreen) | `evergreen` | `activo` |
| Concierto Marzo 2026 | `evento`, valor `medio`, futuro | `activo` con caducidad |

Cambiar la policy desde `/profile` ajusta el destino sin reingestar.

### Apéndice — Comportamiento previo (referencia histórica)

**Origen**: duda del usuario tras intentar ingestar
`https://aemetblog.es/2020/09/18/avance-climatico-nacional-del-verano-2020/`
(análisis del verano 2020 publicado por AEMET en 2020) y observar que el
sistema **no lo reconoce como evento pasado** ni como referencia histórica.

**Comportamiento actual del prompt #1**:

- El prompt solicita `expiration_date` solo cuando el texto menciona "una
  fecha concreta de evento, deadline, fin de oferta o caducidad
  explícita".
- Para un artículo descriptivo sobre el pasado, el LLM tiende a
  responder `expiration_date: null`.
- Cuando `expiration_date` es null, `src/data/db.py:170-177` cae al
  fallback `fecha_caducidad = today + estimated_useful_life_days`.
- Resultado: el AEMET-2020 se guarda como `activo` con caducidad
  sintética hacia 2026-09-XX, **perdiendo la naturaleza histórica del
  contenido**.

**Por qué este gap es conceptual, no de implementación**:

La columna `recursos.fecha_caducidad` mezcla **dos conceptos distintos** que
el prompt #1 no separa:

| Concepto | Pregunta que responde | Ejemplo AEMET 2020 |
|----------|----------------------|--------------------|
| Caducidad del EVENTO | ¿Cuándo ocurre/terminó lo que el contenido describe? | Verano 2020 (pasado, ~5 años) |
| Vigencia del CONTENIDO | ¿Hasta cuándo es útil este recurso como referencia? | Indefinida (datos climáticos archivables) |

**Para los recursos tipo "concierto futuro / deadline / oferta", ambos
conceptos coinciden** y el sistema funciona. Para los tipo "análisis
descriptivo / referencia histórica / tutorial atemporal", **divergen** y
el sistema se equivoca.

**Posibles direcciones (NO se implementan en este documento — quedan para
otro plan)**:

1. **Nuevo campo en el output del prompt #1**: `temporal_class` (enum:
   `evento` / `referencia` / `evergreen`). Para `referencia` y
   `evergreen`, `fecha_caducidad` se guarda como `NULL` (el cron de
   obsolescencia ya filtra `IS NOT NULL`, así que NULL bypasses
   automáticamente).
2. **Separar columnas**: `fecha_evento` (cuándo ocurre lo descrito,
   puede ser pasado) y `fecha_caducidad` (vigencia del recurso). Schema
   más explícito pero migración no trivial.
3. **Toggle de usuario**: dejar el LLM como está y añadir un control
   en la UI del KB para que el usuario marque manualmente un recurso
   como "Histórico/Referencia" → backend lo trata como caducidad
   `NULL`.
4. **Híbrido**: combinar (1) y (3) — LLM clasifica por defecto, usuario
   puede sobreescribir desde la UI.

Para evaluar cualquiera de estas opciones se requiere una sesión
separada con AskUserQuestion sobre:

- ¿El contenido histórico aparece en el RAG con prioridad normal o
  penalizada por antigüedad?
- ¿Quién decide la clasificación temporal — solo LLM, solo usuario, o
  ambos?
- ¿Eventos ya pasados al ingestar (AEMET 2020 visto hoy) → cuarentena
  automática o referencia automática?

**Mientras tanto** este gap está documentado pero el comportamiento es:

- AEMET 2020 → ingestado como `activo` con caducidad sintética futura.
- A los `estimated_useful_life_days` días → audit-cron lo mueve a
  cuarentena con motivo `caducidad`.
- A los 30 días más (`OBSOLESCENCE_GRACE_DAYS`) → `expirado`.
- El usuario podría rescatarlo manualmente desde `/quarantine` o
  `/expired` con el botón "Rescatar", que recalcula caducidad según
  `volatilidad` (`api/database.py:rescue_recurso`).

---

## Apéndice — Cuándo actualizar este documento

Si editas:

| Cambio | Acción |
|--------|--------|
| Texto literal de un prompt inline (`worker.py`, `main.py`, etc.) | Actualizar el bloque ```text correspondiente en el mismo commit |
| Modelo / temperatura / max_tokens | Actualizar la tabla de cabecera del prompt afectado |
| Archivos en `ops/prompts/*.txt` | El doc cita el contenido literal — re-pegar |
| `litellm_client.py::send_prompt` signature | Actualizar sección 5 |
| Nuevo prompt en cualquier sitio | Añadir nueva sección, actualizar TOC y mapa |
| Resolución del gap temporal (sección 6) | Cuando se implemente, mover la sección 6 a un archivo histórico y reescribir |
