"""Bootstrap idempotente de las virtual-keys del demo (LiteLLM BYOK).

Se ejecuta una sola vez como servicio one-shot en docker-compose tras
LiteLLM y postgres-migrate. Genera una virtual-key contra el proxy
LiteLLM con permiso sobre los 3 model groups (cerebro-lite,
cerebro-embeddings, cerebro-pro), la cifra con Fernet y la persiste
en ``usuarios.llm_key_*`` para el demo.

Idempotencia
------------
- Si el demo ya tiene una key cifrada que NO es la master key, no hace
  nada (exit 0).
- Si tiene la master key (fallback histórico) o no tiene ninguna, regenera.

Por qué este servicio y no seed_demo_user
-----------------------------------------
seed_demo_user.py espera DEMO_KEY_* en env-vars (configurado a mano).
Este script *genera* esas keys a partir de la master key de LiteLLM,
cerrando el último paso manual del onboarding del demo. seed_demo_user
sigue siendo responsable de los recursos sembrados; este script solo
toca las llm_keys.

Variables requeridas
--------------------
- DATABASE_URL: postgres del cerebro
- LITELLM_URL: e.g. http://litellm:4000
- LITELLM_MASTER_KEY: admin token del proxy
- LLM_KEYS_ENCRYPTION_KEY: Fernet key (compartida con cerebro-api)
- DEMO_EMAIL: opcional, default 'demo@cerebro.local'
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import urllib.error
import urllib.request
from typing import Any
from uuid import UUID

import asyncpg

# El módulo crypto vive en src/api/. En el contenedor cerebro-api,
# /app/src está en PYTHONPATH; añadimos manualmente para corridas locales.
sys.path.insert(0, "/app/src")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from api.crypto import encrypt_llm_key, decrypt_llm_key  # noqa: E402
from cryptography.fernet import InvalidToken  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [bootstrap_demo_keys] %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

LITELLM_URL = os.environ.get("LITELLM_URL", "http://litellm:4000").rstrip("/")
LITELLM_MASTER_KEY = os.environ["LITELLM_MASTER_KEY"]
DEMO_EMAIL = os.environ.get("DEMO_EMAIL", "demo@cerebro.local")

# Aliases que la key debe cubrir — coinciden con infra/litellm/config.yaml
MODEL_ALIASES = ["cerebro-lite", "cerebro-embeddings", "cerebro-pro"]


def _http_request(
    method: str, path: str, payload: dict[str, Any] | None = None
) -> tuple[int, dict[str, Any]]:
    """POST/GET sencillo contra el proxy LiteLLM."""
    body = json.dumps(payload).encode("utf-8") if payload else None
    req = urllib.request.Request(
        url=f"{LITELLM_URL}{path}",
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {LITELLM_MASTER_KEY}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


async def _wait_for_litellm(max_wait_s: int = 120) -> None:
    """Espera a que LiteLLM esté listo (tablas Prisma creadas + healthy)."""
    deadline = asyncio.get_event_loop().time() + max_wait_s
    last_err: str | None = None
    while asyncio.get_event_loop().time() < deadline:
        try:
            status, _ = _http_request("GET", "/health/readiness")
            if status == 200:
                log.info("LiteLLM ready at %s", LITELLM_URL)
                return
        except (urllib.error.URLError, urllib.error.HTTPError) as exc:
            last_err = str(exc)
        await asyncio.sleep(2)
    raise RuntimeError(
        f"LiteLLM not ready after {max_wait_s}s. Last error: {last_err}"
    )


def _generate_virtual_key(alias: str) -> str:
    """Llama a /key/generate y devuelve la sk-... emitida."""
    status, body = _http_request(
        "POST",
        "/key/generate",
        payload={
            "models": MODEL_ALIASES,
            "key_alias": alias,
            "metadata": {"source": "bootstrap_demo_keys"},
        },
    )
    if status != 200 or "key" not in body:
        raise RuntimeError(
            f"key/generate failed (status={status}): {body}"
        )
    return body["key"]


def _is_master_key(plaintext: str) -> bool:
    """Una key existente es la master si coincide o si NO empieza por
    el prefijo de virtual-key emitida por LiteLLM."""
    return (
        plaintext == LITELLM_MASTER_KEY
        or not plaintext.startswith("sk-")  # placeholder
        or plaintext.startswith("sk-cerebro-master")  # heurística defensiva
    )


async def _existing_demo_key_is_valid(conn: asyncpg.Connection) -> bool:
    """True si el demo ya tiene una virtual-key emitida (no la master)."""
    row = await conn.fetchrow(
        """
        SELECT llm_key_lite, llm_keys_configured
          FROM usuarios
         WHERE email = $1
        """,
        DEMO_EMAIL,
    )
    if not row or not row["llm_keys_configured"] or not row["llm_key_lite"]:
        return False
    try:
        plaintext = decrypt_llm_key(row["llm_key_lite"])
    except InvalidToken:
        log.warning("Cannot decrypt existing demo key — encryption rotated.")
        return False
    if _is_master_key(plaintext):
        log.info("Demo currently uses master key (or placeholder) — replacing.")
        return False
    return True


async def _upsert_demo_keys(
    conn: asyncpg.Connection, encrypted_key: str
) -> UUID:
    """UPDATE de las 3 columnas con la misma key cifrada. Crea el demo
    si no existe (sin password — seed_demo_user lo completará). El
    fallback en src/api/llm_keys.py permite que una sola key sirva
    para los 3 aliases."""
    row = await conn.fetchrow(
        """
        INSERT INTO usuarios (
            email, password_hash, tenant_id, is_demo,
            llm_key_lite, llm_key_embeddings, llm_key_pro,
            llm_keys_configured
        )
        VALUES ($1, '!bootstrap-no-login!', gen_random_uuid(),
                true, $2, $2, $2, true)
        ON CONFLICT (email) DO UPDATE
            SET llm_key_lite = EXCLUDED.llm_key_lite,
                llm_key_embeddings = EXCLUDED.llm_key_embeddings,
                llm_key_pro = EXCLUDED.llm_key_pro,
                llm_keys_configured = true,
                is_demo = true,
                updated_at = NOW()
        RETURNING id
        """,
        DEMO_EMAIL,
        encrypted_key,
    )
    return row["id"]


async def main() -> int:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        log.error("DATABASE_URL not set")
        return 1

    log.info("Waiting for LiteLLM at %s ...", LITELLM_URL)
    await _wait_for_litellm()

    conn = await asyncpg.connect(database_url)
    try:
        if await _existing_demo_key_is_valid(conn):
            log.info("Demo already has a valid virtual-key — skipping.")
            return 0

        log.info("Generating new virtual-key for demo ...")
        plaintext = _generate_virtual_key(alias="demo-user")
        encrypted = encrypt_llm_key(plaintext)
        user_id = await _upsert_demo_keys(conn, encrypted)
        log.info(
            "Demo user %s configured with virtual-key (sk-...%s)",
            user_id,
            plaintext[-4:],
        )
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
