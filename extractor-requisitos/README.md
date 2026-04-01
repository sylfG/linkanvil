# Elite Requirements Engineering Workspace

Convierte contexto bruto de negocio en backlog estructurado, arquitectura documentada e Issues de GitHub.
Compatible con **Claude Code**, **GitHub Copilot** y **Antigravity**.

> **Regla principal:** este repositorio no genera código fuente de aplicaciones.
> La IA extrae requisitos desde fuentes brutas (entrevistas, conversaciones, notas), no desde requisitos ya redactados.

---

## Arquitectura: fuente única de verdad

Las reglas, fases y skills están escritas **una sola vez** en `docs/`. Cada herramienta de IA tiene un adapter mínimo que apunta a esa fuente.

```
repo/
├── CLAUDE.md                          ← Adapter Claude Code
├── .github/copilot-instructions.md    ← Adapter GitHub Copilot
├── .claude/requirements-workflow.md   ← Skill Claude Code
├── .agent/skills/
│   └── requirements-workflow.md       ← Skill Antigravity
└── docs/
    ├── workflow/
    │   ├── rules.md                   ← Reglas globales (AI-agnostic)
    │   └── pipeline.md                ← Fases 1-7 (AI-agnostic)
    ├── skills/
    │   ├── business-analyst.md        ← Skill BA canónico
    │   ├── system-architect.md        ← Skill SA canónico
    │   └── change-manager.md          ← Skill gestión de cambios
    ├── templates/
    │   ├── feature-backlog.md         ← Plantilla de Feature
    │   └── change-request.md          ← Plantilla de cambio
    └── src/
        ├── 0_descripcion_proyecto.md  ← Contexto maestro del proyecto
        ├── 0_cambios_requisitos.md    ← Registro de cambios (Fase 7)
        └── backlog/                   ← Features generadas (F-XX.Y_nombre.md)
```

---

## Configuración por herramienta de IA

### Claude Code

El archivo `CLAUDE.md` se carga automáticamente. No requiere configuración adicional.

Comandos disponibles:

```
/iniciar-requisitos     → Fase 1: descubrimiento y desglose
/revisar-cambios        → Fase 7: análisis de impacto sobre backlog existente
/requirements-workflow  → Carga el skill completo del workspace
```

### GitHub Copilot Chat (VS Code)

El archivo `.github/copilot-instructions.md` se carga automáticamente.

Para iniciar con contexto completo, usa en Copilot Chat:

```
@workspace /iniciar-requisitos
#file:docs/src/0_descripcion_proyecto.md
#file:docs/workflow/pipeline.md
#file:docs/skills/business-analyst.md
#file:docs/skills/system-architect.md
```

Para revisar cambios:

```
@workspace /revisar-cambios
#file:docs/src/0_cambios_requisitos.md
#file:docs/workflow/pipeline.md
#file:docs/skills/change-manager.md
```

### Antigravity

Instala los skills del workspace con:

```bash
npx antigravity-awesome-skills --antigravity
```

El skill propio del workspace está en `.agent/skills/requirements-workflow.md`.
Para activarlo en una sesión:

```
Use @requirements-workflow para iniciar el proceso de requisitos
```

---

## Prerrequisitos generales

1. Uno de los siguientes entornos de IA:
   - Claude Code CLI
   - VS Code con extensión GitHub Copilot Chat
   - Antigravity con `npx antigravity-awesome-skills --antigravity`
2. Para Fase 6 (publicación en GitHub):
   - `gh` CLI >= 2.40 instalado y autenticado (`gh auth status`)
   - `jq` instalado
   - GitHub Project con campo **Single-Select** `Priority` (opciones: Must / Should / Could)

---

## Ejecución paso a paso

### Paso 1 — Cargar contexto en el documento maestro

1. Abre `docs/src/0_descripcion_proyecto.md`.
2. Completa como mínimo los bloques: **0, 2, 3, 4, 5, 6, 7**.
3. Marca el semáforo de la fase objetivo en el bloque 9 como "Listo".

### Paso 2 — Lanzar el workflow

Ejecuta el comando según tu herramienta:

| Herramienta | Comando de inicio |
|-------------|-------------------|
| Claude Code | `/iniciar-requisitos` |
| Copilot Chat | `@workspace /iniciar-requisitos #file:docs/src/0_descripcion_proyecto.md #file:docs/workflow/pipeline.md #file:docs/skills/business-analyst.md` |
| Antigravity | `Use @requirements-workflow to start /iniciar-requisitos` |

### Paso 3 — Aprobar cada fase

El agente pausa entre fases y espera tu aprobación explícita:

| Fase | Artefacto generado |
|------|--------------------|
| Fase 1 | `docs/src/1_epics_and_features.md` |
| Fase 2 | `docs/src/2_architecture_risks.md` |
| Fase 3 | `docs/src/backlog/F-XX.Y_nombre.md` (uno por Feature) |
| Fase 4 | `docs/src/3_c4_diagrams.md` |
| Fase 5 | `docs/.vitepress/config.mts` actualizado |
| Fase 6 | GitHub Issues + Milestones + Dependencias |
| Fase 7 | Backlogs modificados / nuevos (a demanda) |

---

## Gestión de cambios (Fase 7)

Cuando el cliente o el equipo introduzca cambios, nuevos requisitos o modificaciones:

1. Abre `docs/src/0_cambios_requisitos.md`.
2. Añade un bloque `CHANGE-XX` siguiendo la plantilla en `docs/templates/change-request.md`.
3. Ejecuta `/revisar-cambios`.
4. El agente analiza todos los backlogs existentes y presenta una **matriz de impacto**:

   | Símbolo | Significado |
   |---------|-------------|
   | ✅ | Backlog no afectado |
   | ⚠️ | Backlog debe modificarse |
   | 🆕 | Requiere nuevo backlog |
   | 🗑️ | Backlog obsoleto / deprecar |

5. Tú apruebas la matriz. El agente aplica los cambios y actualiza el `AUDIT_LOG.md`.

> La Fase 7 puede ejecutarse múltiples veces. Cada ejecución queda registrada como `CHANGE-XX`.

---

## Publicación en GitHub (Fase 6)

Antes de publicar, completa el bloque "Contexto GitHub" en `docs/src/0_descripcion_proyecto.md`.

```bash
# Simular sin crear
bash .github/scripts/upload_backlog_to_github.sh --dry-run

# Ejecutar en real
bash .github/scripts/upload_backlog_to_github.sh

# Opciones
bash .github/scripts/upload_backlog_to_github.sh --skip-milestones
bash .github/scripts/upload_backlog_to_github.sh --skip-deps
```

El script es idempotente: omite Issues cuyo título ya existe, solo crea los nuevos.

---

## Verificación rápida al finalizar

Al completar un ciclo completo deberías tener:

- [ ] `docs/src/1_epics_and_features.md` generado
- [ ] `docs/src/2_architecture_risks.md` generado
- [ ] Archivos en `docs/src/backlog/` (uno por Feature)
- [ ] `docs/src/3_c4_diagrams.md` generado
- [ ] `docs/.vitepress/config.mts` con sidebar agrupado por categoría
- [ ] `docs/src/AUDIT_LOG.md` con entradas de cada fase

---

## Mantenimiento del workspace

Para modificar reglas, añadir fases o actualizar skills: **edita únicamente los archivos en `docs/workflow/` y `docs/skills/`**.
Los adapters de cada herramienta de IA se actualizan automáticamente porque apuntan a esos canónicos.

---

## Problemas frecuentes

| Problema | Solución |
|----------|---------|
| El flujo no avanza de fase | Revisa bloque 9 de `0_descripcion_proyecto.md`; completa los bloques mínimos exigidos |
| No publica en GitHub | Revisa bloque "Contexto GitHub" en `0_descripcion_proyecto.md`; verifica `gh auth status` |
| El backlog no se sube completo | Verifica formato de archivos en `docs/src/backlog/`; revisa `ERROR_PREVENTION_LOG.md` |
| Copilot no sigue las reglas | Incluye los `#file:` de los skills canónicos en tu mensaje de Copilot Chat |
| Antigravity no encuentra el skill | Verifica que `.agent/skills/requirements-workflow.md` existe; reinicia la sesión |
