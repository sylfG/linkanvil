import asyncio
import json
import logging
import os
import uuid
from typing import Optional

from src.data.db import DatabaseManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Período de gracia tras el cual un recurso en cuarentena se expira de
# verdad (F-05.2). Permite al usuario rescatar antes de la expiración.
GRACE_PERIOD_DAYS = int(os.getenv("OBSOLESCENCE_GRACE_DAYS", "30"))


async def _emit_outbox_for_tenant(
    conn,
    tenant_id: str,
    recurso_id,
    url: Optional[str],
    evento_tipo: str,
    motivo: str,
    trace_id: str,
    *,
    event_origin: str = "audit_cron",
) -> None:
    """Emite un único evento outbox para un (tenant, recurso) concreto.

    Helper extraído del bucle de `_emit_outbox_per_tenant` para que el
    audit del demo (`run_demo_audit_for_session`) pueda emitir sin tener
    que pasar por el lookup de `usuario_recursos` — el demo ya conoce
    el tenant_id porque viene del propio evento programado.
    """
    payload = {
        "event_origin": event_origin,
        "trace_id": trace_id,
        "recurso_id": str(recurso_id),
        "url": url,
        "motivo": motivo,
    }
    await conn.execute(
        """
        INSERT INTO outbox_eventos (
            tenant_id, agregado_tipo, agregado_id, evento_tipo, payload
        ) VALUES (
            $1, 'recurso', $2, $3, $4::jsonb
        )
        """,
        tenant_id, recurso_id, evento_tipo, json.dumps(payload),
    )


async def _emit_outbox_per_tenant(
    conn,
    rows,
    evento_tipo: str,
    motivo: str,
    trace_id: str,
):
    """Emite un evento outbox por cada tenant que tenga linkeado el recurso.

    Usado por el cron de producción (`run_audit_cron`), donde una sola
    transición puede afectar a varios tenants que comparten el recurso.
    Internamente delega en `_emit_outbox_for_tenant` para un único
    formato canónico de payload.
    """
    for row in rows:
        tenants = await conn.fetch(
            "SELECT tenant_id FROM usuario_recursos WHERE recurso_id = $1",
            row["id"],
        )
        for t in tenants:
            await _emit_outbox_for_tenant(
                conn,
                t["tenant_id"],
                row["id"],
                row["url"],
                evento_tipo,
                motivo,
                trace_id,
            )


async def run_audit_cron() -> dict:
    """F-05.1 + F-05.2 — Auditoría temporal en dos fases.

    Fase A: recursos `activo` con `fecha_caducidad` superada → `cuarentena`
            con motivo `'caducidad'` y un período de gracia configurable.
    Fase B: recursos `cuarentena` cuyo `quarantine_grace_until` ya pasó →
            `expirado` (limpieza definitiva).

    Idempotente: ambas UPDATEs filtran por estado actual, así que rerun
    no produce transiciones espurias. Devuelve los contadores para que
    el endpoint admin pueda reportarlos.
    """
    logger.info("Iniciando tarea de auditoría temporal relacional...")
    db = DatabaseManager()
    await db.connect()

    trace_id = str(uuid.uuid4())
    cuarentenados = 0
    expirados = 0

    try:
        async with db.pool.acquire() as conn:
            # ----------------------------------------------------------------
            # Fase A — caducidad → cuarentena
            # ----------------------------------------------------------------
            cuarentena_rows = await conn.fetch(
                """
                UPDATE recursos
                SET estado = 'cuarentena',
                    quarantined_at = NOW(),
                    quarantine_reason = 'caducidad',
                    quarantine_grace_until = (NOW() + ($1::int * INTERVAL '1 day'))::DATE,
                    updated_at = NOW()
                WHERE estado = 'activo'
                  AND temporal_class = 'evento'
                  AND fecha_caducidad IS NOT NULL
                  AND fecha_caducidad <= NOW()::DATE
                RETURNING id, url
                """,
                GRACE_PERIOD_DAYS,
            )
            # NOTA migración 0006: el filtro `temporal_class = 'evento'`
            # es defensa en profundidad. Las clases 'referencia' y
            # 'evergreen' tienen fecha_caducidad NULL al ingestar y
            # ya estarían excluidas por `IS NOT NULL`. Pero si algún
            # flujo deja una caducidad rellena por error en una
            # referencia, no queremos que el cron la cuarentene
            # silenciosamente — esa decisión debe pasar por
            # save_with_outbox respetando el strictness del tenant.
            cuarentenados = len(cuarentena_rows)
            if cuarentena_rows:
                logger.info(
                    f"[{trace_id}] {cuarentenados} recursos movidos a cuarentena."
                )
                await _emit_outbox_per_tenant(
                    conn, cuarentena_rows, "recurso.cuarentena", "caducidad", trace_id,
                )

            # ----------------------------------------------------------------
            # Fase B — gracia agotada → expirado
            # ----------------------------------------------------------------
            expira_rows = await conn.fetch(
                """
                UPDATE recursos
                SET estado = 'expirado',
                    updated_at = NOW()
                WHERE estado = 'cuarentena'
                  AND quarantine_grace_until IS NOT NULL
                  AND quarantine_grace_until <= NOW()::DATE
                RETURNING id, url
                """
            )
            expirados = len(expira_rows)
            if expira_rows:
                logger.info(
                    f"[{trace_id}] {expirados} recursos expirados tras período de gracia."
                )
                await _emit_outbox_per_tenant(
                    conn, expira_rows, "recurso.expirado", "gracia_agotada", trace_id,
                )

            if not cuarentena_rows and not expira_rows:
                logger.info(
                    f"[{trace_id}] Auditoría sin transiciones (BD al día)."
                )

    except Exception as e:
        logger.error(f"[{trace_id}] Error durante la auditoría cron: {e}")
        raise
    finally:
        await db.close()
        logger.info("Finalizada la tarea de auditoría.")

    return {
        "trace_id": trace_id,
        "cuarentenados": cuarentenados,
        "expirados": expirados,
    }


async def run_demo_audit_for_session(tenant_id: str, conn) -> dict:
    """Slice 6 — Auditoría intra-sesión para un sub-tenant demo.

    A diferencia de `run_audit_cron` (global, DATE-precision), esta
    función:

      - Trabaja sobre UN solo tenant (filtra por `demo_session_events`).
      - Tiene precisión TIMESTAMPTZ (eventos a los 5min del login).
      - Procesa eventos EXPLÍCITOS de la tabla, no lee `fecha_caducidad`.
      - Reutiliza la pipeline outbox/notifier real — las notificaciones
        del bell del frontend funcionan idénticamente al cron de prod.

    El caller (`_cleanup_demo_sessions_loop` en `src/api/main.py`) abre la
    conexión y configura `app.tenant_id` para satisfacer la RLS forced
    sobre `recursos`/`usuario_recursos`. La función asume que el caller
    ya ha llamado a `set_config('app.tenant_id', tenant_id, true)` y
    está dentro de una transacción.

    Idempotente: cada evento se marca con `fired_at = NOW()` al
    procesarse; futuros tics del loop solo verán los eventos que
    todavía estén pending.
    """
    trace_id = str(uuid.uuid4())
    pending = await conn.fetch(
        """
        SELECT id, kind, recurso_id, motivo, description
          FROM demo_session_events
         WHERE tenant_id = $1
           AND fires_at <= NOW()
           AND fired_at IS NULL
         ORDER BY fires_at ASC
        """,
        tenant_id,
    )

    counts = {"cuarentena": 0, "expirado": 0, "reminder": 0, "skipped": 0}

    for ev in pending:
        kind = ev["kind"]
        recurso_id = ev["recurso_id"]
        motivo = ev["motivo"] or ""

        if kind == "transition_cuarentena":
            # `RETURNING url` permite emitir el outbox sin un segundo
            # query, y el guard `estado = 'activo'` hace la transición
            # idempotente si por alguna razón el recurso ya cambió.
            row = await conn.fetchrow(
                """
                UPDATE recursos
                   SET estado = 'cuarentena',
                       quarantined_at = NOW(),
                       quarantine_reason = $2,
                       quarantine_grace_until = (NOW() + INTERVAL '30 days')::DATE,
                       updated_at = NOW()
                 WHERE id = $1::uuid AND estado = 'activo'
                 RETURNING id, url
                """,
                recurso_id, motivo or "caducidad",
            )
            if row:
                await _emit_outbox_for_tenant(
                    conn, tenant_id, row["id"], row["url"],
                    "recurso.cuarentena", motivo or "caducidad",
                    trace_id, event_origin="demo_audit",
                )
                counts["cuarentena"] += 1
            else:
                counts["skipped"] += 1

        elif kind == "transition_expirado":
            row = await conn.fetchrow(
                """
                UPDATE recursos
                   SET estado = 'expirado',
                       auto_archive_pending = false,
                       updated_at = NOW()
                 WHERE id = $1::uuid AND estado IN ('activo', 'cuarentena')
                 RETURNING id, url
                """,
                recurso_id,
            )
            if row:
                await _emit_outbox_for_tenant(
                    conn, tenant_id, row["id"], row["url"],
                    "recurso.expirado", motivo or "auto_archive",
                    trace_id, event_origin="demo_audit",
                )
                counts["expirado"] += 1
            else:
                counts["skipped"] += 1

        elif kind == "reminder_expiry_5min":
            # Sin transición de recurso — solo marca el evento como
            # disparado. El frontend lee la tabla y muestra el banner
            # correspondiente; no necesita una notificación in-app
            # extra (el countdown ya cubre la UX).
            counts["reminder"] += 1

        else:
            logger.warning(
                "[%s] demo event kind desconocido: %r — saltado", trace_id, kind,
            )
            counts["skipped"] += 1

        # Marcar como disparado independientemente del resultado: si
        # `skipped` (porque el recurso ya cambió), no queremos reintentar.
        await conn.execute(
            "UPDATE demo_session_events SET fired_at = NOW() WHERE id = $1",
            ev["id"],
        )

    return {
        "tenant_id": tenant_id,
        "trace_id": trace_id,
        "processed": len(pending),
        **counts,
    }


if __name__ == "__main__":
    asyncio.run(run_audit_cron())
