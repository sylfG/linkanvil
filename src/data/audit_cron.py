import asyncio
import logging
import uuid
import json
from datetime import datetime
from data.db import DatabaseManager

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
            # 1. Buscamos y marcamos aquellos que expiraron.
            # estado pasará a 'obsoleto' si estaban en 'procesando' o 'completado' o lo que sea
            # excepto si ya son 'obsoleto'.
            rows = await conn.fetch(
                """
                UPDATE recursos
                SET estado = 'obsoleto',
                    updated_at = NOW()
                WHERE fecha_caducidad <= NOW()
                  AND estado != 'obsoleto'
                RETURNING id, tenant_id, url
                """
            )
            
            if rows:
                logger.info(f"[{trace_id}] Se auditaron/obsoletaron {len(rows)} recursos caducados.")
                
                # 2. Generar eventos outbox para cada uno para que los embeddings asíncronos también se enteren (arquitectura orientada a eventos)
                for row in rows:
                    outbox_payload = {
                        "event_origin": "audit_cron",
                        "trace_id": trace_id,
                        "recurso_id": str(row['id']),
                        "url": row['url'],
                        "motivo": "caducidad_superada"
                    }
                    
                    await conn.execute(
                        """
                        INSERT INTO outbox_eventos (
                            tenant_id, agregado_tipo, agregado_id, evento_tipo, payload
                        ) VALUES (
                            $1, 'recurso', $2, 'recurso.obsoleto', $3::jsonb
                        )
                        """,
                        row['tenant_id'], row['id'], json.dumps(outbox_payload)
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