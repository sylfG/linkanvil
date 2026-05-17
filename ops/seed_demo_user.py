#!/usr/bin/env python3
"""Seed idempotente del usuario demo de LinkAnvil.

Crea (si no existe) el usuario demo@linkanvil.io con tenant fijo
'user_demo_landing' y siembra 5 recursos representativos linkeados a su
KB:

- 1 evergreen activo (tutorial atemporal).
- 1 evento futuro activo (con fecha_caducidad futura).
- 1 referencia activa de valor medio.
- 1 referencia archivada por auto_archive (estado='expirado' + chunks).
- 1 recurso en cuarentena con motivo evento_pasado.

Para ejecutar dentro del contenedor cerebro-api:

    docker exec -i cerebro-api python /app/ops/seed_demo_user.py

El script es idempotente: ejecutarlo varias veces no duplica filas.
Recrea los recursos del demo si fueron borrados.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

import asyncpg
import bcrypt

DEMO_EMAIL = "demo@linkanvil.io"
DEMO_PASSWORD = "linkanvil-demo"
DEMO_TENANT_ID = "user_demo_landing"

DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://cerebro:cerebro_db_pass_CHANGE_ME@localhost:5432/cerebro_brain",
)


SEED_RESOURCES = [
    # 1. Evergreen activo — tutorial atemporal sobre Docker.
    {
        "url": "https://docs.docker.com/get-started/overview/",
        "titulo": "Docker Overview — Conceptos fundamentales",
        "resumen": (
            "Introducción oficial a Docker: contenedores, imágenes, "
            "Dockerfile, redes y volúmenes. Documentación canónica del "
            "ecosistema Docker."
        ),
        "categoria": "technology",
        "tags": ["docker", "contenedores", "devops", "tutorial"],
        "volatilidad": "baja",
        "temporal_class": "evergreen",
        "valor_archivistico": "alto",
        "fecha_evento": None,
        "fecha_caducidad": None,
        "estado": "activo",
        "quarantine_reason": None,
        "auto_archive_pending": False,
    },
    # 2. Evento futuro activo — concierto a 3 meses vista.
    {
        "url": "https://www.example-festival.com/lineup-2026",
        "titulo": "Festival Primavera Sound 2026 — Lineup completo",
        "resumen": (
            "El cartel oficial del festival incluye headliners "
            "internacionales del 28 al 30 de mayo de 2026 en Barcelona. "
            "Entradas a la venta hasta agotar aforo."
        ),
        "categoria": "entertainment",
        "tags": ["festival", "música", "barcelona", "2026"],
        "volatilidad": "media",
        "temporal_class": "evento",
        "valor_archivistico": "medio",
        "fecha_evento": "2026-05-28",
        "fecha_caducidad_offset_days": 90,
        "estado": "activo",
        "quarantine_reason": None,
        "auto_archive_pending": False,
    },
    # 3. Referencia activa de valor medio.
    {
        "url": "https://github.com/anthropics/skills",
        "titulo": "anthropics/skills — Public skill repository",
        "resumen": (
            "Repositorio oficial de Anthropic con implementaciones de "
            "Claude Skills para distintos dominios. Las skills son "
            "carpetas de instrucciones reutilizables."
        ),
        "categoria": "technology",
        "tags": ["claude", "skills", "anthropic", "agentes"],
        "volatilidad": "media",
        "temporal_class": "referencia",
        "valor_archivistico": "medio",
        "fecha_evento": None,
        "fecha_caducidad": None,
        "estado": "activo",
        "quarantine_reason": None,
        "auto_archive_pending": False,
    },
    # 4. Referencia archivada (auto_archive) — informe histórico AEMET.
    {
        "url": "https://aemetblog.es/2020/09/18/avance-climatico-nacional-del-verano-2020/",
        "titulo": "Avance Climático Nacional del verano 2020 (AEMET)",
        "resumen": (
            "Informe oficial del verano 2020: segundo verano más cálido "
            "desde 1965, anomalía de +0.9°C. Datos por estaciones, "
            "olas de calor y precipitación acumulada por comunidad."
        ),
        "categoria": "science",
        "tags": ["aemet", "clima", "verano-2020", "informe-oficial"],
        "volatilidad": "baja",
        "temporal_class": "referencia",
        "valor_archivistico": "alto",
        "fecha_evento": "2020-09-18",
        "fecha_caducidad": None,
        "estado": "expirado",
        "quarantine_reason": None,
        "auto_archive_pending": False,
    },
    # 5. Cuarentena por evento_pasado — artículo de prensa sobre feria
    #    pasada con valor medio.
    {
        "url": "https://www.diaridegirona.cat/girona/2024/03/18/expojove-oferira-propostes-d-estudis-99635086.html",
        "titulo": (
            "ExpoJove oferirà propostes d'estudis i de formació a més "
            "de 6.000 visitants"
        ),
        "resumen": (
            "Crónica de la edición 2024 de ExpoJove (Girona). El salón "
            "del estudiante y la formación reunió a centros educativos, "
            "universidades y empresas durante el fin de semana."
        ),
        "categoria": "education",
        "tags": ["expojove", "girona", "feria", "2024"],
        "volatilidad": "media",
        "temporal_class": "referencia",
        "valor_archivistico": "medio",
        "fecha_evento": "2024-03-18",
        "fecha_caducidad": None,
        "estado": "cuarentena",
        "quarantine_reason": "evento_pasado",
        "auto_archive_pending": False,
    },
]


def _url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


async def upsert_demo_user(conn: asyncpg.Connection) -> UUID:
    """Crea o actualiza el usuario demo. Devuelve su id."""
    pwd_hash = bcrypt.hashpw(
        DEMO_PASSWORD.encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")

    row = await conn.fetchrow(
        """
        INSERT INTO cerebro.usuarios (email, password_hash, tenant_id)
        VALUES ($1, $2, $3)
        ON CONFLICT (email) DO UPDATE
            SET password_hash = EXCLUDED.password_hash,
                updated_at = NOW()
        RETURNING id
        """,
        DEMO_EMAIL,
        pwd_hash,
        DEMO_TENANT_ID,
    )
    return row["id"]


async def upsert_resource(
    conn: asyncpg.Connection, tenant_id: str, spec: dict
) -> UUID:
    """Inserta o actualiza un recurso global + asocia al tenant demo."""
    today = date.today()
    fecha_caducidad = spec.get("fecha_caducidad")
    if fecha_caducidad is None and "fecha_caducidad_offset_days" in spec:
        fecha_caducidad = today + timedelta(
            days=spec["fecha_caducidad_offset_days"]
        )

    fecha_evento_str = spec.get("fecha_evento")
    fecha_evento = (
        date.fromisoformat(fecha_evento_str) if fecha_evento_str else None
    )

    estado = spec["estado"]
    qreason = spec.get("quarantine_reason")
    quarantined_at = None
    qgrace = None
    if estado == "cuarentena":
        quarantined_at = datetime.now(timezone.utc)
        qgrace = today + timedelta(days=30)

    url = spec["url"]
    row = await conn.fetchrow(
        """
        INSERT INTO cerebro.recursos (
            url, url_hash, titulo, resumen, contenido, categoria, tags,
            volatilidad, fecha_caducidad, estado,
            quarantined_at, quarantine_reason, quarantine_grace_until,
            temporal_class, valor_archivistico, fecha_evento,
            auto_archive_pending
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9, $10,
            $11, $12, $13, $14, $15, $16, $17
        )
        ON CONFLICT (url_hash) DO UPDATE
            SET titulo = EXCLUDED.titulo,
                resumen = EXCLUDED.resumen,
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
        url,
        _url_hash(url),
        spec["titulo"],
        spec["resumen"],
        spec["resumen"],  # contenido = resumen para el demo (no scrapeamos)
        spec["categoria"],
        json.dumps(spec["tags"]),
        spec["volatilidad"],
        fecha_caducidad,
        estado,
        quarantined_at,
        qreason,
        qgrace,
        spec["temporal_class"],
        spec["valor_archivistico"],
        fecha_evento,
        spec["auto_archive_pending"],
    )
    recurso_id = row["id"]

    await conn.execute(
        """
        INSERT INTO cerebro.usuario_recursos (tenant_id, recurso_id)
        VALUES ($1, $2)
        ON CONFLICT DO NOTHING
        """,
        tenant_id,
        recurso_id,
    )
    return recurso_id


async def main() -> None:
    conn = await asyncpg.connect(DB_URL)
    try:
        # RLS forzada — necesitamos seteo de tenant para INSERT en
        # tablas con políticas.
        await conn.execute(
            f"SET app.tenant_id = '{DEMO_TENANT_ID}'"
        )

        user_id = await upsert_demo_user(conn)
        print(f"✓ Demo user upserted: {DEMO_EMAIL} ({user_id})")

        for spec in SEED_RESOURCES:
            rid = await upsert_resource(conn, DEMO_TENANT_ID, spec)
            print(f"  ✓ {spec['estado']:10s} {spec['url'][:70]}  → {rid}")

        print(f"\nSeed completo. Total recursos sembrados: {len(SEED_RESOURCES)}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
