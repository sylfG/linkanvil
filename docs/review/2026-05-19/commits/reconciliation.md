# Commit ↔ Backlog Reconciliation · 2026-05-19

**Reconciler**: commit-backlog-reconciler
**Ventana**: `60 days ago`
**Total commits analizados**: 197 (no-merge)
**Versión del repo**: `develop` @ `7c723f3`

## Resumen

- Significativos: 78
- Covered (mapean a backlog existente): 36
- Orphans → backlogs nuevos creados: 10
- Subdetails (ampliación propuesta sobre backlog existente): 7
- Ignored (trivial / docs / formatting / harness dev tooling): 119
- Skipped (idempotencia, archivo ya existía): 0

## Tabla maestra

| Commit | Subject | LOC | Acción | Detalle |
|---|---|---|---|---|
| 7c723f3 | docs: reorganizar VitePress + inventario IA | 898 | IGNORED | Solo `docs/` |
| 8150d7d | fix(demo): Slice 6.6 — error 429 legible + nav anónimo | 77 | COVERED → F-09.4 (nuevo) | Slice 6.6 demo |
| a10795b | perf(demo): Slice 6.5 — cache embeddings staged | 390 | ORPHAN → F-03.6 (nuevo) | 0 calls LiteLLM/sesión |
| 1b38f09 | fix(demo): Slice 6.4 — staged buscables RAG | 199 | COVERED → F-09.4 (nuevo) | Slice 6.4 demo |
| 1915168 | docs: renames de drafts | 0 | IGNORED | docs |
| c67c505 | fix(chat): redirect /chat + sidebar + tooltips | 82 | SUBDETAIL of F-04.1 | Redirect post-login |
| 57ca84f | docs: rename prompts.md | 0 | IGNORED | docs |
| a273b6f | docs: renombra demo/lifecycle/prompts | 0 | IGNORED | docs |
| 53870a9 | fix(demo): Slice 6.3 — 1 sesión/IP/día UTC | 172 | COVERED → F-09.4 (nuevo) | Cuota demo |
| a3737c6 | docs: reestructura docs/src | 2304 | IGNORED | docs |
| 540d7ba | docs(demo): Slice 6.2 docs | 251 | IGNORED | docs |
| eb5f529 | refactor(demo): Slice 6.2 chrome compartido | 1042 | COVERED → F-09.4 (nuevo) | Slice 6.2 demo |
| ebb3735 | feat(demo): Slice 6.1 tabs reales /demo | 901 | COVERED → F-09.4 (nuevo) | Slice 6.1 demo |
| a536da9 | feat(demo): Slice 6 frontend vista /demo | 829 | COVERED → F-09.4 (nuevo) | Slice 6 frontend |
| f87af38 | feat(demo): Slice 6 backend endpoint dedicado | 712 | COVERED → F-09.4 (nuevo) | Slice 6 backend |
| 59d09eb | docs(demo): página dedicada al demo | 341 | IGNORED | docs |
| 37db013 | feat(demo): Slice 5 sub-tenants efímeros TTL | 830 | COVERED → F-09.4 (nuevo) | Sub-tenants demo |
| 49d2c1c | fix(byok): cuota demo per-IP + /profile/quota | 279 | COVERED → F-08.5 (nuevo) | BYOK quota |
| 055254e | feat(byok): Slice 3 UI BYOK + 402/429 | 229 | COVERED → F-08.5 (nuevo) | Slice 3 BYOK |
| e2093e3 | feat(byok): Slice 2a endpoint llm-keys | 268 | COVERED → F-08.5 (nuevo) | Slice 2a BYOK |
| 3b0201c | feat(byok): Slice 1 fundación BYOK | 702 | COVERED → F-08.5 (nuevo) | Slice 1 BYOK |
| 75dbbf2 | refactor(landing): Solution 6 pilares | 112 | COVERED → F-09.3 (nuevo) | Landing iter |
| 6beebc1 | feat(landing): icono oficial, NightlyAudit | 517 | COVERED → F-09.3 (nuevo) | Landing iter |
| 7439d07 | feat(landing): página pública + demo /login | 1655 | COVERED → F-09.3 (nuevo) | Landing inicial |
| 8e8a6dd | docs(ejemplo-flujo): didáctica junior | 847 | IGNORED | docs |
| 414e9ff | docs: ciclo de vida, ejemplo flujo | 208 | IGNORED | docs |
| 37d4737 | fix(notifications): outbox en auto-archive | 73 | COVERED → F-04.8 (nuevo) | Outbox notifier |
| 41bfd39 | feat(profile-modal): card auditoría recursos | 186 | COVERED → F-05.4 (nuevo) | UI audit_policy |
| 021c3ab | feat(audit): clasificación temporal + audit_policy JSONB | 2467 | ORPHAN → F-05.4 (nuevo) | Auto-archive policy |
| 2c7e4a5 | fix(auth,hooks,obs): cierre pendientes | 82 | IGNORED | bugfix multi-area trivial |
| ba405e2 | fix(auth,chat,obsolescencia): 5 bugs | 1058 | SUBDETAIL of F-04.1/F-08.3 | Refresh tokens + streaming + copy |
| eb1da66 | refactor(hooks,cron): rondas 14-19 jedi | 1650 | IGNORED | Dev tooling (.githooks, ops/cron) |
| 0ef11f4 | refactor(hooks): tercera ronda jedi | 344 | IGNORED | Dev tooling |
| 5d7e6e6 | refactor(hooks): segunda ronda jedi | 207 | IGNORED | Dev tooling |
| 3b6e99c | refactor(hooks): litellm_client + hardening | 784 | IGNORED | Dev tooling |
| 0d00dbc | fix(cron): ruta ingestion worker | 2 | IGNORED | trivial |
| 6aa042b | refactor(ci): workflows IA → git hooks | 606 | IGNORED | Dev tooling CI |
| f591ca2 | feat(claude): harness de agentes | 16367 | IGNORED | Dev tooling `.claude/` |
| 6d15580 | fix: clamp similitud ≤1.0 | 4 | COVERED → F-03.7 (nuevo) | Bug RAG colisionador |
| 871c605 | fix(rag): chunk size 1200 + split \n+ | 10 | COVERED → F-03.7 (nuevo) | Chunking fix |
| fb5f2cd | feat(rag): contexto 32k + cerebro_chunks | 350 | ORPHAN → F-03.7 (nuevo) | RAG chunking |
| 8f294e5 | refactor(frontend/sidebar): nav reorg | 66 | SUBDETAIL of F-04.3 | UI nav |
| 9191911 | feat(frontend/ingest): listado URLs procesando | 112 | SUBDETAIL of F-04.3 | UX ingest |
| 087f058 | feat(frontend/quarantine,expired): paginación | 36 | SUBDETAIL of F-05.2 | Paginación lista |
| fdca643 | refactor(frontend/kb): solo activos paginado | 79 | SUBDETAIL of F-04.3 | Filtro KB |
| 75e74ca | feat(frontend): paginador cliente reusable | 50 | SUBDETAIL of F-04.3 | Util pagina |
| 8b22f8f | fix(scraper): cuarentenar placeholder | 11 | COVERED → F-02.6 (nuevo) | Anti-zombi |
| d436349 | fix(scraper): escalar Basic→Stealth | 21 | COVERED → F-02.6 (nuevo) | Escalada |
| bca81b3 | feat(frontend): botón Nuevo chat sticky | 11 | SUBDETAIL of F-04.3 | UI |
| 6811575 | feat(frontend): dispatch local feedback | 155 | SUBDETAIL of F-04.8 | UX SSE |
| d05f16a | fix(frontend): un único EventSource | 140 | COVERED → F-04.8 (nuevo) | SSE share |
| bf3b3b9 | fix(outbox): payload doblemente codificado | 86 | COVERED → F-04.8 (nuevo) | Outbox fix |
| 8c05101 | test: rescue desde expirado | 195 | SUBDETAIL of F-05.2 | Tests cuarentena |
| 199f8b2 | feat(frontend): acciones estado KB + rescate | 172 | SUBDETAIL of F-05.2 | UI rescue |
| 22ba12b | feat(api): KB excluye cuarentena/expirados | 119 | SUBDETAIL of F-05.2 | API rescue |
| 193ca0a | test: notifier publica redis | 63 | IGNORED | tests |
| c223817 | feat(frontend): UI reactiva SSE | 112 | COVERED → F-04.8 (nuevo) | SSE feeds |
| f7a4559 | feat(notifier): publicar Redis pub/sub | 50 | COVERED → F-04.8 (nuevo) | Notifier |
| 292f891 | feat(infra): healthcheck qdrant/cerebro-web | 23 | SUBDETAIL of F-06.6 | Healthcheck |
| cd8a7a6 | test: feed notificaciones y worker | 353 | IGNORED | tests |
| b406148 | feat(frontend): campana notificaciones | 204 | COVERED → F-04.8 (nuevo) | Campana |
| eb467aa | feat(api): /notifications endpoints | 104 | COVERED → F-04.8 (nuevo) | Endpoints |
| 7f3c843 | feat(infra): cola q.notifications + worker | 45 | COVERED → F-04.8 (nuevo) | Cola |
| a1c8e12 | feat(notifier): worker Telegram + in-app | 301 | COVERED → F-04.8 (nuevo) | Worker |
| b527be5 | feat(db): mig 0004 notificaciones | 34 | COVERED → F-04.8 (nuevo) | Schema |
| fb7be43 | test: caducidad /resources/expired | 365 | IGNORED | tests |
| 99f5c02 | feat(frontend): /expired página + badge | 285 | SUBDETAIL of F-05.2 | UI expired |
| 5bb172e | feat(api): /resources/expired endpoint | 47 | SUBDETAIL of F-05.2 | API expired |
| da9748a | feat(scraper): expiration_date al ingerir | 73 | COVERED → F-05.1 | Caducidad pipeline |
| 4c5b71d | docs: arquitectura/servicios/flujo | 233 | IGNORED | docs |
| 12cf9ac | feat(infra): Tailscale Funnel Telegram | 65 | ORPHAN → F-00.14 (nuevo) | Túnel persistente |
| 76041a4 | feat(scraper): anti-bot + cuarentena + Medium | 149 | ORPHAN → F-02.6 (nuevo) | Anti-bot + Medium |
| 2a9a56a | fix(litellm): sustituye nemotron-70b | 7 | IGNORED | trivial |
| 57970b7 | fix(frontend): no crear sesión vacía | 10 | IGNORED | trivial |
| 841f499 | feat(rag): enriquecer contexto resumen | 100 | COVERED → F-03.7 (nuevo) | Prompt enrich |
| 276f241 | fix(ingestion): publicar siempre tras bloom | 44 | COVERED → F-01.6 | Ingestion robustez |
| bde9be7 | chore(deps): uv.lock | 3 | IGNORED | deps |
| 664b3af | chore(gitignore) | 5 | IGNORED | repo hygiene |
| 7012d68 | fix(frontend): cookie matchAll | 4 | IGNORED | trivial |
| 89ca998 | refactor(db): baseline migration | 209 | SUBDETAIL of F-00.4 | Baseline rework |
| 6b8f649 | feat(n8n): provisioning zero-touch | 330 | ORPHAN → F-00.15 (nuevo) | Bootstrap |
| cd37988 | feat(infra): AUDIT_CRON_TOKEN + cerebro-migrate | 40 | COVERED → F-00.15 (nuevo) | Cableo tokens |
| 93fbee3 | test: ciclo obsolescencia | 449 | IGNORED | tests |
| 060b835 | feat(frontend): /quarantine + badge | 391 | COVERED → F-05.2 | Bandeja cuarentena UI |
| f7c09b9 | feat(infra): workflow n8n cron auditoría | 136 | COVERED → F-00.15 (nuevo) | Cron diario |
| da0de5e | feat(api): /audit-cron protegido por token | 23 | COVERED → F-05.1 | Endpoint cron |
| ee4f256 | feat(api): bandeja cuarentena endpoints | 261 | COVERED → F-05.2 | Endpoints |
| aa6ce4f | feat(semantic-collider): mover obsolescencia | 45 | COVERED → F-05.1 | Cron→cuarentena |
| bc6cb4c | refactor(audit): cron dos fases | 159 | COVERED → F-05.1 | Cron fases |
| 85fca45 | feat(db): mig 0003 cuarentena | 45 | COVERED → F-05.2 | Schema |
| 560a96f..32d5023 | fix(docs)/feat: docs GitHub Pages | <100 c/u | IGNORED | docs |
| 2f5eebf | chore(infra): compose updates | 37 | IGNORED | infra trivial |
| 87419e2 | feat/fix: schemas + servicios | 572 | COVERED → F-00.4 + F-03.x | Initial backend rewrite |
| 6bdbd26 | docs: arquitectura diagramas | 98 | IGNORED | docs |
| 643361b | chore(tests): mover tests fuera src | 661 | IGNORED | refactor tests |
| e8f836f | chore(cleanup): scripts temp | 133 | IGNORED | cleanup |
| 4ca4af3, 634b850 | docs MCP servers | <50 | IGNORED | docs |
| e63316b | feat(frontend): Next.js app auth/chat/ingest/kb | 5280 | COVERED → F-04.1 + F-04.3 + F-08.1 | Frontend foundational |
| f28601e | feat(infra): n8n bootstrap inicial | 230 | COVERED → F-00.15 (nuevo) | n8n bootstrap iter |
| 2ea68b8 | feat(ui): Streamlit chatbot | 325 | IGNORED | Reemplazado por Next.js |
| 4a0615b | fix(ingestion,data) | 11 | IGNORED | trivial |
| b7af3ab | feat(scraper): strategy BasicHttp+Stealth | 152 | COVERED → F-02.1 | Strategy pattern base |
| 84ec877 | chore(mcp): context7 | 4 | IGNORED | dev tooling |
| 98c00a8 | feat(env): JWT_SECRET etc | 11 | COVERED → F-08.3 | Env auth |
| 993797f | feat(db): cerebro schema + usuarios | 46 | COVERED → F-00.4 | Schema |
| 5567ae8 | fix(infra): OTel + RabbitMQ | 10 | COVERED → F-06.1 | OTel fix |
| fdad644 | chore(repo): dockerignore | 14 | IGNORED | repo |
| a30f1b8 | docs: reescritura post-auditoría | 1777 | IGNORED | docs |
| 81b6e2d, 9b68919, aeb35e8 | docs(backlog): EPIC features audit | 805 | IGNORED | docs/backlog meta |
| 64eae38 | chore(infra): pin digest | 11 | COVERED → F-00.11 | Pin digest |
| 6b48819 | feat(infra): SQL migration runner | 228 | COVERED → F-00.10 | Migration framework |
| aa5f030 | security(auth): httpOnly + CSRF | 209 | COVERED → F-08.3 | Cookies/CSRF |
| 4ba5d0d | feat(infra): production overlay TLS | 287 | COVERED → F-00.12 | TLS overlay |
| 8f9e5bd | feat(api,frontend): paginate /chats | 178 | SUBDETAIL of F-04.2 | Paginación chats |
| 5799c93 | feat(obs): structured JSON logging | 84 | COVERED → F-06.5 | JSON logging |
| 100fff7 | feat(ops): backup script pg+qdrant | 70 | COVERED → F-00.13 | Backup |
| bffea02 | feat(obs): production alert rules | 61 | COVERED → F-06.3 | Prometheus |
| 61e21b5 | feat(frontend): error boundaries | 83 | COVERED → F-04.7 | Error boundaries |
| 9878d06 | feat(workers): heartbeat liveness | 91 | COVERED → F-06.6 | Heartbeat |
| 9212302 | feat(api): rate limit auth + chat | 44 | COVERED → F-08.4 | Rate limit |
| cad4d70 | chore(infra): tune postgres pool | 14 | COVERED → F-00.9 | Tuning |
| a7b602b | chore(infra): non-root containers | 88 | COVERED → F-00.8 | Hardening |
| 4fd8e68 | chore(infra): compose modernization | 167 | COVERED → F-00.7 | Compose limits |
| 7b1798e | chore(infra): mem/cpu limits | 45 | COVERED → F-00.7 | Compose limits |
| 9367e39 | feat(infra): healthcheck ingestion + reset wait | 7 | COVERED → F-01.6 | Healthcheck |
| 3a1aa67 | perf(workers,api): shared httpx.AsyncClient | 401 | COVERED → F-02.5 | Pool httpx |
| b17202a | fix(frontend): chat page leaks + SSE | 423 | COVERED → F-04.7 | Resiliencia |
| 2ad2bfa | feat(api): cerebro-api foundational | 229 | COVERED → F-04.6 | API foundational |
| 225f90b | fix(api): bound /chat /resources | 515 | COVERED → F-04.6 | API hardening |
| f9cfb36 | fix(ingestion): async redis + atomic limiter | 243 | COVERED → F-01.6 | Ingestion robustez |
| d6203c5 | fix(rabbitmq): DLQ embeddings.fallidos | 29 | COVERED → F-01.5 | DLQ |
| 54805a4 | fix(scripts): start_core + OTel reset | 221 | IGNORED | scripts/devops |
| 5dc5739 | feat: MCP server configs | 92 | IGNORED | dev tooling |
| 5449cd7 | feat: tests ingestion + startup scripts | 1830 | IGNORED | tests + scripts |
| 79df2fa | fix(workflow): YAML frontmatter | 2 | IGNORED | trivial |
| 4faa444 | refactor(docs): formatting | 430 | IGNORED | docs |
| d465cde | refactor(docs): rename → LinkAnvil | 88 | IGNORED | docs |
| 4f8d11c | fix(docs) | 2 | IGNORED | docs |
| c0f3808 | feat(docs): EPIC-08/09 features | 214 | IGNORED | docs backlog meta |
| 28f7e8d | feat(config): models LiteLLM | 47 | COVERED → F-02.2 | LLM Gateway |
| a9e4837 | fix(docs): links GH Pages | 9 | IGNORED | docs |
| 4c2f44a | docs/Refactor instalación | 561 | IGNORED | docs |
| ca86638 | feat(docs): VitePress setup | 390 | IGNORED | docs infra |
| c1057a6 | feat(scraper): Scrapling + Playwright | 84 | COVERED → F-02.1 | Strategy pattern |
| fb130a2 | feat(export): in-memory secure | 353 | COVERED → F-07.1 | Export bóveda |
| 6fd1b5e | feat(tests): API gateway tests | 503 | IGNORED | tests |
| 088a25f | feat(export): F-07.3 hot.md | 130 | COVERED → F-07.3 | hot.md |
| b7d1162 | feat(export): F-07.2 bidirectional | 133 | COVERED → F-07.2 | Aristas Obsidian |
| 956287f | feat(export): F-07.1 LLM Wiki | 250 | COVERED → F-07.1 | LLM Wiki |
| 5e8371c | feat(collider): F-03.3 typed relations | 135 | COVERED → F-03.3 | Colisionador |
| 47bc627 | feat(colisionador): pipeline criteria | 34 | SUBDETAIL of F-03.3 | Pipeline mejora |
| fe4b14e | feat(export): vault offline | 116 | COVERED → F-07.1 | Vault |
| c708c82 | feat(ia): skills + agentic workflows | 4227 | IGNORED | `.github/` agents (dev tooling) |
| 6581e33 | feat(throttling): rate limit local | 125 | COVERED → F-06.4 | Throttling |
| e5f9751 | feat(chatbot): fetch_historico_rag_crudo | 129 | COVERED → F-04.5 | Function calling |
| 4df7404 | feat(export): fetch_all_resources_for_export | 134 | COVERED → F-07.1 / F-03.5 | Export ZIP |
| bc6e25f | feat(audit): fetch_resources_for_audit | 106 | COVERED → F-05.3 | Auditoría IA |
| ea22a8d | feat(session): async session context | 136 | COVERED → F-04.2 | Persistencia |
| b925f92 | feat(dashboard): admin metrics | 126 | COVERED → F-04.3 | Dashboard |
| 5cfef45 | feat(semantic-collider): save_semantic_collisions | 136 | COVERED → F-03.3 | Colisionador |
| e863d70 | feat(webhook): external webhook | 73 | COVERED → F-01.4 | Webhook |
| 8b9e6c2 | feat(prometheus): alerting rules | 36 | COVERED → F-06.3 | Prometheus |
| be90150 | feat(telemetry): OTel embedder/outbox/scraper | 31 | COVERED → F-06.1 | OTel |
| 04e77a1 | feat(telemetry): OTel ingestion/chatbot | 121 | COVERED → F-06.1 | OTel |
| 3275c87 | feat(chatbot): quarantine functions | 219 | COVERED → F-05.2 | Cuarentena |
| 20555da | feat(audit_cron) + Redis session | 242 | COVERED → F-05.1 + F-04.2 | Cron + sesiones |
| 77fa53b | feat(chatbot): multi-tenant RAG | 176 | COVERED → F-04.1 | Chatbot RAG |
| aa503c4 | feat(rls): tenant isolation tests | 133 | COVERED → F-03.4 | RLS |
| fc6e480 | feat(embedder): EmbedderWorker | 223 | COVERED → F-03.2 | Embedder |
| 977012c | feat(database): DatabaseManager outbox | 306 | COVERED → F-03.1 | Outbox |
| 5a8dc54 | feat(database): outbox publisher | 21 | COVERED → F-03.1 | Outbox |
| 28f9015 | feat(schema): ScrapedDataSchema | 112 | COVERED → F-02.4 | Schema clasificación |
| a19ee96 | feat(strategy): AiProxyStrategy | 415 | COVERED → F-02.1 + F-02.3 | Strategy + Zero-Defect |
| 677b750 | feat(ai_proxy): LLM gateway tests | 166 | COVERED → F-02.2 | Gateway |
| 9934932 | feat(scraper): dynamic worker | 273 | COVERED → F-02.1 | Strategy base |
| 2ff53ec | feat(dlq): DLQManager retry | 175 | COVERED → F-01.5 | DLQ |
| ed45de6 | feat(telegram): webhook URL ingestion | 142 | COVERED → F-01.3 | Telegram |
| 67bb0f5 | feat(ingestion): Redis dedup + RabbitMQ | 221 | COVERED → F-01.2 + F-01.1 | Ingestion |
| e48dba3 | feat(redis): Bloom Filter | 242 | COVERED → F-01.1 | Bloom |
| 7f45bdf | feat(qdrant): init collections | 22 | COVERED → F-00.6 | Qdrant base |
| de3a531 | feat(postgres): tenant policies | 11 | COVERED → F-03.4 | RLS |
| c1b09df | feat(n8n): execution settings | 7 | COVERED → F-00.3 | n8n config |
| c5ce5fd | feat(traefik): rate + retry middleware | 40 | COVERED → F-00.2 | Traefik |
| dd3e830 | feat(infra): compose + cerebro-net | 1605 | COVERED → F-00.1 | Compose base |
| b5ad42e | fix: backlog upload script | 65 | IGNORED | script |
| 3f03f66 | feat: initialize project infra | 8006 | IGNORED | Project scaffolding inicial (snapshot pre-backlog) |
| 4b6287b | feat: initialize workspace | 6889 | IGNORED | Project scaffolding inicial |
| e417771 | Initial commit | 1 | IGNORED | initial |

## Backlogs creados (10 nuevos en `docs/src/Extractor_de_Requisitos/backlog/`)

1. `F-00.14_tailscale-funnel-telegram-webhook.md` — cubre `12cf9ac`. Túnel Tailscale persistente para webhook Telegram.
2. `F-00.15_n8n-provisioning-zero-touch.md` — cubre `6b8f649`, `cd37988`, `f7c09b9`, `f28601e`. Bootstrap automático de n8n.
3. `F-02.6_scraper-antibot-escalada-stealth.md` — cubre `76041a4`, `d436349`, `8b22f8f`. Anti-bot + escalada Basic→Stealth + Medium rewrite.
4. `F-03.6_cache-embeddings-staged-bd.md` — cubre `a10795b`. Cache de embeddings staged en BD (0 calls LiteLLM/sesión demo).
5. `F-03.7_rag-chunking-cerebro-chunks-32k.md` — cubre `fb5f2cd`, `871c605`, `841f499`, `6d15580`. Chunking RAG + contexto 32k + prompt enrich.
6. `F-04.8_notificaciones-in-app-telegram-sse.md` — cubre `b527be5`, `a1c8e12`, `7f3c843`, `eb467aa`, `b406148`, `f7a4559`, `c223817`, `bf3b3b9`, `d05f16a`, `37d4737`. Campana + SSE + Telegram outbound.
7. `F-05.4_clasificacion-temporal-llm-audit-policy-jsonb.md` — cubre `021c3ab`, `41bfd39`. Clasificación temporal LLM + auto-archive con `audit_policy JSONB`.
8. `F-08.5_byok-llaves-llm-por-usuario.md` — cubre `3b0201c`, `e2093e3`, `055254e`, `49d2c1c`. BYOK + cuota demo per-IP.
9. `F-09.3_landing-publico-marketing.md` — cubre `7439d07`, `6beebc1`, `75dbbf2`. Landing público marketing.
10. `F-09.4_demo-publico-sub-tenants-efimeros.md` — cubre `37db013`, `f87af38`, `a536da9`, `ebb3735`, `eb5f529`, `53870a9`, `1b38f09`, `8150d7d`. Demo público + sub-tenants efímeros.

## Ampliaciones propuestas (no escritas en disco)

Backlogs existentes que el reconciler sugiere actualizar para reflejar trabajo reciente. El usuario los aplica manualmente.

- **F-04.1** (Chatbot RAG): añadir AC sobre `redirect` automático a `/chat` post-login + tooltips contextuales en sidebar (commit `c67c505`). Añadir AC sobre streaming RAG resiliente y refresh tokens (commit `ba405e2`).
- **F-04.2** (Persistencia multi-sesión): añadir AC sobre paginación de `/chats` con `limit/offset/total` (commit `8f9e5bd`).
- **F-04.3** (Dashboard administrativo): añadir AC sobre paginador cliente reutilizable y filtros de KB “solo activos” (commits `75e74ca`, `fdca643`, `9191911`, `bca81b3`, `8f294e5`).
- **F-04.8** (notificaciones — nuevo): añadir AC sobre dispatch local para feedback UI inmediato (commit `6811575`) si se quiere granular.
- **F-05.1** (Auditoría temporal): añadir AC explícito sobre la extracción de `expiration_date` al ingerir (commit `da9748a`) y endpoint `/audit-cron` protegido por token (commit `da0de5e`); las dos fases caducidad→cuarentena→expirado (commit `bc6cb4c`).
- **F-05.2** (Bandeja cuarentena): añadir AC sobre página `/expired` con días desde expiración (commits `99f5c02`, `5bb172e`), rescate desde expirado (commit `199f8b2`, `22ba12b`, `8c05101`) y paginación cliente en `/quarantine` y `/expired` (commit `087f058`, `060b835`).
- **F-06.6** (Heartbeat liveness): añadir AC sobre healthchecks `qdrant` y `cerebro-web` (commit `292f891`).

## Skipped (idempotencia)

Ninguno — primera ejecución de este reconciler sobre el repo. Re-correr no debe crear duplicados gracias a que cada archivo nuevo tiene un slug determinista en su nombre.

---

## Notas para el orquestador

- Los 10 archivos nuevos están en `/tmp/linkanvil-staging/docs/src/Extractor_de_Requisitos/backlog/` listos para `rsync` al remoto.
- No se han modificado backlogs existentes en disco; las ampliaciones quedan como propuestas para revisión humana.
- LOC reportadas vienen de `git log --numstat` con suma `added+deleted` por commit (incluye renames, que aparecen como 0/0).
- Significancia: ≥50 LOC en `src/` o `infra/`, O subject empezando con `feat:/perf:/Slice`. Commits que solo tocan `docs/`, `tests/`, `.github/agents`, `.claude/`, `.githooks/`, `ops/cron/`, `ops/triggers/` se marcan IGNORED como dev tooling.
