-- =============================================================================
-- Segundo Cerebro Autónomo — PostgreSQL Schema Inicial
-- Patrón Outbox · Multi-Tenancy (RLS) · Curador Nocturno
-- =============================================================================

-- Extensiones necesarias
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";       -- Búsqueda por similaridad de texto
CREATE EXTENSION IF NOT EXISTS "unaccent";        -- Normalización de caracteres

-- -----------------------------------------------------------------------------
-- SCHEMA n8n (para n8n workflow engine)
-- -----------------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS n8n;

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
    sesion_id       UUID NOT NULL REFERENCES sesiones_chat(id) ON DELETE CASCADE,
    tenant_id       VARCHAR(128) NOT NULL,
    rol             VARCHAR(20) NOT NULL CHECK (rol IN ('user', 'assistant', 'system')),
    contenido       TEXT NOT NULL,
    embedding_id    VARCHAR(255),                    -- ID del vector en Qdrant
    tokens_entrada  INTEGER DEFAULT 0,
    tokens_salida   INTEGER DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mensajes_sesion ON mensajes_chat (sesion_id, created_at DESC);

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
CREATE POLICY tenant_isolation ON recursos
    USING (tenant_id = current_setting('app.tenant_id', true));

CREATE POLICY tenant_isolation ON sesiones_chat
    USING (tenant_id = current_setting('app.tenant_id', true));

CREATE POLICY tenant_isolation ON mensajes_chat
    USING (tenant_id = current_setting('app.tenant_id', true));

-- Cuenta de servicio (bypass RLS para workers internos)
CREATE ROLE cerebro_service NOLOGIN;
ALTER TABLE recursos FORCE ROW LEVEL SECURITY;

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

-- Datos de ejemplo para verificación
INSERT INTO recursos (tenant_id, url, url_hash, titulo, volatilidad, estado) VALUES
    ('tenant_demo', 'https://ejemplo.com/web3-intro', 
     md5('https://ejemplo.com/web3-intro'), 
     'Introducción a Web 3.0', 'dinamica', 'activo')
ON CONFLICT DO NOTHING;
