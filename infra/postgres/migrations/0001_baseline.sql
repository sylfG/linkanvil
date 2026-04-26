-- 0001_baseline.sql
--
-- Mirrors the current init.sql so that an existing deployment whose
-- volume was bootstrapped from init.sql is recorded as already at this
-- baseline. All statements use IF NOT EXISTS / IF EXISTS so re-running
-- on an already-initialised database is a no-op.
--
-- For NEW databases this migration is harmless duplication: init.sql
-- already created everything, so every CREATE here is skipped.
--
-- Subsequent migrations (0002, 0003, ...) carry actual deltas.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "unaccent";

CREATE SCHEMA IF NOT EXISTS cerebro;

SET search_path TO cerebro, public;

CREATE TABLE IF NOT EXISTS recursos (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       VARCHAR(128) NOT NULL,
    url             TEXT NOT NULL,
    url_hash        CHAR(64) NOT NULL,
    titulo          TEXT,
    resumen         TEXT,
    categoria       VARCHAR(100),
    tags            JSONB DEFAULT '[]',
    volatilidad     VARCHAR(20) DEFAULT 'media'
                    CHECK (volatilidad IN ('baja', 'media', 'alta', 'dinamica')),
    fecha_caducidad DATE,
    estado          VARCHAR(20) DEFAULT 'activo'
                    CHECK (estado IN ('activo', 'cuarentena', 'expirado', 'procesando')),
    embedding_version INTEGER DEFAULT 1,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_recursos_hash ON recursos (tenant_id, url_hash);

CREATE TABLE IF NOT EXISTS sesiones_chat (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       VARCHAR(128) NOT NULL,
    plataforma      VARCHAR(30) NOT NULL DEFAULT 'web'
                    CHECK (plataforma IN ('web', 'telegram', 'api')),
    titulo          TEXT,
    contexto_comprimido TEXT,
    tokens_usados   INTEGER DEFAULT 0,
    ultimo_acceso   TIMESTAMPTZ DEFAULT NOW(),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

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
