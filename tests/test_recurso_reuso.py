"""Test del flujo de reuso cross-tenant (post-migración 0012).

Cuando un segundo tenant ingiere una URL ya conocida globalmente, el
scraper aplica la policy del NUEVO tenant a la metadata almacenada y
persiste la decisión en su propia fila `usuario_recursos`. Aquí
ejercitamos el contrato a nivel de DatabaseManager.
"""
import pytest
import hashlib
from datetime import date, datetime, timedelta

from src.data.db import DatabaseManager
from src.data.audit_decision import compute_audit_decision


def _hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


@pytest.mark.asyncio
async def test_reuso_cross_tenant():
    db = DatabaseManager()
    await db.connect()

    tenant_a = "tenant_reuso_A"
    tenant_b = "tenant_reuso_B"
    url = f"https://example.com/reuso-{datetime.utcnow().timestamp()}"
    recurso_id = None

    try:
        # Sembrar un recurso global como si tenant_a ya lo hubiera procesado.
        async with db.pool.acquire() as conn:
            recurso_id = await conn.fetchval(
                """
                INSERT INTO recursos (url, url_hash, titulo, resumen, categoria, tags,
                                      volatilidad, temporal_class, valor_archivistico,
                                      useful_life_days, contenido)
                VALUES ($1, $2, 'Doc reusable', 'resumen', 'tech', '[]'::jsonb,
                        'baja', 'evento', 'alto', 60, 'cuerpo completo del doc')
                ON CONFLICT (url_hash) DO UPDATE SET updated_at = NOW()
                RETURNING id
                """,
                url, _hash(url),
            )
            # Migración 0012: el estado/fecha_caducidad de tenant_a viven aquí.
            await conn.execute(
                """INSERT INTO usuario_recursos (
                        tenant_id, recurso_id, estado, fecha_caducidad
                    ) VALUES ($1, $2, 'activo', (NOW() + INTERVAL '60 day')::DATE)
                    ON CONFLICT DO NOTHING""",
                tenant_a, recurso_id,
            )

        # tenant_b llega: find_existing_recurso_by_url devuelve la
        # metadata intrínseca (no el estado per-tenant).
        existing = await db.find_existing_recurso_by_url(url)
        assert existing is not None, "El recurso global debería ser encontrado"
        assert existing["temporal_class"] == "evento"
        assert existing["valor_archivistico"] == "alto"
        assert existing["useful_life_days"] == 60
        assert existing["has_contenido"] is True

        # El scraper aplica policy del NUEVO tenant. Aquí simulamos una
        # policy equilibrada (default). Como evento_pasado_alto=expirado
        # y la fecha_evento es None (no evento pasado), el caso 'pasado'
        # no aplica: estado='procesando' tras compute (el embedder lo
        # transicionará a 'activo' después).
        policy = {
            "evento_pasado_alto": "expirado",
            "evento_pasado_medio": "cuarentena",
            "evento_pasado_nulo": "cuarentena",
            "referencia_pasada_alto": "expirado",
            "referencia_pasada_medio": "cuarentena",
            "referencia_pasada_nulo": "cuarentena",
        }
        decision = compute_audit_decision(
            temporal_class=existing["temporal_class"],
            valor_archivistico=existing["valor_archivistico"],
            fecha_evento=existing.get("fecha_evento"),
            useful_life_days=existing["useful_life_days"],
            policy=policy,
        )
        assert decision["estado"] == "procesando"
        assert decision["fecha_caducidad"] is not None

        await db.upsert_usuario_recurso_estado(tenant_b, str(existing["id"]), decision)
        await db.emit_reuse_event(tenant_b, "trace-reuso", str(existing["id"]), url)

        # Verificación: ambos tenants linkean el mismo recurso, una sola fila en recursos.
        async with db.pool.acquire() as conn:
            recursos_count = await conn.fetchval(
                "SELECT COUNT(*) FROM recursos WHERE url_hash = $1",
                _hash(url),
            )
            assert recursos_count == 1, "El recurso debe estar deduplicado globalmente"

            # Los dos tenants tienen sus propias filas con estados independientes.
            estados = await conn.fetch(
                """SELECT tenant_id, estado FROM usuario_recursos
                   WHERE recurso_id = $1 ORDER BY tenant_id""",
                recurso_id,
            )
            estado_map = {r["tenant_id"]: r["estado"] for r in estados}
            assert estado_map[tenant_a] == "activo"
            assert estado_map[tenant_b] == "procesando"

            outbox_evt = await conn.fetchval(
                """
                SELECT evento_tipo FROM outbox_eventos
                WHERE tenant_id = $1 AND agregado_id = $2
                ORDER BY creado_en DESC LIMIT 1
                """,
                tenant_b, recurso_id,
            )
            assert outbox_evt == "recurso.reusado", \
                "Debe haberse emitido evento outbox 'recurso.reusado' para tenant_b"

    finally:
        async with db.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM outbox_eventos WHERE tenant_id IN ($1, $2)", tenant_a, tenant_b,
            )
            await conn.execute(
                "DELETE FROM usuario_recursos WHERE tenant_id IN ($1, $2)", tenant_a, tenant_b,
            )
            if recurso_id:
                await conn.execute("DELETE FROM recursos WHERE id = $1", recurso_id)
        await db.close()
