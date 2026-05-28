-- 0007_audit_policy_y_auto_archive.sql
--
-- Refactor de strictness a policy JSONB por celda:
--
-- 1. Sustituye usuarios.audit_strictness (enum 3 valores) por
--    usuarios.audit_policy (JSONB con 6 keys), permitiendo configuración
--    fina por celda de la matriz (temporal_class × valor_archivistico).
-- 2. Añade recursos.auto_archive_pending — flag que el embedder lee al
--    terminar de vectorizar para transicionar a 'expirado' en vez de
--    'activo' (auto-archive de contenido pasado con valor alto sin
--    requerir triaje manual del usuario).
--
-- Backward-compat: rows existentes en usuarios se migran preservando la
-- intención del strictness anterior. Recursos sin migración previa
-- reciben auto_archive_pending=false (comportamiento idéntico).

BEGIN;

-- ----------------------------------------------------------------------
-- 1. usuarios.audit_policy JSONB (sustituto de audit_strictness)
-- ----------------------------------------------------------------------
-- Default: preset "Equilibrado" (alto → expirado, medio/nulo → cuarentena).
ALTER TABLE usuarios
    ADD COLUMN IF NOT EXISTS audit_policy JSONB NOT NULL DEFAULT
        '{
            "evento_pasado_alto": "expirado",
            "evento_pasado_medio": "cuarentena",
            "evento_pasado_nulo": "cuarentena",
            "referencia_pasada_alto": "expirado",
            "referencia_pasada_medio": "cuarentena",
            "referencia_pasada_nulo": "cuarentena"
        }'::jsonb;

-- Migrar valores existentes de audit_strictness al JSONB equivalente.
-- Estricto: todo a cuarentena. Equilibrado: ya es el default. Permisivo:
-- alto→expirado, referencia medio→activo, resto cuarentena.
--
-- Idempotente: el bloque DO solo ejecuta UPDATE+DROP si la columna
-- todavía existe (la migración puede haber sido aplicada manualmente
-- en preproducción antes de que el container `cerebro-migrate` la corra).
DO $migrate$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'usuarios'
          AND column_name = 'audit_strictness'
    ) THEN
        EXECUTE $update$
            UPDATE usuarios SET audit_policy = CASE audit_strictness
                WHEN 'estricto' THEN
                    '{
                        "evento_pasado_alto": "cuarentena",
                        "evento_pasado_medio": "cuarentena",
                        "evento_pasado_nulo": "cuarentena",
                        "referencia_pasada_alto": "cuarentena",
                        "referencia_pasada_medio": "cuarentena",
                        "referencia_pasada_nulo": "cuarentena"
                    }'::jsonb
                WHEN 'permisivo' THEN
                    '{
                        "evento_pasado_alto": "expirado",
                        "evento_pasado_medio": "cuarentena",
                        "evento_pasado_nulo": "cuarentena",
                        "referencia_pasada_alto": "expirado",
                        "referencia_pasada_medio": "activo",
                        "referencia_pasada_nulo": "cuarentena"
                    }'::jsonb
                ELSE  -- equilibrado o NULL: default ya aplicado
                    audit_policy
            END
            WHERE audit_strictness IS NOT NULL
        $update$;
        EXECUTE 'ALTER TABLE usuarios DROP COLUMN audit_strictness';
    END IF;
END
$migrate$;

-- ----------------------------------------------------------------------
-- 2. recursos.auto_archive_pending
-- ----------------------------------------------------------------------
-- Cuando true, el embedder transiciona a 'expirado' tras vectorizar
-- (en vez del default 'activo'). Permite que los chunks queden indexados
-- en Qdrant para el toggle Archivo ON en chat, pero el recurso aparezca
-- como "archivo histórico" en /expired (no en KB activo).
ALTER TABLE recursos
    ADD COLUMN IF NOT EXISTS auto_archive_pending BOOLEAN NOT NULL DEFAULT false;

COMMIT;
