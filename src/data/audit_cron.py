import asyncio
import json
import logging
import os
import uuid

from src.data.db import DatabaseManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Período de gracia tras el cual un recurso en cuarentena se expira de
# verdad (F-05.2). Permite al usuario rescatar antes de la expiración.
GRACE_PERIOD_DAYS = int(os.getenv("OBSOLESCENCE_GRACE_DAYS", "30"))


async def _emit_outbox_per_tenant(
    conn,
    rows,
    evento_tipo: str,
    motivo: str,
    trace_id: str,
):
    """Emite un evento outbox por cada tenant que tenga linkeado el recurso."""
    for row in rows:
        tenants = await conn.fetch(
            "SELECT tenant_id FROM usuario_recursos WHERE recurso_id = $1",
            row["id"],
        )
        for t in tenants:
            payload = {
                "event_origin": "audit_cron",
                "trace_id": trace_id,
                "recurso_id": str(row["id"]),
                "url": row["url"],
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
                t["tenant_id"], row["id"], evento_tipo, json.dumps(payload),
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


if __name__ == "__main__":
    asyncio.run(run_audit_cron())
