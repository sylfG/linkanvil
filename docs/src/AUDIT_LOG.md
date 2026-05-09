<div align="center">
  <img src="/logo-light.png" alt="Logo" width="80" height="80" class="light-only">
  <img src="/logo-dark.png" alt="Logo" width="80" height="80" class="dark-only">


# 📋 AUDIT LOG — Linkanvil

</div>


<!-- La IA añade una fila por cada fase completada del workflow. No editar manualmente. -->

| Fecha | Fase | Skill Usada | Archivos Generados | Estado |
| --- | --- | --- | --- | --- |

## 2026-04-09 18:08 � Fase 1 completada

- **Skill usada**: Business Analyst
- **Acción**: ExtrAcción y priorizaci�n de iniciativas desde el bloque t�cnico y funcional brutales.
- **Archivos generados**:
  - docs/src/1_epics_and_features.md

## 2026-04-09 18:09 � Fase 2 completada

- **Skill usada**: System Architect
- **Acción**: Definici�n de Requisitos No Funcionales (NFRs) y ejecuci�n de an�lisis de riesgos STRIDE basado en arquitectura orientada a eventos.
- **Archivos generados**:
  - docs/src/2_architecture_risks.md

## 2026-04-09 18:12 � Fase 3 completada

- **Skill usada**: Business Analyst
- **Acción**: Generaci�n de Backlog individual por Feature aplicando principios MoSCoW, categor�as universales y relacionando dependencias para la arquitectura Event-Driven del Segundo Cerebro.
- **Archivos generados**:
  - 32 archivos en docs/src/backlog/ correspondientes a cada una de las 32 features validadas.

## 2026-04-09 18:15 � Fase 4 completada

- **Skill usada**: System Architect
- **Acción**: Generaci�n de Documentaci�n Visual con Diagramas C4 y Secuencias Mermaid, basados en el dise�o de arquitectura y el backlog en 2_architecture_risks.md y 1_epics_and_features.md.
- **Archivos generados**:
  - docs/src/3_c4_diagrams.md

## 2026-04-09 18:17 � Fase 5 completada

- **Skill usada**: Business Analyst + System Architect
- **Acción**: Generaci�n y Agrupaci�n visual mediante categorias para el Sidebar de Vitepress y el documento maestro Index.
- **Archivos generados**:
  - docs/.vitepress/config.mts
  - docs/src/index.md

## 2026-04-09 18:20 � Fase 6 completada

- **Acción**: Lanzamiento de script de publicaci�n de backlogs a GitHub (Fase 6).
- **Nota**: El usuario debe ejecutarlo en un entorno con bash y \gh\ (GitHub CLI) instalados o configurados adecuadamente.

| 2026-04-19 | Actualización general de la arquitectura para documentar integraciones de Exportador LLM Wiki (Obsidian) | Asistente IA | Usuario |

## 2026-04-19 — Explicación de Doble Base de Datos

- **Skill usada**: System Architect
- **Acción**: Refactorización de Arquitectura: Inclusión de la explicación detallada sobre el Patrón de Persistencia Dual (Postgres como Cerebro Lógico vs Qdrant como Cerebro Semántico).
- **Archivos modificados**:
  - `docs/src/6_arquitectura.md`
  - `docs/src/5_resumen_servicios.md`
  - `docs/src/backlog/F-00.4...md`
  - `docs/src/backlog/F-00.6...md`

## 2026-05-09 — Hardening del pipeline de ingesta + RAG enriquecido + Telegram público

- **Skill usada**: System Architect + Asistente IA
- **Acción**: Sesión de hardening end-to-end disparada por incidencias reales (URLs ingeridas que no aparecían en KB, RAG respondiendo sin usar el resumen guardado, modelo `cerebro-pro` colgándose, URL de Medium devolviendo basura, webhooks de Telegram sin URL pública).
- **Cambios funcionales**:
  - **Ingestion API ([src/ingestion/main.py](../../src/ingestion/main.py))**: ahora publica al queue `q.url.ingesta` aunque el bloom filter marque como duplicada. El bloom es un hint best-effort y divergía del estado de Postgres tras un reset, dejando `usuario_recursos` sin link para el tenant. Idempotencia movida al scraper (ruta de reuso).
  - **Chat RAG ([src/api/main.py](../../src/api/main.py), [src/api/database.py](../../src/api/database.py))**: tras el match de Qdrant se llama a `get_resources_for_rag(tenant, ids)` para traer `titulo+resumen+tags+categoría` desde Postgres y construir el contexto rico que se pasa al LLM. Antes solo se inyectaba `title+url+score` y el modelo respondía a ciegas. System prompt endurecido para forzar citas textuales del contexto.
  - **LiteLLM ([infra/litellm/config.yaml](../../infra/litellm/config.yaml))**: `nvidia/llama-3.1-nemotron-70b-instruct` retirado por NVIDIA NIM (404). Sustituido por `meta/llama-3.3-70b-instruct` (primario) + `nvidia/llama-3.3-nemotron-super-49b-v1.5` (fallback).
  - **Frontend ([src/frontend/app/(app)/page.tsx](../../src/frontend/app/(app)/page.tsx))**: eliminado el `useEffect` que creaba sesiones huérfanas al recargar la página sin escribir nada. La sesión se crea en lazy desde `send()`.
  - **Scraper ([src/scraper/strategy.py](../../src/scraper/strategy.py), [src/scraper/worker.py](../../src/scraper/worker.py), [src/data/db.py](../../src/data/db.py))**: nueva excepción `BlockedContentError`, función `_rewrite_for_scrape()` (medium.com → readmedium.com), `_looks_blocked()` con marcadores específicos (sin `cloudflare`/`captcha` planos que daban falsos positivos en `cdnjs.cloudflare.com`) y ejecutado tras *cada* estrategia. Guard de calidad post-clean: < 300 chars → cuarentena. Nueva función `db.quarantine_recurso_blocked()` que marca el recurso con `quarantine_reason='manual'` y 30 días de gracia.
  - **Telegram público ([docker-compose.yml](../../docker-compose.yml), [infra/tailscale/serve.json](../../infra/tailscale/serve.json), [.env.example](../../.env.example))**: nuevo sidecar `tailscale-funnel` (profile `telegram`) con imagen `tailscale/tailscale:stable`. Expone `ingestion-api:8000` en `https://linkanvil-ingest.<tailnet>.ts.net` con HTTPS automático. Volumen `cerebro-tailscale-state` mantiene la URL persistente entre reconstrucciones. Validado end-to-end con un bot real entregando URLs al webhook.
- **Docs actualizadas en esta sesión**:
  - `3_c4_diagrams.md` — añadido `tailscale` al diagrama de contenedores; flujo de ingesta refleja publish-on-duplicate y rama de cuarentena automática; flujo RAG muestra el enriquecimiento desde Postgres.
  - `5_resumen_servicios.md` — entrada nueva para `cerebro-tailscale`; descripción del scraper actualizada con detección anti-bot y cuarentena.
  - `6_arquitectura.md` — flujo de ingesta y de Chat RAG actualizados; nueva subsección "Túnel Telegram — Tailscale Funnel"; descripción del scraper actualizada.
  - `7_ejemplo_flujo.md` — Fase 1 actualizada con publish-on-duplicate, rewrite anti-bot y cuarentena automática.
  - `8_instalacion_y_configuracion.md` — sección 6.4 nueva con los pasos completos para configurar Tailscale Funnel + bot.
  - `AUDIT_LOG.md` — esta entrada.

---

## 2026-04-28 — Fase auditoría completada (commits 5dc5739..64eae38)

- **Skill usada**: Change Manager + Business Analyst
- **Acción**: Mapeo de los 23 commits de la auditoría (bugs A1-A11, mejoras B1-B4, hardening de producción C1-C15) a backlogs en `docs/src/backlog/`. Se generan 15 backlogs nuevos y se amplían 3 existentes con sección "Historial de Cambios". Se actualiza `1_epics_and_features.md` (tablas de Epics + resumen de prioridades) para reflejar las nuevas Features.
- **Backlogs nuevos**: F-00.7, F-00.8, F-00.9, F-00.10, F-00.11, F-00.12, F-00.13, F-01.6, F-02.5, F-04.6, F-04.7, F-06.5, F-06.6, F-08.3, F-08.4
- **Backlogs modificados**: F-00.1, F-01.5, F-06.3 (sección Historial de Cambios)
- **Archivos generados/modificados**:
  - 15 archivos en `docs/src/backlog/`
  - `docs/src/1_epics_and_features.md` (filas nuevas + tabla de resumen 25/10/4 → 34/16/4)
  - `docs/src/AUDIT_LOG.md` (esta entrada)
- **Pendiente de confirmación**: subir los nuevos Issues a GitHub vía `bash .github/scripts/upload_backlog_to_github.sh` (skill change-manager exige confirmación explícita).
