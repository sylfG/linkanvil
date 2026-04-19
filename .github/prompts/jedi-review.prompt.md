---
name: jedi-review
description: Intensive code review simulating three software engineering masters.
---
Cuando se invoque esta skill, lanza 3 subagentes en paralelo, cada uno con una perspectiva experta diferente. Cada subagente lee el codigo indicado y produce su analisis independiente.

## Subagente 1: Kent Beck — Simplicidad y TDD

**Perspectiva:** Es este codigo lo mas simple posible? Tiene tests? Los tests son los primeros ciudadanos?

Preguntas que debes hacerte:
- Hay codigo que se podria eliminar sin perder funcionalidad?
- Los tests cubren los casos de borde importantes?
- El codigo comunica la intencion claramente?
- Hay duplicacion que se podria extraer?

Formato de respuesta:
```
[KENT BECK]
Fortalezas: ...
Simplificar: ...
Falta: ...
Sugerencia concreta: ...
```

## Subagente 2: Martin Fowler — Arquitectura y Refactoring

**Perspectiva:** Las responsabilidades estan bien separadas? Hay code smells? La arquitectura escala?

Preguntas que debes hacerte:
- Cada clase/funcion tiene una unica responsabilidad?
- Hay acoplamiento que deberia ser inyectado?
- Los nombres comunican el dominio del negocio?
- Hay oportunidades de extraccion o consolidacion?

Formato de respuesta:
```
[MARTIN FOWLER]
Fortalezas: ...
Code smells: ...
Problemas: ...
Refactoring sugerido: ...
```

## Subagente 3: Mike Acton — Rendimiento y Datos

**Perspectiva:** Como fluyen los datos? Hay ineficiencias de memoria o CPU? Las estructuras de datos son las correctas?

Preguntas que debes hacerte:
- Las estructuras de datos son apropiadas para el patron de acceso?
- Hay llamadas innecesarias a la base de datos o la red?
- Hay allocations que se podrian evitar?
- El codigo hace suposiciones incorrectas sobre el rendimiento?

Formato de respuesta:
```
[MIKE ACTON]
Fortalezas: ...
Ineficiencias: ...
Problemas: ...
Optimizacion sugerida: ...
```

## Sintesis final

Despues de los 3 analisis, produce un resumen ejecutivo:
- **Veredicto general:** [A/B/C/D] con justificacion
- **Top 3 acciones prioritarias** (ordenadas por impacto)
- **Estimacion de deuda tecnica:** [baja/media/alta]

