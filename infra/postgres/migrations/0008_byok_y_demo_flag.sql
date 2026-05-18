-- 0008_byok_y_demo_flag.sql
--
-- BYOK (Bring Your Own Key) per-tenant + flag de cuenta demo.
--
-- Hoy todos los tenants comparten una única LITELLM_KEY global, lo que
-- hace inviable un demo público (cualquiera consume el saldo del owner).
-- Esta migración añade 3 columnas para guardar las virtual keys de
-- LiteLLM cifradas con Fernet (lite/embeddings/pro) y un flag is_demo
-- para bloquear el endpoint PUT /profile/llm-keys en cuentas demo.
--
-- Las keys NO se guardan en plaintext (a diferencia de telegram_bot_token,
-- que es legacy y se migrará en una sesión paralela). El cifrado lo hace
-- src/api/crypto.py con la env-var LLM_KEYS_ENCRYPTION_KEY.
--
-- Backward-compat: rows existentes reciben is_demo=false y NULL en las
-- tres columnas de keys, llm_keys_configured=false. La primera request
-- a /ingest o /chat les devolverá 402 hasta que configuren BYOK.
-- Excepción: el tenant demo se marca is_demo=true por el UPDATE final.

BEGIN;

-- ----------------------------------------------------------------------
-- 1. Columnas BYOK (Fernet-encrypted) + estado agregado
-- ----------------------------------------------------------------------
ALTER TABLE usuarios
    ADD COLUMN IF NOT EXISTS llm_key_lite        TEXT,
    ADD COLUMN IF NOT EXISTS llm_key_embeddings  TEXT,
    ADD COLUMN IF NOT EXISTS llm_key_pro         TEXT,
    ADD COLUMN IF NOT EXISTS llm_keys_configured BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS is_demo             BOOLEAN NOT NULL DEFAULT false;

COMMENT ON COLUMN usuarios.llm_key_lite IS
    'Fernet ciphertext de la virtual-key LiteLLM para cerebro-lite.';
COMMENT ON COLUMN usuarios.llm_key_embeddings IS
    'Fernet ciphertext para cerebro-embeddings.';
COMMENT ON COLUMN usuarios.llm_key_pro IS
    'Fernet ciphertext para cerebro-pro.';
COMMENT ON COLUMN usuarios.llm_keys_configured IS
    'true si al menos una de las 3 keys está rellena. Permite chequear '
    'BYOK sin desencriptar (útil para guards rápidos).';
COMMENT ON COLUMN usuarios.is_demo IS
    'true para cuentas demo compartidas. Bloquea PUT /profile/llm-keys '
    'y activa cuotas diarias adicionales en /chat y /ingest.';

-- ----------------------------------------------------------------------
-- 2. Backfill: marca el tenant demo
-- ----------------------------------------------------------------------
-- Idempotente: si la cuenta demo aún no existe, el UPDATE no afecta
-- a 0 filas y la migración no falla. El seed (ops/seed_demo_user.py)
-- se encarga de crear el row y reaplicar is_demo=true vía ON CONFLICT.
UPDATE usuarios
   SET is_demo = true
 WHERE tenant_id = 'user_demo_landing'
   AND is_demo IS DISTINCT FROM true;

COMMIT;
