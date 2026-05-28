"""Detección de caducidad en el momento de ingerir (no esperar al cron).

Cubre `save_with_outbox` cuando el LLM extrae `expiration_date`:
  - fecha pasada → recurso entra directo en `cuarentena` con motivo `caducidad`
  - fecha futura → comportamiento normal, fecha_caducidad = la extraída
  - sin fecha → fallback a `estimated_useful_life_days`

Patrón de cleanup espejo de tests/test_quarantine_lifecycle.py."""
import json
from datetime import date, datetime, timedelta

import pytest

from src.data.db import DatabaseManager, GRACE_PERIOD_DAYS


def _fmt(d: date) -> str:
    return d.isoformat()


@pytest.mark.asyncio
async def test_save_with_past_expiration_date_quarantines():
    db = DatabaseManager()
    await db.connect()
    tenant_id = "tenant_test_past_exp"
    trace_id = "trc-past-exp"
    url = "https://example.test/eventos/concierto-2024-pasado"
    recurso_id = None
    try:
        past = date.today() - timedelta(days=10)
        extracted = {
            "title": "Concierto pasado",
            "summary": "Evento ya celebrado",
            "category": "entertainment",
            "keywords": ["evento"],
            "volatility_score": "alta",
            "estimated_useful_life_days": 60,
            "expiration_date": _fmt(past),
        }
        recurso_id = await db.save_with_outbox(tenant_id, trace_id, extracted, url)
        assert recurso_id is not None

        async with db.pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT estado, fecha_caducidad, quarantine_reason,
                          quarantine_grace_until, quarantined_at
                   FROM usuario_recursos
                   WHERE tenant_id = $1 AND recurso_id = $2""",
                tenant_id, recurso_id,
            )
            assert row["estado"] == "cuarentena"
            # Migración 0012 + compute_audit_decision: el motivo per evento
            # pasado pasa a 'evento_pasado' (no 'caducidad').
            assert row["quarantine_reason"] == "evento_pasado"
            # Migración 0012: las decisiones sobre pasado limpian fecha_caducidad.
            assert row["fecha_caducidad"] is None
            assert row["quarantined_at"] is not None
            # gracia ≈ today + GRACE_PERIOD_DAYS, tolerando ±1 día
            expected_grace = date.today() + timedelta(days=GRACE_PERIOD_DAYS)
            delta = abs((row["quarantine_grace_until"] - expected_grace).days)
            assert delta <= 1

            evt = await conn.fetchrow(
                """SELECT evento_tipo, payload FROM outbox_eventos
                   WHERE agregado_id = $1 AND tenant_id = $2""",
                recurso_id, tenant_id,
            )
            assert evt is not None
            assert evt["evento_tipo"] == "recurso.cuarentena"
            payload = json.loads(evt["payload"])
            assert payload["motivo"] == "evento_pasado"
            assert payload["url"] == url
    finally:
        async with db.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM outbox_eventos WHERE tenant_id = $1", tenant_id,
            )
            await conn.execute(
                "DELETE FROM usuario_recursos WHERE tenant_id = $1", tenant_id,
            )
            if recurso_id:
                await conn.execute("DELETE FROM recursos WHERE id = $1", recurso_id)
        await db.close()


@pytest.mark.asyncio
async def test_save_with_future_expiration_date_uses_it():
    db = DatabaseManager()
    await db.connect()
    tenant_id = "tenant_test_future_exp"
    trace_id = "trc-future-exp"
    url = "https://example.test/eventos/conferencia-futura"
    recurso_id = None
    try:
        future = date.today() + timedelta(days=90)
        extracted = {
            "title": "Conferencia",
            "summary": "Evento próximo",
            "category": "education",
            "keywords": ["evento"],
            "volatility_score": "media",
            "estimated_useful_life_days": 30,
            "expiration_date": _fmt(future),
        }
        recurso_id = await db.save_with_outbox(tenant_id, trace_id, extracted, url)

        async with db.pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT estado, fecha_caducidad, quarantine_reason,
                          quarantine_grace_until
                   FROM usuario_recursos
                   WHERE tenant_id = $1 AND recurso_id = $2""",
                tenant_id, recurso_id,
            )
            assert row["estado"] == "procesando"
            # La fecha extraída debe sobrescribir el cálculo basado en useful_life
            assert row["fecha_caducidad"] == future
            assert row["quarantine_reason"] is None
            assert row["quarantine_grace_until"] is None

            evt_tipo = await conn.fetchval(
                """SELECT evento_tipo FROM outbox_eventos
                   WHERE agregado_id = $1 AND tenant_id = $2""",
                recurso_id, tenant_id,
            )
            assert evt_tipo == "recurso.procesado"
    finally:
        async with db.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM outbox_eventos WHERE tenant_id = $1", tenant_id,
            )
            await conn.execute(
                "DELETE FROM usuario_recursos WHERE tenant_id = $1", tenant_id,
            )
            if recurso_id:
                await conn.execute("DELETE FROM recursos WHERE id = $1", recurso_id)
        await db.close()


@pytest.mark.asyncio
async def test_save_without_expiration_date_falls_back_to_useful_life():
    """Comportamiento legacy: sin `expiration_date`, fecha_caducidad = today + useful_life."""
    db = DatabaseManager()
    await db.connect()
    tenant_id = "tenant_test_no_exp"
    trace_id = "trc-no-exp"
    url = "https://example.test/articulo-sin-fecha"
    recurso_id = None
    try:
        extracted = {
            "title": "Artículo perenne",
            "summary": "Tutorial sin fecha de caducidad explícita",
            "category": "technology",
            "keywords": ["python"],
            "volatility_score": "baja",
            "estimated_useful_life_days": 60,
            # sin expiration_date
        }
        recurso_id = await db.save_with_outbox(tenant_id, trace_id, extracted, url)

        async with db.pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT estado, fecha_caducidad FROM usuario_recursos
                    WHERE tenant_id = $1 AND recurso_id = $2""",
                tenant_id, recurso_id,
            )
            assert row["estado"] == "procesando"
            expected = date.today() + timedelta(days=60)
            delta = abs((row["fecha_caducidad"] - expected).days)
            assert delta <= 1

            evt_tipo = await conn.fetchval(
                """SELECT evento_tipo FROM outbox_eventos
                   WHERE agregado_id = $1 AND tenant_id = $2""",
                recurso_id, tenant_id,
            )
            assert evt_tipo == "recurso.procesado"
    finally:
        async with db.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM outbox_eventos WHERE tenant_id = $1", tenant_id,
            )
            await conn.execute(
                "DELETE FROM usuario_recursos WHERE tenant_id = $1", tenant_id,
            )
            if recurso_id:
                await conn.execute("DELETE FROM recursos WHERE id = $1", recurso_id)
        await db.close()


@pytest.mark.asyncio
async def test_save_with_today_expiration_date_quarantines():
    """Caso borde: fecha_caducidad = HOY debe considerarse ya caducada
    (mismo criterio que el cron: `fecha_caducidad <= NOW()::DATE`)."""
    db = DatabaseManager()
    await db.connect()
    tenant_id = "tenant_test_today_exp"
    trace_id = "trc-today-exp"
    url = "https://example.test/oferta-vence-hoy"
    recurso_id = None
    try:
        today = date.today()
        extracted = {
            "title": "Oferta",
            "summary": "Vence hoy",
            "category": "business",
            "keywords": ["oferta"],
            "volatility_score": "dinamica",
            "estimated_useful_life_days": 30,
            "expiration_date": _fmt(today),
        }
        recurso_id = await db.save_with_outbox(tenant_id, trace_id, extracted, url)

        async with db.pool.acquire() as conn:
            estado = await conn.fetchval(
                """SELECT estado FROM usuario_recursos
                    WHERE tenant_id = $1 AND recurso_id = $2""",
                tenant_id, recurso_id,
            )
            assert estado == "cuarentena"
    finally:
        async with db.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM outbox_eventos WHERE tenant_id = $1", tenant_id,
            )
            await conn.execute(
                "DELETE FROM usuario_recursos WHERE tenant_id = $1", tenant_id,
            )
            if recurso_id:
                await conn.execute("DELETE FROM recursos WHERE id = $1", recurso_id)
        await db.close()
