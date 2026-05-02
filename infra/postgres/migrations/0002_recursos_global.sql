-- 0002_recursos_global.sql
--
-- Migración a modelo de recursos global con pivote per-tenant:
--   * `recursos` deja de tener `tenant_id` (deduplicado por `url_hash`).
--   * Nueva tabla `usuario_recursos(tenant_id, recurso_id)` con RLS.
--   * `grafo_relaciones` no cambia (las colisiones semánticas siguen per-tenant).
--
-- Pre-condición: las tablas afectadas se asumen vacías (acordado en plan).
-- Las sentencias son idempotentes vía IF EXISTS / IF NOT EXISTS / DROP+CREATE
-- para POLICY (Postgres < 17 no soporta IF NOT EXISTS en CREATE POLICY).

SET search_path TO cerebro, public;

-- ----------------------------------------------------------------------------
-- 1. Quitar RLS y tenant_id de `recursos`
-- ----------------------------------------------------------------------------
DROP POLICY IF EXISTS tenant_isolation ON recursos;
ALTER TABLE recursos DISABLE ROW LEVEL SECURITY;
ALTER TABLE recursos NO FORCE ROW LEVEL SECURITY;

DROP INDEX IF EXISTS idx_recursos_hash;
DROP INDEX IF EXISTS idx_recursos_tenant;
DROP INDEX IF EXISTS idx_recursos_estado;

ALTER TABLE recursos DROP COLUMN IF EXISTS tenant_id;

CREATE UNIQUE INDEX IF NOT EXISTS idx_recursos_url_hash ON recursos (url_hash);
CREATE INDEX IF NOT EXISTS idx_recursos_estado ON recursos (estado);

-- ----------------------------------------------------------------------------
-- 2. Nueva tabla pivote `usuario_recursos`
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS usuario_recursos (
    tenant_id    VARCHAR(128) NOT NULL,
    recurso_id   UUID NOT NULL REFERENCES recursos(id) ON DELETE CASCADE,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (tenant_id, recurso_id)
);

CREATE INDEX IF NOT EXISTS idx_usuario_recursos_tenant
    ON usuario_recursos (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_usuario_recursos_recurso
    ON usuario_recursos (recurso_id);

ALTER TABLE usuario_recursos ENABLE ROW LEVEL SECURITY;
ALTER TABLE usuario_recursos FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON usuario_recursos;
CREATE POLICY tenant_isolation ON usuario_recursos
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
