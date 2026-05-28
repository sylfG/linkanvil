-- 0009_demo_sessions.sql
--
-- Sesiones efímeras del demo (sub-tenants con TTL de 15 min).
--
-- Hasta aquí el demo era un único tenant compartido (user_demo_landing):
-- todos los visitantes veían/ingestaban en el mismo namespace, y un
-- eventual reset cron echaba a todos a la vez. Esto cambia la arquitectura
-- para que CADA visitante reciba un sub-tenant aislado:
--
--   tenant_id = "demo_<8hex>"    ej. "demo_a3b9f1c4"
--
-- El sub-tenant tiene TTL fijo de 15 min desde el login. Un cleanup
-- task (cada 60s desde cerebro-api) detecta los expirados y borra:
--
--   1. cerebro.demo_sessions row
--   2. cerebro.usuario_recursos rows asociados al sub-tenant
--   3. cerebro.recursos huérfanos (sin ningún tenant tras el delete)
--   4. cerebro.chat_sessions + chat_messages del sub-tenant
--   5. cerebro.notificaciones del sub-tenant
--   6. Qdrant points en cerebro_chunks y cerebro_recursos filtrados por
--      payload.tenant_id (lo hace el cleanup task en código, no aquí)
--
-- El seed de 18 recursos sigue en user_demo_landing y nunca se borra.
-- El RAG/KB de los sub-tenants hace UNION ALL con user_demo_landing
-- para verlos. La ingesta nueva del demo va SOLO al sub-tenant.

BEGIN;

CREATE TABLE IF NOT EXISTS cerebro.demo_sessions (
    tenant_id   TEXT PRIMARY KEY,
    user_id     UUID NOT NULL REFERENCES cerebro.usuarios(id) ON DELETE CASCADE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at  TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ip          TEXT
);

-- Cleanup task escanea por expires_at < NOW().
CREATE INDEX IF NOT EXISTS idx_demo_sessions_expires
    ON cerebro.demo_sessions(expires_at);

-- Útil para limitar sesiones simultáneas por user_id si fuera necesario
-- en el futuro (no implementado todavía).
CREATE INDEX IF NOT EXISTS idx_demo_sessions_user
    ON cerebro.demo_sessions(user_id);

COMMENT ON TABLE cerebro.demo_sessions IS
    'Sub-tenants efímeros del demo (TTL 15min). Cada login del demo crea '
    'uno; un cleanup task los borra al expirar junto con sus recursos.';

COMMIT;
