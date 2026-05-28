-- 0006_temporal_class_y_strictness.sql
--
-- Clasificación temporal de recursos + nivel de estricto por tenant.
-- Resuelve el gap del prompt §6 (artículos de eventos pasados como
-- Expojove 2024 / AEMET 2020 que el LLM clasificaba con caducidad
-- sintética futura).
--
-- Cambios:
-- 1. quarantine_reason acepta el motivo nuevo 'evento_pasado'.
-- 2. recursos.temporal_class — clasificación semántica del contenido.
-- 3. recursos.valor_archivistico — ¿merece guardarse como referencia?
-- 4. recursos.fecha_evento — fecha del evento descrito (puede ser pasada).
-- 5. usuarios.audit_strictness — qué hace el sistema con fechas pasadas
--    (estricto / equilibrado / permisivo).
--
-- Backward-compat: rows existentes reciben defaults que reproducen el
-- comportamiento actual (temporal_class='evento', valor='medio',
-- strictness='equilibrado').

BEGIN;

-- ----------------------------------------------------------------------
-- 1. Extender CHECK de quarantine_reason
-- ----------------------------------------------------------------------
ALTER TABLE recursos DROP CONSTRAINT IF EXISTS recursos_quarantine_reason_check;
ALTER TABLE recursos ADD CONSTRAINT recursos_quarantine_reason_check
    CHECK (
        quarantine_reason IS NULL OR
        quarantine_reason IN ('caducidad', 'colision_semantica', 'manual', 'evento_pasado')
    );

-- ----------------------------------------------------------------------
-- 2-4. Nuevas columnas en recursos
-- ----------------------------------------------------------------------
ALTER TABLE recursos
    ADD COLUMN IF NOT EXISTS temporal_class VARCHAR(20) NOT NULL DEFAULT 'evento'
        CHECK (temporal_class IN ('evento', 'referencia', 'evergreen')),
    ADD COLUMN IF NOT EXISTS valor_archivistico VARCHAR(20) NOT NULL DEFAULT 'medio'
        CHECK (valor_archivistico IN ('alto', 'medio', 'nulo')),
    ADD COLUMN IF NOT EXISTS fecha_evento DATE NULL;

-- Índice parcial: los queries que filtran por clase suelen buscar las
-- minorías (referencia / evergreen). Saltarse 'evento' acelera lookups.
CREATE INDEX IF NOT EXISTS idx_recursos_temporal_class
    ON recursos (temporal_class)
    WHERE temporal_class != 'evento';

-- ----------------------------------------------------------------------
-- 5. Strictness por tenant en usuarios
-- ----------------------------------------------------------------------
ALTER TABLE usuarios
    ADD COLUMN IF NOT EXISTS audit_strictness VARCHAR(20) NOT NULL DEFAULT 'equilibrado'
        CHECK (audit_strictness IN ('estricto', 'equilibrado', 'permisivo'));

COMMIT;
