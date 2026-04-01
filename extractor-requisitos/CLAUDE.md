# Requirements Engineering Workspace — Claude Code

Este workspace convierte contexto de negocio bruto en backlog estructurado, arquitectura documentada e Issues de GitHub.

## Documentación canónica

Lee estos archivos antes de actuar. Son la fuente única de verdad:

@docs/workflow/rules.md
@docs/workflow/pipeline.md
@docs/skills/business-analyst.md
@docs/skills/system-architect.md
@docs/skills/change-manager.md

## Comandos disponibles

| Comando | Fase | Descripción |
|---------|------|-------------|
| `/iniciar-requisitos` | Fase 1 | Descubrimiento y desglose de Epics y Features |
| `/revisar-cambios` | Fase 7 | Análisis de impacto y revisión del backlog existente |

Las fases 2-6 se activan por aprobación explícita en chat, no por comando.

## Contexto del proyecto

- Documento maestro: `docs/src/0_descripcion_proyecto.md`
- Registro de cambios: `docs/src/0_cambios_requisitos.md`
- Backlog generado: `docs/src/backlog/`
- Auditoría: `docs/src/AUDIT_LOG.md`
- Errores y lecciones: `docs/src/ERROR_PREVENTION_LOG.md`

## Herramientas MCP activas

Este workspace tiene configurados los siguientes servidores MCP (ver `.claude/settings.local.json`):
`memory`, `filesystem`, `git`, `github`, `brave-search`, `web-reader`, `project-manager`, `docker`, `n8n`

Úsalos para escribir archivos en disco directamente — no devuelvas entregables en el chat.
