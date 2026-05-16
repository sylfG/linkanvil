-- =============================================================================
-- 0005_recursos_contenido.sql
-- Añade columna `contenido` para almacenar el texto limpio extraído por el
-- scraper. El RAG por chunks necesita el cuerpo completo (no solo el resumen)
-- para responder preguntas sobre datos específicos del documento.
-- =============================================================================

SET search_path TO cerebro, public;

ALTER TABLE recursos
    ADD COLUMN IF NOT EXISTS contenido TEXT;
