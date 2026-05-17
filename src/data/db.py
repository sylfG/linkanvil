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

# Preset por defecto (Equilibrado) que sirve también como fail-safe del
# cache si la consulta a usuarios.audit_policy falla. Coincide bit-a-bit
# con el DEFAULT de la columna en la migración 0007.
DEFAULT_AUDIT_POLICY: dict[str, str] = {
    "evento_pasado_alto": "expirado",
    "evento_pasado_medio": "cuarentena",
    "evento_pasado_nulo": "cuarentena",
    "referencia_pasada_alto": "expirado",
    "referencia_pasada_medio": "cuarentena",
    "referencia_pasada_nulo": "cuarentena",
}

POLICY_KEYS = frozenset(DEFAULT_AUDIT_POLICY.keys())
POLICY_VALUES = frozenset({"activo", "cuarentena", "expirado"})


class DatabaseManager:
    # Cache de policy JSONB en memoria de proceso. La invalidación se hace
    # explícitamente desde el endpoint `PUT /profile/audit-policy`. No
    # usamos Redis para no acoplar workers al cliente redis; los workers
    # son pocos y reinician con cada deploy.
    _policy_cache: dict[str, tuple[dict[str, str], float]] = {}
    _POLICY_TTL_SEC = 60.0

    def __init__(self, db_url: str = None):
        self.db_url = db_url or os.getenv(
            "DATABASE_URL",
            "postgresql://cerebro:cerebro_db_pass_CHANGE_ME@localhost:5432/cerebro_brain"
        )
        self.pool = None

    async def _get_user_audit_policy(self, tenant_id: str) -> dict[str, str]:
        """Devuelve la policy de auditoría del tenant como dict con 6 keys.
        Cachea 60s en memoria del proceso. Fail-safe: si la consulta falla
        o el JSON está malformado, devuelve DEFAULT_AUDIT_POLICY (equivale
        al preset Equilibrado)."""
        import time
        now = time.monotonic()
        cached = self._policy_cache.get(tenant_id)
        if cached and cached[1] > now:
            return cached[0]
        if not self.pool:
            await self.connect()
        policy = dict(DEFAULT_AUDIT_POLICY)
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT audit_policy FROM usuarios WHERE tenant_id = $1",
                    tenant_id,
                )
            raw = row["audit_policy"] if row else None
            if isinstance(raw, str):
                raw = json.loads(raw)
            if isinstance(raw, dict):
                # Solo aceptamos keys y values conocidos; el resto se ignora
                # para no propagar configuraciones rotas a la decisión.
                for k in POLICY_KEYS:
                    v = raw.get(k)
                    if v in POLICY_VALUES:
                        policy[k] = v
        except Exception as exc:
            logger.warning(f"_get_user_audit_policy fallback (default): {exc}")
        self._policy_cache[tenant_id] = (policy, now + self._POLICY_TTL_SEC)
        return policy

    @classmethod
    def invalidate_policy_cache(cls, tenant_id: str | None = None) -> None:
        """Llamar tras `PUT /profile/audit-policy`. Si tenant_id=None,
        purga toda la cache (útil en tests)."""
        if tenant_id is None:
            cls._policy_cache.clear()
        else:
            cls._policy_cache.pop(tenant_id, None)

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
        parsed_event = _parse_iso_date(extracted_data.get("event_date"))
        today = datetime.utcnow().date()

        # Nuevos campos del LLM (migración 0006). Defaults seguros si el
        # LLM falló: temporal_class='evento', valor='medio' → comportamiento
        # equivalente al previo a la migración.
        temporal_class = extracted_data.get("temporal_class", "evento")
        if temporal_class not in ("evento", "referencia", "evergreen"):
            temporal_class = "evento"
        valor_archivistico = extracted_data.get("valor_archivistico", "medio")
        if valor_archivistico not in ("alto", "medio", "nulo"):
            valor_archivistico = "medio"
        fecha_evento = parsed_event

        # Policy de auditoría del tenant (6 keys, valores activo|cuarentena|expirado).
        # Reemplaza al strictness enum: ahora cada celda (class × valor)
        # se decide individualmente. Ver migración 0007.
        policy = await self._get_user_audit_policy(tenant_id)

        # fecha_caducidad: solo aplica a temporal_class='evento' futuro.
        # Para 'referencia' y 'evergreen', o cualquier 'evento' con fecha
        # pasada, queda NULL (los recursos pasados se gestionan vía policy,
        # no por cron de caducidad).
        if temporal_class == "evento":
            if parsed_exp is not None:
                fecha_caducidad = parsed_exp
            else:
                fecha_caducidad = today + timedelta(days=useful_life)
        else:
            fecha_caducidad = None

        event_past = fecha_evento is not None and fecha_evento <= today
        caducidad_past = fecha_caducidad is not None and fecha_caducidad <= today
        pasado = event_past or caducidad_past

        # Decisión policy-driven. Solo aplica a contenido pasado no-evergreen.
        # Casos triviales (evergreen, evento futuro, referencia futura) caen
        # al default: estado='procesando' → activo tras embedder.
        estado = "procesando"
        quarantine_reason = None
        quarantine_grace_until = None
        quarantined_at = None
        auto_archive_pending = False
        evento_tipo = "recurso.procesado"

        if temporal_class != "evergreen" and pasado:
            # Componer la key según la clase. Las 6 keys del JSONB siguen
            # un esquema {evento_pasado|referencia_pasada}_{alto|medio|nulo}.
            if temporal_class == "evento":
                key = f"evento_pasado_{valor_archivistico}"
            else:  # referencia
                key = f"referencia_pasada_{valor_archivistico}"
            # Si el LLM produjo un valor archivístico inesperado, key no
            # existirá en la policy; default conservador = cuarentena.
            decision = policy.get(key, "cuarentena")
            # Las decisiones sobre "pasado" siempre limpian fecha_caducidad
            # — el ciclo de caducidad ya no aplica una vez se categoriza
            # el recurso como histórico/archivable.
            fecha_caducidad = None
            if decision == "cuarentena":
                estado = "cuarentena"
                quarantine_reason = "evento_pasado"
                quarantine_grace_until = today + timedelta(days=GRACE_PERIOD_DAYS)
                quarantined_at = datetime.utcnow()
                evento_tipo = "recurso.cuarentena"
            elif decision == "expirado":
                # Auto-archive: el recurso pasa por el embedder igualmente
                # (para tener chunks indexados en Qdrant, accesibles vía
                # Archivo ON en chat) pero al terminar el embedder lo
                # transiciona a 'expirado' en lugar de 'activo'.
                auto_archive_pending = True
            # decision == "activo" → no-op, queda procesando→activo

        recurso_id = None

        logger.info(
            f"Guardando recurso global + link tenant + outbox. Tenant={tenant_id} "
            f"estado={estado} caducidad={fecha_caducidad} class={temporal_class} "
            f"valor={valor_archivistico} fecha_evento={fecha_evento} "
            f"auto_archive={auto_archive_pending}"
        )
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    INSERT INTO recursos (
                        url, url_hash, titulo, resumen, contenido, categoria, tags,
                        volatilidad, fecha_caducidad, estado,
                        quarantined_at, quarantine_reason, quarantine_grace_until,
                        temporal_class, valor_archivistico, fecha_evento,
                        auto_archive_pending
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9, $10,
                        $11, $12, $13, $14, $15, $16, $17
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
                        temporal_class = EXCLUDED.temporal_class,
                        valor_archivistico = EXCLUDED.valor_archivistico,
                        fecha_evento = EXCLUDED.fecha_evento,
                        auto_archive_pending = EXCLUDED.auto_archive_pending,
                        updated_at = NOW()
                    RETURNING id
                    """,
                    url, url_hash, titulo, resumen, contenido, categoria, tags,
                    volatilidad, fecha_caducidad, estado,
                    quarantined_at, quarantine_reason, quarantine_grace_until,
                    temporal_class, valor_archivistico, fecha_evento,
                    auto_archive_pending,
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
                if estado == "cuarentena":
                    outbox_payload["motivo"] = quarantine_reason
                elif auto_archive_pending:
                    # Pista al embedder: tras vectorizar, transicionar a
                    # 'expirado' en lugar de 'activo'. Lectura redundante
                    # con la columna en BD, pero ahorra una query.
                    outbox_payload["auto_archive_pending"] = True

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
        """`estado` es global (recurso.activo/procesando/expirado/cuarentena).
        No filtra por tenant.

        Defensa en profundidad para transiciones del embedder:
        - 'activo' solo se acepta desde 'procesando' Y solo cuando el flag
          auto_archive_pending es FALSE. Si está TRUE, el embedder debería
          haber llamado con estado='expirado' (caso auto-archive).
        - 'expirado' desde 'procesando' solo se acepta si auto_archive_pending
          es TRUE. Cualquier otra transición a 'expirado' (cron, manual)
          pasa por la rama 'else' (sin condiciones).

        Sin este guard, el embedder (con sesgo de 'finalizar = activo')
        revertía recursos ya transicionados a 'cuarentena'/'expirado' por
        el ciclo de obsolescencia (audit_cron, colisión semántica, rescate
        manual) o ignoraría la decisión de auto-archive del scraper."""
        if not self.pool:
            await self.connect()
        async with self.pool.acquire() as conn:
            if estado == "activo":
                # El embedder marca como activo: requiere estar en procesando
                # y NO tener auto_archive_pending (si lo tiene, debió pedir
                # estado='expirado' en su lugar). El flag se limpia al
                # transicionar a estado final.
                await conn.execute(
                    """UPDATE recursos
                       SET estado = 'activo',
                           auto_archive_pending = false,
                           updated_at = NOW()
                       WHERE id = $1::uuid
                         AND estado = 'procesando'
                         AND auto_archive_pending = false""",
                    recurso_id,
                )
            elif estado == "expirado":
                # Transición del embedder cuando auto_archive_pending=true:
                # solo válida desde 'procesando'. Si el recurso ya está en
                # 'cuarentena' o 'activo', el embedder llega tarde y la
                # decisión del cron/manual gana — esta query no afecta filas.
                # Otras transiciones a 'expirado' (cron, manual desde
                # /quarantine) van por el catch-all del else.
                result = await conn.execute(
                    """UPDATE recursos
                       SET estado = 'expirado',
                           auto_archive_pending = false,
                           updated_at = NOW()
                       WHERE id = $1::uuid
                         AND estado = 'procesando'
                         AND auto_archive_pending = true""",
                    recurso_id,
                )
                # Si no afectó filas, no es un caso auto-archive; aplicamos
                # transición libre (cron expira por gracia, manual desde
                # cuarentena, etc.).
                if result and result.endswith("0"):
                    await conn.execute(
                        "UPDATE recursos SET estado = 'expirado', updated_at = NOW() WHERE id = $1::uuid",
                        recurso_id,
                    )
            else:
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