# Extracción de requisitos del sistema

> Subrepo que se usó al inicio del proyecto para destilar los requisitos
> de LinkAnvil — desde una descripción libre del problema hasta un
> backlog técnico ejecutable — aplicando un pipeline de **7 fases
> asistido por IA**.

## ¿Qué hay aquí?

5 documentos maestros + 54 features de backlog repartidos en 10 épicas
(E-00 … E-09). Esto **no es código del producto**; es el **diseño** que
justificó cada decisión técnica que después se implementó en `src/`.

Si vienes a entender el "cómo" del sistema, ve a la sección
[Proyecto](../0-resumen) del sidebar. Si vienes a entender el "por qué",
quédate aquí.

## El flujo de 7 fases

El pipeline ejecuta una transición controlada de **ambigüedad → diseño
ejecutable**, dejando trazabilidad en cada paso. Cada fase produce un
artefacto concreto que alimenta a la siguiente.

| Fase | Entrada | Salida | Asistencia IA |
|---|---|---|---|
| **1. Contexto bruto** | Idea libre del stakeholder | [`0_descripcion_proyecto.md`](./0_descripcion_proyecto) — problema, restricciones, glosario inicial | Entrevista guiada con Claude para no dejar huecos |
| **2. Destilación de épicas** | Contexto bruto | [`1_epics_and_features.md`](./1_epics_and_features) — 10 épicas, 54 features clasificados MoSCoW (MUST · SHOULD · COULD) | Agente `planner` extrae y clasifica |
| **3. Análisis de riesgos** | Épicas + restricciones | [`2_architecture_risks.md`](./2_architecture_risks) — NFRs, ADRs, tabla STRIDE | Agentes `architect` + `security-reviewer` |
| **4. Backlogs detallados** | Cada feature → ficha individual | [`backlog/F-XX.Y_*.md`](#backlog) — acceptance criteria, dependencias, notas de implementación | `planner` por feature, revisión cruzada |
| **5. Diagramas C4** | Épicas + backlog | [`3_c4_diagrams.md`](./3_c4_diagrams) — 21 contenedores en C4 (Context → Container → Component) | `architect` produce mermaid |
| **6. Documentación VitePress** | Todo lo anterior | `docs/src/*.md` (lo que estás leyendo) | `doc-updater` convierte backlog en docs para humanos |
| **7. GitHub Issues / Projects** | Backlog cerrado | Una issue por feature, agrupadas por épica en un Project board | `github-orchestrator` |

> Cada paso queda registrado en [`AUDIT_LOG.md`](./AUDIT_LOG) con
> timestamp, agente responsable y prompt usado.

## Por qué se mantiene este subrepo

Aunque el código final ya vive en `src/`, conservar este subrepo cumple
tres funciones:

- **Trazabilidad feature → ADR → código**. Si en el futuro se cuestiona
  "¿por qué tomamos esta decisión arquitectónica?", el ADR existe y
  apunta al feature que lo motivó.
- **Onboarding rápido**. Un nuevo colaborador puede leer una ficha
  `F-XX.Y` y entender el **porqué** antes de tocar el **cómo** en el
  repo principal.
- **Re-uso del proceso**. El pipeline de 7 fases es replicable en
  futuros sub-proyectos o módulos. Las plantillas de los maestros
  sirven de base.

## Mapeo a la arquitectura final

Cada épica tiene contrapartida directa en contenedores del sistema
desplegado. Esta tabla es el puente entre el "qué pedimos" y el "qué
construimos":

| Épica | Contenedores reales | Documentación canónica |
|-------|---------------------|------------------------|
| E-00 Setup | `docker-compose`, `traefik`, `postgres`, `redis`, `rabbitmq`, `qdrant` | [1 · Instalación](../1-instalacion-configuracion) · [4 · Arquitectura](../4-arquitectura) |
| E-01 Ingesta | `scraper-worker`, `ingest-api`, bot Telegram | [3 · Componentes](../3-componentes) · [9 · Ejemplo Fase 1](../9-ejemplo_flujo) |
| E-02 Procesamiento IA | `embedder-worker`, LiteLLM, prompt extractor | [7 · Prompts](../7-prompts) · [3 · Componentes](../3-componentes) |
| E-03 RAG | `qdrant`, embedder, retriever en `api` | [8 · Lifecycle](../8-lifecycle) · [9 · Ejemplo Fase 2](../9-ejemplo_flujo) |
| E-04 Chat | `api` (chat + SSE), `frontend` Next.js | [9 · Ejemplo Fase 3](../9-ejemplo_flujo) · [10 · Demo](../10-demo) |
| E-05 Curación | `audit_cron`, notificaciones outbox | [8 · Lifecycle](../8-lifecycle) · [4 · Arquitectura](../4-arquitectura) |
| E-06 Observabilidad | OTel collector, métricas Prometheus | [4 · Arquitectura](../4-arquitectura) |
| E-07 Offline | (fuera de scope MVP — backlog congelado) | — |
| E-08 Auth | `api` JWT + refresh tokens httpOnly | [4 · Arquitectura](../4-arquitectura) |
| E-09 UX | `frontend`, demo público con sub-tenants | [10 · Demo](../10-demo) · [9 · Ejemplo Fase 3.d](../9-ejemplo_flujo) |

## Convenciones de los documentos

- **Idioma**: español. Los snippets de código y los IDs internos
  (épica, feature, ADR) permanecen en inglés.
- **Numeración estable**: los IDs de épica/feature/ADR NO se reutilizan
  si se borra un elemento. Garantiza que un link externo no apunte a
  contenido distinto del esperado.
- **MoSCoW** por feature: MUST · SHOULD · COULD · WON'T (esta última
  vacía en el MVP).
- **STRIDE** por superficie de ataque en `2_architecture_risks.md`.

## Navegación

- [Documento maestro de entrada](./0_descripcion_proyecto)
- [Épicas y features (vista global)](./1_epics_and_features)
- [Riesgos, NFRs y ADRs](./2_architecture_risks)
- [Diagramas C4](./3_c4_diagrams)
- [Audit log de la extracción](./AUDIT_LOG)

### Backlog

Las 54 fichas individuales están agrupadas por épica en el sidebar a la
izquierda. Cada ficha sigue el mismo esquema:

```
# F-XX.Y · Nombre del feature
- Épica: E-XX
- Prioridad: MUST | SHOULD | COULD
- Dependencias: F-AA.B, F-CC.D
- Acceptance criteria
- Notas de implementación
- ADRs relacionados
```
