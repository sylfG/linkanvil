# Requirements Engineering Workspace — GitHub Copilot

Este workspace convierte contexto de negocio bruto en backlog estructurado, arquitectura documentada e Issues de GitHub.

## Cómo cargar el contexto completo

Antes de ejecutar cualquier fase, incluye los archivos canónicos en tu contexto de Copilot Chat:

```
#file:docs/workflow/rules.md
#file:docs/workflow/pipeline.md
#file:docs/skills/business-analyst.md
#file:docs/skills/system-architect.md
#file:docs/skills/change-manager.md
```

**Atajo recomendado para iniciar:**
```
@workspace /iniciar-requisitos
#file:docs/src/0_descripcion_proyecto.md
#file:docs/workflow/pipeline.md
#file:docs/skills/business-analyst.md
#file:docs/skills/system-architect.md
```

**Atajo para revisar cambios:**
```
@workspace /revisar-cambios
#file:docs/src/0_cambios_requisitos.md
#file:docs/workflow/pipeline.md
#file:docs/skills/change-manager.md
#file:docs/skills/business-analyst.md
```

## Comandos disponibles

| Comando | Fase | Descripción |
|---------|------|-------------|
| `/iniciar-requisitos` | Fase 1 | Descubrimiento y desglose de Epics y Features |
| `/revisar-cambios` | Fase 7 | Análisis de impacto y revisión del backlog existente |

Las fases 2-6 se activan por aprobación explícita en chat.

## Reglas esenciales

1. **No generar código fuente de aplicación.**
2. **Escribir los entregables directamente en disco** usando herramientas del workspace.
3. **Modo archivo-primero:** leer `docs/src/0_descripcion_proyecto.md` antes de preguntar nada.
4. **Antirreincidencia:** revisar `docs/src/ERROR_PREVENTION_LOG.md` antes de cada fase.
5. **Auditoría:** actualizar `docs/src/AUDIT_LOG.md` al finalizar cada fase.

Para el detalle completo de cada regla y cada fase, ver los archivos canónicos referenciados arriba.

## Archivos de contexto del proyecto

- Documento maestro: `docs/src/0_descripcion_proyecto.md`
- Registro de cambios: `docs/src/0_cambios_requisitos.md`
- Backlog generado: `docs/src/backlog/`
- Plantillas: `docs/templates/`
- Auditoría: `docs/src/AUDIT_LOG.md`
