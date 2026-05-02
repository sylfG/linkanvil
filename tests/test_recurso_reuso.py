"""Test del flujo de reuso cross-tenant.

Cuando un segundo tenant ingiere una URL ya conocida globalmente, el scraper
debe asociarla vía `link_user_to_recurso` y emitir `recurso.reusado` por
outbox sin volver a hacer scrape ni llamar al LLM. Aquí ejercitamos el
contrato a nivel de DatabaseManager (las llamadas que el scraper hace en
la rama de reuso).
"""
import pytest
import hashlib
from datetime import datetime, timedelta

from src.data.db import DatabaseManager


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
                                      volatilidad, fecha_caducidad, estado)
                VALUES ($1, $2, 'Doc reusable', 'resumen', 'tech', '[]'::jsonb,
                        'baja', NOW() + INTERVAL '60 day', 'activo')
                ON CONFLICT (url_hash) DO UPDATE SET updated_at = NOW()
                RETURNING id
                """,
                url, _hash(url),
            )
            await conn.execute(
                "INSERT INTO usuario_recursos (tenant_id, recurso_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                tenant_a, recurso_id,
            )

        # tenant_b consulta: debe encontrar el recurso global como activo y fresco.
        existing = await db.find_existing_recurso_by_url(url)
        assert existing is not None, "El recurso global debería ser encontrado"
        assert existing["estado"] == "activo"
        assert existing["fecha_caducidad"] > (datetime.utcnow().date() + timedelta(days=15))

        # Asociación cross-tenant + evento de reuso.
        await db.link_user_to_recurso(tenant_b, str(existing["id"]))
        await db.emit_reuse_event(tenant_b, "trace-reuso", str(existing["id"]), url)

        # Verificación: ambos tenants linkean el mismo recurso, hay 1 sola fila en `recursos`.
        async with db.pool.acquire() as conn:
            recursos_count = await conn.fetchval(
                "SELECT COUNT(*) FROM recursos WHERE url_hash = $1",
                _hash(url),
            )
            assert recursos_count == 1, "El recurso debe estar deduplicado globalmente"

            tenants_with_link = await conn.fetch(
                "SELECT tenant_id FROM usuario_recursos WHERE recurso_id = $1 ORDER BY tenant_id",
                recurso_id,
            )
            tenant_set = {r["tenant_id"] for r in tenants_with_link}
            assert tenant_a in tenant_set and tenant_b in tenant_set

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
