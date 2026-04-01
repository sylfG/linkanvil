# Requirements Engineering Workflow

Activa el pipeline completo de ingeniería de requisitos del workspace.
**Herramienta:** Claude Code — invocación: `/requirements-workflow`

## Cuándo usar este skill

- Al iniciar un proyecto nuevo de extracción de requisitos.
- Al ejecutar `/iniciar-requisitos` o `/revisar-cambios`.
- Cuando el usuario quiera generar, revisar o actualizar backlog de producto.

## Instrucciones

Lee y aplica los siguientes documentos canónicos del workspace en este orden:

1. `docs/workflow/rules.md` — Reglas globales (sin código, archivo-primero, auditoría).
2. `docs/workflow/pipeline.md` — Fases 1-7 y sus triggers.
3. `docs/skills/business-analyst.md` — Skill para Fases 1, 3 y 7 (parcial).
4. `docs/skills/system-architect.md` — Skill para Fases 2 y 4.
5. `docs/skills/change-manager.md` — Skill para Fase 7.

## Archivos clave del workspace

| Archivo | Propósito |
|---------|-----------|
| `docs/src/0_descripcion_proyecto.md` | Contexto maestro del proyecto (rellenar antes de iniciar) |
| `docs/src/0_cambios_requisitos.md` | Registro de cambios y nuevos requisitos |
| `docs/src/backlog/` | Archivos de Feature generados (F-XX.Y_nombre.md) |
| `docs/templates/feature-backlog.md` | Plantilla canónica de backlog |
| `docs/templates/change-request.md` | Plantilla canónica de cambio |
| `docs/src/AUDIT_LOG.md` | Auditoría de fases completadas |
| `docs/src/ERROR_PREVENTION_LOG.md` | Lecciones aprendidas y reglas preventivas |

## Comandos

- `/iniciar-requisitos` → Fase 1: Descubrimiento y desglose
- `/revisar-cambios` → Fase 7: Análisis de impacto sobre backlog existente

## Restricciones

- No generar código fuente de aplicación.
- Escribir entregables en disco, no en el chat.
- Siempre leer `0_descripcion_proyecto.md` antes de preguntar.
