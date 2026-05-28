import hashlib
import json
import os
import secrets
from typing import Optional

import asyncpg

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    # Fail-fast: sin variable de entorno el módulo no debe arrancar.
    # Evita que un fallback con valores triviales se cuele por error.
    # Configurar la cadena de conexión Postgres en .env (ver .env.example).
    raise RuntimeError("Missing env-var DATABASE_URL — ver .env.example")

# Slice 5: tenant inmutable que aloja los 18 recursos seed del demo.
# Los sub-tenants efímeros del demo (demo_<8hex>) hacen UNION con este
# tenant en READS para ver los seed compartidos.
DEMO_SEED_TENANT_ID = "user_demo_landing"
DEMO_SESSION_TTL_MINUTES = 15

_pool: Optional[asyncpg.Pool] = None


def _as_tenant_list(tenant_id_or_list) -> list[str]:
    """Helper de compat: el código viejo pasaba ``tenant_id: str``.
    Las funciones de lectura ahora aceptan ``str | list[str]``; si reciben
    string lo envuelven en lista de 1 elemento, si reciben lista la usan
    tal cual. Permite migrar callers incrementalmente sin romper nada.
    """
    if isinstance(tenant_id_or_list, str):
        return [tenant_id_or_list]
    return list(tenant_id_or_list)


# ── demo sessions (Slice 5) ───────────────────────────────────────────────────

# Slice 6: definición canónica de los 3 recursos efímeros que se stagean
# al login del demo. Cada uno se inserta en `recursos` con un URL único
# por sesión y se referencia desde `usuario_recursos` para el sub-tenant.
# El cron de producción los ignora por `fecha_caducidad IS NULL`.
_STAGED_RECURSOS = [
    {
        "titulo": "Conferencia DevOps Barcelona 2026",
        "resumen": (
            "Programa oficial de la Conferencia DevOps Barcelona 2026, "
            "celebrada los días 18 y 19 de junio de 2026 en el Palau de "
            "Congressos de Catalunya. Tres tracks paralelos: "
            "Observabilidad (OpenTelemetry, eBPF, métricas de SRE), "
            "Plataformas Internas (backstage, golden paths, IDP) y "
            "Seguridad de la cadena de suministro (SLSA, sigstore, SBOM). "
            "Keynotes: Charity Majors (Honeycomb), Kelsey Hightower (ex-Google) "
            "y Liz Fong-Jones (Honeycomb). Más de 60 ponencias y 8 talleres "
            "prácticos. Entrada: 450€ early-bird hasta el 1 de marzo. "
            "Coorganizada por la AETIC y la comunidad DevOps Barcelona."
        ),
        "categoria": "evento",
    },
    {
        "titulo": "Webinar: Patrones RAG en producción",
        "resumen": (
            "Webinar técnico de 90 minutos sobre cómo desplegar pipelines "
            "de Retrieval-Augmented Generation en producción sin quemar "
            "presupuesto en LLM. Cubre: chunking semántico vs naive "
            "splitting, estrategias de re-ranking (Cohere rerank-3, "
            "ColBERT), evaluación con Ragas y TruLens, observabilidad de "
            "embeddings con Arize Phoenix, y el patrón de fallback a "
            "conocimiento general cuando el RAG no encuentra hits relevantes. "
            "Ponente: Jerry Liu (LlamaIndex). 14 de febrero 2026 a las "
            "17:00 CET, retransmisión gratuita en YouTube y registro "
            "previo para Q&A en vivo."
        ),
        "categoria": "webinar",
    },
    {
        "titulo": "Hackathon LinkAnvil — edición invierno",
        "resumen": (
            "Crónica del hackathon interno de LinkAnvil celebrado en diciembre "
            "de 2025. 48 horas continuas, 12 equipos, premio al mejor proyecto "
            "para 'Smart Quarantine': un sistema que predice qué recursos "
            "irán a cuarentena en los próximos 7 días usando features "
            "temporales (fecha_caducidad, último acceso, score del LLM). "
            "Métricas: 850 commits, 47 PRs mergeados, reducción del 30% en "
            "el tiempo de auditoría manual. Lecciones aprendidas: prototipar "
            "con datos reales (no synthetic seed), tests de regresión sobre "
            "el cron desde el día 1, y comunicar las transiciones del "
            "lifecycle con copy menos técnico para el usuario final."
        ),
        "categoria": "hackathon",
    },
]


async def create_demo_session(user_id: str, ip: Optional[str] = None) -> dict:
    """Crea un sub-tenant efímero (TTL 15min) para una nueva sesión demo.

    Slice 6 — además del INSERT en `demo_sessions`, esta función ahora
    también ``stagea`` 3 recursos sintéticos linkeados al nuevo tenant y
    programa 4 eventos en `demo_session_events` que dispararán las
    transiciones intra-sesión:

      - +5min  → 2 recursos a cuarentena (motivo `caducidad`)
      - +5min  → 1 recurso a expirado    (motivo `auto_archive`)
      - +10min → reminder pasivo "quedan 5 min"

    Todo va en la misma transacción: si falla el staging, no queda una
    sesión a medio crear. Devuelve { tenant_id, created_at, expires_at }.
    """
    tenant_id = f"demo_{secrets.token_hex(4)}"
    p = await get_pool()
    async with p.acquire() as conn:
        async with conn.transaction():
            # ── 1) sesión demo ────────────────────────────────────────
            session_row = await conn.fetchrow(
                """
                INSERT INTO demo_sessions (tenant_id, user_id, expires_at, ip)
                VALUES ($1, $2::uuid, NOW() + ($3::int * INTERVAL '1 minute'), $4)
                RETURNING tenant_id, created_at, expires_at
                """,
                tenant_id,
                user_id,
                DEMO_SESSION_TTL_MINUTES,
                ip,
            )

            # RLS bypass para las tablas con `tenant_isolation` FORCED:
            # `usuario_recursos` requiere current_setting('app.tenant_id').
            await conn.execute(
                "SELECT set_config('app.tenant_id', $1, true)",
                tenant_id,
            )

            # ── 2) 3 recursos efímeros ────────────────────────────────
            # URL sintética única por sesión + url_hash sha256 hex (la
            # columna `recursos.url_hash` es UNIQUE; el tenant en la URL
            # garantiza unicidad sin colisionar con seed ni otras sesiones).
            #
            # Importante: `fecha_caducidad = NULL` y `temporal_class = 'evento'`
            # son defensivos. El cron de PRODUCCIÓN filtra por
            # `fecha_caducidad IS NOT NULL`, así que no los toca. Solo el
            # audit del demo (via demo_session_events) los hará transicionar.
            recurso_ids: list = []
            for idx, spec in enumerate(_STAGED_RECURSOS, start=1):
                url = f"https://demo.linkanvil.local/staged-{tenant_id}-{idx}"
                url_hash = hashlib.sha256(url.encode()).hexdigest()
                r_row = await conn.fetchrow(
                    """
                    INSERT INTO recursos (
                        url, url_hash, titulo, resumen, categoria,
                        volatilidad, temporal_class
                    ) VALUES (
                        $1, $2, $3, $4, $5, 'media', 'evento'
                    )
                    RETURNING id
                    """,
                    url,
                    url_hash,
                    spec["titulo"],
                    spec["resumen"],
                    spec["categoria"],
                )
                recurso_ids.append(r_row["id"])
                # Migración 0012: estado per-tenant en usuario_recursos.
                # Los recursos staged arrancan en 'activo' — los demo_audit
                # events los transicionarán a cuarentena/expirado a +5min.
                await conn.execute(
                    """
                    INSERT INTO usuario_recursos (tenant_id, recurso_id, estado)
                    VALUES ($1, $2, 'activo')
                    """,
                    tenant_id,
                    r_row["id"],
                )

            # ── 3) 4 eventos programados ──────────────────────────────
            # Centralizamos `created_at` como base de los offsets para que
            # los `fires_at` sean predecibles desde el cliente y desde el
            # cleanup loop. `NOW()` en una transacción Postgres es estable
            # durante toda la tx, lo cual nos da consistencia.
            events_spec = [
                # +5min — 2 transiciones a cuarentena (motivo `caducidad`)
                {
                    "offset_min": 5,
                    "kind": "transition_cuarentena",
                    "recurso_id": recurso_ids[0],
                    "motivo": "caducidad",
                    "description": (
                        "Recurso movido a cuarentena por caducidad simulada."
                    ),
                },
                {
                    "offset_min": 5,
                    "kind": "transition_cuarentena",
                    "recurso_id": recurso_ids[1],
                    "motivo": "caducidad",
                    "description": (
                        "Recurso movido a cuarentena por caducidad simulada."
                    ),
                },
                # +5min — 1 transición a expirado (auto-archive)
                {
                    "offset_min": 5,
                    "kind": "transition_expirado",
                    "recurso_id": recurso_ids[2],
                    "motivo": "auto_archive",
                    "description": (
                        "Recurso archivado directamente por alto valor "
                        "histórico (no pasa por cuarentena)."
                    ),
                },
                # +10min — reminder pasivo para el banner del demo
                {
                    "offset_min": 10,
                    "kind": "reminder_expiry_5min",
                    "recurso_id": None,
                    "motivo": None,
                    "description": ("Quedan 5 minutos para que la sesión demo expire."),
                },
            ]
            for ev in events_spec:
                await conn.execute(
                    """
                    INSERT INTO demo_session_events (
                        tenant_id, fires_at, kind, recurso_id,
                        motivo, description
                    ) VALUES (
                        $1,
                        $2::timestamptz + ($3::int * INTERVAL '1 minute'),
                        $4, $5, $6, $7
                    )
                    """,
                    tenant_id,
                    session_row["created_at"],
                    ev["offset_min"],
                    ev["kind"],
                    ev["recurso_id"],
                    ev["motivo"],
                    ev["description"],
                )

    return dict(session_row)


async def get_demo_session_events(tenant_id: str) -> list[dict]:
    """Devuelve los eventos programados de una sesión demo en orden
    cronológico. Usado por `GET /demo/timeline` para pintar la línea
    temporal en el frontend."""
    p = await get_pool()
    rows = await p.fetch(
        """
        SELECT id, tenant_id, fires_at, fired_at, kind, recurso_id,
               motivo, description, created_at
          FROM demo_session_events
         WHERE tenant_id = $1
         ORDER BY fires_at ASC, created_at ASC
        """,
        tenant_id,
    )
    return [dict(r) for r in rows]


async def get_sessions_with_due_events() -> list[str]:
    """Devuelve la lista de tenant_ids cuyas sesiones tienen al menos un
    evento pending (fires_at <= NOW() AND fired_at IS NULL).

    Usado por el cleanup loop para saber a qué sesiones lanzar
    `run_demo_audit_for_session`. Aprovecha el índice parcial
    `idx_demo_events_due` (definido en la migración 0010) que indexa
    solo los eventos no disparados — el scan es barato incluso con
    cientos de sesiones activas.
    """
    p = await get_pool()
    rows = await p.fetch(
        """
        SELECT DISTINCT tenant_id
          FROM demo_session_events
         WHERE fires_at <= NOW()
           AND fired_at IS NULL
        """,
    )
    return [r["tenant_id"] for r in rows]


async def get_demo_session(tenant_id: str) -> Optional[dict]:
    """Devuelve el row de demo_sessions o None si no existe / no es demo."""
    if not tenant_id or not tenant_id.startswith("demo_"):
        return None
    p = await get_pool()
    row = await p.fetchrow(
        """SELECT tenant_id, user_id, created_at, expires_at, last_seen_at
             FROM demo_sessions
            WHERE tenant_id = $1""",
        tenant_id,
    )
    return dict(row) if row else None


async def get_expired_demo_sessions() -> list[dict]:
    p = await get_pool()
    rows = await p.fetch(
        "SELECT tenant_id, user_id FROM demo_sessions WHERE expires_at < NOW()",
    )
    return [dict(r) for r in rows]


async def delete_demo_session_cascade(tenant_id: str) -> dict:
    """Borra una sesión demo expirada y todo su contenido en BD.

    Orden de borrado (FK + integridad referencial):
      1. chat_messages → chat_sessions de ese tenant
      2. chat_sessions del tenant
      3. notificaciones del tenant
      4. usuario_recursos del tenant
      5. recursos huérfanos (sin ningún tenant_id tras 4) — EXCEPTO los
         que tienen url_hash idéntico a algún recurso del seed (para
         no borrar accidentalmente los canónicos si el visitante reingestó
         un URL que ya existía en el seed)
      6. demo_sessions row

    Devuelve un dict con conteos para logging.

    Los Qdrant points (chunks + recurso summaries) los borra el cleanup
    task EN main.py, no aquí — necesita HTTP al servicio Qdrant.
    """
    if not tenant_id.startswith("demo_"):
        # Salvaguarda: nunca borrar tenants que no sean demo sub-sessions.
        raise ValueError(f"refusing to cascade-delete non-demo tenant: {tenant_id!r}")

    p = await get_pool()
    out = {"tenant_id": tenant_id}
    async with p.acquire() as conn:
        async with conn.transaction():
            # sesiones_chat y usuario_recursos llevan RLS forced con
            # policy ``tenant_isolation``: requieren que
            # ``current_setting('app.tenant_id')`` coincida con la fila
            # antes de poder borrar. Set LOCAL → solo para esta tx.
            await conn.execute(
                "SELECT set_config('app.tenant_id', $1, true)",
                tenant_id,
            )

            # sesiones_chat: tabla en español. mensajes_chat cascadea
            # vía FK ON DELETE CASCADE (no la borramos explícita).
            r = await conn.execute(
                "DELETE FROM sesiones_chat WHERE tenant_id = $1",
                tenant_id,
            )
            out["sesiones_chat"] = _parse_delete_count(r)

            # notificaciones: sin RLS, delete directo.
            r = await conn.execute(
                "DELETE FROM notificaciones WHERE tenant_id = $1",
                tenant_id,
            )
            out["notificaciones"] = _parse_delete_count(r)

            # Capturar recurso_ids ANTES de borrar usuario_recursos
            # para poder detectar huérfanos después.
            recurso_rows = await conn.fetch(
                "SELECT recurso_id FROM usuario_recursos WHERE tenant_id = $1",
                tenant_id,
            )
            recurso_ids = [r["recurso_id"] for r in recurso_rows]

            r = await conn.execute(
                "DELETE FROM usuario_recursos WHERE tenant_id = $1",
                tenant_id,
            )
            out["usuario_recursos"] = _parse_delete_count(r)

            # Huérfanos: recursos que quedaron sin ningún tenant tras el delete
            # de usuario_recursos. Salvaguarda extra: no borrar nunca un recurso
            # cuyo url_hash coincida con uno asociado al seed canónico.
            if recurso_ids:
                r = await conn.execute(
                    """DELETE FROM recursos r
                        WHERE r.id = ANY($1::uuid[])
                          AND NOT EXISTS (
                              SELECT 1 FROM usuario_recursos ur
                               WHERE ur.recurso_id = r.id
                          )
                          AND NOT EXISTS (
                              SELECT 1 FROM usuario_recursos ur2
                                JOIN recursos r2 ON r2.id = ur2.recurso_id
                               WHERE ur2.tenant_id = $2
                                 AND r2.url_hash = r.url_hash
                          )""",
                    recurso_ids,
                    DEMO_SEED_TENANT_ID,
                )
                out["recursos_huerfanos"] = _parse_delete_count(r)
            else:
                out["recursos_huerfanos"] = 0

            r = await conn.execute(
                "DELETE FROM demo_sessions WHERE tenant_id = $1",
                tenant_id,
            )
            out["demo_sessions"] = _parse_delete_count(r)

    return out


def _parse_delete_count(execute_result: str) -> int:
    """asyncpg.execute() devuelve 'DELETE N' como string. Extrae N."""
    parts = execute_result.split()
    return int(parts[-1]) if parts and parts[-1].isdigit() else 0


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


async def update_llm_keys(
    user_id: str,
    encrypted_lite: Optional[str],
    encrypted_embeddings: Optional[str],
    encrypted_pro: Optional[str],
) -> None:
    """Actualiza las virtual-keys LiteLLM cifradas del usuario (migración
    0008). Aplica PATCH semántico: cada parámetro None deja la columna
    intacta; el llm_keys_configured se recalcula en función del estado
    final tras el merge.

    El cifrado lo hace el caller (``encrypt_llm_key`` en ``crypto.py``);
    aquí solo guardamos el ciphertext en BD.
    """
    p = await get_pool()
    await p.execute(
        """
        UPDATE usuarios
           SET llm_key_lite       = COALESCE($2, llm_key_lite),
               llm_key_embeddings = COALESCE($3, llm_key_embeddings),
               llm_key_pro        = COALESCE($4, llm_key_pro),
               llm_keys_configured = (
                   COALESCE($2, llm_key_lite)       IS NOT NULL
                OR COALESCE($3, llm_key_embeddings) IS NOT NULL
                OR COALESCE($4, llm_key_pro)        IS NOT NULL
               ),
               updated_at = NOW()
         WHERE id = $1::uuid
        """,
        user_id,
        encrypted_lite,
        encrypted_embeddings,
        encrypted_pro,
    )


# ── recursos (KB) ─────────────────────────────────────────────────────────────


async def get_resources(
    tenant_id, estado: str = "todos", limit: int = 100
) -> list[dict]:
    """Lista los recursos asociados al tenant via la pivote `usuario_recursos`.
    `created_at` es el momento en que el usuario añadió la URL a su KB
    (no el de creación global del recurso).

    Slice 5: ``tenant_id`` acepta ``str`` (single tenant) o ``list[str]``
    (UNION — usado por demo sessions que ven session_tenant + seed).

    Por defecto (`estado='todos'`) excluimos `cuarentena` y `expirado` —
    tienen vistas dedicadas (`/quarantine`, `/expired`) y mezclarlos en la
    KB es ruidoso. Para verlos hay que pedirlos explícitamente
    (`estado='cuarentena'` o `estado='expirado'`) o usar el alias
    `estado='_all'` que sí los incluye."""
    tenants = _as_tenant_list(tenant_id)
    p = await get_pool()
    # Migración 0012: estado y fecha_caducidad son per-tenant.
    base = """SELECT r.id, r.url, r.titulo, r.resumen, r.categoria, r.tags,
                     ur.estado, r.volatilidad, ur.fecha_caducidad,
                     ur.created_at, r.updated_at
              FROM recursos r
              JOIN usuario_recursos ur ON ur.recurso_id = r.id
              WHERE ur.tenant_id = ANY($1::text[])"""
    if estado == "_all":
        rows = await p.fetch(
            base + " ORDER BY ur.created_at DESC LIMIT $2",
            tenants,
            limit,
        )
    elif estado and estado != "todos":
        rows = await p.fetch(
            base + " AND ur.estado = $2 ORDER BY ur.created_at DESC LIMIT $3",
            tenants,
            estado,
            limit,
        )
    else:
        rows = await p.fetch(
            base + " AND ur.estado NOT IN ('cuarentena','expirado')"
            " ORDER BY ur.created_at DESC LIMIT $2",
            tenants,
            limit,
        )
    return [dict(r) for r in rows]


async def get_active_resource_ids(
    tenant_id, ids: list[str], include_archive: bool = False
) -> list[str]:
    """Return only the IDs from `ids` that the tenant(s) have linked AND
    are `estado='activo'`. Si `include_archive=True`, también incluye
    recursos en `estado='expirado'`.

    Slice 5: acepta ``tenant_id`` como str o list[str] para soportar el
    UNION de demo session + seed."""
    if not ids:
        return []
    tenants = _as_tenant_list(tenant_id)
    p = await get_pool()
    allowed_states = ["activo"]
    if include_archive:
        allowed_states.append("expirado")
    rows = await p.fetch(
        """
        SELECT DISTINCT r.id::text
        FROM recursos r
        JOIN usuario_recursos ur ON ur.recurso_id = r.id
        WHERE ur.tenant_id = ANY($1::text[])
          AND ur.estado = ANY($2::text[])
          AND r.id = ANY($3::uuid[])
        """,
        tenants,
        allowed_states,
        ids,
    )
    return [r["id"] for r in rows]


async def get_resources_for_rag(tenant_id, ids: list[str]) -> list[dict]:
    """Devuelve recursos activos del tenant con campos enriquecidos para
    inyectar como contexto del LLM. Slice 5: tenant_id str | list[str]."""
    if not ids:
        return []
    tenants = _as_tenant_list(tenant_id)
    p = await get_pool()
    rows = await p.fetch(
        """
        SELECT DISTINCT r.id::text, r.titulo, r.resumen, r.url, r.tags, r.categoria
        FROM recursos r
        JOIN usuario_recursos ur ON ur.recurso_id = r.id
        WHERE ur.tenant_id = ANY($1::text[])
          AND ur.estado = 'activo'
          AND r.id = ANY($2::uuid[])
        """,
        tenants,
        ids,
    )
    return [dict(r) for r in rows]


# ── bandeja de cuarentena (F-05.2) ────────────────────────────────────────────

GRACE_PERIOD_DAYS = int(os.getenv("OBSOLESCENCE_GRACE_DAYS", "30"))

# Mapa de volatilidad → días de vida útil que el scraper asume cuando un
# recurso es rescatado de la cuarentena (no recalculamos via LLM aquí).
_VOLATILITY_DAYS = {"baja": 365, "media": 180, "alta": 60, "dinamica": 30}


async def list_quarantine(tenant_id, limit: int = 100) -> list[dict]:
    """Recursos en `cuarentena` linkeados al tenant. Slice 5: str|list."""
    tenants = _as_tenant_list(tenant_id)
    p = await get_pool()
    rows = await p.fetch(
        """SELECT DISTINCT r.id, r.url, r.titulo, r.resumen, r.categoria,
                  r.volatilidad, ur.fecha_caducidad,
                  ur.quarantined_at, ur.quarantine_reason, ur.quarantine_grace_until,
                  GREATEST(0, (ur.quarantine_grace_until - NOW()::DATE))::int AS dias_restantes,
                  ur.created_at
           FROM recursos r
           JOIN usuario_recursos ur ON ur.recurso_id = r.id
           WHERE ur.tenant_id = ANY($1::text[]) AND ur.estado = 'cuarentena'
           ORDER BY ur.quarantine_grace_until ASC NULLS LAST
           LIMIT $2""",
        tenants,
        limit,
    )
    return [dict(r) for r in rows]


async def count_quarantine(tenant_id) -> int:
    tenants = _as_tenant_list(tenant_id)
    p = await get_pool()
    row = await p.fetchrow(
        """SELECT COUNT(DISTINCT r.id) AS n
           FROM recursos r
           JOIN usuario_recursos ur ON ur.recurso_id = r.id
           WHERE ur.tenant_id = ANY($1::text[]) AND ur.estado = 'cuarentena'""",
        tenants,
    )
    return int(row["n"])


async def list_expired(tenant_id, limit: int = 100) -> list[dict]:
    """Recursos en `expirado` linkeados al tenant. Slice 5: str|list."""
    tenants = _as_tenant_list(tenant_id)
    p = await get_pool()
    rows = await p.fetch(
        """SELECT DISTINCT r.id, r.url, r.titulo, r.resumen, r.categoria,
                  r.volatilidad, ur.fecha_caducidad,
                  ur.quarantined_at, ur.quarantine_reason,
                  CASE WHEN ur.fecha_caducidad IS NULL THEN NULL
                       ELSE GREATEST(0, (NOW()::DATE - ur.fecha_caducidad))::int
                  END AS dias_desde_expiracion,
                  ur.created_at, r.updated_at
           FROM recursos r
           JOIN usuario_recursos ur ON ur.recurso_id = r.id
           WHERE ur.tenant_id = ANY($1::text[]) AND ur.estado = 'expirado'
           ORDER BY ur.fecha_caducidad DESC NULLS LAST
           LIMIT $2""",
        tenants,
        limit,
    )
    return [dict(r) for r in rows]


async def count_expired(tenant_id) -> int:
    tenants = _as_tenant_list(tenant_id)
    p = await get_pool()
    row = await p.fetchrow(
        """SELECT COUNT(DISTINCT r.id) AS n
           FROM recursos r
           JOIN usuario_recursos ur ON ur.recurso_id = r.id
           WHERE ur.tenant_id = ANY($1::text[]) AND ur.estado = 'expirado'""",
        tenants,
    )
    return int(row["n"])


async def list_active(tenant_id, limit: int = 100) -> list[dict]:
    """Recursos en `activo` linkeados al tenant. Slice 5: str|list.
    Misma forma que list_quarantine — feed para sidebar/KB count."""
    tenants = _as_tenant_list(tenant_id)
    p = await get_pool()
    rows = await p.fetch(
        """SELECT DISTINCT r.id, r.url, r.titulo, r.resumen, r.categoria,
                  r.volatilidad, ur.fecha_caducidad, ur.created_at
           FROM recursos r
           JOIN usuario_recursos ur ON ur.recurso_id = r.id
           WHERE ur.tenant_id = ANY($1::text[]) AND ur.estado = 'activo'
           ORDER BY ur.created_at DESC
           LIMIT $2""",
        tenants,
        limit,
    )
    return [dict(r) for r in rows]


async def count_active(tenant_id) -> int:
    """Recursos `activo` para el badge "BC" del sidebar. Incluye seed
    tenant para sesiones demo (UNION via _as_tenant_list)."""
    tenants = _as_tenant_list(tenant_id)
    p = await get_pool()
    row = await p.fetchrow(
        """SELECT COUNT(DISTINCT r.id) AS n
           FROM recursos r
           JOIN usuario_recursos ur ON ur.recurso_id = r.id
           WHERE ur.tenant_id = ANY($1::text[]) AND ur.estado = 'activo'""",
        tenants,
    )
    return int(row["n"])


# ── notificaciones in-app (F-05.3) ────────────────────────────────────────────


async def list_notifications(
    tenant_id,
    limit: int = 50,
    only_unread: bool = False,
) -> list[dict]:
    """Slice 5: tenant_id str|list[str]. Demo session une con seed_tenant."""
    tenants = _as_tenant_list(tenant_id)
    p = await get_pool()
    if only_unread:
        rows = await p.fetch(
            """SELECT id, evento_tipo, recurso_id, titulo, url, motivo,
                      leido, created_at
               FROM notificaciones
               WHERE tenant_id = ANY($1::text[]) AND leido = FALSE
               ORDER BY created_at DESC LIMIT $2""",
            tenants,
            limit,
        )
    else:
        rows = await p.fetch(
            """SELECT id, evento_tipo, recurso_id, titulo, url, motivo,
                      leido, created_at
               FROM notificaciones
               WHERE tenant_id = ANY($1::text[])
               ORDER BY created_at DESC LIMIT $2""",
            tenants,
            limit,
        )
    return [dict(r) for r in rows]


async def count_unread_notifications(tenant_id) -> int:
    tenants = _as_tenant_list(tenant_id)
    p = await get_pool()
    row = await p.fetchrow(
        """SELECT COUNT(*) AS n FROM notificaciones
           WHERE tenant_id = ANY($1::text[]) AND leido = FALSE""",
        tenants,
    )
    return int(row["n"])


async def mark_notification_read(tenant_id: str, notification_id: str) -> bool:
    """Marca una notificación como leída. Devuelve True si se actualizó
    una fila (existía y pertenecía al tenant), False si no."""
    p = await get_pool()
    row = await p.fetchrow(
        """UPDATE notificaciones
           SET leido = TRUE, leido_en = NOW()
           WHERE id = $1::uuid AND tenant_id = $2 AND leido = FALSE
           RETURNING id""",
        notification_id,
        tenant_id,
    )
    return row is not None


async def mark_all_notifications_read(tenant_id: str) -> int:
    p = await get_pool()
    row = await p.fetchrow(
        """WITH upd AS (
              UPDATE notificaciones
              SET leido = TRUE, leido_en = NOW()
              WHERE tenant_id = $1 AND leido = FALSE
              RETURNING id
           )
           SELECT COUNT(*) AS n FROM upd""",
        tenant_id,
    )
    return int(row["n"])


async def _tenant_owns_recurso(conn, tenant_id: str, recurso_id: str) -> bool:
    row = await conn.fetchrow(
        "SELECT 1 FROM usuario_recursos WHERE tenant_id = $1 AND recurso_id = $2::uuid",
        tenant_id,
        recurso_id,
    )
    return row is not None


async def _emit_outbox(
    conn, tenant_id: str, recurso_id, evento_tipo: str, payload: dict
) -> None:
    # OJO: este pool tiene un codec jsonb (encoder=json.dumps) instalado
    # en `_init_conn`. Pasar el dict directamente: si lo serializamos aquí
    # con json.dumps() el codec lo vuelve a serializar y queda
    # doblemente codificado (string JSON dentro de jsonb), rompiendo al
    # outbox-publisher al hacer json.loads().
    await conn.execute(
        """INSERT INTO outbox_eventos (
               tenant_id, agregado_tipo, agregado_id, evento_tipo, payload
           ) VALUES ($1, 'recurso', $2, $3, $4)""",
        tenant_id,
        recurso_id,
        evento_tipo,
        payload,
    )


async def rescue_recurso(tenant_id: str, recurso_id: str) -> Optional[dict]:
    """Devuelve un recurso a 'activo' y limpia los campos de cuarentena.
    Recalcula `fecha_caducidad` a partir de la volatilidad para que el cron
    no lo vuelva a meter inmediatamente. Acepta tanto recursos en
    cuarentena como expirados (rescate fast-track desde la papelera).
    Devuelve None si el tenant no es dueño o el recurso no está en un
    estado rescatable."""
    p = await get_pool()
    async with p.acquire() as conn:
        async with conn.transaction():
            if not await _tenant_owns_recurso(conn, tenant_id, recurso_id):
                return None
            # Migración 0012: rescue per-tenant. Solo el link del caller
            # cambia; los otros tenants linkeados mantienen su estado.
            # Recalcula fecha_caducidad desde volatilidad (sin LLM).
            row = await conn.fetchrow(
                """UPDATE usuario_recursos ur
                   SET estado = 'activo',
                       quarantined_at = NULL,
                       quarantine_reason = NULL,
                       quarantine_grace_until = NULL,
                       fecha_caducidad = (NOW() + (
                           COALESCE(
                               CASE r.volatilidad
                                   WHEN 'baja' THEN 365
                                   WHEN 'media' THEN 180
                                   WHEN 'alta' THEN 60
                                   WHEN 'dinamica' THEN 30
                                   ELSE 180
                               END, 180
                           ) * INTERVAL '1 day'
                       ))::DATE,
                       updated_at = NOW()
                   FROM recursos r
                   WHERE ur.recurso_id = r.id
                     AND ur.tenant_id = $1
                     AND ur.recurso_id = $2::uuid
                     AND ur.estado IN ('cuarentena','expirado')
                   RETURNING r.id, r.url, ur.fecha_caducidad""",
                tenant_id,
                recurso_id,
            )
            if not row:
                return None
            await _emit_outbox(
                conn,
                tenant_id,
                row["id"],
                "recurso.rescatado",
                {
                    "recurso_id": str(row["id"]),
                    "url": row["url"],
                    "rescued_by": tenant_id,
                    "fecha_caducidad": row["fecha_caducidad"].isoformat(),
                },
            )
            return dict(row)


async def quarantine_recurso(
    tenant_id: str,
    recurso_id: str,
    grace_days: int = GRACE_PERIOD_DAYS,
) -> Optional[dict]:
    """Mueve manualmente un recurso `activo` o `procesando` a cuarentena
    con motivo='manual'. Útil desde la KB cuando el usuario decide que un
    recurso ya no es relevante pero quiere darse un período de gracia
    antes de eliminarlo del RAG. Idempotente: si ya está en cuarentena,
    devuelve None (no transición)."""
    p = await get_pool()
    async with p.acquire() as conn:
        async with conn.transaction():
            if not await _tenant_owns_recurso(conn, tenant_id, recurso_id):
                return None
            # Migración 0012: cuarentena manual per-tenant. Solo afecta el
            # link del caller; otros tenants mantienen su estado.
            row = await conn.fetchrow(
                """UPDATE usuario_recursos ur
                   SET estado = 'cuarentena',
                       quarantined_at = NOW(),
                       quarantine_reason = 'manual',
                       quarantine_grace_until = (NOW() + ($3::int * INTERVAL '1 day'))::DATE,
                       updated_at = NOW()
                   FROM recursos r
                   WHERE ur.recurso_id = r.id
                     AND ur.tenant_id = $1
                     AND ur.recurso_id = $2::uuid
                     AND ur.estado IN ('activo','procesando')
                   RETURNING r.id, r.url, ur.quarantine_grace_until""",
                tenant_id,
                recurso_id,
                grace_days,
            )
            if not row:
                return None
            await _emit_outbox(
                conn,
                tenant_id,
                row["id"],
                "recurso.cuarentena",
                {
                    "recurso_id": str(row["id"]),
                    "url": row["url"],
                    "motivo": "manual",
                    "quarantined_by": tenant_id,
                },
            )
            return dict(row)


async def expire_recurso(tenant_id: str, recurso_id: str) -> Optional[dict]:
    """Fast-track: el usuario confirma la expiración antes del fin del período
    de gracia. Marca como 'expirado' y emite outbox por cada tenant que tenga
    el recurso linkeado."""
    p = await get_pool()
    async with p.acquire() as conn:
        async with conn.transaction():
            if not await _tenant_owns_recurso(conn, tenant_id, recurso_id):
                return None
            # Migración 0012: expire per-tenant. Solo el link del caller pasa
            # a 'expirado'; otros tenants mantienen su estado.
            row = await conn.fetchrow(
                """UPDATE usuario_recursos ur
                   SET estado = 'expirado', updated_at = NOW()
                   FROM recursos r
                   WHERE ur.recurso_id = r.id
                     AND ur.tenant_id = $1
                     AND ur.recurso_id = $2::uuid
                     AND ur.estado != 'expirado'
                   RETURNING r.id, r.url""",
                tenant_id,
                recurso_id,
            )
            if not row:
                return None
            await _emit_outbox(
                conn,
                tenant_id,
                row["id"],
                "recurso.expirado",
                {
                    "recurso_id": str(row["id"]),
                    "url": row["url"],
                    "motivo": "manual",
                    "expired_by": tenant_id,
                },
            )
            return dict(row)


async def delete_recurso_for_tenant(tenant_id: str, recurso_id: str) -> Optional[dict]:
    """Borra el link tenant↔recurso. Si no quedan más tenants linkeados,
    borra la fila global de `recursos` (la limpieza del punto Qdrant la
    hace el caller en el endpoint, ya que vive fuera de la transacción).

    Devuelve {'deleted_globally': bool, 'recurso_id', 'url'} o None si el
    tenant no es dueño."""
    p = await get_pool()
    async with p.acquire() as conn:
        async with conn.transaction():
            if not await _tenant_owns_recurso(conn, tenant_id, recurso_id):
                return None
            result = await conn.fetchrow(
                """SELECT r.id, r.url FROM recursos r WHERE r.id = $1::uuid""",
                recurso_id,
            )
            if not result:
                return None
            await conn.execute(
                "DELETE FROM usuario_recursos WHERE tenant_id = $1 AND recurso_id = $2::uuid",
                tenant_id,
                recurso_id,
            )
            remaining = await conn.fetchrow(
                "SELECT COUNT(*) AS n FROM usuario_recursos WHERE recurso_id = $1::uuid",
                recurso_id,
            )
            deleted_globally = int(remaining["n"]) == 0
            if deleted_globally:
                await conn.execute(
                    "DELETE FROM recursos WHERE id = $1::uuid",
                    recurso_id,
                )
            await _emit_outbox(
                conn,
                tenant_id,
                result["id"],
                "recurso.eliminado",
                {
                    "recurso_id": str(result["id"]),
                    "url": result["url"],
                    "deleted_globally": deleted_globally,
                },
            )
            return {
                "id": result["id"],
                "url": result["url"],
                "deleted_globally": deleted_globally,
            }


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
        tenant_id,
        limit,
        offset,
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
        session_id,
        tenant_id,
    )
    return dict(row) if row else None


async def delete_chat_session(tenant_id: str, session_id: str) -> bool:
    p = await get_pool()
    result = await p.execute(
        "DELETE FROM sesiones_chat WHERE id = $1::uuid AND tenant_id = $2",
        session_id,
        tenant_id,
    )
    return result == "DELETE 1"


# ── mensajes_chat ─────────────────────────────────────────────────────────────


async def get_chat_messages(tenant_id: str, session_id: str) -> list[dict]:
    p = await get_pool()
    rows = await p.fetch(
        """SELECT * FROM mensajes_chat
           WHERE sesion_id = $1::uuid AND tenant_id = $2
           ORDER BY seq ASC""",
        session_id,
        tenant_id,
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
                    session_id,
                    tenant_id,
                    m["role"],
                    m["content"],
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
                    first_user["content"],
                    session_id,
                    tenant_id,
                )
            else:
                await conn.execute(
                    """UPDATE sesiones_chat SET ultimo_acceso = NOW()
                       WHERE id = $1::uuid AND tenant_id = $2""",
                    session_id,
                    tenant_id,
                )
            return rows
