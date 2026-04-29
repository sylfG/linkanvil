-- =============================================================================
-- LinkAnvil — PostgreSQL Schema Inicial
-- Patrón Outbox · Multi-Tenancy (RLS) · Curador Nocturno
-- =============================================================================

-- Extensiones necesarias (deben ir en public)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "unaccent";

-- -----------------------------------------------------------------------------
-- SCHEMAS
-- cerebro: tablas propias (aisladas de las migraciones Prisma de LiteLLM)
-- n8n:     tablas del workflow engine
-- -----------------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS cerebro;
CREATE SCHEMA IF NOT EXISTS n8n;

-- Mover todas las tablas propias al schema cerebro
SET search_path TO cerebro, public;

-- -----------------------------------------------------------------------------
-- TABLA PRINCIPAL: recursos capturados
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS recursos (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       VARCHAR(128) NOT NULL,
    url             TEXT NOT NULL,
    url_hash        CHAR(64) NOT NULL,              -- SHA-256 para deduplicación
    titulo          TEXT,
    resumen         TEXT,
    categoria       VARCHAR(100),
    tags            JSONB DEFAULT '[]',
    volatilidad     VARCHAR(20) DEFAULT 'media'     -- baja | media | alta | dinamica
                    CHECK (volatilidad IN ('baja', 'media', 'alta', 'dinamica')),
    fecha_caducidad DATE,
    estado          VARCHAR(20) DEFAULT 'activo'
                    CHECK (estado IN ('activo', 'cuarentena', 'expirado', 'procesando')),
    embedding_version INTEGER DEFAULT 1,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Índices para rendimiento
CREATE UNIQUE INDEX IF NOT EXISTS idx_recursos_hash ON recursos (tenant_id, url_hash);
CREATE INDEX IF NOT EXISTS idx_recursos_tenant ON recursos (tenant_id);
CREATE INDEX IF NOT EXISTS idx_recursos_estado ON recursos (estado, tenant_id);
CREATE INDEX IF NOT EXISTS idx_recursos_caducidad ON recursos (fecha_caducidad) WHERE estado = 'activo';
CREATE INDEX IF NOT EXISTS idx_recursos_tags ON recursos USING GIN (tags);

-- -----------------------------------------------------------------------------
-- OUTBOX PATTERN: tabla de eventos para consistencia eventual
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS outbox_eventos (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       VARCHAR(128) NOT NULL,
    agregado_tipo   VARCHAR(100) NOT NULL,           -- Tipo: 'recurso', 'sesion', etc.
    agregado_id     UUID NOT NULL,
    evento_tipo     VARCHAR(100) NOT NULL,           -- 'recurso.creado', 'embedding.requerido'
    payload         JSONB NOT NULL,
    procesado       BOOLEAN DEFAULT FALSE,
    reintentos      INTEGER DEFAULT 0,
    creado_en       TIMESTAMPTZ DEFAULT NOW(),
    procesado_en    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_outbox_no_procesados ON outbox_eventos (creado_en)
    WHERE procesado = FALSE;

-- -----------------------------------------------------------------------------
-- GRAFO SEMÁNTICO: aristas entre recursos relacionados
-- (Colisionadores Semánticos - similitud coseno > 0.92)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS grafo_relaciones (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       VARCHAR(128) NOT NULL,
    recurso_origen  UUID NOT NULL REFERENCES recursos(id) ON DELETE CASCADE,
    recurso_destino UUID NOT NULL REFERENCES recursos(id) ON DELETE CASCADE,
    similitud       FLOAT NOT NULL CHECK (similitud BETWEEN 0 AND 1),
    tipo_relacion   VARCHAR(50) DEFAULT 'semantica',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_relacion UNIQUE (recurso_origen, recurso_destino)
);

CREATE INDEX IF NOT EXISTS idx_grafo_origen ON grafo_relaciones (recurso_origen);
CREATE INDEX IF NOT EXISTS idx_grafo_similitud ON grafo_relaciones (similitud DESC)
    WHERE similitud > 0.92;

-- -----------------------------------------------------------------------------
-- SESIONES DE CHAT con soporte de Sliding Window
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sesiones_chat (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       VARCHAR(128) NOT NULL,
    plataforma      VARCHAR(30) NOT NULL DEFAULT 'web'
                    CHECK (plataforma IN ('web', 'telegram', 'api')),
    titulo          TEXT,
    contexto_comprimido TEXT,                        -- Sliding Window resume
    tokens_usados   INTEGER DEFAULT 0,
    ultimo_acceso   TIMESTAMPTZ DEFAULT NOW(),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sesiones_tenant ON sesiones_chat (tenant_id, ultimo_acceso DESC);

CREATE TABLE IF NOT EXISTS mensajes_chat (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    seq             BIGSERIAL NOT NULL,
    sesion_id       UUID NOT NULL REFERENCES sesiones_chat(id) ON DELETE CASCADE,
    tenant_id       VARCHAR(128) NOT NULL,
    rol             VARCHAR(20) NOT NULL CHECK (rol IN ('user', 'assistant', 'system')),
    contenido       TEXT NOT NULL,
    fuentes         JSONB NOT NULL DEFAULT '[]'::jsonb,
    embedding_id    VARCHAR(255),
    tokens_entrada  INTEGER DEFAULT 0,
    tokens_salida   INTEGER DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mensajes_sesion ON mensajes_chat (sesion_id, seq ASC);

-- -----------------------------------------------------------------------------
-- ROW-LEVEL SECURITY (Multi-Tenancy) 
-- Bloquea acceso cruzado entre tenants por defecto
-- -----------------------------------------------------------------------------
ALTER TABLE recursos ENABLE ROW LEVEL SECURITY;
ALTER TABLE sesiones_chat ENABLE ROW LEVEL SECURITY;
ALTER TABLE mensajes_chat ENABLE ROW LEVEL SECURITY;
ALTER TABLE grafo_relaciones ENABLE ROW LEVEL SECURITY;
ALTER TABLE outbox_eventos ENABLE ROW LEVEL SECURITY;

-- Política: cada usuario solo ve sus datos
DROP POLICY IF EXISTS tenant_isolation ON recursos;
CREATE POLICY tenant_isolation ON recursos
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

DROP POLICY IF EXISTS tenant_isolation ON sesiones_chat;
CREATE POLICY tenant_isolation ON sesiones_chat
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

DROP POLICY IF EXISTS tenant_isolation ON mensajes_chat;
CREATE POLICY tenant_isolation ON mensajes_chat
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

DROP POLICY IF EXISTS tenant_isolation ON grafo_relaciones;
CREATE POLICY tenant_isolation ON grafo_relaciones
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

DROP POLICY IF EXISTS tenant_isolation ON outbox_eventos;
CREATE POLICY tenant_isolation ON outbox_eventos
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

-- Cuenta de servicio (bypass RLS para workers internos)
DO $$ 
BEGIN 
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'cerebro_service') THEN 
        CREATE ROLE cerebro_service NOLOGIN BYPASSRLS; 
    END IF; 
END $$;
ALTER TABLE recursos FORCE ROW LEVEL SECURITY;
ALTER TABLE sesiones_chat FORCE ROW LEVEL SECURITY;
ALTER TABLE mensajes_chat FORCE ROW LEVEL SECURITY;
ALTER TABLE grafo_relaciones FORCE ROW LEVEL SECURITY;
ALTER TABLE outbox_eventos FORCE ROW LEVEL SECURITY;

-- -----------------------------------------------------------------------------
-- FUNCIÓN: actualizar updated_at automáticamente
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION trigger_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS set_updated_at_recursos ON recursos;
CREATE TRIGGER set_updated_at_recursos
    BEFORE UPDATE ON recursos
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

-- -----------------------------------------------------------------------------
-- FUNCIÓN: Curador Nocturno — marcar expirados
-- Llamada por n8n cron job diariamente
-- -----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION curador_marcar_expirados()
RETURNS INTEGER AS $$
DECLARE
    cnt INTEGER;
BEGIN
    UPDATE recursos
    SET estado = 'cuarentena'
    WHERE estado = 'activo'
      AND fecha_caducidad IS NOT NULL
      AND fecha_caducidad < NOW()::DATE;
    GET DIAGNOSTICS cnt = ROW_COUNT;
    RETURN cnt;
END;
$$ LANGUAGE plpgsql;

-- -----------------------------------------------------------------------------
-- TABLA: usuarios del sistema (auth multi-tenant)
-- Auth controlado en API layer (JWT). Sin RLS — cerebro es superuser.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS usuarios (
    id                      UUID        PRIMARY KEY DEFAULT uuid_generate_v4(),
    email                   TEXT        UNIQUE NOT NULL,
    password_hash           TEXT        NOT NULL,
    tenant_id               TEXT        UNIQUE NOT NULL
                            DEFAULT 'user_' || replace(uuid_generate_v4()::text, '-', ''),
    telegram_bot_token      TEXT,
    telegram_bot_token_hash TEXT,
    telegram_bot_active     BOOLEAN     DEFAULT FALSE,
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_usuarios_email ON usuarios (email);
CREATE INDEX IF NOT EXISTS idx_usuarios_token_hash ON usuarios (telegram_bot_token_hash)
    WHERE telegram_bot_token_hash IS NOT NULL;

DROP TRIGGER IF EXISTS set_updated_at_usuarios ON usuarios;
CREATE TRIGGER set_updated_at_usuarios
    BEFORE UPDATE ON usuarios
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

-- Datos de ejemplo para verificación
INSERT INTO recursos (tenant_id, url, url_hash, titulo, volatilidad, estado) VALUES
    ('tenant_demo', 'https://ejemplo.com/web3-intro', 
     md5('https://ejemplo.com/web3-intro'), 
     'Introducción a Web 3.0', 'dinamica', 'activo')
ON CONFLICT DO NOTHING;
