-- 0012_estado_per_tenant.sql
--
-- Refactor multi-tenant: mover la decisión de auditoría (estado +
-- columnas asociadas) de `recursos` (global por url_hash) a
-- `usuario_recursos` (per-tenant). Cierra issue #123.
--
-- Antes: dos tenants linkeados al mismo recurso compartían `estado`,
-- de modo que la última policy aplicada sobre la URL afectaba al
-- resto. La policy es per-usuario pero el estado calculado se
-- almacenaba global → contaminación cruzada.
--
-- Tras esta migración:
--   - `recursos` solo guarda metadata intrínseca del contenido
--     (título, resumen, contenido, temporal_class, valor_archivistico,
--     fecha_evento, useful_life_days, embedding_version).
--   - `usuario_recursos` guarda la decisión de auditoría per-tenant
--     (estado, quarantine_*, auto_archive_pending, fecha_caducidad).
--
-- Idempotente: todas las operaciones son ADD COLUMN IF NOT EXISTS,
-- CREATE INDEX IF NOT EXISTS, DROP COLUMN IF EXISTS. El backfill
-- solo se ejecuta si las viejas columnas todavía existen.

BEGIN;

SET search_path TO cerebro, public;

-- ----------------------------------------------------------------------
-- 1. Añadir columnas decisión-per-tenant a usuario_recursos
-- ----------------------------------------------------------------------
-- estado: replica del CHECK constraint de recursos.estado.
-- DEFAULT 'procesando' coincide con el comportamiento previo (recurso
-- nuevo entra en 'procesando' hasta que el embedder lo transiciona).
ALTER TABLE usuario_recursos
    ADD COLUMN IF NOT EXISTS estado VARCHAR(20) NOT NULL DEFAULT 'procesando'
        CHECK (estado IN ('activo', 'cuarentena', 'expirado', 'procesando')),
    ADD COLUMN IF NOT EXISTS quarantine_reason VARCHAR(50),
    ADD COLUMN IF NOT EXISTS quarantine_grace_until DATE,
    ADD COLUMN IF NOT EXISTS quarantined_at TIMESTAMP WITH TIME ZONE,
    ADD COLUMN IF NOT EXISTS auto_archive_pending BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS fecha_caducidad DATE,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();

-- Reaplicar el CHECK constraint de quarantine_reason en usuario_recursos.
-- Idempotente: si ya existe, lo recreamos solo si no contempla
-- 'evento_pasado' (mismo CHECK que recursos.quarantine_reason en 0006).
DO $reason_check$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname = 'usuario_recursos_quarantine_reason_check'
    ) THEN
        ALTER TABLE usuario_recursos
            ADD CONSTRAINT usuario_recursos_quarantine_reason_check
            CHECK (
                quarantine_reason IS NULL OR
                quarantine_reason IN (
                    'caducidad', 'colision_semantica', 'manual', 'evento_pasado'
                )
            );
    END IF;
END
$reason_check$;

-- ----------------------------------------------------------------------
-- 2. Añadir useful_life_days a recursos (necesaria para el fast-path
--    en scraper/worker.py: poder calcular fecha_caducidad para un
--    nuevo tenant sin re-invocar al LLM)
-- ----------------------------------------------------------------------
ALTER TABLE recursos
    ADD COLUMN IF NOT EXISTS useful_life_days INTEGER;

-- ----------------------------------------------------------------------
-- 3. Backfill desde recursos hacia usuario_recursos (solo si las
--    columnas viejas existen en recursos — primer apply)
-- ----------------------------------------------------------------------
DO $backfill$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_schema = current_schema()
           AND table_name = 'recursos'
           AND column_name = 'estado'
    ) THEN
        EXECUTE $copy$
            UPDATE usuario_recursos ur
               SET estado                 = r.estado,
                   quarantine_reason      = r.quarantine_reason,
                   quarantine_grace_until = r.quarantine_grace_until,
                   quarantined_at         = r.quarantined_at,
                   auto_archive_pending   = r.auto_archive_pending,
                   fecha_caducidad        = r.fecha_caducidad,
                   updated_at             = COALESCE(r.updated_at, NOW())
              FROM recursos r
             WHERE r.id = ur.recurso_id
        $copy$;

        -- Backfill useful_life_days en recursos para entradas existentes:
        -- aproximación a partir de fecha_caducidad - created_at, con cap
        -- razonable. Para entradas sin fecha_caducidad queda NULL (el
        -- scraper lo recalculará al re-procesar o usar un default).
        EXECUTE $life$
            UPDATE recursos
               SET useful_life_days = GREATEST(
                       LEAST(
                           (fecha_caducidad - created_at::DATE),
                           365
                       ),
                       1
                   )
             WHERE fecha_caducidad IS NOT NULL
               AND useful_life_days IS NULL
        $life$;
    END IF;
END
$backfill$;

-- ----------------------------------------------------------------------
-- 4. Índices nuevos en usuario_recursos
-- ----------------------------------------------------------------------
-- Reemplazo de idx_recursos_estado: las queries de listing filtran
-- ahora por (tenant_id, estado).
CREATE INDEX IF NOT EXISTS idx_usuario_recursos_estado
    ON usuario_recursos (tenant_id, estado);

-- Reemplazo de idx_recursos_caducidad: audit_cron filtra por
-- (estado='activo', fecha_caducidad).
CREATE INDEX IF NOT EXISTS idx_usuario_recursos_caducidad
    ON usuario_recursos (fecha_caducidad)
    WHERE estado = 'activo';

-- Reemplazo de idx_recursos_cuarentena_grace: audit_cron filtra por
-- (estado='cuarentena', quarantine_grace_until).
CREATE INDEX IF NOT EXISTS idx_usuario_recursos_cuarentena_grace
    ON usuario_recursos (quarantine_grace_until)
    WHERE estado = 'cuarentena';

-- ----------------------------------------------------------------------
-- 5. DROP columnas viejas en recursos
-- ----------------------------------------------------------------------
-- Las viejas restricciones CHECK y los índices que dependían de ellas
-- caen automáticamente al borrar la columna (ON DELETE CASCADE en
-- pg_attribute → pg_constraint → pg_index).
ALTER TABLE recursos
    DROP COLUMN IF EXISTS estado,
    DROP COLUMN IF EXISTS quarantine_reason,
    DROP COLUMN IF EXISTS quarantine_grace_until,
    DROP COLUMN IF EXISTS quarantined_at,
    DROP COLUMN IF EXISTS auto_archive_pending,
    DROP COLUMN IF EXISTS fecha_caducidad;

-- Limpieza explícita por si quedaron índices huérfanos (DROP COLUMN
-- los borra normalmente, pero defensivo en caso de aplicar manual).
DROP INDEX IF EXISTS cerebro.idx_recursos_estado;
DROP INDEX IF EXISTS cerebro.idx_recursos_caducidad;
DROP INDEX IF EXISTS cerebro.idx_recursos_cuarentena_grace;

COMMIT;
