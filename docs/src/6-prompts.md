<div align="center">
  <img src="/logo-light.png" alt="Logo" width="80" height="80" class="light-only">
  <img src="/logo-dark.png" alt="Logo" width="80" height="80" class="dark-only">


# Prompts del sistema — LinkAnvil

</div>


> Referencia canónica de todos los puntos donde LinkAnvil llama a un LLM:
> qué prompt envía, qué intenta extraer y dónde se invoca a nivel
> funcional.

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
6. [Clasificación temporal del contenido (cerrado en migraciones 0006 + 0007)](#6-clasificación-temporal-del-contenido-cerrado-en-migraciones-0006--0007)

---

## 1. Mapa general de la pipeline

```
                     ┌──────────────────────────────────────────┐
   USUARIO ─▶ /ingest │  RabbitMQ q.url.ingesta                  │
                     │            │                              │
                     │            ▼                              │
                     │  ┌─────────────────────┐                  │
                     │  │ cerebro-scraper     │                  │
                     │  │  └─ Prompt #1       │ ← extrae metadata│
                     │  │     (cerebro-lite)  │   incl. caducidad│
                     │  └────────┬────────────┘                  │
                     │           │ outbox: recurso.procesado     │
                     │           ▼                               │
                     │  ┌─────────────────────┐                  │
                     │  │ cerebro-embedder    │                  │
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
                  Prompt #5 (chatbot Streamlit de desarrollo local)
```

**Servicio dorsal**: todos los prompts pasan por LiteLLM (contenedor
`cerebro-litellm`, expuesto en `http://localhost:4000` en desarrollo).
El proxy LiteLLM expone los alias virtuales `cerebro-lite`, `cerebro-pro`
y `cerebro-embeddings` que mapean a los providers configurados en su
`config.yaml`.

---

## 2. Prompts de ingesta

### 2.1 Extracción de metadata (scraper)

- **Componente**: prompt de extracción de metadata del worker scraper.
- **Disparador**: cada mensaje en la cola `q.url.ingesta`. El scraper
  baja la URL, limpia el HTML, y llama a este prompt con los primeros
  6000 caracteres del texto.
- **Modelo**: `cerebro-lite`.
- **Temperatura**: `0.1` (cuasi-determinista — buscamos estabilidad en
  la salida JSON).
- **Inputs interpolados**: `url`, `title` (HTML `<title>`),
  `clean_text[:6000]`.
- **Outputs esperados**: JSON estricto con 10 campos (los 7 originales
  + 3 añadidos en la migración 0006: `event_date`, `temporal_class`,
  `valor_archivistico`).
- **Qué intenta conseguir**: transformar HTML scrappeado en estructura
  consumible aguas abajo — categoría, palabras clave, volatilidad
  estimada, caducidad del recurso, y desde la migración 0006 también la
  **clasificación temporal del contenido** (¿es un evento concreto, una
  referencia descriptiva o evergreen?) y su **valor archivístico**
  (¿merece guardarse si su fecha es pasada?). El cruce policy × class ×
  valor decide el destino del recurso al ingestar — ver el documento de
  ciclo de vida.

**Texto literal del prompt:**

> El prompt empieza con un bloque opcional `[PISTAS ESTRUCTURADAS DEL HTML]`
> (poblado por `htmldate` + `extruct` — ver §4.3 de
> [5 · Herramientas IA](./5-herramientas-ia#43-pre-extraccion-determinista-antes-del-llm)).
> Después viene la lista de campos a producir. El bloque inicial solo
> aparece cuando hay datos deterministas que ofrecer.

```text
[PISTAS ESTRUCTURADAS DEL HTML — fuentes deterministas; úsalas como punto de partida pero contrástalas con el texto y la URL, no las prefieras ciegamente si entran en conflicto]
- event_date (htmldate/OG/JSON-LD): {pre_extracted.event_date}
- og:type: {pre_extracted.og_type}
- schema.org @type: {pre_extracted.schema_type}
- og:description: {pre_extracted.og_description}
- authors: {pre_extracted.authors}
- keywords (autor): {pre_extracted.keywords}
[FIN DATOS ESTRUCTURADOS]

Analiza el siguiente texto extraído de una página web y responde ÚNICAMENTE con un JSON válido (sin markdown) con estos campos:
- "title": título del contenido
- "summary": resumen de 2-3 frases en español
- "category": una palabra en inglés (technology, science, business, health, politics, entertainment, education, other)
- "keywords": lista de 3-5 palabras clave
- "volatility_score": "baja" (docs/tutoriales), "media" (artículos), "alta" (noticias), o "dinamica" (precios/stocks)
- "estimated_useful_life_days": entero entre 30 y 365
- "expiration_date": fecha ISO YYYY-MM-DD si el contenido menciona una fecha concreta de evento, deadline, fin de oferta o caducidad explícita; null si no aplica o no se puede determinar
- "event_date": fecha ISO YYYY-MM-DD del evento principal descrito en el contenido (puede ser pasada o futura). Si la URL contiene un patrón YYYY/MM/DD en el path (típico de prensa: '/2024/03/18/'), úsalo como pista cuando el texto no diga la fecha de forma explícita. Para documentos normativos (BOE, decretos, sentencias, RFCs), usa la 'Fecha de disposición', 'Fecha de publicación' o el año explícito del identificador (p.ej. 'Real Decreto 686/2010' → 2010-01-01, 'BOE-A-2010-9269' → 2010-01-01, 'RFC 821' deducido desde el header Date). null si no hay ninguna fecha identificable.
- "temporal_class": clasificación temporal del contenido:
    * "evento" — feria, concierto, deadline, oferta, lanzamiento con fecha concreta;
    * "referencia" — análisis o crónica descriptiva (artículo de prensa retrospectivo, informe técnico, paper, post-mortem);
    * "evergreen" — tutorial, documentación técnica estable, definición, guía atemporal QUE SIGA SIENDO LA REFERENCIA ACTUAL. Si el documento ha sido reemplazado, derogado, modificado por una versión posterior, retractado, marcado como deprecated o existe un sucesor que lo actualiza, NO uses evergreen — usa "referencia" en su lugar (es documentación histórica, no atemporal vigente).
- "valor_archivistico": ¿merece guardarse como referencia histórica si su fecha es pasada?
    * "alto" — datos verificables, análisis estructural, autoridad de la fuente (papers, informes oficiales tipo AEMET/BOE/sentencias, post-mortems con cifras, retrospectivas con datos, normativa superada pero con valor histórico, RFCs obsoletos por sucesores);
    * "medio" — artículo de prensa estándar, crónica común con valor moderado;
    * "nulo" — anuncio caducado o evento trivial pasado sin valor de referencia.

URL: {url}
Título HTML: {title or '(sin título)'}

Texto:
{clean_text[:6000]}

Responde SOLO con el JSON.
```

> El `clean_text` que llega al prompt puede empezar con los bloques
> sintéticos `[OBSOLESCENCIA DETECTADA — extractos del documento]` y
> `[METADATA DEL AUTOR]` (ver
> [3 · Componentes · cerebro-scraper](./3-componentes#-cerebro-scraper--el-lector-de-paginas)).
> El LLM los lee como cualquier otro párrafo del texto.

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

**Cómo se usa cada campo aguas abajo:**

- `temporal_class='evergreen'` o evento/referencia con **fecha futura** →
  `estado='procesando'` → `'activo'` tras embedder.
- `temporal_class != 'evergreen'` con **fecha pasada**: se compone la
  key `{evento_pasado|referencia_pasada}_{alto|medio|nulo}` y se lee
  la decisión de `usuarios.audit_policy[key]`:
  - `"activo"` → activo en KB (caducidad NULL).
  - `"cuarentena"` → cuarentena con motivo `evento_pasado`.
  - `"expirado"` → flag de auto-archivado pendiente; el embedder
    vectoriza igualmente y transiciona a `expirado` (archivo histórico).

**Manejo de errores**: reintentos con back-off. Si tras los reintentos
la llamada falla, **fail-open** con valores por defecto seguros:
`title=url`, `summary=primeros 400 chars`, `volatility="media"`,
`useful_life=30`, `expiration_date=None`, `event_date=None`,
`temporal_class="evento"`, `valor_archivistico="medio"`.

**Observaciones**:

- El prompt clasifica la naturaleza temporal del contenido
  (`temporal_class`: evento / referencia / evergreen) y su
  `valor_archivistico` desde la migración 0006. Antes solo pedía
  `expiration_date` y caía al fallback `today + useful_life` para
  artículos descriptivos sobre el pasado — ese era el comportamiento
  documentado en la [sección 6](#6-clasificación-temporal-del-contenido-cerrado-en-migraciones-0006--0007)
  como referencia histórica.
- `temperature=0.1` (no 0.0) es un compromiso: la salida es JSON
  estructurado pero algunos campos (`summary`, `keywords`) se benefician
  de un poco de variabilidad estilística.
- Trunca el texto a 6000 chars — páginas largas pierden contexto en
  esta fase. El chunking para RAG ocurre después, en el embedder,
  sobre el `contenido` completo guardado en BD. El bloque
  `[OBSOLESCENCIA DETECTADA]` se prepone **antes** del truncado, así
  que los marcadores de derogación llegan al LLM aunque el cuerpo
  exceda 6000 chars.
- **Merge defensivo post-LLM**: si la respuesta del LLM contiene
  `event_date=null` o `keywords=[]`, el scraper rellena ese campo con
  el valor determinista de `pre_extracted` antes de persistir en
  Postgres. Si el LLM falla por completo (3 retries agotados), el
  fallback hard-coded (`title=url`, `summary=primeros 400 chars`,
  etc.) también se enriquece con `event_date` y `keywords`
  pre-extraídos. Resultado: `event_date` y `keywords` rara vez quedan
  vacíos si el HTML tiene metadatos estructurados.
- **Heurística de coherencia URL-año**: si `htmldate` devuelve un año
  contradictorio con el que aparece en la URL (`BOE-A-YYYY-…`,
  `/YYYY/MM/`), se sobreescribe a `{año_url}-01-01` antes de pasarlo
  al LLM. Evita que el LLM herede una fecha errónea del CMS y
  preserva la pista del prompt para normativa (`BOE-A-2010-…` → 2010).

---

### 2.2 Clasificador de relación semántica (embedder)

- **Componente**: prompt de tipificación de relaciones del worker
  embedder.
- **Disparador**: tras generar el embedding de un recurso, cuando
  Qdrant detecta uno preexistente con alta similitud. Se invoca por
  cada par (nuevo, antiguo) cuya similitud supere el umbral.
- **Modelo**: `cerebro-lite`.
- **Temperatura**: `0.0` (determinismo absoluto — la salida es un enum
  de 5 valores).
- **Tokens máximos**: `max_tokens: 10` (limitación dura — el LLM solo
  debe responder UNA palabra).
- **Inputs interpolados**: `new_info.title`, `new_info.summary`,
  `old_info.title`, `old_info.summary`.
- **Outputs esperados**: una sola palabra del enum
  `{ES_UN, CONTRADICE, EXTIENDE, VUELVE_OBSOLETO, ASOCIACION_GENERAL}`.
- **Qué intenta conseguir**: tipificar la relación entre dos recursos
  similares para alimentar el grafo (tabla `grafo_relaciones`) y
  disparar el colisionador semántico. Si la relación es `VUELVE_OBSOLETO`
  o `CONTRADICE`, el recurso antiguo se manda a cuarentena con motivo
  `colision_semantica`.

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

> Nota: el prompt incluye un newline inicial y 8 espacios de
> indentación por línea (artefacto de un f-string indentado). Si
> reproduces este prompt en el sandbox de LiteLLM, incluye la
> indentación tal cual — empíricamente no afecta al output pero forma
> parte del input real en producción.

**Manejo de errores**: try/except. Si LiteLLM falla, retorna
`"ASOCIACION_GENERAL"` (la relación más conservadora — no dispara
transición de cuarentena). El parser busca substrings del enum en la
respuesta para tolerar ruido en el formato.

**Observaciones**:

- Patrón **enum-classification** muy reusable: temperatura 0.0 +
  `max_tokens` bajo + parser tolerante a ruido. Si en el futuro se
  quiere clasificar algo nuevo con cardinalidad fija, este es el
  template a copiar.
- El prompt es **monolingüe en español** mientras que el enum es
  mayúsculas-snake-case. No genera confusión empíricamente, pero es un
  detalle de estilo a refinar si se internacionaliza.
- Solo se ejecuta cuando hay un "match" en Qdrant — no en toda
  ingesta. Eso limita el coste pero también significa que el grafo no
  se construye para recursos completamente nuevos.

---

## 3. Prompts de consulta (chat)

### 3.1 Chat con RAG

- **Componente**: system prompt del endpoint `POST /chat` cuando hay
  contexto recuperado de Qdrant.
- **Disparador**: cada `POST /chat` con `use_rag=true` y al menos un
  hit válido en Qdrant cuyo recurso esté `activo` para el tenant.
- **Modelo**: dinámico — viene en el campo `req.model` del body,
  típicamente `cerebro-lite` o `cerebro-pro`.
- **Streaming**: sí (`stream: true`), respuesta SSE.
- **Inputs interpolados**: `context_block` (fragmentos de chunks del
  RAG formateados como markdown). Los chunks vienen de la colección
  `cerebro_chunks` en Qdrant, ordenados por score descendente.
- **Outputs**: respuesta libre en lenguaje natural. El streaming
  devuelve deltas `{choices: [{delta: {content: "..."}}]}`.
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

**Construcción del `context_block`**: cada hit de Qdrant se formatea
en un bucle dentro del handler de `/chat`:

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

**Manejo de errores**: el handler captura cualquier fallo del RAG y
deja `context_block=""`. Si el bloque queda vacío, se ramifica al
prompt **3.2** (sin RAG). El stream emite `data: {"type": "error", ...}`
ante fallos del LLM para que el frontend muestre el error al usuario en
lugar de un bubble vacío.

**Observaciones**:

- El prompt incluye solo los **10 últimos mensajes** del historial
  (sliding window), no toda la conversación.
- No hay límite explícito sobre el tamaño del `context_block`. Si
  Qdrant devuelve muchos chunks largos, el system prompt puede llegar
  a decenas de miles de tokens — confía en el rate limit de LiteLLM y
  la ventana del modelo.

---

### 3.2 Chat sin RAG (fallback)

- **Componente**: system prompt del endpoint `POST /chat` cuando no
  hay contexto.
- **Disparador**: `POST /chat` con `use_rag=false`, o con `use_rag=true`
  pero sin hits relevantes (Qdrant vacío o todos los hits filtrados
  por estado).
- **Modelo / temperatura / streaming**: igual que 3.1.
- **Inputs**: ninguno (prompt estático).
- **Outputs**: respuesta libre.
- **Qué intenta conseguir**: dejar claro al usuario que la respuesta
  NO viene de su KB, para que no asuma que tiene cobertura sobre la
  pregunta.

**Texto literal del prompt (system role):**

```text
Eres un asistente experto. La base de conocimiento del usuario no ha
devuelto resultados relevantes para esta pregunta. Responde con tu
conocimiento general e indícalo explícitamente.
```

**Observaciones**:

- Es el camino de salida más débil del sistema — el usuario podría no
  notar la diferencia con 3.1 si el LLM no acompaña la respuesta con
  la cláusula "según mi conocimiento general". Vigilar: si la calidad
  percibida del chat baja, este prompt es el primer sospechoso.
- Se puede observar en métricas cuándo se dispara por el log
  estructurado del chat (`hits=0`).

---

### 3.3 Chat legacy Streamlit (deprecated)

- **Componente**: chatbot Streamlit de desarrollo local.
- **Disparador**: solo si alguien arranca `streamlit run` sobre el
  módulo del chatbot manualmente. **NO está en docker-compose**, no se
  ejecuta en producción.
- **Modelo**: dinámico (selectbox de Streamlit).
- **Inputs interpolados**: `context_block` (lista de URLs+similitud,
  NO chunks reales).
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
  que tampoco quede como servicio en `docker-compose.yml` (verificado:
  no aparece).
- Su `context_block` es muy pobre (solo `title — url [similitud: 0.XX]`),
  no incluye el texto del chunk. Diferencia clave vs 3.1 — el LLM no
  puede citar datos textualmente.

---

## 4. Prompts de auditoría / seguridad

### 4.1 Pre-push hook

- **Componente**: template externo `ops/prompts/pre-push.txt` (18
  líneas).
- **Disparador**: hook git `.githooks/pre-push` antes de cada
  `git push`. El hook envía el diff a través del cliente compartido
  LiteLLM (ver §5).
- **Modelo**: `cerebro-lite` (default del cliente compartido; la
  variable de entorno `LITELLM_MODEL` puede sobreescribirlo).
- **Temperatura**: `0` (audit determinista).
- **`max_tokens`**: `600` (default del cliente compartido).
- **Inputs interpolados**: `{diff}` — diff completo de
  `git diff origin/<branch>..HEAD`, truncado a `MAX_DIFF_CHARS`
  (actualmente `8000`), con aviso por stderr cuando se trunca.
- **Outputs esperados**: una de dos formas:
  - `CLEAN` (línea única) si no hay hallazgos.
  - Una línea por hallazgo con el prefijo `CRITICAL|HIGH|MEDIUM:
    archivo:línea descripción`.
- **Qué intenta conseguir**: cazar 6 categorías clásicas de
  vulnerabilidad específicas de LinkAnvil antes de subir a GitHub.
  Bloquea el push solo si encuentra `CRITICAL`; `HIGH`/`MEDIUM` son
  warnings que no bloquean.

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

**Manejo de errores**: el cliente compartido retorna respuesta nula si
LiteLLM no responde — el hook trata el nulo como **fail-open** (avisa
por stderr y el push continúa sin análisis). El push **no se bloquea**
si LiteLLM cae.

**Observaciones**:

- Las 6 categorías son **fijas y específicas del dominio**. Si añades
  una nueva práctica de seguridad (por ejemplo, OAuth), edita el
  archivo `.txt` del prompt, no el código del hook.
- Cuidado con el truncado a 8000 chars en PRs grandes — el análisis es
  parcial.
- Asume que el repo respeta el patrón outbox: si un día se añade un
  servicio nuevo con su propia ruta de eventos, este prompt empezará a
  generar falsos positivos en la categoría 5.

---

### 4.2 Weekly audit cron

- **Componente**: template externo `ops/prompts/weekly-audit.txt`
  (19 líneas).
- **Disparador**: cron semanal (script `ops/cron/weekly_audit.py`
  invocado por cron del host o equivalente según despliegue).
- **Modelo**: `cerebro-lite` (default).
- **Temperatura**: `0`.
- **`max_tokens`**: `1200` (más generoso que pre-push porque el output
  es un reporte estructurado).
- **`timeout`**: 60s.
- **Inputs interpolados**: `{code}` — concatenación de archivos
  críticos (auth, outbox, scraper, embedder).
- **Outputs esperados**: markdown con 3 secciones fijas:
  - `## Resumen Ejecutivo`
  - `## Hallazgos (CRITICAL/HIGH/MEDIUM)`
  - `## Acciones recomendadas`
- **Qué intenta conseguir**: auditoría más profunda y reflexiva que el
  pre-push. No mira un diff, mira el código entero de archivos
  sensibles y produce un informe legible que se archiva en
  `ops/sessions/security-audit-<fecha>.md`.

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

**Manejo de errores**: como en 4.1, fail-open vía el cliente
compartido. Si la ejecución cron falla, no rompe nada; al lunes
siguiente vuelve a intentar.

**Observaciones**:

- Las **6 categorías son casi idénticas a 4.1** con una addición:
  "Rate limiting" (categoría 5 aquí). Conviene mantener ambos prompts
  alineados — si añades una categoría, hazlo en los dos sitios.
- Output en markdown es legible para humanos.
- Si los archivos auditados crecen, el prompt puede superar el
  contexto de `cerebro-lite`. En ese caso, considerar dividir en
  múltiples llamadas (por archivo) o pasar a `cerebro-pro`.

---

## 5. Cliente LiteLLM compartido

- **Componente**: módulo Python `litellm_client` que vive en
  `ops/cron/`. Se importa como librería desde los hooks de git y los
  scripts cron.
- **API pública**: `send_prompt(prompt, max_tokens=600, timeout=30, ...)`
  → cadena de respuesta o `None` si la llamada falla.
- **Quién lo usa**: los prompts #6 (pre-push) y #7 (weekly audit). Los
  prompts #1-#5 llaman directamente a `httpx` desde sus propios
  módulos.
- **Resolución de credenciales** (orden de precedencia):
  1. Variable de entorno `LITELLM_KEY` (exportada en el shell).
  2. Variable de entorno `LITELLM_MASTER_KEY` (alias usado por
     docker-compose).
  3. Fallback: parser de `.env` del root del repo que puebla
     `os.environ` con `setdefault` (no pisa overrides manuales).
- **Resolución de URL**: variable `LITELLM_URL` → default
  `http://localhost:4000`. Se valida para evitar esquemas no-HTTP.
- **Resolución de modelo**: variable `LITELLM_MODEL` → default
  `cerebro-lite`.
- **Comportamiento de errores**: nunca lanza. Captura errores de red
  y de parsing, imprime warning y retorna `None`.
- **Headers que envía**:
  - `Content-Type: application/json`
  - `Authorization: Bearer <key>` (si hay key resuelta).

**Por qué los prompts #1-#5 NO usan este cliente**:

- Son código de runtime (workers / API) que ya tienen un cliente
  `httpx.AsyncClient` abierto en el lifespan del proceso. Reusan el
  pool de conexiones.
- Necesitan streaming (chat) o headers extra ya hardcodeados con la
  `LITELLM_KEY` del entorno del contenedor.
- Histórico — el cliente compartido se introdujo para hooks/cron
  donde no había httpx ni event loop. Centralizarlo todo en un único
  cliente queda como refactor pendiente.

---

## 6. Clasificación temporal del contenido (cerrado en migraciones 0006 + 0007)

> **Estado**: gap cerrado. Esta sección queda como referencia histórica.
> El comportamiento descrito al final del documento es el del prompt #1
> ANTES de las migraciones 0006 + 0007; el comportamiento actual se
> documenta en §2.1 ("Output esperado") y en el documento de ciclo de
> vida.

### Resumen del cierre

1. **Migración 0006**: el prompt #1 ahora extrae tres campos
   adicionales — `temporal_class` (evento/referencia/evergreen),
   `valor_archivistico` (alto/medio/nulo), `event_date` (fecha del
   evento, posiblemente pasada). Las columnas equivalentes existen en
   `recursos`.
2. **Migración 0007**: la decisión "qué hacer con un recurso de fecha
   pasada" se pasó de un enum `audit_strictness`
   (estricto/equilibrado/permisivo) a una `audit_policy` JSONB con 6
   keys (una por celda `temporal_class × valor_archivistico`). El
   frontend ofrece 3 presets (Estricto/Equilibrado/Permisivo) que
   rellenan las 6 celdas + 6 selects para ajuste fino. Decisiones
   posibles por celda: `activo`, `cuarentena`, `expirado`.
3. **Auto-archive**: cuando la policy decide `expirado` para un
   recurso de fecha pasada, el scraper marca el recurso como pendiente
   de auto-archivado y el embedder transiciona a `'expirado'` tras
   vectorizar (en vez del default `'activo'`). Los chunks quedan
   disponibles para recuperación vía toggle "Archivo ON" en el chat
   (campo `include_archive` del `/chat`).

### Trazas con el comportamiento nuevo (preset Equilibrado, default)

| URL | LLM clasifica | Destino |
|-----|---------------|---------|
| Expojove 2024 (artículo de prensa) | `referencia`, valor `medio` | cuarentena/`evento_pasado` |
| AEMET 2020 (informe oficial) | `referencia`, valor `alto` | auto-archive → `expirado` |
| Tutorial de Docker (evergreen) | `evergreen` | `activo` |
| Concierto Marzo 2026 | `evento`, valor `medio`, futuro | `activo` con caducidad |

Cambiar la policy desde `/profile` ajusta el destino sin reingestar.

### Apéndice — Comportamiento previo (solo referencia histórica)

> Los párrafos siguientes describen el caso que motivó las migraciones
> 0006 + 0007. **Ya no aplica al sistema actual** — se conserva como
> contexto para entender por qué se introdujeron `temporal_class`,
> `valor_archivistico` y `audit_policy`.

**Origen**: duda del usuario tras intentar ingestar
`https://aemetblog.es/2020/09/18/avance-climatico-nacional-del-verano-2020/`
(análisis del verano 2020 publicado por AEMET en 2020) y observar que
el sistema **no lo reconocía** como evento pasado ni como referencia
histórica.

**Comportamiento previo del prompt #1**:

- El prompt solicitaba `expiration_date` solo cuando el texto mencionaba
  "una fecha concreta de evento, deadline, fin de oferta o caducidad
  explícita".
- Para un artículo descriptivo sobre el pasado, el LLM tendía a
  responder `expiration_date: null`.
- Cuando `expiration_date` era null, la lógica de persistencia caía al
  fallback `fecha_caducidad = today + estimated_useful_life_days`.
- Resultado: el AEMET-2020 se guardaba como `activo` con caducidad
  sintética hacia 2026-09-XX, **perdiendo la naturaleza histórica del
  contenido**.

**Por qué este gap fue conceptual, no de implementación**:

La columna `recursos.fecha_caducidad` mezclaba **dos conceptos distintos**
que el prompt #1 no separaba:

| Concepto | Pregunta que responde | Ejemplo AEMET 2020 |
|----------|----------------------|--------------------|
| Caducidad del EVENTO | ¿Cuándo ocurre/terminó lo que el contenido describe? | Verano 2020 (pasado, ~5 años) |
| Vigencia del CONTENIDO | ¿Hasta cuándo es útil este recurso como referencia? | Indefinida (datos climáticos archivables) |

Para los recursos tipo "concierto futuro / deadline / oferta", ambos
conceptos coincidían y el sistema funcionaba. Para los tipo "análisis
descriptivo / referencia histórica / tutorial atemporal", divergían y
el sistema se equivocaba.

**Direcciones consideradas en su momento** (las opciones 1 y 2 fueron
las que finalmente se implementaron en las migraciones 0006 + 0007):

1. **Nuevo campo en el output del prompt #1**: `temporal_class` (enum:
   `evento` / `referencia` / `evergreen`). Implementado en 0006.
2. **Separar columnas**: `fecha_evento` (cuándo ocurre lo descrito,
   puede ser pasado) y `fecha_caducidad` (vigencia del recurso).
   Implementado en 0006.
3. **Toggle de usuario**: dejar el LLM como estaba y añadir un control
   en la UI del KB para que el usuario marcase manualmente un recurso
   como "Histórico/Referencia". No se implementó como mecanismo
   principal; el equivalente actual es la `audit_policy` configurable
   desde `/profile` (migración 0007).
4. **Híbrido**: combinar (1) y (3) — LLM clasifica por defecto, usuario
   puede sobreescribir desde la UI. Parcialmente vigente: el LLM
   clasifica y la policy del usuario decide qué hacer con cada celda
   class × valor.

**Comportamiento previo end-to-end (antes de 0006 + 0007)**:

- AEMET 2020 → ingestado como `activo` con caducidad sintética futura.
- A los `estimated_useful_life_days` días → la auditoría temporal lo
  movía a cuarentena con motivo `caducidad`.
- A los 30 días más (`OBSOLESCENCE_GRACE_DAYS`) → `expirado`.
- El usuario podía rescatarlo manualmente desde `/quarantine` o
  `/expired` con el botón "Rescatar", que recalculaba caducidad según
  `volatilidad`.

---

## Apéndice — Cuándo actualizar este documento

Si editas:

| Cambio | Acción |
|--------|--------|
| Texto literal de un prompt inline | Actualizar el bloque ```text correspondiente en el mismo commit |
| Modelo / temperatura / max_tokens | Actualizar la tabla de cabecera del prompt afectado |
| Archivos en `ops/prompts/*.txt` | El doc cita el contenido literal — re-pegar |
| Signatura de `send_prompt` en el cliente LiteLLM | Actualizar sección 5 |
| Nuevo prompt en cualquier sitio | Añadir nueva sección, actualizar TOC y mapa |
