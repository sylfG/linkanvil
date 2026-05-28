#!/usr/bin/env python3
"""Seed idempotente del usuario demo de LinkAnvil.

Crea (si no existe) el usuario demo@linkanvil.io con tenant fijo
``user_demo_landing``, lo marca como ``is_demo=true`` y siembra una
selección amplia de recursos representativos que cubre las distintas
clasificaciones temporales × valor archivístico × categorías.

Categorías cubiertas
--------------------
- **Recetas** (food, evergreen): ejemplos de uso doméstico.
- **Repos de IA famosos** (technology, referencia): proyectos canónicos.
- **Papers arXiv** (science, referencia valor alto).
- **Eventos futuros** (entertainment/science, evento + caducidad futura).
- **Eventos pasados de alto valor** (referencia + ``expirado`` por
  auto-archive).
- **Cuarentena por evento_pasado** (referencia + cuarentena).
- **Documentación atemporal** (technology, evergreen).

BYOK del demo
-------------
El demo lleva ``is_demo=true`` y tres virtual-keys cifradas (Fernet)
en columnas ``llm_key_lite``, ``llm_key_embeddings``, ``llm_key_pro``.
Las claves plaintext se leen de env-vars antes de cifrar::

    DEMO_KEY_LITE=sk-litellm-virtual-xxxx
    DEMO_KEY_EMBEDDINGS=sk-litellm-virtual-yyyy
    DEMO_KEY_PRO=sk-litellm-virtual-zzzz

Si alguna falta, ese campo se deja NULL y el demo no podrá usar el
alias correspondiente hasta que el owner re-corra el seed con la
env-var poblada. ``LLM_KEYS_ENCRYPTION_KEY`` también es requerida.

Para ejecutar (desde el host remoto, vía el contenedor cerebro-api)::

    docker cp ops/seed_demo_user.py cerebro-api:/tmp/seed_demo_user.py
    docker exec -i cerebro-api python /tmp/seed_demo_user.py

Idempotente: ejecutar varias veces no duplica filas. Recrea recursos
borrados y re-cifra las keys (cada ejecución produce ciphertext nuevo
porque Fernet incluye IV aleatorio — el plaintext se preserva).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

import asyncpg
import bcrypt

# Importamos crypto.py del propio repo (montado en /app/src/api dentro
# del contenedor cerebro-api). Si se ejecuta el script desde el host,
# añadir /root/linkanvil/src al PYTHONPATH antes.
sys.path.insert(0, "/app/src")  # contenedor
sys.path.insert(0, "/root/linkanvil/src")  # host (fallback)
from api.crypto import encrypt_llm_key  # noqa: E402

DEMO_EMAIL = "demo@linkanvil.io"
DEMO_PASSWORD = "linkanvil-demo"
DEMO_TENANT_ID = "user_demo_landing"

DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://cerebro:cerebro_db_pass_CHANGE_ME@localhost:5432/cerebro_brain",
)

DEMO_KEYS_PLAINTEXT = {
    "lite": os.getenv("DEMO_KEY_LITE"),
    "embeddings": os.getenv("DEMO_KEY_EMBEDDINGS"),
    "pro": os.getenv("DEMO_KEY_PRO"),
}


# ---------------------------------------------------------------------------
# Catálogo de recursos sembrados (18 entradas, cobertura amplia)
# ---------------------------------------------------------------------------
SEED_RESOURCES = [
    # ---------- Recetas (food, evergreen y referencia) ------------------
    {
        "url": "https://www.lecturas.com/recetas/nutricion/menu-semanal-saludable-cocina-facil-ensaladas-pollo-tortillas-postres-para-disfrutar-sin-remordimientos_21973",
        "titulo": "Menú semanal saludable — Lecturas",
        "resumen": (
            "Propuesta de menú semanal equilibrado: ensaladas, pollo, "
            "tortillas y postres saludables. Recetas familiares para "
            "comer sano sin renunciar al sabor."
        ),
        "categoria": "food",
        "tags": ["recetas", "menu-semanal", "nutricion", "saludable"],
        "volatilidad": "baja",
        "temporal_class": "referencia",
        "valor_archivistico": "medio",
        "fecha_evento": None,
        "fecha_caducidad": None,
        "estado": "activo",
        "quarantine_reason": None,
        "auto_archive_pending": False,
    },
    {
        "url": "https://www.recetasderechupete.com/paella-valenciana-receta-tradicional/29677/",
        "titulo": "Paella Valenciana tradicional — Recetas de Rechupete",
        "resumen": (
            "Receta canónica de paella valenciana con pollo, conejo, "
            "garrofó, judía verde y arroz bomba. Tiempos exactos y "
            "trucos para el socarrat."
        ),
        "categoria": "food",
        "tags": ["paella", "valencia", "receta-tradicional", "arroz"],
        "volatilidad": "baja",
        "temporal_class": "evergreen",
        "valor_archivistico": "alto",
        "fecha_evento": None,
        "fecha_caducidad": None,
        "estado": "activo",
        "quarantine_reason": None,
        "auto_archive_pending": False,
    },
    # ---------- Repos de IA famosos (technology, referencia alta) -------
    {
        "url": "https://github.com/openai/whisper",
        "titulo": "openai/whisper — Robust speech recognition",
        "resumen": (
            "Modelo open-source de OpenAI para transcripción multilingüe "
            "y traducción de audio a texto. Entrenado con 680k horas de "
            "audio supervisado de la web."
        ),
        "categoria": "technology",
        "tags": ["openai", "whisper", "asr", "speech-to-text"],
        "volatilidad": "media",
        "temporal_class": "referencia",
        "valor_archivistico": "alto",
        "fecha_evento": None,
        "fecha_caducidad": None,
        "estado": "activo",
        "quarantine_reason": None,
        "auto_archive_pending": False,
    },
    {
        "url": "https://github.com/huggingface/transformers",
        "titulo": "huggingface/transformers — State-of-the-art ML",
        "resumen": (
            "Librería de referencia para modelos transformer en PyTorch, "
            "TensorFlow y JAX. Incluye BERT, GPT-2, T5, Llama, Mistral "
            "y miles de checkpoints pre-entrenados del Hub."
        ),
        "categoria": "technology",
        "tags": ["huggingface", "transformers", "llm", "nlp"],
        "volatilidad": "media",
        "temporal_class": "referencia",
        "valor_archivistico": "alto",
        "fecha_evento": None,
        "fecha_caducidad": None,
        "estado": "activo",
        "quarantine_reason": None,
        "auto_archive_pending": False,
    },
    {
        "url": "https://github.com/langchain-ai/langchain",
        "titulo": "langchain-ai/langchain — Framework para LLMs",
        "resumen": (
            "Framework Python/JS para componer aplicaciones con LLMs: "
            "agents, chains, memory, retrievers, tool-use. Estándar de "
            "facto del ecosistema RAG en 2023-2024."
        ),
        "categoria": "technology",
        "tags": ["langchain", "llm", "framework", "agents"],
        "volatilidad": "alta",
        "temporal_class": "referencia",
        "valor_archivistico": "alto",
        "fecha_evento": None,
        "fecha_caducidad": None,
        "estado": "activo",
        "quarantine_reason": None,
        "auto_archive_pending": False,
    },
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
    {
        "url": "https://github.com/sylfG/linkanvil",
        "titulo": "sylfG/linkanvil — Tu segundo cerebro autónomo",
        "resumen": (
            "Repo público del propio LinkAnvil. Self-hosted, multi-tenant, "
            "RAG sobre Qdrant + Postgres con clasificación temporal del "
            "contenido y archivo histórico opt-in."
        ),
        "categoria": "technology",
        "tags": ["linkanvil", "self-hosted", "rag", "knowledge-base"],
        "volatilidad": "alta",
        "temporal_class": "referencia",
        "valor_archivistico": "alto",
        "fecha_evento": None,
        "fecha_caducidad": None,
        "estado": "activo",
        "quarantine_reason": None,
        "auto_archive_pending": False,
    },
    # ---------- Papers arXiv (science, referencia alta) -----------------
    {
        "url": "https://arxiv.org/abs/1706.03762",
        "titulo": "Attention Is All You Need (Vaswani et al., 2017)",
        "resumen": (
            "Paper fundacional de la arquitectura Transformer. Introduce "
            "el mecanismo de self-attention sin recurrencia ni convolución. "
            "Base de todos los LLMs modernos."
        ),
        "categoria": "science",
        "tags": ["transformer", "attention", "paper-canónico", "arxiv"],
        "volatilidad": "baja",
        "temporal_class": "referencia",
        "valor_archivistico": "alto",
        "fecha_evento": "2017-06-12",
        "fecha_caducidad": None,
        "estado": "activo",
        "quarantine_reason": None,
        "auto_archive_pending": False,
    },
    {
        "url": "https://arxiv.org/abs/2310.06825",
        "titulo": "Mistral 7B (Jiang et al., 2023)",
        "resumen": (
            "Modelo abierto de 7B parámetros con sliding-window attention "
            "y grouped-query attention. Supera a Llama 2 13B en la mayoría "
            "de benchmarks con menos cómputo."
        ),
        "categoria": "science",
        "tags": ["mistral", "llm-abierto", "paper", "7b"],
        "volatilidad": "media",
        "temporal_class": "referencia",
        "valor_archivistico": "alto",
        "fecha_evento": "2023-10-10",
        "fecha_caducidad": None,
        "estado": "activo",
        "quarantine_reason": None,
        "auto_archive_pending": False,
    },
    {
        "url": "https://arxiv.org/abs/2307.09288",
        "titulo": "Llama 2 — Open Foundation Models (Touvron et al., 2023)",
        "resumen": (
            "Suite de modelos Llama 2 (7B/13B/70B), pre-entrenados con "
            "2T tokens, con variantes fine-tuned para chat (RLHF). "
            "Licencia comercialmente viable."
        ),
        "categoria": "science",
        "tags": ["llama2", "meta", "open-weights", "paper"],
        "volatilidad": "media",
        "temporal_class": "referencia",
        "valor_archivistico": "alto",
        "fecha_evento": "2023-07-18",
        "fecha_caducidad": None,
        "estado": "activo",
        "quarantine_reason": None,
        "auto_archive_pending": False,
    },
    # ---------- Eventos futuros (evento + caducidad futura) -------------
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
    {
        "url": "https://neurips.cc/Conferences/2026/CallForPapers",
        "titulo": "NeurIPS 2026 — Call for Papers",
        "resumen": (
            "Convocatoria de la 39ª edición de NeurIPS (San Diego, dic "
            "2026). Submission deadline 15 de mayo, decisión 22 de "
            "septiembre. Tracks principales y datasets/benchmarks."
        ),
        "categoria": "science",
        "tags": ["neurips", "conference", "cfp", "2026"],
        "volatilidad": "media",
        "temporal_class": "evento",
        "valor_archivistico": "alto",
        "fecha_evento": "2026-05-15",
        "fecha_caducidad_offset_days": 30,
        "estado": "activo",
        "quarantine_reason": None,
        "auto_archive_pending": False,
    },
    # ---------- Eventos pasados → archivo histórico ---------------------
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
    {
        "url": "https://www.apple.com/newsroom/2023/06/introducing-apple-vision-pro/",
        "titulo": "Apple Vision Pro — Anuncio WWDC 2023",
        "resumen": (
            "Comunicado de prensa de Apple sobre el anuncio del Vision "
            "Pro durante la keynote del WWDC 2023. Spatial computing, "
            "M2+R1, visionOS y casos de uso."
        ),
        "categoria": "technology",
        "tags": ["apple", "wwdc-2023", "vision-pro", "keynote"],
        "volatilidad": "baja",
        "temporal_class": "referencia",
        "valor_archivistico": "alto",
        "fecha_evento": "2023-06-05",
        "fecha_caducidad": None,
        "estado": "expirado",
        "quarantine_reason": None,
        "auto_archive_pending": False,
    },
    # ---------- Cuarentena por evento_pasado (medio) --------------------
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
    # ---------- Documentación atemporal (evergreen) ---------------------
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
    {
        "url": "https://kubernetes.io/docs/concepts/overview/",
        "titulo": "Kubernetes — Conceptos generales",
        "resumen": (
            "Documentación oficial de Kubernetes: arquitectura, control "
            "plane, workloads, networking, storage. Punto de entrada "
            "canónico al ecosistema."
        ),
        "categoria": "technology",
        "tags": ["kubernetes", "k8s", "orquestación", "tutorial"],
        "volatilidad": "baja",
        "temporal_class": "evergreen",
        "valor_archivistico": "alto",
        "fecha_evento": None,
        "fecha_caducidad": None,
        "estado": "activo",
        "quarantine_reason": None,
        "auto_archive_pending": False,
    },
    {
        "url": "https://docs.python.org/3/tutorial/",
        "titulo": "Python Tutorial — docs oficial",
        "resumen": (
            "Tutorial oficial de Python 3: tipos, control de flujo, "
            "funciones, módulos, OOP, I/O y librería estándar. "
            "Referencia atemporal para principiantes."
        ),
        "categoria": "technology",
        "tags": ["python", "tutorial", "oficial", "documentación"],
        "volatilidad": "baja",
        "temporal_class": "evergreen",
        "valor_archivistico": "alto",
        "fecha_evento": None,
        "fecha_caducidad": None,
        "estado": "activo",
        "quarantine_reason": None,
        "auto_archive_pending": False,
    },
]


def _url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def _encrypted_demo_keys() -> dict[str, str | None]:
    """Cifra las claves plaintext de las env-vars DEMO_KEY_*.

    Si una env-var no está set, deja NULL en esa posición (la columna
    queda sin actualizar). El demo no podrá usar ese alias hasta que
    el owner re-corra el seed con la env-var poblada.
    """
    out: dict[str, str | None] = {}
    for kind, plaintext in DEMO_KEYS_PLAINTEXT.items():
        out[kind] = encrypt_llm_key(plaintext) if plaintext else None
    return out


async def upsert_demo_user(conn: asyncpg.Connection) -> UUID:
    """Crea o actualiza el usuario demo. Marca is_demo=true y carga las
    3 keys cifradas si las env-vars DEMO_KEY_* están presentes.
    Devuelve el id del usuario.
    """
    pwd_hash = bcrypt.hashpw(
        DEMO_PASSWORD.encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")

    encrypted = _encrypted_demo_keys()
    configured = any(v is not None for v in encrypted.values())

    row = await conn.fetchrow(
        """
        INSERT INTO usuarios (
            email, password_hash, tenant_id, is_demo,
            llm_key_lite, llm_key_embeddings, llm_key_pro,
            llm_keys_configured
        )
        VALUES ($1, $2, $3, true, $4, $5, $6, $7)
        ON CONFLICT (email) DO UPDATE
            SET password_hash = EXCLUDED.password_hash,
                is_demo = true,
                llm_key_lite = COALESCE(
                    EXCLUDED.llm_key_lite, usuarios.llm_key_lite),
                llm_key_embeddings = COALESCE(
                    EXCLUDED.llm_key_embeddings, usuarios.llm_key_embeddings),
                llm_key_pro = COALESCE(
                    EXCLUDED.llm_key_pro, usuarios.llm_key_pro),
                llm_keys_configured = (
                    COALESCE(EXCLUDED.llm_key_lite, usuarios.llm_key_lite) IS NOT NULL
                    OR COALESCE(EXCLUDED.llm_key_embeddings, usuarios.llm_key_embeddings) IS NOT NULL
                    OR COALESCE(EXCLUDED.llm_key_pro, usuarios.llm_key_pro) IS NOT NULL
                ),
                updated_at = NOW()
        RETURNING id
        """,
        DEMO_EMAIL,
        pwd_hash,
        DEMO_TENANT_ID,
        encrypted["lite"],
        encrypted["embeddings"],
        encrypted["pro"],
        configured,
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
    # Migración 0012: `recursos` ahora solo contiene campos globales.
    # estado / fecha_caducidad / quarantine_* / auto_archive_pending viven
    # en `usuario_recursos` per-tenant.
    row = await conn.fetchrow(
        """
        INSERT INTO recursos (
            url, url_hash, titulo, resumen, contenido, categoria, tags,
            volatilidad, temporal_class, valor_archivistico, fecha_evento
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9, $10, $11
        )
        ON CONFLICT (url_hash) DO UPDATE
            SET titulo = EXCLUDED.titulo,
                resumen = EXCLUDED.resumen,
                categoria = EXCLUDED.categoria,
                tags = EXCLUDED.tags,
                volatilidad = EXCLUDED.volatilidad,
                temporal_class = EXCLUDED.temporal_class,
                valor_archivistico = EXCLUDED.valor_archivistico,
                fecha_evento = EXCLUDED.fecha_evento,
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
        spec["temporal_class"],
        spec["valor_archivistico"],
        fecha_evento,
    )
    recurso_id = row["id"]

    # Linkeo per-tenant con los campos de estado/policy.
    await conn.execute(
        """
        INSERT INTO usuario_recursos (
            tenant_id, recurso_id, estado, fecha_caducidad,
            quarantined_at, quarantine_reason, quarantine_grace_until,
            auto_archive_pending
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (tenant_id, recurso_id) DO UPDATE
            SET estado = EXCLUDED.estado,
                fecha_caducidad = EXCLUDED.fecha_caducidad,
                quarantined_at = EXCLUDED.quarantined_at,
                quarantine_reason = EXCLUDED.quarantine_reason,
                quarantine_grace_until = EXCLUDED.quarantine_grace_until,
                auto_archive_pending = EXCLUDED.auto_archive_pending,
                updated_at = NOW()
        """,
        tenant_id,
        recurso_id,
        estado,
        fecha_caducidad,
        quarantined_at,
        qreason,
        qgrace,
        spec["auto_archive_pending"],
    )
    return recurso_id


async def main() -> None:
    # Gate de ejecución: el seed solo corre cuando SEED_DEMO=true.
    # Permite que en producción el contenedor cerebro-seed-demo arranque
    # y salga limpio sin tocar BD (idempotente vía exit 0). En dev,
    # poner SEED_DEMO=true en .env para auto-poblar el demo.
    if os.getenv("SEED_DEMO", "").lower() not in ("1", "true", "yes"):
        print(
            "SEED_DEMO no está activado — saltando seed del demo. "
            "Setea SEED_DEMO=true para ejecutar."
        )
        return

    conn = await asyncpg.connect(DB_URL)
    try:
        # RLS forzada — necesitamos seteo de tenant para INSERT en
        # tablas con políticas.
        await conn.execute(
            f"SET app.tenant_id = '{DEMO_TENANT_ID}'"
        )

        user_id = await upsert_demo_user(conn)
        print(f"✓ Demo user upserted: {DEMO_EMAIL} ({user_id})")

        missing = [k for k, v in DEMO_KEYS_PLAINTEXT.items() if not v]
        if missing:
            print(
                f"  ⚠ DEMO_KEY_* env-vars no configuradas: {missing}. "
                "El demo no podrá usar esos aliases LLM hasta que el "
                "owner re-corra el seed con las variables pobladas."
            )
        else:
            print("  ✓ 3 virtual-keys cifradas (Fernet) y guardadas.")

        for spec in SEED_RESOURCES:
            rid = await upsert_resource(conn, DEMO_TENANT_ID, spec)
            print(f"  ✓ {spec['estado']:10s} {spec['url'][:70]}  → {rid}")

        print(f"\nSeed completo. Total recursos sembrados: {len(SEED_RESOURCES)}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
