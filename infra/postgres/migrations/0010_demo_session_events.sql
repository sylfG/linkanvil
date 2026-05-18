-- 0010_demo_session_events.sql
--
-- Eventos programados intra-sesión del demo (Slice 6).
--
-- Cada login del demo (vía POST /auth/demo-start) crea su sub-tenant
-- efímero + stagea 3 recursos sintéticos + programa 4 eventos en esta
-- tabla. El cleanup loop existente (cada 60s) procesa los eventos
-- con fires_at <= NOW() y dispara la transición correspondiente
-- (activo → cuarentena, activo → expirado, o un recordatorio pasivo).
--
-- Por qué una tabla y no leer fecha_caducidad: la columna
-- recursos.fecha_caducidad es DATE (precisión 1 día). Para programar
-- eventos a los 5min del login necesitamos TIMESTAMPTZ. Esta tabla
-- materializa esa precisión sin romper el schema base de recursos.
--
-- FK CASCADE a demo_sessions: cuando una sesión se borra (al expirar),
-- sus eventos asociados desaparecen automáticamente.

BEGIN;

CREATE TABLE IF NOT EXISTS cerebro.demo_session_events (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id   TEXT NOT NULL REFERENCES cerebro.demo_sessions(tenant_id)
                ON DELETE CASCADE,
    fires_at    TIMESTAMPTZ NOT NULL,
    fired_at    TIMESTAMPTZ,
    kind        VARCHAR(50) NOT NULL,
    recurso_id  UUID,
    motivo      VARCHAR(50),
    description TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON COLUMN cerebro.demo_session_events.kind IS
    'transition_cuarentena | transition_expirado | reminder_expiry_5min';
COMMENT ON COLUMN cerebro.demo_session_events.motivo IS
    'caducidad | auto_archive | gracia_agotada | NULL (para reminders)';

-- El cleanup loop escanea por eventos pending (fires_at vencido +
-- fired_at NULL). Índice parcial para que el scan sea barato.
CREATE INDEX IF NOT EXISTS idx_demo_events_due
    ON cerebro.demo_session_events(fires_at)
    WHERE fired_at IS NULL;

-- Consulta frecuente del frontend: "dame todos los eventos de esta
-- sesión en orden cronológico" para pintar la timeline + tabla.
CREATE INDEX IF NOT EXISTS idx_demo_events_tenant_chrono
    ON cerebro.demo_session_events(tenant_id, fires_at);

COMMIT;
