# Requirements Engineering Workflow

Activa el pipeline completo de ingeniería de requisitos de este workspace.

## Cuándo usar este skill

Usa `@requirements-workflow` cuando quieras:

- Iniciar un proceso de extracción de requisitos (`/iniciar-requisitos`)
- Revisar y propagar cambios sobre el backlog existente (`/revisar-cambios`)
- Generar o actualizar backlogs, arquitectura o diagramas del proyecto

## Instrucciones

Lee y aplica los siguientes documentos canónicos del workspace en este orden:

1. `docs/workflow/rules.md` — Reglas globales (sin código de app, archivo-primero, auditoría)
2. `docs/workflow/pipeline.md` — Fases 1-7 y sus triggers
3. `docs/skills/business-analyst.md` — Skill para Fases 1, 3 y 7
4. `docs/skills/system-architect.md` — Skill para Fases 2 y 4
5. `docs/skills/change-manager.md` — Skill para Fase 7 (gestión de cambios)

## Archivos clave del workspace

| Archivo | Propósito |
|---------|-----------|
| `docs/src/0_descripcion_proyecto.md` | Contexto maestro — rellenar antes de iniciar |
| `docs/src/0_cambios_requisitos.md` | Registro de cambios y nuevos requisitos |
| `docs/src/backlog/` | Features generadas (`F-XX.Y_nombre.md`) |
| `docs/templates/feature-backlog.md` | Plantilla canónica de backlog |
| `docs/templates/change-request.md` | Plantilla canónica de change request |
| `docs/src/AUDIT_LOG.md` | Auditoría de fases completadas |
| `docs/src/ERROR_PREVENTION_LOG.md` | Lecciones aprendidas y reglas preventivas |

## Comandos disponibles

| Comando | Fase | Descripción |
|---------|------|-------------|
| `/iniciar-requisitos` | Fase 1 | Descubrimiento: Epics y Features desde contexto bruto |
| `/revisar-cambios` | Fase 7 | Análisis de impacto y revisión del backlog existente |

Las fases 2-6 se activan por aprobación explícita en chat.

## Restricciones

- No generar código fuente de aplicación.
- Escribir entregables directamente en disco, no en el chat.
- Leer siempre `0_descripcion_proyecto.md` antes de preguntar nada al usuario.
