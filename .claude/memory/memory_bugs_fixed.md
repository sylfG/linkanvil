---
name: bugs-fixed-2026-05-16
description: Dos bugs críticos encontrados y resueltos el 2026-05-16 durante la re-ingesta con RAG chunking
type: project
---

Dos bugs críticos corregidos en la sesión de re-ingesta del 2026-05-16, ambos comiteados como `6d15580` en develop y main.

## Bug 1 — Chunker rompía con texto web (sin párrafos dobles)

**Síntoma**: `_chunk_text()` producía chunks de 0 bytes cuando el texto extraído por el scraper no tenía `\n\n` (separadores de párrafo doble).

**Causa**: Usaba `re.split(r"\n{2,}", text)` — el texto HTML limpiado por `_html_to_clean_text` usa saltos simples `\n`.

**Fix en `src/data/embedder_worker.py`**:
- `re.split(r"\n{2,}", text)` → `re.split(r"\n+", text)`
- `target_chars=1600` → `target_chars=1200` (para respetar el límite de 512 tokens del modelo NVIDIA)

**Why:** El modelo `nv-embedqa-e5-v5` tiene límite duro de 512 tokens ≈ 1200-1300 chars en texto español/inglés mixto. 1600 chars superaba ese límite silenciosamente.

**How to apply:** Nunca aumentar `target_chars` por encima de 1200 sin cambiar el modelo de embedding.

---

## Bug 2 — Violación de constraint en grafo_relaciones.similitud_check

**Síntoma**: `asyncpg.exceptions.CheckViolationError: grafo_relaciones_similitud_check` al guardar colisiones semánticas.

**Causa**: La similitud coseno puede retornar valores ligeramente superiores a 1.0 (ej: `1.0000002`) por precisión de punto flotante. La tabla tiene `CHECK (similitud BETWEEN 0 AND 1)`.

**Fix en `src/data/db.py`, función `save_semantic_collisions()`**:
- En dos INSERTs (forward y inverse): `c["similitud"]` → `min(c["similitud"], 1.0)`

**Why:** Invariante matemático: la similitud coseno no puede ser > 1, pero la aritmética de float sí puede producirlo. El clamp es la solución canónica.

**How to apply:** Toda vez que se inserte un valor de similitud coseno en `grafo_relaciones`, aplicar `min(value, 1.0)` antes del INSERT.
