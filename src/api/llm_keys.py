"""Resolución per-tenant de virtual keys LiteLLM.

Los 5 call-sites de LLM identificados (scraper, embedder x3, chat
completions + chat embeddings) llaman a ``resolve_llm_key(conn,
tenant_id, kind)`` justo antes de armar el ``Authorization`` header.

Algoritmo
---------
1. ``SELECT is_demo, llm_keys_configured, llm_key_<kind> FROM usuarios``
2. Si el row no existe → ``HTTPException 401`` (tenant inválido, no
   debería pasar tras auth, pero protección defensiva).
3. Si ``llm_key_<kind>`` está poblada → desencripta y devuelve.
4. Si NO está poblada pero alguna OTRA key SÍ → fallback a la primera
   no-NULL. Caso típico: el usuario configura una sola key (lite) y
   espera que sirva para los 3 aliases. LiteLLM acepta esto si la key
   tiene permiso sobre los tres modelos.
5. Si NO hay ninguna y es demo → ``RuntimeError`` (mala config del owner).
6. Si NO hay ninguna y no es demo → ``HTTPException 402``.

Cache
-----
TTL 60s in-process por ``tenant_id``. Mismo patrón que
``_get_user_audit_policy`` en ``src/data/db.py``. La invalidación
manual la dispara ``PUT /profile/llm-keys`` llamando a
``invalidate_llm_key_cache(tenant_id)`` tras el UPDATE.
"""
from __future__ import annotations

import time
from typing import Literal

import asyncpg
from fastapi import HTTPException

from .crypto import decrypt_llm_key

KeyKind = Literal["lite", "embeddings", "pro"]

# tenant_id -> (timestamp, dict con las 3 keys ya desencriptadas o None)
_CACHE: dict[str, tuple[float, dict]] = {}
_TTL_SECONDS = 60.0


def _now() -> float:
    return time.monotonic()


def invalidate_llm_key_cache(tenant_id: str) -> None:
    """Borra la entrada del cache para forzar relectura tras UPDATE."""
    _CACHE.pop(tenant_id, None)


async def _load_keys(
    conn: asyncpg.Connection, tenant_id: str
) -> dict:
    row = await conn.fetchrow(
        """
        SELECT is_demo,
               llm_keys_configured,
               llm_key_lite,
               llm_key_embeddings,
               llm_key_pro
          FROM usuarios
         WHERE tenant_id = $1
        """,
        tenant_id,
    )
    if not row:
        raise HTTPException(status_code=401, detail="invalid_tenant")

    # Desencripta perezosamente — si falla, el caller lo verá.
    keys: dict[str, str | None] = {}
    for kind in ("lite", "embeddings", "pro"):
        ciphertext = row[f"llm_key_{kind}"]
        keys[kind] = decrypt_llm_key(ciphertext) if ciphertext else None

    return {
        "is_demo": row["is_demo"],
        "llm_keys_configured": row["llm_keys_configured"],
        "keys": keys,
    }


async def resolve_llm_key(
    conn: asyncpg.Connection, tenant_id: str, kind: KeyKind
) -> str:
    """Devuelve la virtual key del tenant para el alias ``kind``.

    Levanta ``HTTPException(402)`` si el tenant no es demo y no tiene
    ninguna key configurada.
    """
    cached = _CACHE.get(tenant_id)
    if cached and (_now() - cached[0]) < _TTL_SECONDS:
        data = cached[1]
    else:
        data = await _load_keys(conn, tenant_id)
        _CACHE[tenant_id] = (_now(), data)

    # 1. Key específica disponible
    specific = data["keys"][kind]
    if specific:
        return specific

    # 2. Fallback a la primera key no-None
    for fallback_kind in ("lite", "embeddings", "pro"):
        candidate = data["keys"][fallback_kind]
        if candidate:
            return candidate

    # 3. Ninguna key. Si es demo, error de config del owner — el seed
    #    debería haber poblado las 3 con free-tier keys.
    if data["is_demo"]:
        raise RuntimeError(
            f"Demo tenant {tenant_id} has no LLM keys configured. "
            "Re-run ops/seed_demo_user.py with DEMO_KEY_* env-vars set."
        )

    # 4. Usuario registrado sin BYOK → 402 con CTA al modal.
    raise HTTPException(
        status_code=402,
        detail={
            "error": "byok_required",
            "message": (
                "Configura tus claves de LLM en el perfil para usar "
                "el chat o ingestar URLs."
            ),
        },
    )


async def is_demo_tenant(
    conn: asyncpg.Connection, tenant_id: str
) -> bool:
    """Helper rápido para guards de endpoint (no toca el cache de keys)."""
    return bool(
        await conn.fetchval(
            "SELECT is_demo FROM usuarios WHERE tenant_id = $1",
            tenant_id,
        )
    )
