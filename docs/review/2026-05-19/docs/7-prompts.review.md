# Auditoría docs-reality — `docs/src/7-prompts.md`

**Branch auditada**: `develop` @ `7c723f3` (linkanvil)
**Fecha**: 2026-05-19
**Auditor**: docs-reality-auditor
**Documento**: `docs/src/7-prompts.md` (635 líneas)
**Última actualización declarada en el doc**: 2026-05-17

---

## Resumen ejecutivo

| Severidad | Hallazgos |
|-----------|-----------|
| **CRITICAL** | 0 — el texto literal de los 5 prompts inline está sustancialmente intacto |
| **HIGH** | 6 — drift masivo de números de línea (cientos / >1000 líneas) en casi todas las referencias a `src/api/main.py`, `src/data/db.py`, `src/scraper/worker.py` y `src/data/embedder_worker.py`. Riesgo: cualquier lector que abra el código por la línea citada **no encontrará el código descrito** |
| **MEDIUM** | 3 — pequeñas divergencias semánticas (indentación del prompt 4, prompt 1 no cita el texto literal, función `pre_push.py::_collect_diff` no existe con ese nombre) |
| **LOW** | 2 — observaciones menores de estilo / nomenclatura |

**Veredicto global**: el contenido conceptual del documento es **fiel a la realidad** (modelos, temperaturas, schemas, texto de prompts). El problema es **operativo**: los `path:línea` están sistemáticamente desactualizados, lo cual contradice la promesa explícita del propio doc:

> "Si modificas un prompt en código, actualiza este archivo en el mismo commit para que no se desincronicen." (`7-prompts.md:6-7`)

Los prompts no han cambiado pero el código alrededor sí — el commit que migró `src/api/main.py` a `1690+` líneas no actualizó este doc. Recomendación: refactor del doc para que las citas de línea sean **rangos amplios o anclajes a símbolos** (`función _extract_metadata_with_llm`, `dentro de @app.post("/chat")`), no números absolutos.

---

## Hallazgos detallados

### HIGH-01 — Drift masivo en referencias a `src/api/main.py` (prompts #2 y #3)

**Severidad**: HIGH
**Categoría**: line-number staleness

El documento cita repetidamente líneas del rango 500-810 de `src/api/main.py`, pero el archivo real tiene **2041 líneas** y el endpoint `/chat` (donde viven los prompts #2 y #3) está en líneas 1697-1900+.

| Doc dice | Realidad (`src/api/main.py`) | Diferencia |
|----------|------------------------------|------------|
| `main.py:779-794` (prompt #2 RAG, sección 3.1, línea 217 del doc) | **lines 1798-1814** | +1019 líneas |
| `main.py:797-801` (prompt #3 fallback, sección 3.2, línea 291 del doc) | **lines 1815-1820** | +1018 líneas |
| `main.py:572-589` (construcción de `context_block`, línea 255 del doc) | **lines 1785-1794** | +1213 líneas |
| `main.py:803` (logger `CHAT model=...`, línea 315 del doc) | **lines 1826-1829** | +1023 líneas |

**Evidencia**:
- `src/api/main.py:1697` — `@app.post("/chat")` (no en línea ~770)
- `src/api/main.py:1799` — `system_prompt = (` con el texto del prompt RAG (no línea 779)
- `src/api/main.py:1816` — `system_prompt = (` rama `else` con el prompt sin RAG (no línea 797)
- `src/api/main.py:1826-1829` — `logger.info("CHAT model=%s use_rag=%s hits=%d ...")` (no línea 803)

**Impacto**: un lector que use Cmd+G "ir a línea 779" en `main.py` cae en código completamente distinto (probablemente middleware o un endpoint de listados). Esto erosiona la credibilidad de TODO el documento.

**Texto literal del prompt #2 (RAG)** — verificado **OK, coincide carácter por carácter** con `src/api/main.py:1799-1814`. La 4 reglas, el orden, las comillas simples en "'no hay información específica'", todo verbatim.

**Texto literal del prompt #3 (no RAG)** — verificado **OK, coincide carácter por carácter** con `src/api/main.py:1816-1820`.

**Recomendación**: sustituir todas las citas `main.py:779-794` por `main.py:@app.post("/chat") → bloque if context_block` o por rangos amplios `main.py:1797-1820` con anclaje al símbolo.

---

### HIGH-02 — Drift en referencias a `src/data/embedder_worker.py` (prompt #4)

**Severidad**: HIGH
**Categoría**: line-number staleness

El doc cita `src/data/embedder_worker.py:260-275` (línea 158 del doc). El prompt real está en lines **262-273**.

**Evidencia**:
- `src/data/embedder_worker.py:262-273` — `prompt = f"""\n    Como un evaluador experto, compara el nuevo documento con el antiguo...`
- `src/data/embedder_worker.py:277-281` — payload con `"model": "cerebro-lite"`, `"temperature": 0.0`, `"max_tokens": 10` ✅ coincide con el doc
- `src/data/embedder_worker.py:290-293` — parser tolerante: `for t in ["VUELVE_OBSOLETO", "CONTRADICE", "EXTIENDE", "ES_UN"]` ✅

El rango `260-275` está cerca pero es **inexacto** (el prompt real ocupa 262-273; el bloque entero hasta el parser llega a 296). No es bug bloqueante, pero sí inconsistente con la precisión que el doc declara perseguir.

**Comentario sobre el rango sugerido en mi prompt de auditoría ("líneas 260-290")**: el rango real del bloque completo (prompt + payload + parser) es 262-296.

---

### HIGH-03 — Drift en `src/data/db.py:170-177` (sección 6, línea 562 del doc)

**Severidad**: HIGH

El doc afirma:

> "Cuando `expiration_date` es null, `src/data/db.py:170-177` cae al fallback `fecha_caducidad = today + estimated_useful_life_days`."

Realidad: `src/data/db.py:265` contiene `fecha_caducidad = today + timedelta(days=useful_life)`. La lógica completa de fallback ocupa lines **257-267** dentro de `save_with_outbox` (linea 214). Las líneas 170-177 actuales pertenecen a otra función (`find_existing_recurso_by_url`).

**Evidencia**: `src/data/db.py:214` — `async def save_with_outbox(...)`; `src/data/db.py:257-267` — bloque de cálculo de `fecha_caducidad`.

---

### HIGH-04 — Drift en `src/scraper/worker.py` (prompt #1 y fail-open)

**Severidad**: HIGH

El doc cita:
- `worker.py:73-91` para la función `_extract_metadata_with_llm` (línea 79 del doc)
- `worker.py:115-123` para los valores fail-open (línea 134 del doc)

Realidad:
- `src/scraper/worker.py:69` — `async def _extract_metadata_with_llm(...)`
- `src/scraper/worker.py:73-112` — bloque del prompt (40 líneas, no 18 como sugiere "73-91")
- `src/scraper/worker.py:136-147` — diccionario fail-open con valores por defecto

**Evidencia**: `src/scraper/worker.py:136` — `return { "title": title or url, "summary": clean_text[:400], ..., "temporal_class": "evento", "valor_archivistico": "medio", }`. El rango 115-123 actual está dentro del `try:` y no contiene el fallback.

---

### HIGH-05 — Drift en `src/ui/chatbot.py` (prompt #5)

**Severidad**: HIGH

El doc cita `src/ui/chatbot.py:136-142` (línea 321 del doc). Realidad: el prompt vive en lines **136-139** del archivo (el archivo tiene 319 líneas, no llega a 142 con prompt — la línea 142 ya es código no relacionado).

**Evidencia**: `src/ui/chatbot.py:136-139` —
```python
system_prompt = (
    "Eres un asistente experto que responde usando el contexto de la base de conocimiento del usuario. "
    "Si no hay contexto relevante, responde con tu conocimiento general e indícalo."
)
```

**Verificación literal**: el texto declarado en el doc (líneas 333-337) **coincide verbatim** al concatenar las dos strings del código. ✅

---

### HIGH-06 — Función `pre_push.py::_collect_diff` no existe

**Severidad**: HIGH (referencia rota)
**Categoría**: broken cross-reference

El doc dice (línea 406):

> "Ver `pre_push.py::_collect_diff` para el algoritmo de truncado."

Realidad: **no hay archivo `pre_push.py`** en el repo. El hook es `.githooks/pre-push` (sin extensión, script Python ejecutable). La función real se llama `build_prompt` y vive en `.githooks/pre-push:124`. La constante `MAX_DIFF_CHARS = 8_000` está en `ops/cron/hook_config.py:12`. **No existe `_collect_diff`**.

**Evidencia**: `git ls-files | grep pre_push` retorna solo `ops/cron/tests/test_pre_push.py` (un test). El hook ejecutable es `.githooks/pre-push`, líneas 124-138 para `build_prompt`.

**Acción**: cambiar la referencia a `.githooks/pre-push::build_prompt` y `ops/cron/hook_config.py:MAX_DIFF_CHARS`.

---

### MEDIUM-01 — El doc NO incluye el texto literal del prompt #1

**Severidad**: MEDIUM
**Líneas afectadas**: doc 96-101

El doc dice explícitamente:

> "El prompt actual en `src/scraper/worker.py` solicita los 7 campos originales más los 3 nuevos. Para el texto exacto del prompt consulta el código fuente — varía con la fase de prompt-engineering."

Esto contradice la promesa del propio doc en su cabecera: "Si modificas un prompt en código, actualiza este archivo en el mismo commit para que no se desincronicen." Para los prompts #2, #3, #4, #5, #6, #7 sí se incluye el texto literal. **El #1 es el único que se omite**, y es justamente el más complejo y crítico de la pipeline.

**Recomendación**: o se incluye el texto literal (preferible, son ~40 líneas verificables), o se elimina la promesa de sincronización para este caso concreto.

El texto actual del prompt está en `src/scraper/worker.py:73-112` y se puede pegar verbatim. Es estable estructuralmente — los 10 campos del schema están documentados, y la migración 0006 ya está reflejada.

---

### MEDIUM-02 — Prompt #4 — indentación divergente

**Severidad**: MEDIUM
**Líneas afectadas**: doc 180-191 vs `src/data/embedder_worker.py:262-273`

El bloque ```text del doc presenta el prompt sin indentación. El código real tiene **8 espacios de indentación al inicio de cada línea** porque es un f-string dentro de un método:

```python
prompt = f"""
        Como un evaluador experto, compara el nuevo documento con el antiguo.
        Documento Nuevo (ID Reciente):
        Título: {new_info.get('title', '')}
        ...
```

Esto significa que el prompt que **realmente llega al LLM** tiene 8 espacios al principio de cada línea (y un newline inicial extra del `"""\n`). El doc presenta una versión "limpia" que es engañosa. Para un debugger que copie el prompt del doc al sandbox de LiteLLM, el resultado **no será exactamente lo que el LLM recibe en producción**.

**Recomendación**: o (a) reflejar la indentación real en el bloque ```text del doc, o (b) refactorizar `embedder_worker.py` para usar `textwrap.dedent()` o un raw string sin indent.

Empíricamente la indentación no suele afectar al output del LLM, pero el doc tiene como criterio "carácter por carácter" — y aquí no cumple.

---

### MEDIUM-03 — Sección 6 marcada "resuelto" pero el apéndice describe comportamiento como si fuera actual

**Severidad**: MEDIUM (consistencia interna)
**Líneas afectadas**: doc 511-621

La cabecera de la sección 6 dice:

> "**Estado**: gap cerrado. Esta sección queda como referencia histórica."

Pero más abajo, el subapartado "Comportamiento actual del prompt #1" (línea 556) y la lista (557-567) usa presente indicativo:

> "- El prompt solicita `expiration_date` solo cuando..."
> "- Para un artículo descriptivo sobre el pasado, el LLM tiende a responder `expiration_date: null`."
> "- Cuando `expiration_date` es null, `src/data/db.py:170-177` cae al fallback..."
> "- Resultado: el AEMET-2020 se guarda como `activo` con caducidad sintética hacia 2026-09-XX, **perdiendo la naturaleza histórica del contenido**."

Esto se contradice con el §2.1 actualizado, donde el prompt SÍ extrae `temporal_class` y `valor_archivistico`. Un lector queda confundido sobre si el bug AEMET-2020 está corregido o no.

**Recomendación**: encerrar el subapartado (líneas 549-621) dentro de un bloque "Comportamiento PRE-migración 0006 — solo referencia histórica" y cambiar todos los verbos a pretérito imperfecto.

---

### LOW-01 — Inconsistencia en el rango del prompt #2 (síntoma del drift)

**Severidad**: LOW

El doc declara prompt #2 RAG en líneas `779-794` (16 líneas). El bloque real ocupa `1798-1814` (17 líneas incluyendo el `f"{context_block}"` final dentro del paréntesis). Discrepancia menor de delimitación.

---

### LOW-02 — La nota "Última actualización: 2026-05-17"

**Severidad**: LOW

El doc declara última actualización 2026-05-17. El commit más reciente del repo en develop es `7c723f3 docs: reorganizar VitePress + inventario IA + integrar Extractor_de_Requisitos` (sin fecha visible en `git log -1 --oneline`, pero el doc declara explícitamente la fecha). Los drifts de línea documentados arriba sugieren que el código se ha movido SIN actualizar este doc desde antes de 2026-05-17.

---

## Verificaciones positivas (lo que SÍ está correcto)

✅ **Modelo declarado** — `cerebro-lite` en prompts #1, #4, #6, #7 → coincide con código.
✅ **Modelo dinámico** en prompts #2, #3 (`req.model`) → coincide con `src/api/main.py:1837`.
✅ **Temperatura** — 0.1 para #1, 0.0 para #4, 0 para #6/#7 → coincide.
✅ **Max tokens** — `max_tokens: 10` en #4, `600` default en pre-push, `1200` en weekly-audit → coincide con `embedder_worker.py:280`, `litellm_client.py:161`, `weekly_audit.py:185`.
✅ **Streaming** del chat → coincide (no verificado en detalle pero la estructura del endpoint /chat usa SSE).
✅ **Schema JSON del prompt #1** → los 10 campos declarados en la tabla del doc (lines 105-117) coinciden con los 10 campos en el diccionario fail-open de `worker.py:136-147` y con los campos solicitados en el prompt (`worker.py:73-107`).
✅ **Texto literal del prompt #6 (pre-push)** → `ops/prompts/pre-push.txt:1-19` coincide carácter por carácter con doc líneas 375-394.
✅ **Texto literal del prompt #7 (weekly-audit)** → `ops/prompts/weekly-audit.txt:1-19` coincide carácter por carácter con doc líneas 435-456.
✅ **Texto literal del prompt #2 (chat RAG)** → coincide verbatim (excepto la nota HIGH-01 sobre línea).
✅ **Texto literal del prompt #3 (chat sin RAG)** → coincide verbatim.
✅ **Texto literal del prompt #4 (embedder)** → coincide salvo indentación (MEDIUM-02).
✅ **Texto literal del prompt #5 (chatbot)** → coincide verbatim.
✅ **Mapa del pipeline** (líneas 31-66) → conceptualmente correcto.
✅ **Sliding window de 10 mensajes** (`req.messages[-10:]`) → verificado en `src/api/main.py:1823`.
✅ **Sin prompts no documentados** — los únicos archivos con `chat/completions` son los 4 ya documentados (scraper, embedder, api, chatbot). **No hay prompts huérfanos**.

---

## Auditoría de "prompts NUEVOS no documentados"

Búsqueda exhaustiva con `grep -rln "chat/completions\|cerebro-lite\|cerebro-pro" src/` produce:

- `src/scraper/worker.py` → prompt #1 (documentado)
- `src/data/embedder_worker.py` → prompt #4 (documentado)
- `src/api/main.py` → prompts #2, #3 (documentados)
- `src/ui/chatbot.py` → prompt #5 (documentado)

**No se detectan prompts adicionales** en src/. Tampoco en ops/ (solo los templates pre-push.txt y weekly-audit.txt, ambos documentados). El doc declara que existen exactamente 5 prompts inline + 2 templates = 7 prompts; la realidad confirma exactamente esto. ✅

**Si hubiera demos o flujos de extracción de eventos demo distintos del prompt #1**, no aparecen en `develop`. Si existen en otra rama (ej. `feature/demo-events`), no son objeto de esta auditoría.

---

## Plan de fix sugerido (prioridad descendente)

### P0 — refactor de citas de línea
Sustituir TODAS las citas `path:línea` exactas por anclajes a símbolos (`worker.py::_extract_metadata_with_llm`, `main.py::chat (rama if context_block)`, etc.). Reduce el drift a casi cero porque los nombres de función son estables.

Aplicar a:
- 7-prompts.md:79 — `worker.py:73-91` → `worker.py::_extract_metadata_with_llm (~líneas 69-112)`
- 7-prompts.md:134 — `worker.py:115-123` → `worker.py::_extract_metadata_with_llm fallback dict (~líneas 136-147)`
- 7-prompts.md:158 — `embedder_worker.py:260-275` → `embedder_worker.py::_classify_relation prompt (~líneas 262-273)`
- 7-prompts.md:217 — `main.py:779-794` → `main.py:@app.post("/chat") if context_block branch (~líneas 1798-1814)`
- 7-prompts.md:255 — `main.py:572-589` → `main.py:@app.post("/chat") frags loop (~líneas 1779-1794)`
- 7-prompts.md:291 — `main.py:797-801` → `main.py:@app.post("/chat") else branch (~líneas 1816-1820)`
- 7-prompts.md:315 — `main.py:803` → `main.py:@app.post("/chat") logger CHAT model=... (~línea 1826)`
- 7-prompts.md:321 — `chatbot.py:136-142` → `chatbot.py system_prompt construction (~líneas 136-139)`
- 7-prompts.md:406 — `pre_push.py::_collect_diff` → `.githooks/pre-push::build_prompt (~línea 124)`
- 7-prompts.md:562 — `db.py:170-177` → `db.py::save_with_outbox fecha_caducidad fallback (~líneas 257-267)`

### P1 — incluir texto literal del prompt #1
Pegar verbatim el contenido de `worker.py:73-112` en el bloque ```text que actualmente está en lines 96-101 del doc.

### P2 — clarificar sección 6
Encerrar el subapartado "Comportamiento previo" (lines 549-621) dentro de un bloque `> ⚠️ Sección histórica` y conjugar verbos en pretérito.

### P3 — alinear indentación prompt #4
O bien (a) reflejar la indentación real del f-string en el bloque ```text del doc, o (b) limpiar `embedder_worker.py` con `textwrap.dedent`.

---

## Anexo — Evidencia bruta

### Conteo de archivos
- `docs/src/7-prompts.md`: 635 líneas (doc auditado)
- `src/scraper/worker.py`: 328 líneas
- `src/api/main.py`: **2041 líneas** (el doc cita rangos < 810 → drift sistemático)
- `src/data/embedder_worker.py`: 678 líneas
- `src/ui/chatbot.py`: 319 líneas
- `src/data/db.py`: leído parcialmente — `save_with_outbox` en línea 214
- `ops/prompts/pre-push.txt`: 18 líneas (template externo, OK)
- `ops/prompts/weekly-audit.txt`: 19 líneas (template externo, OK)
- `ops/cron/litellm_client.py`: 218 líneas

### Snippets clave verificados

**Prompt #2 (RAG) en código real** — `src/api/main.py:1799-1814`:
```python
system_prompt = (
    "Eres un asistente experto. Tienes acceso al contexto extraído de la base "
    "de conocimiento del usuario, delimitado más abajo.\n\n"
    "REGLAS ESTRICTAS:\n"
    "1. Si la respuesta a la pregunta del usuario está total o parcialmente en "
    "el contexto, úsala como fuente principal y cita los datos textualmente "
    "(fechas, nombres, cifras) tal y como aparecen.\n"
    ...
    f"{context_block}"
)
```

**Prompt #4 (embedder) en código real** — `src/data/embedder_worker.py:262-273`:
```python
prompt = f"""
        Como un evaluador experto, compara el nuevo documento con el antiguo.
        Documento Nuevo (ID Reciente):
        Título: {new_info.get('title', '')}
        Resumen: {new_info.get('summary', '')}

        Documento Antiguo (ID Existente):
        Título: {old_info.get('title', '')}
        Resumen: {old_info.get('summary', '')}

        Tipifica la relación como UNA ÚNICA PALABRA: 'ES_UN', 'CONTRADICE', 'EXTIENDE', 'VUELVE_OBSOLETO' o 'ASOCIACION_GENERAL'.
        """
```

(Nótense las 8 espacios de indentación — ver MEDIUM-02.)

---

## Conclusión

El documento `7-prompts.md` tiene **alto valor conceptual** (mapa, schemas, descripciones de propósito, manejo de errores) y los textos literales de los prompts son fieles. Pero la **promesa de sincronización commit-a-commit está rota** en lo que respecta a números de línea: el código se ha movido masivamente (especialmente `src/api/main.py`, que ha pasado de ~800 a >2000 líneas) sin que esta documentación se actualice.

La acción más rentable es el refactor P0 (sustituir números por anclajes a símbolos). Eso elimina el 80% del problema con cambios cosméticos y vuelve el doc inmune a futuros movimientos de código.

No se detectan prompts no documentados ni divergencias críticas en los textos literales que vayan al LLM.

**Veredicto final**: PUBLICABLE con fix P0 obligatorio antes del próximo merge. P1-P3 deseable pero no bloqueante.
