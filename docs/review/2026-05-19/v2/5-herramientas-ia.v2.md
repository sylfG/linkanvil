# Herramientas IA del proyecto

> Inventario completo de toda la maquinaria IA que se usó para construir
> y operar LinkAnvil — desde los **agentes Claude Code** que escribieron
> el código hasta los **prompts en producción** que clasifican los
> recursos del usuario en tiempo real.

## Tabla de contenidos

1. [Visión general — la pirámide IA del proyecto](#vision-general)
2. [Agentes Claude Code (28)](#agentes-claude-code)
3. [MCP servers conectados (12)](#mcp-servers)
4. [Modelos LLM en producción (3, vía LiteLLM)](#modelos-llm-en-produccion)
5. [Git hooks asistidos por IA (2)](#git-hooks-asistidos-por-ia)
6. [Workflows automatizados (1 n8n)](#workflows-n8n)
7. [GitHub Actions del pipeline (1 con IA)](#github-actions-con-ia)
8. [Prompts externos (2 templates)](#prompts-externos)
9. [Scripts ad-hoc con IA (2)](#scripts-ad-hoc-con-ia)
10. [Cómo decidimos qué usar dónde](#decision-tree)

---

## 1. Visión general {#vision-general}

LinkAnvil incorpora IA en **tres capas** con responsabilidades muy
distintas. Confundirlas lleva a usar la herramienta equivocada — un
agente Claude Code en producción saldría carísimo; un modelo LiteLLM
en desarrollo no tendría contexto del repo. La pirámide:

```
┌─────────────────────────────────────────────────────────────┐
│   PRODUCCIÓN       (el usuario está delante)                │
│   • 3 modelos LiteLLM (cerebro-lite, -pro, -embeddings)     │
│   • 5 prompts inline (scraper, embedder, chat RAG/no-RAG,   │
│     clasificador semántico) — ver §7-prompts del sistema    │
│   • 1 workflow n8n (audit_cron_daily)                       │
├─────────────────────────────────────────────────────────────┤
│   BUILD & CI       (push, PR, deploy)                       │
│   • 3 GitHub Actions (solo 1 usa IA: copilot-check)         │
│   • 2 git hooks en .githooks/ (pre-commit ruff, pre-push)   │
│   • 2 scripts ad-hoc (weekly_audit, build_staged_embeddings)│
├─────────────────────────────────────────────────────────────┤
│   DESARROLLO       (Claude Code está delante)               │
│   • 28 agentes Claude Code                                  │
│   • 12 MCP servers                                          │
└─────────────────────────────────────────────────────────────┘
```

- **Desarrollo**: vive en la máquina local. Coste lo paga la API key
  personal del desarrollador.
- **Build/CI**: corre en GitHub Actions o git hooks. Coste lo paga la
  organización vía `ANTHROPIC_API_KEY` en secrets.
- **Producción**: corre en el cluster, sirviendo al usuario final.
  Coste viene de la `LITELLM_KEY` global (o de las virtual keys BYOK
  del usuario registrado).

---

## 2. Agentes Claude Code (28) {#agentes-claude-code}

Cada agente vive en `.claude/agents/<nombre>.md` con frontmatter
declarando modelo, descripción y herramientas permitidas. El harness
los invoca explícitamente (`Agent(subagent_type=...)`) o
automáticamente cuando un trigger encaja con la `description`.

### 2.1 Familia · Planificación

| Agente | Modelo | Cuándo se invoca |
|---|---|---|
| `planner` | sonnet | Features complejas, refactors grandes, descomposición en pasos |
| `architect` | opus | Decisiones arquitectónicas, trade-offs de escalabilidad |

### 2.2 Familia · Code review

| Agente | Modelo | Cuándo se invoca |
|---|---|---|
| `code-reviewer` | sonnet | Tras escribir/modificar código — review proactiva |
| `security-reviewer` | sonnet | Endpoints, auth, input handling, crypto |
| `typescript-reviewer` | sonnet | Todo cambio en `.ts` / `.tsx` — type safety, async correctness |
| `database-reviewer` | sonnet | SQL, migraciones, schema design (Postgres + Supabase patterns) |
| `silent-failure-hunter` | sonnet | Detección de catch vacíos, fallbacks peligrosos, stack traces perdidas |
| `comment-analyzer` | haiku | Comentarios desactualizados, redundantes, TODOs obsoletos |

### 2.3 Familia · Implementación

| Agente | Modelo | Cuándo se invoca |
|---|---|---|
| `tdd-guide` | sonnet | Nuevas features, bug fixes — fuerza ciclo RED-GREEN-REFACTOR |
| `build-error-resolver` | sonnet | Build falla, TypeScript errors — fixes mínimos |
| `refactor-cleaner` | sonnet | Limpieza de código muerto, duplicados (corre knip + ts-prune) |
| `ui-engineer` | sonnet | Construir/refactor componentes UI con 10 categorías de prioridad |
| `performance-optimizer` | sonnet | Bottlenecks, bundle size, render optimization |

### 2.4 Familia · Exploración / lookup

| Agente | Modelo | Cuándo se invoca |
|---|---|---|
| `docs-lookup` | haiku | Preguntas de API, librerías, frameworks (usa Context7 MCP) |

> Adicionalmente, el CLI provee dos agentes built-in para búsqueda
> read-only (`Explore`, modelo haiku) y trabajo abierto multi-step
> (`general-purpose`, modelo sonnet). No están en `.claude/agents/`
> porque los gestiona el propio harness.

### 2.5 Familia · Testing

| Agente | Modelo | Cuándo se invoca |
|---|---|---|
| `e2e-runner` | sonnet | E2E tests (Vercel Agent Browser preferido, Playwright fallback) |
| `pr-test-analyzer` | sonnet | Análisis de cobertura comportamental en PRs |

### 2.6 Familia · Operación del harness

| Agente | Modelo | Cuándo se invoca |
|---|---|---|
| `loop-operator` | sonnet | Loops autónomos multi-step con stall detection |
| `memory-consolidator` | haiku | Compresión periódica de `.claude/memory/` cuando crece > 600 LOC |
| `conversation-analyzer` | sonnet | Detección de fricción en sesiones (correcciones repetidas, reverts) |
| `harness-optimizer` | sonnet | Mejora del propio harness (hooks, routing, context, safety, cost) |

### 2.7 Familia · Auditoría (código + docs + backlog)

| Agente | Modelo | Cuándo se invoca |
|---|---|---|
| `architecture-auditor` | sonnet | Audita un proyecto contra `.claude/rules/project/architecture.md` |
| `repo-reviewer` | sonnet | Evalúa repos externos para extraer skills/agents/rules/patterns |
| `docs-reality-auditor` | sonnet | Audita UN documento markdown contra la realidad del código — cita `path:línea` por hallazgo y emite reporte en `docs/review/<fecha>/docs/` |
| `backlog-implementation-auditor` | sonnet | Audita TODOS los backlogs `F-XX.Y` de `Extractor_de_Requisitos/backlog/` contra el código real (IMPLEMENTED / PARTIAL / NOT_STARTED / OBSOLETE / SUPERSEDED_BY) |
| `commit-backlog-reconciler` | sonnet | Reconcilia commits recientes con backlogs; identifica commits huérfanos y crea nuevos `F-XX.Y` |

### 2.8 Familia · Integración GitHub

| Agente | Modelo | Cuándo se invoca |
|---|---|---|
| `github-orchestrator` | sonnet | Publica resultados de agentes en PR comments, Issues, Projects |

### 2.9 Familia · Documentación

| Agente | Modelo | Cuándo se invoca |
|---|---|---|
| `doc-updater` | sonnet | Actualiza codemaps, READMEs, guías — corre `/update-codemaps` y `/update-docs` |
| `doc-reviser` | sonnet | Toma un doc + su review report y produce la v2 corregida aplicando CRITICAL/HIGH/MEDIUM sin reescribir desde cero |

Total en `.claude/agents/`: **28 archivos** (27 ya mergeados en `develop` +
`doc-reviser.md` introducido junto con esta auditoría). Los built-in del
CLI (`Explore`, `general-purpose`, `Plan`, `statusline-setup`, `claude`)
no cuentan aquí porque no se versionan en el repo.

---

## 3. MCP servers conectados (12) {#mcp-servers}

Los MCP servers viven en `.mcp.json` y proporcionan **herramientas
estructuradas** que los agentes invocan como funciones. A diferencia
del shell, un MCP devuelve JSON tipado y respeta permisos granulares.

| Servidor | Paquete / transporte | Para qué se usa en LinkAnvil |
|---|---|---|
| `postgres` | `@modelcontextprotocol/server-postgres` (stdio) | Queries de inspección directa contra `cerebro-postgres` durante debug — sin necesidad de `docker exec psql` |
| `qdrant` | `mcp-server-qdrant` vía `uvx` (stdio) | Inspección de la colección `cerebro_recursos`, búsqueda semántica manual desde el chat |
| `n8n` | `@czlonkowski/n8n-mcp` (stdio) | Lectura/gestión de workflows n8n (incl. `audit_cron_daily`) sin entrar a la UI |
| `redis` | `@gongrzhe/server-redis-mcp` (stdio) | Inspección del cache de LiteLLM y de las claves del outbox en Redis |
| `github` | `@modelcontextprotocol/server-github` (stdio) | PR comments, issues, search code/repos, labels — usado por `github-orchestrator` |
| `fetch` | `mcp-server-fetch` vía `uvx` (stdio) | HTTP GET de URLs externas sin pasar por `WebFetch` (útil cuando el flag de webfetch está restringido) |
| `brave-search` | `@modelcontextprotocol/server-brave-search` (stdio) | Búsquedas web sin abrir el navegador (alternativa neutra a Google) |
| `sequential-thinking` | `@modelcontextprotocol/server-sequential-thinking` (stdio) | Razonamiento estructurado para problemas complejos — usado por `architect` y `planner` |
| `docker` | `mcp-server-docker` vía `uvx` (stdio) | Listar contenedores, leer logs y describir servicios del compose local |
| `telegram` | `telegram-mcp` (stdio) | Enviar notificaciones a un bot de Telegram (alertas de audit_cron o cron semanal) |
| `prometheus` | `prometheus-mcp-server` vía `uvx` (stdio) | Queries PromQL contra el endpoint local `http://localhost:9090` para chequear métricas |
| `context7` | `@upstash/context7-mcp` (stdio) | Buscar documentación actualizada de librerías (Next.js, FastAPI, asyncpg…) sin abrir el navegador |

Detalles de configuración (env vars, credenciales) en `.mcp.json`. Permisos por
servidor en `.claude/settings.json` bajo `allowedTools`.

---

## 4. Modelos LLM en producción (3, vía LiteLLM) {#modelos-llm-en-produccion}

LiteLLM corre como contenedor (`cerebro-litellm`) y expone **3 alias
virtuales** que apuntan a providers reales configurables. El código de
LinkAnvil **nunca** habla con NVIDIA/Anthropic/OpenAI directamente —
siempre va a `LITELLM_HOST/v1/chat/completions` con el alias.

**Stack actual** (`infra/litellm/config.yaml`): la totalidad de los
modelos está servida por **NVIDIA NIM Preview** (free tier) en
`https://integrate.api.nvidia.com/v1`. El comentario inicial del
archivo lo declara: *"Estrategia: Lite + Pro usando modelos gratuitos
de NVIDIA NIM Preview"*.

| Alias | Provider real configurado | Uso en LinkAnvil | Call-sites |
|---|---|---|---|
| `cerebro-lite` | NVIDIA NIM · `meta/llama-3.1-8b-instruct` + fallback `mistralai/mixtral-8x7b-instruct-v0.1` | Extracción metadata estructurada, clasificador de relaciones, chat sin RAG complejo, pre-push security scan | `src/scraper/worker.py`, `src/data/embedder_worker.py` (relación semántica), `src/api/main.py` (chat modo lite), `ops/cron/litellm_client.py` |
| `cerebro-pro` | NVIDIA NIM · `meta/llama-3.3-70b-instruct` + fallback `nvidia/llama-3.3-nemotron-super-49b-v1.5` | Chat con RAG denso, respuestas largas, razonamiento complejo. Usuario lo elige con `model=pro` | `src/api/main.py` (chat modo pro) |
| `cerebro-embeddings` | NVIDIA NIM · `nvidia/nv-embedqa-e5-v5` | Vectores **1024-dim** para Qdrant: ingesta de recursos + embedding del query de chat para retrieval | `src/data/embedder_worker.py` (batch + single), `src/api/main.py` (chat RAG retrieval) |

Routing: `least-busy` con `num_retries: 3`, `request_timeout: 90s`,
`allowed_fails: 1` y `cooldown_time: 15s`. Cache Redis activado para
`completion` y `embedding` con TTL 3600s.

### 4.1 BYOK · virtual keys per-tenant

Cada usuario registrado debe **traer sus propias 3 virtual keys** de
LiteLLM (lite + embeddings + pro). Sin ellas, `/ingest` y `/chat`
devuelven `402 Payment Required`. El demo público usa keys
pre-configuradas con free tiers (NVIDIA NIM Preview) y cuota dura
20 chats + 5 ingests/día.

### 4.2 Cómo se cambia el provider real

Editar `infra/litellm/config.yaml` y reiniciar el contenedor
`cerebro-litellm`. El alias `cerebro-*` permanece estable; el código
no necesita cambios. Esto permite mover de NIM a OpenAI/Anthropic/Groq/
Voyage el día que se decida pagar, sin tocar los workers.

> **Catálogo de prompts**: cada uno de los 5 prompts inline (scraper,
> embedder, chat RAG, chat no-RAG, clasificador semántico) vive
> documentado en [7 · Prompts del sistema](./7-prompts) con texto
> literal, schema JSON y manejo de errores.

---

## 5. Git hooks asistidos por IA (2) {#git-hooks-asistidos-por-ia}

Los hooks viven en `.githooks/` y se activan con
`git config core.hooksPath .githooks` (no se usa Husky — LinkAnvil es
Python-first y no hay `package.json` en la raíz que la justifique).
Se ejecutan en cada desarrollador local — no en CI.

### 5.1 `.githooks/pre-commit` — ruff (mecánico, sin IA)

Script bash que recoge los `.py` staged y los pasa por **`ruff check`**
y **`ruff format --check`**. Fragmento real:

```bash
#!/usr/bin/env bash
set -euo pipefail

mapfile -t STAGED < <(
    git diff --cached --name-only --diff-filter=ACM | grep '\.py$' || true
)
[[ ${#STAGED[@]} -eq 0 ]] && exit 0

if ! ruff check "${STAGED[@]}"; then
    echo "❌ ruff check falló. Corrige los errores o usa: git commit --no-verify"
    exit 1
fi

if ! ruff format --check "${STAGED[@]}"; then
    echo "❌ ruff format: hay archivos sin formatear."
    exit 1
fi
```

**No usa IA**; se lista aquí por completitud del flujo. Importante:
- Solo opera sobre archivos `.py` **staged** (no todo `src/`).
- Usa `ruff format --check` (no modifica; falla si hay drift de formato).
- **No** re-stagea archivos automáticamente.

### 5.2 `.githooks/pre-push` — security review con LiteLLM

Script Python (~180 líneas) que analiza el diff con `cerebro-lite`
antes de subir a GitHub. Importa el cliente compartido como librería:

```python
# .githooks/pre-push  (extracto)
sys.path.insert(0, str(_REPO_ROOT / "ops" / "cron"))
import litellm_client
from hook_config import MAX_DIFF_CHARS, NEW_BRANCH_BASE_REFS, WATCH_PATHS

def main() -> None:
    diff = get_diff()                  # lee stdin del protocolo git
    prompt = build_prompt(diff)        # carga ops/prompts/pre-push.txt
    response = litellm_client.send_prompt(prompt)
    findings = litellm_client.parse_findings(response)
    if litellm_client.has_critical(findings):
        sys.exit(1)                    # bloquea push
    sys.exit(0)
```

Lo que hace que NO es un simple one-liner con pipe:

- **Parsea el stdin** del protocolo git hook
  (`<local-ref> <local-sha> <remote-ref> <remote-sha>`) y procesa cada
  ref pusheado.
- **Branches nuevas**: `_resolve_new_branch_base` prueba refs en
  `NEW_BRANCH_BASE_REFS` con `git merge-base` para encontrar una base
  razonable cuando el remote_sha es `0000...`.
- **Restringe el diff** a `WATCH_PATHS` (no audita todo el diff —
  solo paths sensibles).
- **Trunca** a `MAX_DIFF_CHARS` y avisa por stderr si trunca.
- Invoca `litellm_client.send_prompt()` como **librería** Python,
  no como CLI con `--prompt`/`--model`.
- Si la respuesta contiene findings `CRITICAL`, el hook **bloquea** el
  push con `sys.exit(1)`. Para `HIGH/MEDIUM` solo imprime y deja pasar.
- **Fail-open**: si LiteLLM devuelve `None` (timeout, error de red),
  `sys.exit(0)` y el push sigue. Filosofía: la red caída no debe parar
  el flujo del desarrollador.

El template del prompt vive en `ops/prompts/pre-push.txt` (ver §8) e
instruye al LLM a buscar las 6 categorías de problema configuradas
(JWT/SQL injection/SSRF/secrets/outbox/validación Pydantic).

Coste típico por push: ~$0.002 con `cerebro-lite` (free tier NIM en
la práctica).

---

## 6. Workflows automatizados (1 n8n) {#workflows-n8n}

### 6.1 `audit_cron_daily`

- **Definición**: `infra/n8n/workflows/audit_cron_daily.json`.
- **Schedule**: cron `0 3 * * *` (verificado literal en el JSON:
  `"field": "cronExpression"`, `"expression": "0 3 * * *"` —
  03:00 UTC cada día).
- **Acción**: HTTP POST a `https://api.linkanvil.internal/resources/audit-cron-tick`
  con el header `Authorization: Bearer <CRON_SECRET>`.
- **Qué hace el endpoint**: dispara `run_audit_cron()` en
  `src/data/audit_cron.py`, que escanea **todos los tenants** y mueve
  recursos `activo → cuarentena` o `cuarentena → expirado` según las
  `audit_policy` de cada usuario.
- **Notificaciones**: cada transición emite un evento al outbox que
  termina llegando al bell de la UI vía SSE.

> NO confundir con `_cleanup_demo_sessions_loop` (en
> `src/api/main.py`), que es un bucle interno del proceso `api`
> corriendo cada 60s para cleanup de sub-tenants demo. Ese no pasa
> por n8n.

---

## 7. GitHub Actions del pipeline (1 con IA) {#github-actions-con-ia}

Workflows en `.github/workflows/`. Solo **uno** invoca un modelo de
IA — los otros dos se listan por completitud del pipeline.

| Workflow | Trigger | Función | ¿Usa IA? |
|---|---|---|---|
| `ci.yml` | push / PR a `main`, `develop` | Ruff + pytest + npm build | No |
| `deploy-docs.yml` | push a `main` con cambios en `docs/**` | Build VitePress + deploy a `gh-pages` | No |
| `copilot-customization-check.yml` | PR contra `main` | Valida que `.github/copilot-instructions.md` no haya divergido de `.claude/CLAUDE.md`. Llama a `claude -p` (Claude Code en modo CI) con `ANTHROPIC_API_KEY` para comparar semánticamente | **Sí** (`claude -p`) |

### 7.1 Patrón `claude -p` en CI

El workflow `copilot-customization-check.yml` ilustra el patrón
canónico de invocar Claude Code desde GitHub Actions:

```yaml
- name: Check Copilot instructions drift
  env:
    ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
  run: |
    claude -p "Compara .claude/CLAUDE.md con .github/copilot-instructions.md \
               y reporta divergencias semánticas" \
      --allowedTools "Read,Grep,Glob" \
      --output-format json > drift_report.json
```

Detalles:
- `--allowedTools` restringe al mínimo necesario (read-only).
- Output JSON parseable por el siguiente paso del workflow.
- Falla la check si hay divergencias críticas.

---

## 8. Prompts externos (2 templates) {#prompts-externos}

Templates de prompt que viven **fuera** del código, en `ops/prompts/`.
Se usan desde el cliente compartido `ops/cron/litellm_client.py`.

| Archivo | Disparador | Modelo | Output esperado |
|---|---|---|---|
| `ops/prompts/pre-push.txt` | git pre-push hook (ver §5.2) | `cerebro-lite` | Texto plano: lista de findings por severidad (CRITICAL/HIGH/MEDIUM) o "OK" |
| `ops/prompts/weekly-audit.txt` | cron semanal (ver §9.1) | `cerebro-lite` | Markdown estructurado: Resumen Ejecutivo · Hallazgos · Acciones recomendadas |

Razones de mantenerlos como archivos `.txt` en vez de hardcodeados:

- **Iteración rápida**: editar un prompt no requiere rebuild ni
  re-deploy del contenedor — el cliente lo lee en cada ejecución.
- **Audit log**: cambios en el prompt quedan en `git log` con autor y
  fecha.
- **Reuso**: el mismo prompt puede invocarse desde n8n, GitHub Actions
  o manualmente con `python ops/cron/litellm_client.py --prompt ...`.

Para los 5 prompts inline en código (scraper, embedder, chat con/sin
RAG, clasificador semántico) → ver [7 · Prompts del sistema](./7-prompts).

---

## 9. Scripts ad-hoc con IA (2) {#scripts-ad-hoc-con-ia}

### 9.1 `ops/cron/weekly_audit.py`

- **Qué hace**: corre el template `weekly-audit.txt` sobre una lista
  de archivos críticos (auth, outbox, scraper, embedder) y guarda el
  output en `ops/sessions/security-audit-YYYY-MM-DD.md`.
- **Cuándo**: cron semanal opcional (`0 9 * * 1`). Hoy se activa
  manualmente o vía cron del host; **no existe** un workflow
  GitHub Action equivalente.
- **Coste típico**: ~$0.03 por ejecución (en free tier NIM, $0).

### 9.2 `ops/build_staged_embeddings.py`

- **Qué hace**: pre-computa los embeddings de los 3 recursos "staged"
  que se inyectan en cada sesión demo (Slice 6.5). Los guarda en
  `cerebro.staged_embeddings_cache` para evitar 3 calls live a
  LiteLLM por cada sesión demo nueva.
- **Cuándo se corre**: una vez tras la migración 0011, y de nuevo
  cuando se modifican los textos de `_STAGED_RECURSOS` en
  `src/api/database.py`.
- **Idempotente**: UPSERT por título; re-correrlo no duplica nada.
- **Verificación**: log final muestra `embedded=3/3 dims=<N>`. La
  dimensión `N` no está hardcodeada en el script — se deriva de
  `len(vector)` que devuelve LiteLLM. Con `nvidia/nv-embedqa-e5-v5`
  como provider actual, `N = 1024`.

---

## 10. Cómo decidimos qué usar dónde {#decision-tree}

Mini decision-tree práctico para no equivocar la herramienta:

```
¿Qué quieres hacer?

├── Trabajar en código localmente con Claude
│   ├── ¿Necesitas datos externos (BD, GitHub, n8n, Redis, Docker…)?
│   │    → MCP server (§3)
│   └── ¿Tarea concreta y delimitada?
│        → Agente Claude Code (§2) — pick por familia
│
├── Asegurar calidad antes de que el código salga del laptop
│   ├── Lint mecánico (formato, imports)
│   │    → .githooks/pre-commit (§5.1)
│   └── Análisis de seguridad del diff
│        → .githooks/pre-push con LiteLLM (§5.2)
│
├── Validar / desplegar tras push
│   ├── Tests + build
│   │    → GitHub Action ci.yml (§7)
│   ├── Docs site
│   │    → GitHub Action deploy-docs.yml (§7)
│   └── Validar instrucciones de IA
│        → GitHub Action copilot-customization-check.yml (§7)
│
├── Operación periódica del cluster en producción
│   ├── Ciclo de vida de recursos (cron diario)
│   │    → n8n workflow audit_cron_daily (§6)
│   └── Auditoría semanal de seguridad
│        → Script weekly_audit.py (§9.1)
│
└── Inferencia del usuario en tiempo real
    ├── Clasificación / metadata
    │    → cerebro-lite vía LiteLLM (§4)
    ├── Chat con razonamiento complejo
    │    → cerebro-pro vía LiteLLM (§4)
    └── Embedding vectorial para RAG
         → cerebro-embeddings vía LiteLLM (§4)
```

### Reglas anti-confusión

- **Nunca** un agente Claude Code en producción — no escala a usuarios
  reales y el coste se dispara.
- **Nunca** un modelo LiteLLM en CI o pre-push si una herramienta
  determinística (ruff, mypy, pytest) puede hacer el trabajo. La IA
  es para tareas con ambigüedad, no para lo mecánico.
- **Nunca** un script ad-hoc cuando ya existe un agente o workflow
  para lo mismo. Si crees que necesitas un script, primero busca en
  `.claude/agents/`.
- **Siempre** alias `cerebro-*`, jamás el provider real en código.
  Cambiar provider es trabajo de configuración de LiteLLM, no de
  refactor de código.

---

## Referencias cruzadas

- Texto literal de los 5 prompts inline → [7 · Prompts del sistema](./7-prompts)
- Cómo se integra LiteLLM en la arquitectura → [4 · Arquitectura](./4-arquitectura)
- Contenedor por contenedor (incl. LiteLLM, n8n) → [3 · Componentes](./3-componentes)
- Ciclo de vida de un recurso (el cron es parte de esto) → [8 · Ciclo de vida](./8-lifecycle)
- Pipeline IA-driven de extracción de requisitos → [Extracción de requisitos](./Extractor_de_Requisitos/)

---

## 📋 Notas del v2 (generado por doc-reviser · 2026-05-19)

**Origen**: `docs/src/5-herramientas-ia.md` · branch `develop` (mirror @ `/tmp/linkanvil-mirror/`)
**Review aplicado**: `docs/review/2026-05-19/docs/5-herramientas-ia.review.md`

### Cambios aplicados

- **1 CRITICAL · 4 HIGH · 6 MEDIUM · 0 LOW** (de 13 hallazgos totales del review).
- Secciones tocadas:
  - **§1 pirámide** — corregido "git hooks" → ".githooks/", aclarado "1 con IA" para GitHub Actions, enumerados los 5 prompts inline completos, contadores 24→28 agentes y 11→12 MCPs.
  - **§2 Agentes** — título a 28, ampliada §2.7 "Auditoría" con `docs-reality-auditor`, `backlog-implementation-auditor`, `commit-backlog-reconciler`; añadido `doc-reviser` en §2.9; `repo-reviewer` corregido a `sonnet` (no "haiku→sonnet 2 fases"); cierre actualizado.
  - **§3 MCPs** — tabla regenerada desde `.mcp.json`. Eliminados los inexistentes (`filesystem`, `playwright`, `notion`, `memory`, `time`). Añadidos los reales (`n8n`, `redis`, `brave-search`, `docker`, `telegram`, `prometheus`). Total real: 12.
  - **§4 LiteLLM** — providers corregidos a **NVIDIA NIM Preview** (`llama-3.1-8b-instruct` + mixtral fallback / `llama-3.3-70b-instruct` + nemotron-super-49b fallback / `nv-embedqa-e5-v5`). Citado `infra/litellm/config.yaml`. Añadidos parámetros de routing reales. Lista de prompts inline alineada con §1.
  - **§5 Hooks** — **reescrita completa**. Husky → `.githooks/` (`git config core.hooksPath .githooks`). Snippet pre-commit sustituido por el real (bash con `mapfile`, `ruff check` + `ruff format --check`, sin `--fix`, sin `cd src`). Snippet pre-push sustituido por extracto Python real que importa `litellm_client` como librería; documentado el parseo de stdin, `NEW_BRANCH_BASE_REFS`, `WATCH_PATHS`, `MAX_DIFF_CHARS`, semántica fail-open.
  - **§6 n8n** — verificado literal de cron en JSON (`0 3 * * *`).
  - **§7 GitHub Actions** — título "1 con IA" en vez de "3 con IA"; tabla con columna explícita ¿Usa IA?.
  - **§9.1 weekly_audit** — eliminada la referencia a `agent-scheduled-audit.yml` (inexistente) y a "Antigravity trigger" (no presente en el repo).
  - **§9.2 build_staged_embeddings** — aclarada la dimensión: `N` se deriva de `len(vector)`, no está hardcodeada; con `nv-embedqa-e5-v5` actual N=1024.
  - **§10 decision-tree** — actualizado para reflejar `.githooks/` y ampliar la lista de datos externos (Redis, Docker, n8n).

### Pendientes (no aplicados en este v2)

- **Dimensión real de embeddings (HIGH "sospechoso" del review)**: confirmado documentalmente (modelo `nv-embedqa-e5-v5` produce 1024 dims) y verificado que el script no hardcodea el número. Una verificación runtime (`litellm.embedding(model='cerebro-embeddings', input='test')`) queda como TODO opcional si se quiere capturar evidencia ejecutada.
- **Mención a "Antigravity trigger"**: eliminada en §9.1. No queda nada que verificar.
- **`doc-reviser.md` aún no mergeado en `develop`**: el agente se ha introducido junto con esta auditoría y vive de momento en el worktree de staging (`/tmp/linkanvil-staging/.claude/agents/doc-reviser.md`). El conteo "28 agentes" en §2 asume su merge. Si esta v2 se publica antes de mergear `doc-reviser`, ajustar el contador a 27 y mover la fila de §2.9 a una nota tipo "pendiente de merge".

### Bugs de código flaggeados (no son drift de doc, requieren acción aparte)

- *(ninguno detectado en este pase — los hallazgos del review eran todos drift de documentación, no bugs).*
