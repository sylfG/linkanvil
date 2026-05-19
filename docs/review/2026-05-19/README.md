# Audit · 2026-05-19

**15 agentes en paralelo** corrieron sobre el repo en `develop @ 7c723f3`:
- **13 doc-reality-auditor** (uno por `.md` en `docs/src/`)
- **1 backlog-implementation-auditor** (54 fichas F-XX.Y)
- **1 commit-backlog-reconciler** (ventana 60d, 197 commits no-merge)

> Los 3 agentes quedan persistidos en `.claude/agents/` (versionados con el
> repo) y son reutilizables. Para re-correr un audit:
> ```
> Use the docs-reality-auditor on docs/src/<file>.md
> Run the backlog-implementation-auditor
> Use the commit-backlog-reconciler with window="30 days ago"
> ```

## Veredicto global

| Área | Estado | Detalle |
|---|---|---|
| Documentación (`docs/src/*.md`) | **RED** | 10 docs en RED, 3 en YELLOW, 0 en GREEN |
| Backlog (54 fichas) | **AMARILLO** | 38 IMPLEMENTED, 11 PARTIAL, 4 NOT_STARTED, 1 SUPERSEDED_BY; 23 con drift |
| Commits ↔ Backlog | **PARCHEADO** | 197 commits → 36 covered, 10 nuevos backlogs creados, 7 ampliaciones propuestas |

La documentación está en **drift sistémico**. Los Slices 6.x (demo público,
sub-tenants efímeros, BYOK, cache de embeddings) no llegaron a actualizar
los docs en proporción. El backlog original es genérico (plantillas Gherkin
copy-paste); el código ha evolucionado mucho más allá. Buena noticia: hay
acciones concretas y delimitadas para sincronizar todo.

## Inventario de hallazgos por doc

| # | Doc | Veredicto | Hallazgos principales |
|---|---|---|---|
| 1 | `index.md` | RED | 1 CRITICAL · CTA "Épicas y Features" enlaza a path inexistente |
| 2 | `0-resumen.md` | YELLOW | 1 HIGH (chat archivado 30d no implementado) · 3 MEDIUM · 22 servicios reales, doc dice 5 |
| 3 | `1-instalacion-configuracion.md` | RED | 2 CRITICAL · `localhost:8000/ingest` no funciona; env vars `SESSION_COOKIE_SECURE`/`DOMAIN` inventadas |
| 4 | `2-resumen-servicios.md` | RED | 11 HIGH · 14 MEDIUM · postgres:17 vs 16, redis-stack vs redis:7, 2 servicios productivos sin documentar |
| 5 | `3-componentes.md` | RED | 2 CRITICAL · count 22 vs 24 servicios reales; `notifier-worker` no existe en doc |
| 6 | `4-arquitectura.md` | RED | 2 CRITICAL · §3.1 modelo Qdrant equivocado; diagrama RAG omite `cerebro_chunks` |
| 7 | `5-herramientas-ia.md` | RED ("DIVERGE") | 1 CRITICAL · sección Husky describe herramienta inexistente; lista MCPs no coincide con `.mcp.json` |
| 8 | `7-prompts.md` | YELLOW | 0 CRITICAL · contenido conceptual fiel, pero `path:línea` sistemáticamente desactualizados |
| 9 | `8-lifecycle.md` | RED | 1 CRITICAL · SQL "Fase A" cron omite filtro `temporal_class='evento'`; 5 HIGH adicionales |
| 10 | `9-ejemplo_flujo.md` | RED | 2 CRITICAL · umbral coseno 0.92 vs 0.88 documentado; clasificador en embedder no scraper |
| 11 | `10-demo.md` | RED | 2 CRITICAL · doc dice CTA "Probar demo" en nav pero el código lo excluye explícitamente |
| 12 | `11-Glosario.md` | RED | 2 CRITICAL · 9 HIGH · términos con definición desactualizada (BYOK, tenant, RAG) |
| 13 | `OPERATIONS_SESSION_2026-05-17.md` | YELLOW | 2 HIGH · log inmutable parcialmente sobrescrito por commits posteriores |

## Top-10 acciones prioritarias (orden de aplicación recomendado)

1. **[index.md]** Corregir CTA — apuntar a `/0-resumen` o `/Extractor_de_Requisitos/` en lugar del path inexistente.
2. **[1-instalacion]** Cambiar `localhost:8000/ingest` → `http://localhost/ingest` con Host header `ingest.localhost`. Eliminar `SESSION_COOKIE_SECURE`/`DOMAIN` y documentar `PUBLIC_HOSTNAME`.
3. **[3-componentes]** Añadir `notifier-worker` y los 2 servicios faltantes; actualizar count a 24.
4. **[2-resumen-servicios]** Sincronizar tabla de imágenes: postgres:16, redis-stack-server, agregar Ingestion API y LiteLLM.
5. **[8-lifecycle]** Añadir filtro `AND temporal_class = 'evento'` al SQL documentado del cron. Actualizar line numbers (`database.py:538`, `:805`, `main.py:1520`).
6. **[9-ejemplo_flujo]** Cambiar umbral 0.88 → 0.92 (3 ocurrencias); reasignar clasificador semántico a embedder.
7. **[4-arquitectura]** Corregir §3.1 modelo Qdrant (chunks, no recurso entero); añadir `/auth/demo-start` y `/auth/refresh` al diagrama de auth.
8. **[10-demo]** Eliminar mención al CTA "Probar demo" en nav (ya solo está en hero/banner/footer).
9. **[5-herramientas-ia]** Eliminar sección Husky; reconstruir lista MCPs desde `.mcp.json` real (11 MCPs); arreglar dimension embeddings.
10. **[11-Glosario]** Actualizar definiciones de BYOK, tenant (multi-tenant + sub-tenants demo), RAG (con SSE streaming).

## Backlogs nuevos creados (10)

El `commit-backlog-reconciler` detectó 10 implementaciones huérfanas y
creó sus fichas siguiendo la plantilla canónica:

| Backlog | Cubre | Trigger |
|---|---|---|
| `F-00.14_tailscale-funnel-telegram-webhook.md` | Webhook Telegram público vía Tailscale Funnel | `12cf9ac` |
| `F-00.15_n8n-provisioning-zero-touch.md` | Bootstrap automático de n8n (API key + workflows) | `6b8f649` + 3 más |
| `F-02.6_scraper-antibot-escalada-stealth.md` | Anti-bot + escalada Basic→Stealth + Medium | `76041a4` + 2 más |
| `F-03.6_cache-embeddings-staged-bd.md` | Cache embeddings → 0 calls LiteLLM por sesión demo | `a10795b` (Slice 6.5) |
| `F-03.7_rag-chunking-cerebro-chunks-32k.md` | Chunking de recursos + contexto 32k | `fb5f2cd` + 3 más |
| `F-04.8_notificaciones-in-app-telegram-sse.md` | Bell + SSE + Telegram outbound | `b527be5` + 9 más |
| `F-05.4_clasificacion-temporal-llm-audit-policy-jsonb.md` | `audit_policy` JSONB + auto-archive (2467 LOC) | `021c3ab` + 1 más |
| `F-08.5_byok-llaves-llm-por-usuario.md` | BYOK + cuota demo per-IP | `3b0201c` + 3 más |
| `F-09.3_landing-publico-marketing.md` | Landing público (hero + features + FAQ + casos uso) | `7439d07` + 2 más |
| `F-09.4_demo-publico-sub-tenants-efimeros.md` | Demo público + sub-tenants TTL 15min + Slices 6.x | `37db013` + 7 más |

## Backlog implementation — drift más relevante

- **F-04.1** (chat RAG): código usa SSE streaming desde Slice 4; el AC describe JSON síncrono.
- **F-02.3** (Pydantic zero-defect): `ScrapedDataSchema` ya no existe; sin validación Pydantic post-LLM.
- **F-04.4** (compactación de largo contexto): infraestructura BD lista, lógica de compactación ausente.
- **F-06.5** (logging JSON): 4 workers (scraper, embedder, notifier, dlq) siguen con `basicConfig` plano; solo API+ingestion usan JSON.
- **F-03.5/F-07.x** (export bóveda + Obsidian + hot.md): `VaultExporter` produce ZIP correctamente pero **no hay endpoint HTTP** que lo exponga (solo accesible vía tests).
- **F-04.5** (function calling): NOT_STARTED.
- **F-09.1** (i18n): NOT_STARTED.
- **F-06.4** (estrangulamiento): SUPERSEDED_BY F-01.6 + F-08.4 (rate limit dividido en dos features).

## Bugs reales detectados ([CODE-BUG])

El audit no era para arreglar código, pero los agentes flaggearon
defectos reales con cita `path:línea`. **Tu decisión** si los arreglas:

- **`src/ingestion/main.py`**: `/ingest` publica a RabbitMQ siempre, incluso cuando el bloom filter dice "duplicado" → contradice F-01.1.
- **`src/ingestion/main.py`**: `/webhook/telegram` está expuesto sin path-param ni autenticación → contradice F-08.2.
- Workers (`src/scraper`, `src/data/embedder_worker`, `src/notifier`, `src/dlq`): siguen con `logging.basicConfig` plano (no JSON) → contradice F-06.5.
- 3 tests permanentemente skipped enmascaran cobertura real.
- `src/api/database.py::rescue_recurso` notifica solo al caller, mientras que `quarantine_recurso`/`expire_recurso` notifican a todos los tenants linkeados → asimetría multi-tenant.

## Índice de reportes detallados

- [Doc reviews (13)](./docs/) — un archivo por documento auditado
- [Backlog implementation status](./backlog/implementation-status.md) — tabla con las 54 fichas + propuestas detalladas
- [Commit ↔ Backlog reconciliation](./commits/reconciliation.md) — 197 commits clasificados

## Próximos pasos (separados de este audit)

1. **Aplicar los top-10 fixes** sobre los 10 docs en RED — sesión dedicada.
2. **Comitear los 10 backlogs nuevos** (ya creados en disco por el reconciler) y proponerlos en GitHub Project.
3. **Aplicar updates al backlog** (las 23 fichas con drift): reescribir AC genéricos con comportamiento real.
4. **Triage de CODE-BUGs**: decidir cuáles arreglar ahora vs convertir en backlog futuro.
5. **Programar re-audit**: cron mensual con los 3 agentes para evitar que el drift vuelva a acumularse.

---

_Auditado por el fleet `docs-reality-auditor` × 13 +
`backlog-implementation-auditor` × 1 + `commit-backlog-reconciler` × 1
en paralelo (single-message dispatch). Coste estimado: ~$4-5 en tokens
sonnet._
