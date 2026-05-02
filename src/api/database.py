import json
import os
from typing import Optional

import asyncpg

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://cerebro:cerebro_db_pass@postgres:5432/cerebro_brain",
)

_pool: Optional[asyncpg.Pool] = None


async def _init_conn(conn: asyncpg.Connection) -> None:
    await conn.execute("SET search_path TO cerebro, public")
    await conn.set_type_codec(
        "jsonb",
        schema="pg_catalog",
        encoder=json.dumps,
        decoder=json.loads,
    )


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            DATABASE_URL, min_size=2, max_size=10, init=_init_conn
        )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


# ── usuarios ─────────────────────────────────────────────────────────────────

async def get_user_by_email(email: str) -> Optional[dict]:
    p = await get_pool()
    row = await p.fetchrow("SELECT * FROM usuarios WHERE email = $1", email)
    return dict(row) if row else None


async def create_user(email: str, password_hash: str) -> dict:
    p = await get_pool()
    row = await p.fetchrow(
        "INSERT INTO usuarios (email, password_hash) VALUES ($1, $2) RETURNING *",
        email,
        password_hash,
    )
    return dict(row)


async def get_user_by_id(user_id: str) -> Optional[dict]:
    p = await get_pool()
    row = await p.fetchrow("SELECT * FROM usuarios WHERE id = $1::uuid", user_id)
    return dict(row) if row else None


async def update_telegram_bot(user_id: str, bot_token: str, token_hash: str) -> dict:
    p = await get_pool()
    row = await p.fetchrow(
        """UPDATE usuarios
           SET telegram_bot_token = $1, telegram_bot_token_hash = $2,
               telegram_bot_active = TRUE
           WHERE id = $3::uuid
           RETURNING *""",
        bot_token,
        token_hash,
        user_id,
    )
    return dict(row)


# ── recursos (KB) ─────────────────────────────────────────────────────────────

async def get_resources(
    tenant_id: str, estado: str = "todos", limit: int = 100
) -> list[dict]:
    """Lista los recursos asociados al tenant via la pivote `usuario_recursos`.
    `created_at` es el momento en que el usuario añadió la URL a su KB
    (no el de creación global del recurso)."""
    p = await get_pool()
    base = """SELECT r.id, r.url, r.titulo, r.resumen, r.categoria, r.tags,
                     r.estado, r.volatilidad, r.fecha_caducidad,
                     ur.created_at, r.updated_at
              FROM recursos r
              JOIN usuario_recursos ur ON ur.recurso_id = r.id
              WHERE ur.tenant_id = $1"""
    if estado and estado != "todos":
        rows = await p.fetch(
            base + " AND r.estado = $2 ORDER BY ur.created_at DESC LIMIT $3",
            tenant_id, estado, limit,
        )
    else:
        rows = await p.fetch(
            base + " ORDER BY ur.created_at DESC LIMIT $2",
            tenant_id, limit,
        )
    return [dict(r) for r in rows]


async def get_active_resource_ids(tenant_id: str, ids: list[str]) -> list[str]:
    """Return only the IDs from `ids` that the tenant has linked AND are estado='activo'."""
    if not ids:
        return []
    p = await get_pool()
    rows = await p.fetch(
        """
        SELECT r.id::text
        FROM recursos r
        JOIN usuario_recursos ur ON ur.recurso_id = r.id
        WHERE ur.tenant_id = $1
          AND r.estado = 'activo'
          AND r.id = ANY($2::uuid[])
        """,
        tenant_id, ids,
    )
    return [r["id"] for r in rows]


# ── sesiones_chat ─────────────────────────────────────────────────────────────

async def create_chat_session(tenant_id: str) -> dict:
    p = await get_pool()
    row = await p.fetchrow(
        "INSERT INTO sesiones_chat (tenant_id) VALUES ($1) RETURNING *",
        tenant_id,
    )
    return dict(row)


async def list_chat_sessions(
    tenant_id: str, limit: int = 50, offset: int = 0
) -> list[dict]:
    p = await get_pool()
    rows = await p.fetch(
        """SELECT * FROM sesiones_chat
           WHERE tenant_id = $1
           ORDER BY ultimo_acceso DESC
           LIMIT $2 OFFSET $3""",
        tenant_id, limit, offset,
    )
    return [dict(r) for r in rows]


async def count_chat_sessions(tenant_id: str) -> int:
    p = await get_pool()
    row = await p.fetchrow(
        "SELECT COUNT(*) AS n FROM sesiones_chat WHERE tenant_id = $1",
        tenant_id,
    )
    return int(row["n"])


async def get_chat_session(tenant_id: str, session_id: str) -> Optional[dict]:
    p = await get_pool()
    row = await p.fetchrow(
        "SELECT * FROM sesiones_chat WHERE id = $1::uuid AND tenant_id = $2",
        session_id, tenant_id,
    )
    return dict(row) if row else None


async def delete_chat_session(tenant_id: str, session_id: str) -> bool:
    p = await get_pool()
    result = await p.execute(
        "DELETE FROM sesiones_chat WHERE id = $1::uuid AND tenant_id = $2",
        session_id, tenant_id,
    )
    return result == "DELETE 1"


# ── mensajes_chat ─────────────────────────────────────────────────────────────

async def get_chat_messages(tenant_id: str, session_id: str) -> list[dict]:
    p = await get_pool()
    rows = await p.fetch(
        """SELECT * FROM mensajes_chat
           WHERE sesion_id = $1::uuid AND tenant_id = $2
           ORDER BY seq ASC""",
        session_id, tenant_id,
    )
    return [dict(r) for r in rows]


async def append_chat_messages(
    tenant_id: str, session_id: str, messages: list[dict]
) -> list[dict]:
    p = await get_pool()
    async with p.acquire() as conn:
        async with conn.transaction():
            rows = []
            for m in messages:
                row = await conn.fetchrow(
                    """INSERT INTO mensajes_chat (sesion_id, tenant_id, rol, contenido, fuentes)
                       VALUES ($1::uuid, $2, $3, $4, $5)
                       RETURNING *""",
                    session_id, tenant_id, m["role"], m["content"],
                    m.get("sources", []),
                )
                rows.append(dict(row))
            first_user = next((m for m in messages if m["role"] == "user"), None)
            if first_user:
                await conn.execute(
                    """UPDATE sesiones_chat
                       SET ultimo_acceso = NOW(),
                           titulo = COALESCE(titulo, LEFT($1, 60))
                       WHERE id = $2::uuid AND tenant_id = $3""",
                    first_user["content"], session_id, tenant_id,
                )
            else:
                await conn.execute(
                    """UPDATE sesiones_chat SET ultimo_acceso = NOW()
                       WHERE id = $1::uuid AND tenant_id = $2""",
                    session_id, tenant_id,
                )
            return rows
