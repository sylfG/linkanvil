# Plantilla: Feature Backlog

> Esta plantilla es la fuente canónica para generar archivos de backlog en `docs/src/backlog/`.
> Cada Feature ocupa un archivo `.md` independiente con nombre `F-XX.Y_titulo-corto.md`.

---

# [CATEGORÍA] F-XX.Y — Título Corto

*(Ej: `# [UI / PRESENTATION] F-01.1 — Cards de Resumen por Tipo de Error`)*

**Épica:** EPIC-XX — Nombre de la Épica

## 🏷️ Categoría

**Categoría:** `<etiqueta de la tabla de 9 categorías>`
**Secundaria:** `<segunda etiqueta>`  ← eliminar esta línea si no aplica
**Impacta en:** `<equipo responsable>`

## 📦 Dependencias

> Backlogs que deben estar **completados** antes de implementar esta feature.

| Backlog | Motivo | Bloqueante |
| --- | --- | --- |
| [F-XX.Y](F-XX.Y_nombre.md) | Razón técnica concreta (qué provee exactamente) | Sí |

*(Si es punto de inicio, reemplazar la tabla por:)*
> **Punto de inicio** — no tiene dependencias previas. Debe completarse antes que cualquier otro backlog.

**Prioridad:** `Must | Should | Could`
**Sprint:** Sprint N

---

**Descripción:**
Como [Actor/Persona]
Quiero [Acción/Capacidad]
Para [Beneficio/Valor de Negocio]

**Criterios de Aceptación (Checklist):**

- [ ] **Escenario 1 (Happy Path):**
  **Dado que** [contexto],
  **Cuando** [acción del usuario o sistema],
  **Entonces** [resultado observable].

- [ ] **Escenario 2 (Edge Case):**
  **Dado que** [contexto inusual],
  **Cuando** [acción],
  **Entonces** [mitigación o mensaje de error].

- [ ] **Requisito Técnico:**
  [Especificación no funcional: performance, seguridad, accesibilidad. Sin código.]

---

**MoSCoW:** `Must | Should | Could`
**Sprint:** Sprint N

**Notas:**

- Notas adicionales de implementación, decisiones de diseño, advertencias técnicas.
- Las decisiones de implementación van aquí, nunca en los criterios de aceptación.
