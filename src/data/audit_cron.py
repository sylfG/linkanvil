import asyncio
import logging
import uuid
import json
from datetime import datetime
from src.data.db import DatabaseManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def run_audit_cron():
    """
    F-05.1 — Auditoría Temporal Relacional (Cron SQL ultrarrápido)
    Identifica recursos cuya fecha_caducidad ha sido superada y los marca como obsoletos,
    ahorrando tiempo/costo de LLM.
    """
    logger.info("Iniciando tarea de auditoría temporal relacional...")
    db = DatabaseManager()
    await db.connect()
    
    trace_id = str(uuid.uuid4())
    
    try:
        async with db.pool.acquire() as conn:
            # 1. Marcamos los recursos cuya fecha_caducidad ha expirado.
            # `recursos` es global, así que el cambio aplica a todos los tenants
            # que tengan la URL en su KB.
            rows = await conn.fetch(
                """
                UPDATE recursos
                SET estado = 'expirado',
                    updated_at = NOW()
                WHERE fecha_caducidad <= NOW()
                  AND estado != 'expirado'
                RETURNING id, url
                """
            )

            if rows:
                logger.info(f"[{trace_id}] {len(rows)} recursos marcados como expirados.")

                # 2. Para cada recurso, emitir un evento outbox por cada tenant que
                # lo tiene linkeado, así el flujo de notificaciones llega a cada usuario.
                for row in rows:
                    tenants = await conn.fetch(
                        "SELECT tenant_id FROM usuario_recursos WHERE recurso_id = $1",
                        row['id'],
                    )
                    for t in tenants:
                        outbox_payload = {
                            "event_origin": "audit_cron",
                            "trace_id": trace_id,
                            "recurso_id": str(row['id']),
                            "url": row['url'],
                            "motivo": "caducidad_superada",
                        }
                        await conn.execute(
                            """
                            INSERT INTO outbox_eventos (
                                tenant_id, agregado_tipo, agregado_id, evento_tipo, payload
                            ) VALUES (
                                $1, 'recurso', $2, 'recurso.expirado', $3::jsonb
                            )
                            """,
                            t['tenant_id'], row['id'], json.dumps(outbox_payload),
                        )
            else:
                logger.info(f"[{trace_id}] No se encontraron recursos caducados activos en esta ejecución.")
                
    except Exception as e:
        logger.error(f"[{trace_id}] Error durante la auditoría cron: {e}")
    finally:
        await db.close()
        logger.info("Finalizada la tarea de auditoría.")

if __name__ == "__main__":
    asyncio.run(run_audit_cron())