import asyncpg
import os
import json
import logging
import hashlib
from datetime import datetime, timedelta, date

logger = logging.getLogger(__name__)

# Período de gracia tras detectar caducidad (alineado con audit_cron). Importado
# perezosamente para evitar dependencia circular si audit_cron crece.
GRACE_PERIOD_DAYS = int(os.getenv("OBSOLESCENCE_GRACE_DAYS", "30"))


def _parse_iso_date(value) -> date | None:
    """Acepta str ISO (YYYY-MM-DD o ISO datetime) o None. Devuelve date o None."""
    if not value or not isinstance(value, str):
        return None
    try:
        # fromisoformat acepta tanto YYYY-MM-DD como YYYY-MM-DDTHH:MM:SS
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.date()
    except ValueError:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None

class DatabaseManager:
    def __init__(self, db_url: str = None):
        self.db_url = db_url or os.getenv(
            "DATABASE_URL", 
            "postgresql://cerebro:cerebro_db_pass_CHANGE_ME@localhost:5432/cerebro_brain"
        )
        self.pool = None

    async def update_session_context(self, tenant_id: str, session_id: str, new_context: str):
        if not self.pool:
            await self.connect()

        # Generate a deterministic UUID from session_id
        import uuid, hashlib
        m = hashlib.md5()
        m.update(session_id.encode('utf-8'))
        s_uuid = uuid.UUID(m.hexdigest())

        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO sesiones_chat (id, tenant_id, contexto_comprimido, ultimo_acceso)
                VALUES ($1, $2, $3, NOW())
                ON CONFLICT (id) DO UPDATE SET 
                    contexto_comprimido = EXCLUDED.contexto_comprimido,
                    ultimo_acceso = NOW()
                """,
                s_uuid, tenant_id, new_context
            )

    async def get_session_context(self, tenant_id: str, session_id: str) -> str:
        if not self.pool:
            await self.connect()

        import uuid, hashlib
        m = hashlib.md5()
        m.update(session_id.encode('utf-8'))
        s_uuid = uuid.UUID(m.hexdigest())

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT contexto_comprimido FROM sesiones_chat WHERE id = $1 AND tenant_id = $2",
                s_uuid, tenant_id
            )
            return row['contexto_comprimido'] if row and row['contexto_comprimido'] else ""

    async def connect(self):
        logger.info(f"Conectando a PostgreSQL... {self.db_url}")
        self.pool = await asyncpg.create_pool(self.db_url, min_size=1, max_size=10)
        logger.info("Conectado a PostgreSQL exitosamente")

    async def close(self):
        if self.pool:
            await self.pool.close()
            logger.info("Desconectado de PostgreSQL")

    async def insert_placeholder_recurso(self, tenant_id: str, url: str) -> str:
        """Garantiza que existe una fila en `recursos` para la URL y la asocia al
        tenant vía `usuario_recursos`. Devuelve el `recurso_id` (UUID como str).
        Permite que la URL aparezca en la KB del usuario inmediatamente con
        estado='procesando' antes de que el scraper extraiga los metadatos."""
        if not self.pool:
            await self.connect()

        url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    INSERT INTO recursos (url, url_hash, estado)
                    VALUES ($1, $2, 'procesando')
                    ON CONFLICT (url_hash) DO UPDATE SET updated_at = NOW()
                    RETURNING id
                    """,
                    url, url_hash,
                )
                recurso_id = row["id"]
                await conn.execute(
                    """
                    INSERT INTO usuario_recursos (tenant_id, recurso_id)
                    VALUES ($1, $2)
                    ON CONFLICT DO NOTHING
                    """,
                    tenant_id, recurso_id,
                )
        return str(recurso_id)

    async def find_existing_recurso_by_url(self, url: str) -> dict | None:
        """Busca un recurso global por url_hash. Devuelve dict con
        id, estado, fecha_caducidad o None si no existe."""
        if not self.pool:
            await self.connect()

        url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, estado, fecha_caducidad,
                       (contenido IS NOT NULL AND length(contenido) > 0) AS has_contenido
                FROM recursos WHERE url_hash = $1
                """,
                url_hash,
            )
            return dict(row) if row else None

    async def link_user_to_recurso(self, tenant_id: str, recurso_id: str) -> None:
        """Asocia un recurso global existente a un tenant. Idempotente."""
        if not self.pool:
            await self.connect()
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO usuario_recursos (tenant_id, recurso_id)
                VALUES ($1, $2::uuid)
                ON CONFLICT DO NOTHING
                """,
                tenant_id, recurso_id,
            )

    async def save_with_outbox(self, tenant_id: str, trace_id: str, extracted_data: dict, url: str, contenido: str | None = None):
        """
        Patrón Outbox transaccional (F-03.1): upsert global en `recursos`,
        link en `usuario_recursos` y evento en `outbox_eventos`, todo atómico.
        El recurso es global (sin tenant_id); el evento conserva tenant_id
        para que el embedder genere el punto Qdrant aislado por tenant.
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
        parsed_exp = _parse_iso_date(extracted_data.get("expiration_date"))
        today = datetime.utcnow().date()

        if parsed_exp is not None:
            fecha_caducidad = parsed_exp
        else:
            fecha_caducidad = today + timedelta(days=useful_life)

        already_expired = fecha_caducidad <= today
        if already_expired:
            estado = "cuarentena"
            quarantine_reason = "caducidad"
            quarantine_grace_until = today + timedelta(days=GRACE_PERIOD_DAYS)
            quarantined_at = datetime.utcnow()
            evento_tipo = "recurso.cuarentena"
        else:
            estado = "procesando"
            quarantine_reason = None
            quarantine_grace_until = None
            quarantined_at = None
            evento_tipo = "recurso.procesado"

        recurso_id = None

        logger.info(
            f"Guardando recurso global + link tenant + outbox. Tenant={tenant_id} "
            f"estado={estado} caducidad={fecha_caducidad}"
        )
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    INSERT INTO recursos (
                        url, url_hash, titulo, resumen, contenido, categoria, tags,
                        volatilidad, fecha_caducidad, estado,
                        quarantined_at, quarantine_reason, quarantine_grace_until
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9, $10,
                        $11, $12, $13
                    )
                    ON CONFLICT (url_hash)
                    DO UPDATE SET
                        titulo = EXCLUDED.titulo,
                        resumen = EXCLUDED.resumen,
                        contenido = EXCLUDED.contenido,
                        categoria = EXCLUDED.categoria,
                        tags = EXCLUDED.tags,
                        volatilidad = EXCLUDED.volatilidad,
                        fecha_caducidad = EXCLUDED.fecha_caducidad,
                        estado = EXCLUDED.estado,
                        quarantined_at = EXCLUDED.quarantined_at,
                        quarantine_reason = EXCLUDED.quarantine_reason,
                        quarantine_grace_until = EXCLUDED.quarantine_grace_until,
                        updated_at = NOW()
                    RETURNING id
                    """,
                    url, url_hash, titulo, resumen, contenido, categoria, tags,
                    volatilidad, fecha_caducidad, estado,
                    quarantined_at, quarantine_reason, quarantine_grace_until,
                )

                recurso_id = row['id']

                await conn.execute(
                    """
                    INSERT INTO usuario_recursos (tenant_id, recurso_id)
                    VALUES ($1, $2)
                    ON CONFLICT DO NOTHING
                    """,
                    tenant_id, recurso_id,
                )

                outbox_payload = {
                    "event_origin": "scraper_worker",
                    "trace_id": trace_id,
                    "recurso_id": str(recurso_id),
                    "url": url,
                    "extracted_info": extracted_data,
                    # contenido viaja en el evento para que el embedder pueda chunkear
                    # sin tener que releer Postgres; recursos.contenido queda como
                    # fuente de verdad para re-embedding/backfill futuros.
                    "contenido": contenido or "",
                }
                if already_expired:
                    outbox_payload["motivo"] = "caducidad"

                await conn.execute(
                    """
                    INSERT INTO outbox_eventos (
                        tenant_id, agregado_tipo, agregado_id, evento_tipo, payload
                    ) VALUES (
                        $1, 'recurso', $2, $3, $4::jsonb
                    )
                    """,
                    tenant_id, recurso_id, evento_tipo, json.dumps(outbox_payload)
                )

        logger.info(f"[{trace_id}] Guardado finalizado con ID {recurso_id}")
        return recurso_id

    async def emit_reuse_event(self, tenant_id: str, trace_id: str, recurso_id: str, url: str) -> None:
        """Emite un evento outbox `recurso.reusado` para que el embedder copie
        el punto Qdrant existente al nuevo tenant en lugar de regenerar el embedding."""
        if not self.pool:
            await self.connect()

        payload = {
            "event_origin": "scraper_worker",
            "trace_id": trace_id,
            "recurso_id": str(recurso_id),
            "url": url,
            "reused": True,
        }
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO outbox_eventos (
                    tenant_id, agregado_tipo, agregado_id, evento_tipo, payload
                ) VALUES (
                    $1, 'recurso', $2::uuid, 'recurso.reusado', $3::jsonb
                )
                """,
                tenant_id, recurso_id, json.dumps(payload),
            )

    async def update_recurso_estado(self, recurso_id: str, estado: str):
        """`estado` es global (recurso.activo/procesando/expirado). No filtra por tenant."""
        if not self.pool:
            await self.connect()
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE recursos SET estado = $1, updated_at = NOW() WHERE id = $2::uuid",
                estado, recurso_id,
            )

    async def quarantine_recurso_blocked(self, recurso_id: str):
        """Mueve un recurso a cuarentena porque el scraper recibió una página
        de bloqueo anti-bot y no podemos extraer el contenido. Usa el motivo
        'manual' (no hay valor 'scrape_bloqueado' en el CHECK constraint
        actual; añadirlo requiere migración aparte). El periodo de gracia es
        el mismo que para caducidad."""
        if not self.pool:
            await self.connect()
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE recursos
                SET estado = 'cuarentena',
                    quarantined_at = NOW(),
                    quarantine_reason = 'manual',
                    quarantine_grace_until = (NOW() + INTERVAL '30 days')::DATE,
                    updated_at = NOW()
                WHERE id = $1::uuid
                """,
                recurso_id,
            )

    async def save_semantic_collisions(self, tenant_id: str, recurso_origen: str, collisions: list[dict]):
        if not self.pool:
            await self.connect()

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                for c in collisions:
                    tipo_relacion = c.get("tipo_relacion", "ASOCIACION_GENERAL")
                    await conn.execute(
                        """
                        INSERT INTO grafo_relaciones (
                            tenant_id, recurso_origen, recurso_destino, similitud, tipo_relacion
                        ) VALUES (
                            $1, $2::uuid, $3::uuid, $4, $5
                        )
                        ON CONFLICT (recurso_origen, recurso_destino) 
                        DO UPDATE SET similitud = EXCLUDED.similitud, tipo_relacion = EXCLUDED.tipo_relacion
                        """,
                        tenant_id, recurso_origen, c["recurso_destino"], min(c["similitud"], 1.0), tipo_relacion
                    )
                    
                    # Relación bidireccional (inversa)
                    # Si es VUELVE_OBSOLETO, la inversa podríamos llamarla OBSOLETO_POR
                    tipo_inverso = tipo_relacion
                    if tipo_relacion == "VUELVE_OBSOLETO":
                        tipo_inverso = "OBSOLECIDO_POR"
                    elif tipo_relacion == "EXTIENDE":
                        tipo_inverso = "EXTENDIDO_POR"
                        
                    await conn.execute(
                        """
                        INSERT INTO grafo_relaciones (
                            tenant_id, recurso_origen, recurso_destino, similitud, tipo_relacion
                        ) VALUES (
                            $1, $2::uuid, $3::uuid, $4, $5
                        )
                        ON CONFLICT (recurso_origen, recurso_destino) 
                        DO UPDATE SET similitud = EXCLUDED.similitud, tipo_relacion = EXCLUDED.tipo_relacion
                        """,
                        tenant_id, c["recurso_destino"], recurso_origen, min(c["similitud"], 1.0), tipo_inverso
                    )

                    # Si es obsolescencia, mandamos el destino (antiguo) a cuarentena
                    # con período de gracia, no a 'expirado' directamente: el usuario
                    # debe poder rescatar antes de la limpieza definitiva (F-05.2).
                    # `recursos` es global → no se filtra por tenant_id.
                    if tipo_relacion in ["VUELVE_OBSOLETO", "CONTRADICE"]:
                        grace_days = int(os.getenv("OBSOLESCENCE_GRACE_DAYS", "30"))
                        moved = await conn.fetchrow(
                            """
                            UPDATE recursos
                            SET estado = 'cuarentena',
                                quarantined_at = NOW(),
                                quarantine_reason = 'colision_semantica',
                                quarantine_grace_until = (NOW() + ($2::int * INTERVAL '1 day'))::DATE,
                                updated_at = NOW()
                            WHERE id = $1::uuid AND estado = 'activo'
                            RETURNING id, url
                            """,
                            c["recurso_destino"], grace_days,
                        )
                        if moved:
                            payload = {
                                "event_origin": "semantic_collider",
                                "recurso_id": str(moved["id"]),
                                "url": moved["url"],
                                "motivo": "colision_semantica",
                                "tipo_relacion": tipo_relacion,
                                "recurso_origen": recurso_origen,
                            }
                            tenants = await conn.fetch(
                                "SELECT tenant_id FROM usuario_recursos WHERE recurso_id = $1",
                                moved["id"],
                            )
                            for t in tenants:
                                await conn.execute(
                                    """
                                    INSERT INTO outbox_eventos (
                                        tenant_id, agregado_tipo, agregado_id,
                                        evento_tipo, payload
                                    ) VALUES (
                                        $1, 'recurso', $2, 'recurso.cuarentena', $3::jsonb
                                    )
                                    """,
                                    t["tenant_id"], moved["id"], json.dumps(payload),
                                )