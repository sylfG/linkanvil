"""Resolución per-usuario de virtual keys LiteLLM.

Slice 5 (clones por sesión): la resolución pasa de keyear por
``tenant_id`` a keyear por ``user_id``. El motivo: los sub-tenants
efímeros del demo (``demo_<8hex>``) NO tienen fila en ``usuarios``,
así que un query por tenant_id falla. El user.id (claim ``sub`` del
JWT) sí es estable — el demo siempre es el mismo user, aunque su
tenant cambie cada login.

Los 5 call-sites de LLM (scraper, embedder x3, chat completions +
chat embeddings) llaman a ``resolve_llm_key(conn, user_id, kind)``
justo antes de armar el ``Authorization`` header.

Algoritmo
---------
1. ``SELECT is_demo, llm_keys_configured, llm_key_<kind> FROM usuarios``
2. Si el row no existe → ``HTTPException 401`` (user_id inválido).
3. Si ``llm_key_<kind>`` está poblada → desencripta y devuelve.
4. Si NO está poblada pero alguna OTRA key SÍ → fallback a la primera
   no-NULL. Caso típico: el usuario configura una sola key (lite) y
   espera que sirva para los 3 aliases. LiteLLM acepta esto si la key
   tiene permiso sobre los tres modelos.
5. Si NO hay ninguna y es demo → ``RuntimeError`` (mala config del owner).
6. Si NO hay ninguna y no es demo → ``HTTPException 402``.

Cache
-----
TTL 60s in-process por ``user_id``. Mismo patrón que
``_get_user_audit_policy`` en ``src/data/db.py``. La invalidación
manual la dispara ``PUT /profile/llm-keys`` llamando a
``invalidate_llm_key_cache(user_id)`` tras el UPDATE.
"""
from __future__ import annotations

import time
from typing import Literal

import asyncpg
from fastapi import HTTPException

from .crypto import decrypt_llm_key

KeyKind = Literal["lite", "embeddings", "pro"]

# user_id (str) -> (timestamp, dict con las 3 keys ya desencriptadas o None)
_CACHE: dict[str, tuple[float, dict]] = {}
_TTL_SECONDS = 60.0


def _now() -> float:
    return time.monotonic()


def invalidate_llm_key_cache(user_id: str) -> None:
    """Borra la entrada del cache para forzar relectura tras UPDATE."""
    _CACHE.pop(str(user_id), None)


async def _load_keys(
    conn: asyncpg.Connection, user_id: str
) -> dict:
    row = await conn.fetchrow(
        """
        SELECT is_demo,
               llm_keys_configured,
               llm_key_lite,
               llm_key_embeddings,
               llm_key_pro
          FROM usuarios
         WHERE id = $1::uuid
        """,
        user_id,
    )
    if not row:
        raise HTTPException(status_code=401, detail="invalid_user")

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
    conn: asyncpg.Connection, user_id: str, kind: KeyKind
) -> str:
    """Devuelve la virtual key del usuario para el alias ``kind``.

    Levanta ``HTTPException(402)`` si el user no es demo y no tiene
    ninguna key configurada.
    """
    cache_key = str(user_id)
    cached = _CACHE.get(cache_key)
    if cached and (_now() - cached[0]) < _TTL_SECONDS:
        data = cached[1]
    else:
        data = await _load_keys(conn, user_id)
        _CACHE[cache_key] = (_now(), data)

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
            f"Demo user {user_id} has no LLM keys configured. "
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
