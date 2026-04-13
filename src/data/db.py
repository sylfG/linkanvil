import asyncpg
import os
import json
import logging
import hashlib
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self, db_url: str = None):
        self.db_url = db_url or os.getenv(
            "DATABASE_URL", 
            "postgresql://cerebro:cerebro_db_pass@localhost:5432/cerebro_brain"
        )
        self.pool = None

    async def connect(self):
        logger.info(f"Conectando a PostgreSQL... {self.db_url}")
        self.pool = await asyncpg.create_pool(self.db_url, min_size=1, max_size=10)
        logger.info("Conectado a PostgreSQL exitosamente")

    async def close(self):
        if self.pool:
            await self.pool.close()
            logger.info("Desconectado de PostgreSQL")

    async def save_with_outbox(self, tenant_id: str, trace_id: str, extracted_data: dict, url: str):
        """
        Implementa el Patrón Outbox transaccional (F-03.1) garantizando la
        inserción atómica en 'recursos' y 'outbox_eventos' bajo RLS (tenant isolation).
        """
        if not self.pool:
            await self.connect()

        url_hash = hashlib.sha256(url.encode('utf-8')).hexdigest()
        
        titulo = extracted_data.get("title", "")
        resumen = extracted_data.get("summary", "")
        categoria = extracted_data.get("category", "other")
        tags_list = extracted_data.get("keywords", [])
        tags = json.dumps(tags_list)
        
        volatilidad = extracted_data.get("volatility_score", "media")
        
        vol_map = {"low": "baja", "medium": "media", "high": "alta"}
        volatilidad = vol_map.get(volatilidad, "media")

        useful_life = extracted_data.get("estimated_useful_life_days", 30)
        fecha_caducidad = datetime.utcnow() + timedelta(days=useful_life)
        estado = "procesando"

        recurso_id = None

        logger.info(f"Guardando transaccionalmente recurso + outbox evento. Tenant ID: {tenant_id}")
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    INSERT INTO recursos (
                        tenant_id, url, url_hash, titulo, resumen, categoria, tags, 
                        volatilidad, fecha_caducidad, estado
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9, $10
                    )
                    ON CONFLICT (tenant_id, url_hash)
                    DO UPDATE SET
                        titulo = EXCLUDED.titulo,
                        resumen = EXCLUDED.resumen,
                        categoria = EXCLUDED.categoria,
                        tags = EXCLUDED.tags,
                        volatilidad = EXCLUDED.volatilidad,
                        fecha_caducidad = EXCLUDED.fecha_caducidad,
                        estado = EXCLUDED.estado,
                        updated_at = NOW()
                    RETURNING id
                    """,
                    tenant_id, url, url_hash, titulo, resumen, categoria, tags,
                    volatilidad, fecha_caducidad, estado
                )
                
                recurso_id = row['id']
                
                outbox_payload = {
                    "event_origin": "scraper_worker",
                    "trace_id": trace_id,
                    "recurso_id": str(recurso_id),
                    "url": url,
                    "extracted_info": extracted_data
                }
                
                await conn.execute(
                    """
                    INSERT INTO outbox_eventos (
                        tenant_id, agregado_tipo, agregado_id, evento_tipo, payload
                    ) VALUES (
                        $1, 'recurso', $2, 'recurso.procesado', $3::jsonb
                    )
                    """,
                    tenant_id, recurso_id, json.dumps(outbox_payload)
                )
                
        logger.info(f"[{trace_id}] Guardado finalizado con ID {recurso_id}")
        return recurso_id