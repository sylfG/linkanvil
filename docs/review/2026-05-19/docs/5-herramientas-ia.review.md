# Reality audit · `docs/src/5-herramientas-ia.md`

- **Branch**: `develop` · **Commit base**: `7c723f3` (commit que reescribió el doc)
- **Auditor**: `docs-reality-auditor`
- **Fecha**: 2026-05-19
- **Veredicto global**: **DIVERGE** — el doc tiene 1 hallazgo CRITICAL (sección entera describe una herramienta inexistente: Husky), múltiples HIGH (recuento de agentes desactualizado, lista de MCPs no coincide con `.mcp.json`, providers de LiteLLM ficticios) y varios MEDIUM (3 agentes nuevos sin documentar, modelo cerebro-embeddings con dimensión incorrecta).

---

## Resumen ejecutivo

| Severidad | Cantidad |
|---|---|
| CRITICAL | 1 |
| HIGH | 4 |
| MEDIUM | 6 |
| LOW | 2 |

El doc se escribió antes de que se añadieran 3 agentes nuevos y, además, describe una stack de hooks (Husky) que **no existe en el repo** — los hooks reales están en `.githooks/` y son shell + Python puros, no Husky. Las correcciones son acotadas pero no triviales.

---

## CRITICAL · Husky no existe en el repo

**`docs/src/5-herramientas-ia.md:175-208`** — toda la §5 ("Git hooks asistidos por IA") afirma:

> "Hooks configurados con Husky en `.husky/`. Se ejecutan en cada desarrollador local…"

**Realidad**:
- `.husky/` **no existe** (`ls .husky/` → `No such file or directory`).
- No hay dependencia Husky en el proyecto (Python-first, no hay `package.json` que la justifique).
- Los hooks reales viven en `.githooks/` (`git config core.hooksPath` → `.githooks`).
- Archivos presentes: `.githooks/pre-commit` (bash) y `.githooks/pre-push` (Python).

**Además, los snippets del doc no coinciden con el código real**:

1. **`docs/src/5-herramientas-ia.md:181-185`** muestra el pre-commit como:
   ```bash
   cd src && ruff check --fix .
   ```
   Pero `.githooks/pre-commit` hace algo mucho más sofisticado: recoge solo los `.py` staged, corre `ruff check` (sin `--fix`) **y** `ruff format --check`, y falla con instrucciones específicas. No hace `cd src`. No usa `--fix` (no re-stagea archivos como el doc sugiere).

2. **`docs/src/5-herramientas-ia.md:191-195`** muestra el pre-push como un one-liner bash con pipe:
   ```bash
   git diff origin/$BRANCH..HEAD | python ops/cron/litellm_client.py \
       --prompt ops/prompts/pre-push.txt --model cerebro-lite
   ```
   Pero `.githooks/pre-push` es un script Python completo de ~140 líneas (`.githooks/pre-push:1-140`) que:
   - Parsea stdin del protocolo git hook (`<local-ref> <local-sha> <remote-ref> <remote-sha>`).
   - Maneja branches nuevas (`_resolve_new_branch_base` con `NEW_BRANCH_BASE_REFS`).
   - Restringe el diff a `WATCH_PATHS` (no todo el diff).
   - Trunca a `MAX_DIFF_CHARS`.
   - Invoca `litellm_client.send_prompt()` como librería, **no** como CLI con `--prompt`/`--model`.

**Acción**: reescribir §5 completa. Renombrar a "Git hooks (githooks/, no Husky)". Sustituir snippets por extractos reales o pseudocódigo veraz.

---

## HIGH · Conteo de agentes desactualizado (24 → 27)

**`docs/src/5-herramientas-ia.md:11, 49, 165, 167`** — el doc afirma "Agentes Claude Code (24)" en 4 lugares.

**Realidad** (`ls .claude/agents/ | wc -l`): hay **27 archivos** `.md`. El doc fue escrito antes de que se añadieran:

1. `.claude/agents/docs-reality-auditor.md` — model `sonnet`. *"Audita UN documento markdown contra la realidad del código."*
2. `.claude/agents/backlog-implementation-auditor.md` — model `sonnet`. *"Audita TODOS los backlogs F-XX.Y de Extractor_de_Requisitos/backlog/ contra el código real…"*
3. `.claude/agents/commit-backlog-reconciler.md` — model `sonnet`. *"Reconcilia commits recientes con backlogs F-XX.Y…"*

**Acción**: actualizar título de §2, tabla de contenidos, frase final "Total en `.claude/agents/`: 24 archivos." en línea 165. Añadir entradas en una **nueva familia §2.7 bis · Auditoría documental/backlog** o ampliar la existente §2.7.

---

## HIGH · Lista de MCPs no coincide con `.mcp.json`

**`docs/src/5-herramientas-ia.md:127-141`** — tabla con 11 MCPs.

**MCPs documentados que NO existen en `.mcp.json`**:

| Doc dice | Realidad |
|---|---|
| `filesystem` | Ausente en `.mcp.json` |
| `playwright` | Ausente |
| `notion` | Ausente |
| `memory` | Ausente |
| `time` | Ausente |

**MCPs reales en `.mcp.json` que el doc omite**:

| Servidor real | `.mcp.json` |
|---|---|
| `n8n` (`@czlonkowski/n8n-mcp`) | sí |
| `redis` (`@gongrzhe/server-redis-mcp`) | sí |
| `brave-search` | sí |
| `docker` (`mcp-server-docker`) | sí |
| `telegram` (`telegram-mcp`) | sí |
| `prometheus` (`prometheus-mcp-server`) | sí |

**Coinciden bien**: `postgres`, `qdrant`, `github`, `sequential-thinking`, `fetch`, `context7` (6 de los 12 reales).

El número total real es **12**, no 11. La sección entera necesita reescritura.

**Acción**: regenerar §3 desde cero leyendo `.mcp.json` línea a línea. Documentar cada uno con su uso real en el proyecto.

---

## HIGH · Providers reales de `cerebro-*` son ficticios en el doc

**`docs/src/5-herramientas-ia.md:151-153`** — la tabla afirma:

| Alias | Provider real "típico" según el doc |
|---|---|
| `cerebro-lite` | "Groq Llama 3.1 8B / Mistral Nemo" |
| `cerebro-pro` | "Claude Sonnet 4.5 / GPT-4o" |
| `cerebro-embeddings` | "Voyage-3 / OpenAI text-embedding-3" |

**Realidad** (`infra/litellm/config.yaml:8-37`): **TODOS los providers son NVIDIA NIM**, no Groq/Anthropic/OpenAI/Voyage.

| Alias | Provider real configurado |
|---|---|
| `cerebro-lite` | `openai/meta/llama-3.1-8b-instruct` + fallback `openai/mistralai/mixtral-8x7b-instruct-v0.1` — **vía NVIDIA NIM** (`api_base: https://integrate.api.nvidia.com/v1`) |
| `cerebro-pro` | `openai/meta/llama-3.3-70b-instruct` + fallback `openai/nvidia/llama-3.3-nemotron-super-49b-v1.5` — **vía NVIDIA NIM** |
| `cerebro-embeddings` | `openai/nvidia/nv-embedqa-e5-v5` — **vía NVIDIA NIM** |

El comentario en `infra/litellm/config.yaml:1-3` lo explicita: *"Estrategia: Lite + Pro usando modelos gratuitos de NVIDIA NIM Preview"*.

Decir "Groq/Anthropic/Voyage típicos" no es un ejemplo aspiracional inocente — es factualmente incorrecto y confunde al lector que vaya a `config.yaml` esperando ver esos providers.

**Acción**: corregir §4 tabla. Aclarar que la totalidad de la prod-stack actual corre sobre NVIDIA NIM Preview (free tier) y que el alias permite cambiar sin tocar código.

---

## HIGH · Dimensión de embeddings posiblemente incorrecta

**`docs/src/5-herramientas-ia.md:153`** dice:
> "Vectores **1024-dim** para Qdrant"

**`docs/src/5-herramientas-ia.md:251`** (script de verificación de `build_staged_embeddings.py`) repite:
> "log final muestra `embedded=3/3 dims=1024`"

**Posible discrepancia**: el modelo configurado es `nvidia/nv-embedqa-e5-v5` (`infra/litellm/config.yaml:35`). E5-v5 base produce típicamente vectores de **1024 dimensiones** — el doc puede estar correcto. Sin embargo, sin verificar el código de `build_staged_embeddings.py` para confirmar `dims=1024` hardcoded vs descubierto, queda como HIGH sospechoso.

**Acción**: confirmar dim real con `python -c "import litellm; r=litellm.embedding(model='cerebro-embeddings', input='test'); print(len(r.data[0]['embedding']))"` o leer la verificación del script. Si difiere, corregir.

---

## MEDIUM · 3 agentes nuevos no documentados

Los siguientes existen en `.claude/agents/` y no tienen entrada en §2:

- **`docs-reality-auditor.md`** (sonnet) — auditoría doc-vs-código (este mismo agente). Encaja en §2.7 Auditoría.
- **`backlog-implementation-auditor.md`** (sonnet) — auditoría backlog-vs-código (`Extractor_de_Requisitos/backlog/`). Encaja en §2.7.
- **`commit-backlog-reconciler.md`** (sonnet) — reconciliación commits↔backlogs, creación de F-XX.Y nuevos. Probablemente justifica una nueva familia "§2.10 Backlog management" o ampliar §2.9 a "Documentación y backlog".

**Acción**: añadir filas a las tablas correspondientes con `model | descripción corta`.

---

## MEDIUM · §1 pirámide cita "5 prompts inline" sin lista

**`docs/src/5-herramientas-ia.md:31`**:
> "5 prompts inline en código (scraper, embedder, chat)"

**`docs/src/5-herramientas-ia.md:172`** referencia "los 5 prompts inline (scraper, embedder, chat RAG/no-RAG, clasificador semántico)" — esto sí enumera 5. La §1 omite "chat no-RAG" y "clasificador semántico" y deja solo 3 ejemplos entre paréntesis.

**Acción**: alinear ambas menciones para que coincidan o llevar al lector a la §7 referenciada.

---

## MEDIUM · §1 pirámide describe Husky como "git hooks"

**`docs/src/5-herramientas-ia.md:32`**:
> "• 2 git hooks (pre-commit ruff, pre-push security)"

La numeración es correcta (2 hooks) pero su descripción se contradice con §5 que dice Husky. Resolver coherentemente al corregir CRITICAL.

---

## MEDIUM · §6 schedule del workflow n8n: verificar

**`docs/src/5-herramientas-ia.md:215`** dice schedule `0 3 * * *` (03:00 UTC diario).

`infra/n8n/workflows/audit_cron_daily.json` contiene un nodo `"name": "Cron 03:00 diario"` con `field: cronExpression`. El nombre del nodo sugiere 03:00 pero no validé la expresión literal en el JSON. **Probablemente correcto**, pero recomiendo verificar el `value` de la expresión exacta.

**Acción**: `jq '.. | select(.cronExpression?)' infra/n8n/workflows/audit_cron_daily.json` para confirmar.

---

## MEDIUM · Mención a `agent-scheduled-audit.yml` GitHub Action

**`docs/src/5-herramientas-ia.md:247`** dice:
> "Puede activarse vía Antigravity trigger o **GitHub Action `agent-scheduled-audit.yml`**."

**Realidad**: en `.github/workflows/` solo existen `ci.yml`, `copilot-customization-check.yml`, `deploy-docs.yml`. No hay `agent-scheduled-audit.yml`. El doc inventa una integración que no existe.

**Acción**: eliminar referencia o crear el workflow si era intencional.

---

## MEDIUM · Sección 7 dice "3 GitHub Actions con IA", solo 1 usa IA realmente

**`docs/src/5-herramientas-ia.md:259-265`** lista los 3 workflows y la propia tabla aclara que `ci.yml` y `deploy-docs.yml` **no usan IA**. El título y el conteo en §1 ("3 GitHub Actions") son engañosos. Solo `copilot-customization-check.yml` usa Claude.

**Acción**: renombrar §7 a "GitHub Actions del pipeline (1 con IA)" o similar.

---

## LOW · Mención a "Antigravity trigger"

**`docs/src/5-herramientas-ia.md:247`** — "Antigravity trigger" se cita sin definir. No es propio del repo. Si se mantiene, añadir nota explicativa o eliminar.

---

## LOW · Tabla §2.7 menciona `repo-reviewer` con modelo "haiku→sonnet (2 fases)"

**`docs/src/5-herramientas-ia.md:107`** — formato inusual de "haiku→sonnet (2 fases)" no se ha verificado contra el frontmatter de `.claude/agents/repo-reviewer.md`. Probablemente correcto, pero anotarlo para validar en un pase futuro.

---

## Inventario verificado (lo que SÍ existe y coincide)

| Recurso del doc | Archivo real | Estado |
|---|---|---|
| `infra/n8n/workflows/audit_cron_daily.json` | existe | OK |
| `.github/workflows/ci.yml` | existe | OK |
| `.github/workflows/deploy-docs.yml` | existe | OK |
| `.github/workflows/copilot-customization-check.yml` | existe | OK |
| `ops/prompts/pre-push.txt` | existe | OK |
| `ops/prompts/weekly-audit.txt` | existe | OK |
| `ops/cron/weekly_audit.py` | existe (`ops/cron/weekly_audit.py:1`) | OK — header coincide con la descripción del doc |
| `ops/build_staged_embeddings.py` | existe | OK — header docstring coincide casi literalmente con §9.2 (referencia Slice 6.5, migración 0011, idempotencia ON CONFLICT) |
| `ops/cron/litellm_client.py` | existe | OK |
| `cerebro-lite` / `cerebro-pro` / `cerebro-embeddings` aliases | sí en `infra/litellm/config.yaml:8,21,34` | OK (aliases existen; **providers reales son otros** — ver HIGH arriba) |

### Agentes del doc (24) verificados uno a uno

| Agente citado | `.claude/agents/*.md` |
|---|---|
| planner | ✓ |
| architect | ✓ |
| code-reviewer | ✓ |
| security-reviewer | ✓ |
| typescript-reviewer | ✓ |
| database-reviewer | ✓ |
| silent-failure-hunter | ✓ |
| comment-analyzer | ✓ |
| tdd-guide | ✓ |
| build-error-resolver | ✓ |
| refactor-cleaner | ✓ |
| ui-engineer | ✓ |
| performance-optimizer | ✓ |
| docs-lookup | ✓ |
| e2e-runner | ✓ |
| pr-test-analyzer | ✓ |
| loop-operator | ✓ |
| memory-consolidator | ✓ |
| conversation-analyzer | ✓ |
| harness-optimizer | ✓ |
| architecture-auditor | ✓ |
| repo-reviewer | ✓ |
| github-orchestrator | ✓ |
| doc-updater | ✓ |

**24/24 citados existen.** El problema no es citar inexistentes, es **omitir 3 que sí existen**.

---

## Lista de cambios sugeridos (priorizada)

1. **[CRITICAL]** Reescribir §5 entera — Husky → `.githooks/`, snippets verídicos.
2. **[HIGH]** Actualizar todos los lugares "24 agentes" → "27 agentes" y añadir entradas para los 3 nuevos.
3. **[HIGH]** Regenerar tabla §3 desde `.mcp.json` (lista real: postgres, qdrant, n8n, redis, github, fetch, brave-search, sequential-thinking, docker, telegram, prometheus, context7 — **12, no 11**).
4. **[HIGH]** Corregir §4 tabla — providers reales son NVIDIA NIM, no Groq/Anthropic/Voyage.
5. **[MEDIUM]** Eliminar referencia inexistente a `agent-scheduled-audit.yml`.
6. **[MEDIUM]** Aclarar "GitHub Actions con IA: 1, no 3" o ajustar título.
7. **[MEDIUM]** Alinear "5 prompts inline" en §1 y §4 con la misma enumeración.
8. **[MEDIUM]** Verificar literal cron expression del nodo n8n.
9. **[LOW]** Definir o eliminar "Antigravity trigger".
10. **[LOW]** Confirmar dimensión real de embeddings = 1024.

---

*Fin del reporte.*
