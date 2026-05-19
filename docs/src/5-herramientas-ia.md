# Herramientas IA del proyecto

> Inventario completo de toda la maquinaria IA que se usó para construir
> y operar LinkAnvil — desde los **agentes Claude Code** que escribieron
> el código hasta los **prompts en producción** que clasifican los
> recursos del usuario en tiempo real.

## Tabla de contenidos

1. [Visión general — la pirámide IA del proyecto](#vision-general)
2. [Agentes Claude Code (24)](#agentes-claude-code)
3. [MCP servers conectados (11)](#mcp-servers)
4. [Modelos LLM en producción (3, vía LiteLLM)](#modelos-llm-en-produccion)
5. [Git hooks asistidos por IA (2)](#git-hooks-asistidos-por-ia)
6. [Workflows automatizados (1 n8n)](#workflows-n8n)
7. [GitHub Actions con IA (3)](#github-actions-con-ia)
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
│   • 5 prompts inline en código (scraper, embedder, chat)    │
│   • 1 workflow n8n (audit_cron_daily)                       │
├─────────────────────────────────────────────────────────────┤
│   BUILD & CI       (push, PR, deploy)                       │
│   • 3 GitHub Actions (ci, deploy-docs, copilot-check)       │
│   • 2 git hooks (pre-commit ruff, pre-push security)        │
│   • 2 scripts ad-hoc (weekly_audit, build_staged_embeddings)│
├─────────────────────────────────────────────────────────────┤
│   DESARROLLO       (Claude Code está delante)               │
│   • 24 agentes Claude Code                                  │
│   • 11 MCP servers                                          │
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

## 2. Agentes Claude Code (24) {#agentes-claude-code}

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

### 2.7 Familia · Auditoría

| Agente | Modelo | Cuándo se invoca |
|---|---|---|
| `architecture-auditor` | sonnet | Audita un proyecto contra `.claude/rules/project/architecture.md` |
| `repo-reviewer` | haiku→sonnet (2 fases) | Evalúa repos externos para extraer skills/agents/rules/patterns |

### 2.8 Familia · Integración GitHub

| Agente | Modelo | Cuándo se invoca |
|---|---|---|
| `github-orchestrator` | sonnet | Publica resultados de agentes en PR comments, Issues, Projects |

### 2.9 Familia · Documentación

| Agente | Modelo | Cuándo se invoca |
|---|---|---|
| `doc-updater` | sonnet | Actualiza codemaps, READMEs, guías — corre `/update-codemaps` y `/update-docs` |

Total en `.claude/agents/`: **24 archivos**. Los built-in del CLI
(`Explore`, `general-purpose`, `Plan`, `statusline-setup`, `claude`)
no cuentan aquí porque no se versionan en el repo.

---

## 3. MCP servers conectados (11) {#mcp-servers}

Los MCP servers viven en `.mcp.json` y proporcionan **herramientas
estructuradas** que los agentes invocan como funciones. A diferencia
del shell, un MCP devuelve JSON tipado y respeta permisos granulares.

| Servidor | Transport | Para qué se usa en LinkAnvil |
|---|---|---|
| `context7` | stdio | Buscar documentación actualizada de librerías (Next.js, FastAPI, asyncpg…) sin abrir el navegador |
| `github` | stdio | PR comments, issues, search code/repos, gestión de labels — usado por `github-orchestrator` |
| `filesystem` | stdio | Acceso de lectura/escritura controlado a paths whitelisted del worktree |
| `postgres` | stdio | Queries de inspección directa contra `cerebro-postgres` durante debug — sin necesidad de `docker exec psql` |
| `qdrant` | stdio | Inspección de colecciones, búsqueda semántica manual desde el chat de Claude Code |
| `playwright` | stdio | Automatización browser para E2E tests — fallback cuando Vercel Agent Browser no aplica |
| `sequential-thinking` | stdio | Razonamiento estructurado para problemas complejos — usado por `architect` y `planner` |
| `notion` | http | Sincronización de la base de conocimiento del owner con docs internas |
| `memory` | stdio | Memoria persistente cross-session de Claude Code (separada de `.claude/memory/*.md`) |
| `time` | stdio | Operaciones con zonas horarias — usado al razonar sobre cron schedules y `expires_at` UTC |
| `fetch` | stdio | HTTP GET de URLs externas sin pasar por `WebFetch` (útil cuando el flag de webfetch está restringido) |

Detalles de configuración en `.mcp.json`. Permisos por servidor en
`.claude/settings.json` bajo `allowedTools`.

---

## 4. Modelos LLM en producción (3, vía LiteLLM) {#modelos-llm-en-produccion}

LiteLLM corre como contenedor (`cerebro-litellm`) y expone **3 alias
virtuales** que apuntan a providers reales configurables. El código de
LinkAnvil **nunca** habla con OpenAI/Anthropic/Groq directamente —
siempre va a `LITELLM_HOST/v1/chat/completions` con el alias.

| Alias | Provider real típico | Uso en LinkAnvil | Call-sites |
|---|---|---|---|
| `cerebro-lite` | Groq Llama 3.1 8B / Mistral Nemo | Extracción metadata estructurada, clasificador de relaciones, chat sin RAG complejo, pre-push security scan | `src/scraper/worker.py`, `src/data/embedder_worker.py` (relación semántica), `src/api/main.py` (chat modo lite), `ops/cron/litellm_client.py` |
| `cerebro-pro` | Claude Sonnet 4.5 / GPT-4o | Chat con RAG denso, respuestas largas, razonamiento complejo. Usuario lo elige con `model=pro` | `src/api/main.py` (chat modo pro) |
| `cerebro-embeddings` | Voyage-3 / OpenAI text-embedding-3 | Vectores 1024-dim para Qdrant: ingesta de recursos + embedding del query de chat para retrieval | `src/data/embedder_worker.py` (batch + single), `src/api/main.py` (chat RAG retrieval) |

### 4.1 BYOK · virtual keys per-tenant

Cada usuario registrado debe **traer sus propias 3 virtual keys** de
LiteLLM (lite + embeddings + pro). Sin ellas, `/ingest` y `/chat`
devuelven `402 Payment Required`. El demo público usa keys
pre-configuradas con free tiers (Groq + Voyage free) y cuota dura
20 chats + 5 ingests/día.

### 4.2 Cómo se cambia el provider real

Editar `infra/litellm/config.yaml` y reiniciar el contenedor. El alias
`cerebro-*` permanece estable; el código no necesita cambios. Esto
permite tunear coste/calidad sin tocar los workers.

> **Catálogo de prompts**: cada uno de los 5 prompts inline (scraper,
> embedder, chat RAG/no-RAG, clasificador semántico) vive documentado
> en [7 · Prompts del sistema](./7-prompts) con texto literal, schema
> JSON y manejo de errores.

---

## 5. Git hooks asistidos por IA (2) {#git-hooks-asistidos-por-ia}

Hooks configurados con Husky en `.husky/`. Se ejecutan en cada
desarrollador local — no en CI.

### 5.1 `pre-commit` — ruff (mecánico, sin IA)

```bash
#!/usr/bin/env sh
cd src && ruff check --fix .
```

Aplica autofix de linting Python. **No usa IA**; se lista aquí por
completitud del flujo. Si introduce cambios, el hook re-stagea
automáticamente los archivos modificados.

### 5.2 `pre-push` — security review con LiteLLM

```bash
#!/usr/bin/env sh
git diff origin/$BRANCH..HEAD | python ops/cron/litellm_client.py \
    --prompt ops/prompts/pre-push.txt --model cerebro-lite
```

- Lee el diff vs `origin/<branch>` y lo pasa por el cliente compartido.
- El template `ops/prompts/pre-push.txt` instruye al LLM a buscar 6
  categorías de problema (JWT/SQL injection/SSRF/secrets/outbox/
  validación Pydantic).
- Si la respuesta contiene `CRITICAL`, el hook **bloquea** el push y
  muestra el motivo. Para HIGH/MEDIUM solo avisa.
- **Fail-open**: si LiteLLM no responde en 30s, el push sigue.
  Filosofía: la red caída no debe parar el flujo del desarrollador.

Coste típico por push: ~$0.002 con `cerebro-lite`.

---

## 6. Workflows automatizados (1 n8n) {#workflows-n8n}

### 6.1 `audit_cron_daily`

- **Definición**: `infra/n8n/workflows/audit_cron_daily.json`.
- **Schedule**: cron `0 3 * * *` (03:00 UTC cada día).
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

## 7. GitHub Actions con IA (3) {#github-actions-con-ia}

Workflows en `.github/workflows/`.

| Workflow | Trigger | Función |
|---|---|---|
| `ci.yml` | push / PR a `main`, `develop` | Ruff + pytest + npm build. **No usa IA**; se lista por contexto del pipeline completo. |
| `deploy-docs.yml` | push a `main` con cambios en `docs/**` | Build VitePress + deploy a `gh-pages`. **No usa IA**. |
| `copilot-customization-check.yml` | PR contra `main` | Valida que `.github/copilot-instructions.md` no haya divergido de `.claude/CLAUDE.md`. Llama a `claude -p` (Claude Code en modo CI) con `ANTHROPIC_API_KEY` para comparar semánticamente. |

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
- **Cuándo**: cron semanal opcional (`0 9 * * 1`). Puede activarse
  vía Antigravity trigger o GitHub Action `agent-scheduled-audit.yml`.
- **Coste típico**: ~$0.03 por ejecución.

### 9.2 `ops/build_staged_embeddings.py`

- **Qué hace**: pre-computa los embeddings de los 3 recursos "staged"
  que se inyectan en cada sesión demo (Slice 6.5). Los guarda en
  `cerebro.staged_embeddings_cache` para evitar 3 calls live a
  LiteLLM por cada sesión demo nueva.
- **Cuándo se corre**: una vez tras la migración 0011, y de nuevo
  cuando se modifican los textos de `_STAGED_RECURSOS` en
  `src/api/database.py`.
- **Idempotente**: UPSERT por título; re-correrlo no duplica nada.
- **Verificación**: log final muestra `embedded=3/3 dims=1024`.

---

## 10. Cómo decidimos qué usar dónde {#decision-tree}

Mini decision-tree práctico para no equivocar la herramienta:

```
¿Qué quieres hacer?

├── Trabajar en código localmente con Claude
│   ├── ¿Necesitas datos externos (BD, GitHub, Notion)?
│   │    → MCP server (§3)
│   └── ¿Tarea concreta y delimitada?
│        → Agente Claude Code (§2) — pick por familia
│
├── Asegurar calidad antes de que el código salga del laptop
│   ├── Lint mecánico (formato, imports)
│   │    → git pre-commit (§5.1)
│   └── Análisis de seguridad del diff
│        → git pre-push con LiteLLM (§5.2)
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
