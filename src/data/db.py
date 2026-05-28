import asyncpg
import os
import json
import logging
import hashlib
from datetime import datetime, date

logger = logging.getLogger(__name__)

# Período de gracia tras detectar caducidad (alineado con audit_cron). Importado
# perezosamente para evitar dependencia circular si audit_cron crece.
GRACE_PERIOD_DAYS = int(os.getenv("OBSOLESCENCE_GRACE_DAYS", "30"))
DEFAULT_USEFUL_LIFE_DAYS = int(os.getenv("DEFAULT_USEFUL_LIFE_DAYS", "30"))

from .audit_decision import compute_audit_decision  # noqa: E402


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
            "postgresql://cerebro:cerebro_db_pass_CHANGE_ME@localhost:5432/cerebro_brain",
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
                # Demo sub-tenants (demo_XXXXX) no tienen su propia fila en
                # usuarios — comparten el row del owner "user_demo_landing".
                # Resolvemos via demo_sessions.user_id. Sin este fallback el
                # scraper SIEMPRE ve DEFAULT_AUDIT_POLICY (Equilibrado)
                # para sesiones demo aunque el usuario haya cambiado a
                # Estricto/Permisivo via /profile (porque el endpoint
                # escribe en user_demo_landing pero el scraper consulta
                # por demo_XXXXX).
                if row is None and tenant_id.startswith("demo_"):
                    row = await conn.fetchrow(
                        """SELECT u.audit_policy
                           FROM usuarios u
                           JOIN demo_sessions ds ON ds.user_id = u.id
                           WHERE ds.tenant_id = $1""",
                        tenant_id,
                    )
            raw = row["audit_policy"] if row else None
            # Defensa frente a filas con doble-encoding historico (el writer
            # antiguo en api/main.py hacia json.dumps + codec.encoder=json.dumps
            # y guardaba un JSONB string que envolvia el objeto). Tambien
            # cubre el caso normal en pools sin codec, donde asyncpg
            # devuelve el JSONB como str y requiere UN solo loads.
            while isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except (TypeError, ValueError):
                    break
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

    async def update_session_context(
        self, tenant_id: str, session_id: str, new_context: str
    ):
        if not self.pool:
            await self.connect()

        # Generate a deterministic UUID from session_id
        import uuid
        import hashlib

        # MD5 usado solo como hash determinista para derivar un UUID de session_id
        # — no es uso criptografico, asi que silenciamos B324.
        m = hashlib.md5(usedforsecurity=False)
        m.update(session_id.encode("utf-8"))
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
                s_uuid,
                tenant_id,
                new_context,
            )

    async def get_session_context(self, tenant_id: str, session_id: str) -> str:
        if not self.pool:
            await self.connect()

        import uuid
        import hashlib

        # MD5 usado solo como hash determinista para derivar un UUID de session_id
        # — no es uso criptografico, asi que silenciamos B324.
        m = hashlib.md5(usedforsecurity=False)
        m.update(session_id.encode("utf-8"))
        s_uuid = uuid.UUID(m.hexdigest())

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT contexto_comprimido FROM sesiones_chat WHERE id = $1 AND tenant_id = $2",
                s_uuid,
                tenant_id,
            )
            return (
                row["contexto_comprimido"] if row and row["contexto_comprimido"] else ""
            )

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
                # Migración 0012: el estado vive ahora en usuario_recursos
                # (per-tenant). recursos solo guarda metadata intrínseca
                # del contenido. El placeholder se queda en estado='procesando'
                # hasta que el embedder lo transicione.
                row = await conn.fetchrow(
                    """
                    INSERT INTO recursos (url, url_hash)
                    VALUES ($1, $2)
                    ON CONFLICT (url_hash) DO UPDATE SET updated_at = NOW()
                    RETURNING id
                    """,
                    url,
                    url_hash,
                )
                recurso_id = row["id"]
                await conn.execute(
                    """
                    INSERT INTO usuario_recursos (tenant_id, recurso_id, estado)
                    VALUES ($1, $2, 'procesando')
                    ON CONFLICT DO NOTHING
                    """,
                    tenant_id,
                    recurso_id,
                )
        return str(recurso_id)

    async def find_existing_recurso_by_url(self, url: str) -> dict | None:
        """Busca un recurso global por url_hash. Devuelve la metadata
        intrínseca del contenido (id, temporal_class, valor_archivistico,
        fecha_evento, useful_life_days, has_contenido) o None si no existe.

        Migración 0012: el estado/fecha_caducidad ya no son globales; el
        caller (scraper fast-path) debe calcular su propia decisión usando
        `compute_audit_decision` con la policy del nuevo tenant."""
        if not self.pool:
            await self.connect()

        url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, titulo, temporal_class, valor_archivistico, fecha_evento,
                       useful_life_days,
                       (contenido IS NOT NULL AND length(contenido) > 0) AS has_contenido
                FROM recursos WHERE url_hash = $1
                """,
                url_hash,
            )
            return dict(row) if row else None

    async def upsert_usuario_recurso_estado(
        self,
        tenant_id: str,
        recurso_id: str,
        decision: dict,
    ) -> None:
        """Persiste la decisión de auditoría per-tenant en `usuario_recursos`.

        Migración 0012: usado por el scraper fast-path (reuso global) para
        que el nuevo tenant tenga SU PROPIO estado, no el del tenant que
        ingestó la URL la primera vez. Idempotente: si la fila ya existe,
        se actualiza con la decisión nueva."""
        if not self.pool:
            await self.connect()
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO usuario_recursos (
                    tenant_id, recurso_id, estado,
                    quarantined_at, quarantine_reason, quarantine_grace_until,
                    auto_archive_pending, fecha_caducidad, updated_at
                ) VALUES (
                    $1, $2::uuid, $3, $4, $5, $6, $7, $8, NOW()
                )
                ON CONFLICT (tenant_id, recurso_id) DO UPDATE SET
                    estado = EXCLUDED.estado,
                    quarantined_at = EXCLUDED.quarantined_at,
                    quarantine_reason = EXCLUDED.quarantine_reason,
                    quarantine_grace_until = EXCLUDED.quarantine_grace_until,
                    auto_archive_pending = EXCLUDED.auto_archive_pending,
                    fecha_caducidad = EXCLUDED.fecha_caducidad,
                    updated_at = NOW()
                """,
                tenant_id,
                recurso_id,
                decision["estado"],
                decision["quarantined_at"],
                decision["quarantine_reason"],
                decision["quarantine_grace_until"],
                decision["auto_archive_pending"],
                decision["fecha_caducidad"],
            )

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
                tenant_id,
                recurso_id,
            )

    async def save_with_outbox(
        self,
        tenant_id: str,
        trace_id: str,
        extracted_data: dict,
        url: str,
        contenido: str | None = None,
    ):
        """
        Patrón Outbox transaccional (F-03.1): upsert global en `recursos`,
        link en `usuario_recursos` y evento en `outbox_eventos`, todo atómico.
        El recurso es global (sin tenant_id); el evento conserva tenant_id
        para que el embedder genere el punto Qdrant aislado por tenant.
        """
        if not self.pool:
            await self.connect()

        url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()

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

        # Migración 0012: la decisión per-tenant se calcula con el helper
        # compartido `compute_audit_decision` (mismo path para el camino
        # completo del scraper y para el fast-path de reuso).
        temporal_class = extracted_data.get("temporal_class", "evento")
        valor_archivistico = extracted_data.get("valor_archivistico", "medio")
        fecha_evento = parsed_event

        # useful_life_days: lo guardamos en `recursos` para que el fast-path
        # pueda recalcular fecha_caducidad para nuevos tenants sin LLM.
        # Si el LLM dio una expiration_date explícita, derivamos los días
        # (puede ser pasado → será negativo, el helper lo trata como pasado).
        if parsed_exp is not None:
            useful_life_days = (parsed_exp - today).days
        else:
            useful_life_days = useful_life if temporal_class == "evento" else None

        # Policy de auditoría del tenant (6 keys, valores activo|cuarentena|expirado).
        policy = await self._get_user_audit_policy(tenant_id)

        decision = compute_audit_decision(
            temporal_class=temporal_class,
            valor_archivistico=valor_archivistico,
            fecha_evento=fecha_evento,
            useful_life_days=useful_life_days,
            policy=policy,
            today=today,
        )
        estado = decision["estado"]
        quarantine_reason = decision["quarantine_reason"]
        quarantine_grace_until = decision["quarantine_grace_until"]
        quarantined_at = decision["quarantined_at"]
        auto_archive_pending = decision["auto_archive_pending"]
        fecha_caducidad = decision["fecha_caducidad"]
        evento_tipo = (
            "recurso.cuarentena" if estado == "cuarentena" else "recurso.procesado"
        )

        recurso_id = None

        logger.info(
            f"Guardando recurso global + link tenant + outbox. Tenant={tenant_id} "
            f"estado={estado} caducidad={fecha_caducidad} class={temporal_class} "
            f"valor={valor_archivistico} fecha_evento={fecha_evento} "
            f"auto_archive={auto_archive_pending}"
        )
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # UPSERT en recursos: solo metadata intrínseca del contenido.
                # El estado per-tenant se persiste aparte en usuario_recursos.
                row = await conn.fetchrow(
                    """
                    INSERT INTO recursos (
                        url, url_hash, titulo, resumen, contenido, categoria, tags,
                        volatilidad,
                        temporal_class, valor_archivistico, fecha_evento,
                        useful_life_days
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9, $10, $11, $12
                    )
                    ON CONFLICT (url_hash)
                    DO UPDATE SET
                        titulo = EXCLUDED.titulo,
                        resumen = EXCLUDED.resumen,
                        contenido = EXCLUDED.contenido,
                        categoria = EXCLUDED.categoria,
                        tags = EXCLUDED.tags,
                        volatilidad = EXCLUDED.volatilidad,
                        temporal_class = EXCLUDED.temporal_class,
                        valor_archivistico = EXCLUDED.valor_archivistico,
                        fecha_evento = EXCLUDED.fecha_evento,
                        useful_life_days = EXCLUDED.useful_life_days,
                        updated_at = NOW()
                    RETURNING id
                    """,
                    url,
                    url_hash,
                    titulo,
                    resumen,
                    contenido,
                    categoria,
                    tags,
                    volatilidad,
                    temporal_class,
                    valor_archivistico,
                    fecha_evento,
                    useful_life_days,
                )

                recurso_id = row["id"]

                # UPSERT en usuario_recursos con la decisión per-tenant.
                # Si el tenant ya tenía la URL linkeada (re-ingest tras
                # delete o re-policy), sobreescribimos el estado con la
                # decisión actual.
                await conn.execute(
                    """
                    INSERT INTO usuario_recursos (
                        tenant_id, recurso_id, estado,
                        quarantined_at, quarantine_reason, quarantine_grace_until,
                        auto_archive_pending, fecha_caducidad, updated_at
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8, NOW()
                    )
                    ON CONFLICT (tenant_id, recurso_id) DO UPDATE SET
                        estado = EXCLUDED.estado,
                        quarantined_at = EXCLUDED.quarantined_at,
                        quarantine_reason = EXCLUDED.quarantine_reason,
                        quarantine_grace_until = EXCLUDED.quarantine_grace_until,
                        auto_archive_pending = EXCLUDED.auto_archive_pending,
                        fecha_caducidad = EXCLUDED.fecha_caducidad,
                        updated_at = NOW()
                    """,
                    tenant_id,
                    recurso_id,
                    estado,
                    quarantined_at,
                    quarantine_reason,
                    quarantine_grace_until,
                    auto_archive_pending,
                    fecha_caducidad,
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
                    tenant_id,
                    recurso_id,
                    evento_tipo,
                    json.dumps(outbox_payload),
                )

        logger.info(f"[{trace_id}] Guardado finalizado con ID {recurso_id}")
        return recurso_id

    async def emit_quarantine_event_for_reuse(
        self,
        tenant_id: str,
        trace_id: str,
        recurso_id: str,
        url: str,
        motivo: str,
        titulo: str | None = None,
    ) -> None:
        """Emite outbox `recurso.cuarentena` cuando el scraper fast-path
        ha aplicado la policy y el resultado es cuarentena.

        El emit_reuse_event va siempre (lo consume el embedder para
        copiar el vector Qdrant). Pero el notifier-worker filtra por
        RELEVANT_EVENTS = {cuarentena, expirado, rescatado} y NO crea
        notificacion para `recurso.reusado`. Sin este evento extra, la
        campana queda muda aunque la fila usuario_recursos este en
        cuarentena."""
        if not self.pool:
            await self.connect()
        payload = {
            "event_origin": "scraper_worker_reuse",
            "trace_id": trace_id,
            "recurso_id": str(recurso_id),
            "url": url,
            "motivo": motivo,
            "titulo": titulo,
        }
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO outbox_eventos (
                    tenant_id, agregado_tipo, agregado_id, evento_tipo, payload
                ) VALUES (
                    $1, 'recurso', $2::uuid, 'recurso.cuarentena', $3::jsonb
                )
                """,
                tenant_id,
                recurso_id,
                json.dumps(payload),
            )

    async def emit_reuse_event(
        self, tenant_id: str, trace_id: str, recurso_id: str, url: str
    ) -> None:
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
                tenant_id,
                recurso_id,
                json.dumps(payload),
            )

    async def update_recurso_estado(
        self,
        tenant_id: str,
        recurso_id: str,
        estado: str,
    ):
        """Migración 0012: el estado vive en `usuario_recursos` (per-tenant).
        Esta función actualiza la fila (tenant_id, recurso_id).

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
                await conn.execute(
                    """UPDATE usuario_recursos
                       SET estado = 'activo',
                           auto_archive_pending = false,
                           updated_at = NOW()
                       WHERE tenant_id = $1
                         AND recurso_id = $2::uuid
                         AND estado = 'procesando'
                         AND auto_archive_pending = false""",
                    tenant_id,
                    recurso_id,
                )
            elif estado == "expirado":
                result = await conn.execute(
                    """UPDATE usuario_recursos
                       SET estado = 'expirado',
                           auto_archive_pending = false,
                           updated_at = NOW()
                       WHERE tenant_id = $1
                         AND recurso_id = $2::uuid
                         AND estado = 'procesando'
                         AND auto_archive_pending = true""",
                    tenant_id,
                    recurso_id,
                )
                # Si no afectó filas, no es auto-archive; transición libre.
                if result and result.endswith("0"):
                    await conn.execute(
                        """UPDATE usuario_recursos
                           SET estado = 'expirado', updated_at = NOW()
                           WHERE tenant_id = $1 AND recurso_id = $2::uuid""",
                        tenant_id,
                        recurso_id,
                    )
            else:
                await conn.execute(
                    """UPDATE usuario_recursos
                       SET estado = $1, updated_at = NOW()
                       WHERE tenant_id = $2 AND recurso_id = $3::uuid""",
                    estado,
                    tenant_id,
                    recurso_id,
                )

    async def quarantine_recurso_blocked(self, tenant_id: str, recurso_id: str):
        """Mueve a cuarentena (per-tenant) un recurso que el scraper no
        pudo extraer por bloqueo anti-bot. Motivo 'manual' por el CHECK
        constraint actual. Migración 0012: opera sobre usuario_recursos."""
        if not self.pool:
            await self.connect()
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE usuario_recursos
                SET estado = 'cuarentena',
                    quarantined_at = NOW(),
                    quarantine_reason = 'manual',
                    quarantine_grace_until = (NOW() + INTERVAL '30 days')::DATE,
                    updated_at = NOW()
                WHERE tenant_id = $1 AND recurso_id = $2::uuid
                """,
                tenant_id,
                recurso_id,
            )

    async def save_semantic_collisions(
        self, tenant_id: str, recurso_origen: str, collisions: list[dict]
    ):
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
                        tenant_id,
                        recurso_origen,
                        c["recurso_destino"],
                        min(c["similitud"], 1.0),
                        tipo_relacion,
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
                        tenant_id,
                        c["recurso_destino"],
                        recurso_origen,
                        min(c["similitud"], 1.0),
                        tipo_inverso,
                    )

                    # Si es obsolescencia, mandamos el destino (antiguo) a cuarentena
                    # con período de gracia, no a 'expirado' directamente: el usuario
                    # debe poder rescatar antes de la limpieza definitiva (F-05.2).
                    # Migración 0012: la cuarentena se aplica per-tenant en
                    # TODOS los tenants linkeados al recurso_destino (preserva
                    # el comportamiento previo de "cuarentena global").
                    if tipo_relacion in ["VUELVE_OBSOLETO", "CONTRADICE"]:
                        grace_days = int(os.getenv("OBSOLESCENCE_GRACE_DAYS", "30"))
                        moved_rows = await conn.fetch(
                            """
                            UPDATE usuario_recursos ur
                            SET estado = 'cuarentena',
                                quarantined_at = NOW(),
                                quarantine_reason = 'colision_semantica',
                                quarantine_grace_until = (NOW() + ($2::int * INTERVAL '1 day'))::DATE,
                                updated_at = NOW()
                            FROM recursos r
                            WHERE ur.recurso_id = $1::uuid
                              AND ur.recurso_id = r.id
                              AND ur.estado = 'activo'
                            RETURNING ur.tenant_id, r.id, r.url
                            """,
                            c["recurso_destino"],
                            grace_days,
                        )
                        for moved in moved_rows:
                            payload = {
                                "event_origin": "semantic_collider",
                                "recurso_id": str(moved["id"]),
                                "url": moved["url"],
                                "motivo": "colision_semantica",
                                "tipo_relacion": tipo_relacion,
                                "recurso_origen": recurso_origen,
                            }
                            await conn.execute(
                                """
                                INSERT INTO outbox_eventos (
                                    tenant_id, agregado_tipo, agregado_id,
                                    evento_tipo, payload
                                ) VALUES (
                                    $1, 'recurso', $2, 'recurso.cuarentena', $3::jsonb
                                )
                                """,
                                moved["tenant_id"],
                                moved["id"],
                                json.dumps(payload),
                            )
