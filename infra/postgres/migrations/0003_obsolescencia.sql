-- 0003_obsolescencia.sql
--
-- Sistema de Obsolescencia — Bandeja de Cuarentena (F-05.1 + F-05.2).
--
-- Hasta ahora el estado `'cuarentena'` estaba declarado en el CHECK pero
-- ningún flujo Python lo usaba: tanto `audit_cron.py` como el colisionador
-- semántico saltaban directamente a `'expirado'`, lo cual era irrevocable
-- y desaparecía del RAG sin posibilidad de revisión.
--
-- Esta migración añade los metadatos necesarios para soportar un período
-- de gracia tras el cual el recurso se expira de verdad. La transición
-- pasa a ser:   activo → cuarentena → expirado.

SET search_path TO cerebro, public;

ALTER TABLE recursos
    ADD COLUMN IF NOT EXISTS quarantined_at         TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS quarantine_reason      VARCHAR(50),
    ADD COLUMN IF NOT EXISTS quarantine_grace_until DATE;

-- CHECK separado para poder añadirlo idempotentemente
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'recursos_quarantine_reason_check'
    ) THEN
        ALTER TABLE recursos
            ADD CONSTRAINT recursos_quarantine_reason_check
            CHECK (
                quarantine_reason IS NULL
                OR quarantine_reason IN ('caducidad', 'colision_semantica', 'manual')
            );
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_recursos_cuarentena_grace
    ON recursos (quarantine_grace_until)
    WHERE estado = 'cuarentena';

-- La función PL/pgSQL `curador_marcar_expirados()` quedaba inconsistente
-- con el flujo Python (apuntaba a 'cuarentena' pero nadie la llamaba) y
-- ahora la lógica vive entera en `src/data/audit_cron.py`. La eliminamos
-- para evitar dos fuentes de verdad.
DROP FUNCTION IF EXISTS curador_marcar_expirados();
