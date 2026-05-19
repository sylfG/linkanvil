---
name: audit-docs
description: Lanza el fleet de auditoría de documentación + backlogs + commits. Genera reportes en docs/review/<hoy>/ usando los 5 agentes reutilizables del fleet (docs-reality-auditor, backlog-implementation-auditor, commit-backlog-reconciler, doc-reviser, backlog-reviser). Usar mensualmente o cuando se sospeche drift acumulado.
---

# /audit-docs

Slash command que orquesta el fleet de auditoría documental completo.

## Qué hace

Lanza **15 agentes en paralelo** sobre el repo actual:

1. **13 invocaciones de `docs-reality-auditor`** — una por cada `.md` en
   `docs/src/` (excluyendo `old_/`). Cada agente compara su doc asignado
   con el código real y reporta drift categorizado.
2. **1 invocación de `backlog-implementation-auditor`** — mapea las 54+
   fichas F-XX.Y del Extractor_de_Requisitos a su estado real
   (IMPLEMENTED/PARTIAL/NOT_STARTED/OBSOLETE).
3. **1 invocación de `commit-backlog-reconciler`** — walkea los commits
   recientes (ventana por defecto: 60 días), detecta huérfanos (sin
   backlog que los cubra) y **crea** los backlogs faltantes siguiendo
   la plantilla canónica.

Tras los agentes, el orquestador escribe `docs/review/<hoy>/README.md`
con resumen ejecutivo + top-N acciones prioritarias.

## Argumentos opcionales

| Arg | Default | Descripción |
|---|---|---|
| `window` | `60 days ago` | Ventana de commits para el reconciler. Usa `7 days ago` para audit semanal, `1 day ago` para hotfix. |
| `output_root` | `docs/review/` | Directorio raíz donde se escribe `<YYYY-MM-DD>/`. |
| `mode` | `full` | `full` lanza los 15 agentes; `docs-only` solo los 13 reviewers; `backlog-only` solo el implementation-auditor; `commits-only` solo el reconciler. |

## Ejemplos

```text
/audit-docs                      # audit completo, ventana 60d
/audit-docs window="7 days ago"  # solo última semana
/audit-docs mode=docs-only       # solo los 13 docs
```

## Output esperado

```
docs/review/<YYYY-MM-DD>/
├── README.md                                    # resumen ejecutivo
├── docs/                                        # 13 reportes per-doc
│   ├── 0-resumen.review.md
│   ├── 1-instalacion-configuracion.review.md
│   └── ...
├── backlog/
│   └── implementation-status.md                 # tabla con 54+ fichas
└── commits/
    └── reconciliation.md                        # walk de commits
```

Y nuevos backlogs en `docs/src/Extractor_de_Requisitos/backlog/F-XX.Y_*.md`
si el reconciler detecta huérfanos significativos.

## Después del audit

Tras revisar los reportes (sobre todo el `README.md`), el usuario puede:

1. **Aplicar fixes** a docs/backlogs con drift → invocar **doc-reviser**
   y **backlog-reviser** sobre cada `.md` o ficha individualmente:
   ```
   Use the doc-reviser on docs/src/8-lifecycle.md with review docs/review/<hoy>/docs/8-lifecycle.review.md
   ```
2. **Promocionar v2** a producción una vez aprobadas:
   ```
   cp docs/review/<hoy>/v2/<file>.v2.md docs/src/<file>.md
   ```
3. **Triage de CODE-BUGs** detectados durante el audit.

## Protocolo de invocación (para el LLM ejecutor)

Lee y sigue este orden:

1. Verifica que `.claude/agents/` contiene los 5 agentes del fleet:
   `docs-reality-auditor`, `backlog-implementation-auditor`,
   `commit-backlog-reconciler`, `doc-reviser`, `backlog-reviser`. Si
   falta alguno, error y aborta — el fleet está incompleto.

2. Determina `today` runtime (formato YYYY-MM-DD) para nombrar el dir.

3. Crea `docs/review/<today>/{docs,backlog,commits}/` (mkdir -p).

4. Resuelve el modo:
   - `full`: lanza los 15 agentes en un único mensaje con 15 Agent
     tool_use blocks paralelos.
   - `docs-only`: 13 invocaciones de docs-reality-auditor.
   - `backlog-only`: 1 invocación de backlog-implementation-auditor.
   - `commits-only`: 1 invocación de commit-backlog-reconciler con la
     ventana especificada.

5. Para los 13 doc-reviewers, mapeo doc→áreas de código:

   | Doc | Áreas |
   |---|---|
   | `index.md` | `docs/.vitepress/config.mts`, `docs/src/Extractor_de_Requisitos/` |
   | `0-resumen.md` | visión general, `docker-compose.yml`, `src/` |
   | `1-instalacion-configuracion.md` | `docker-compose.yml`, `infra/`, `.env.example`, `ops/` |
   | `2-resumen-servicios.md` | `docker-compose.yml` (lista de contenedores) |
   | `3-componentes.md` | `src/{api,data,scraper,frontend,ingestion,notifier,observability,dlq}` |
   | `4-arquitectura.md` | Diagramas C4 + auth + outbox + observabilidad |
   | `5-herramientas-ia.md` | `.claude/agents/`, `.mcp.json`, `.githooks/`, `.github/workflows/`, `infra/litellm/`, `infra/n8n/`, `ops/prompts/`, `ops/cron/` |
   | `7-prompts.md` | `src/scraper/worker.py`, `src/data/embedder_worker.py`, `src/api/main.py`, `src/ui/chatbot.py`, `ops/prompts/` |
   | `8-lifecycle.md` | `src/data/audit_cron.py`, `src/api/database.py`, migraciones |
   | `9-ejemplo_flujo.md` | pipeline E2E (scraper, embedder, outbox, chat) |
   | `10-demo.md` | `src/api/main.py` (demo endpoints), sub-tenants, frontend demo |
   | `11-Glosario.md` | términos vs uso real en código |
   | `OPERATIONS_SESSION_*.md` | log inmutable — verifica drift vs commits posteriores |

6. Espera a que los 15 agentes terminen. Recolecta los reportes
   escritos.

7. **Escribe `README.md` ejecutivo** leyendo los outputs y sintetizando:
   - Veredicto global por área (docs / backlog / commits)
   - Top-N acciones prioritarias por severidad
   - Inventario de backlogs nuevos creados
   - CODE-BUGs detectados

8. Reporta al usuario: ruta del review dir + comando para próximos pasos.

## Coste estimado

Modo `full` con sonnet: **~$4-6** por ejecución. Modo `docs-only`: ~$3.
Modo `commits-only`: ~$0.50.
