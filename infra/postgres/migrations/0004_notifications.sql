-- 0004_notifications.sql
--
-- Notificaciones in-app + Telegram para eventos del ciclo de obsolescencia.
--
-- El outbox ya emite `recurso.cuarentena` y `recurso.expirado`; faltaba el
-- consumidor que avise al usuario. Esta migración añade:
--   1. `usuarios.telegram_chat_id`: el chat al que enviar mensajes; se
--      captura en el webhook de Telegram cuando el usuario interactúa.
--   2. `notificaciones`: feed in-app por tenant para mostrar campana en UI.

SET search_path TO cerebro, public;

ALTER TABLE usuarios
    ADD COLUMN IF NOT EXISTS telegram_chat_id BIGINT;

CREATE TABLE IF NOT EXISTS notificaciones (
    id           UUID         PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id    VARCHAR(128) NOT NULL,
    evento_tipo  VARCHAR(100) NOT NULL,        -- recurso.cuarentena | recurso.expirado | ...
    recurso_id   UUID,
    titulo       TEXT,
    url          TEXT,
    motivo       VARCHAR(50),                  -- caducidad | colision_semantica | manual | gracia_agotada
    leido        BOOLEAN      DEFAULT FALSE,
    leido_en     TIMESTAMPTZ,
    created_at   TIMESTAMPTZ  DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_notificaciones_tenant_unread
    ON notificaciones (tenant_id, created_at DESC)
    WHERE leido = FALSE;

CREATE INDEX IF NOT EXISTS idx_notificaciones_tenant_recent
    ON notificaciones (tenant_id, created_at DESC);
