# Pipeline de Trabajo — Fases de Ejecución

> **Skill refs:** `docs/skills/business-analyst.md` · `docs/skills/system-architect.md` · `docs/skills/change-manager.md`
> **Reglas globales:** `docs/workflow/rules.md`

---

## FASE 1: Descubrimiento y Desglose

**Skill:** Business Analyst
**Disparador:** `/iniciar-requisitos`

**Acción autónoma:**

- Leer `docs/src/0_descripcion_proyecto.md` antes de preguntar nada.
- Extraer desde bloques `2`, `3`, `4`, `5`, `6`, `7`. No asumir requisitos pre-estructurados; el documento es fuente de contexto bruto (conversaciones, entrevistas, notas).
- Validar completitud mínima en bloques `0`, `2`, `3`, `4`, `5`, `6`, `7` y semáforo de `9`.
- Si faltan datos: devolver checklist de secciones a completar y **pausar la fase**.
- Solo si persiste bloqueo crítico tras revisar el archivo: máximo 3 preguntas en chat.
- Crear `docs/src/1_epics_and_features.md` en disco.
- Actualizar `AUDIT_LOG.md`.
- *Esperar aprobación en chat.*

---

## FASE 2: Arquitectura y Riesgos

**Skill:** System Architect
**Disparador:** Usuario aprueba Epics.

**Acción autónoma:**

- Definir NFRs y ejecutar análisis STRIDE.
- Crear `docs/src/2_architecture_risks.md` en disco.
- Actualizar `AUDIT_LOG.md`.
- *Pedir aprobación en chat.*

---

## FASE 3: Generación de Backlog

**Skill:** Business Analyst
**Disparador:** Riesgos aprobados.

**Acción autónoma:**

- Aplicar MoSCoW a las Features.
- Por cada Feature: crear **un archivo `.md` independiente** en `docs/src/backlog/` (ej. `F-01.1_nombre.md`).
- Cada archivo sigue estrictamente la plantilla en `docs/templates/feature-backlog.md`, incluyendo obligatoriamente:
  - `## 🏷️ Categoría` con categoría principal (y opcionalmente secundaria).
  - `## 📦 Dependencias` declarando backlogs previos con columna `Bloqueante`.
- Actualizar `AUDIT_LOG.md`.
- *Informar en chat: cuántos archivos creados, agrupados por categoría.*

---

## FASE 4: Documentación Visual

**Skill:** System Architect
**Disparador:** Backlog aprobado.

**Acción autónoma:**

- Generar diagramas C4 Model y Flujos en formato Mermaid.
- Crear `docs/src/3_c4_diagrams.md` en disco.
- Actualizar `AUDIT_LOG.md`.

---

## FASE 5: Publicación en VitePress

**Skill:** Business Analyst + System Architect
**Disparador:** Diagramas aprobados (o instrucción explícita).

**Acción autónoma:**

- Actualizar `docs/.vitepress/config.mts`: sidebar agrupado por categoría universal con emojis:
  - `🖥️ UI / Presentation` · `⚙️ Logic / Business` · `🗄️ Data` · `🔌 Integration`
  - `🏗️ Infrastructure` · `🔒 Security` · `📊 Observability` · `🛠️ DX / Tooling` · `📚 Documentation`
- Cada archivo aparece **una sola vez** bajo su categoría primaria.
- Si existe `docs/src/index.md`, actualizar hero con nombre real del proyecto.
- Actualizar `AUDIT_LOG.md`.
- *Informar en chat las secciones del sidebar generadas.*

---

## FASE 6: Subida del Backlog a GitHub Issues

**Disparador:** Usuario solicita publicar en GitHub (o al finalizar Fase 5).

**Flujo:**

**Paso 1 — Detección del repositorio:**

1. Leer sección `"Contexto GitHub para Publicación de Backlog"` de `docs/src/0_descripcion_proyecto.md`.
2. Si `URL`, `OWNER/REPO`, `Organización` y `Project Number` están completos → continuar.
3. Si falta alguno → pedir al usuario que complete esa sección y pausar.

**Paso 2 — Confirmación:**
Preguntar:
> "¿Quieres que suba el backlog como GitHub Issues al repositorio `<nombre>`? Ejecutaré `.github/scripts/upload_backlog_to_github.sh` que creará un Issue por Feature, lo añadirá al GitHub Project con prioridad (Must/Should/Could), creará milestones por Épica, vinculará dependencias como sub-issues y marcará bloqueantes con 'Blocked by'."

**Paso 3 — Ejecución:**

```bash
# Simular primero (recomendado)
bash .github/scripts/upload_backlog_to_github.sh --dry-run

# Ejecutar en real
bash .github/scripts/upload_backlog_to_github.sh

# Opciones avanzadas
bash .github/scripts/upload_backlog_to_github.sh \
  --repo OWNER/REPO --org ORGANIZATION --project PROJECT_NUMBER
bash .github/scripts/upload_backlog_to_github.sh --skip-milestones
bash .github/scripts/upload_backlog_to_github.sh --skip-deps
```

**Prerrequisitos:**

- `gh` CLI >= 2.40 autenticado (`gh auth status`)
- `jq` instalado
- GitHub Project con campo Single-Select `Priority` (Must / Should / Could)
- Archivos de backlog con formato de nombre `F-XX.Y_titulo.md`

Actualizar `AUDIT_LOG.md` con número de Issues creados y URL del repositorio.

---

## FASE 7: Gestión de Cambios y Revisión de Backlog

**Skill:** Change Manager
**Disparador:** `/revisar-cambios`

**Acción autónoma:**

- Leer `docs/src/0_cambios_requisitos.md` — fuente de los cambios solicitados.
- Leer todos los archivos en `docs/src/backlog/` — estado actual del backlog.
- Leer `docs/src/1_epics_and_features.md` — mapa de Epics y Features.
- Ejecutar análisis de impacto siguiendo el skill `docs/skills/change-manager.md`.
- Mostrar **matriz de impacto en chat** y esperar confirmación antes de modificar.
- Aplicar cambios aprobados: modificar backlogs existentes, crear nuevos, actualizar dependencias.
- Actualizar `AUDIT_LOG.md` con delta de cambios (CHANGE-XX).
- *Esta fase puede ejecutarse múltiples veces. Cada ejecución se registra como CHANGE-XX.*
