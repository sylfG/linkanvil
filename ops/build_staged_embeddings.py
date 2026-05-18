"""Slice 6.5 — Pre-computa los embeddings de los 3 recursos staged
del demo y los cachea en `cerebro.staged_embeddings_cache`.

Ejecutar UNA vez tras aplicar la migración 0011 y cada vez que
`_STAGED_RECURSOS` cambie en `src/api/database.py` (porque modifiques
títulos o resumens). Idempotente: usa INSERT ... ON CONFLICT.

Uso:
    docker exec cerebro-api python -m ops.build_staged_embeddings

Variables necesarias (ya están en el entorno del contenedor):
    DATABASE_URL
    LITELLM_URL
    LITELLM_KEY   (master key del owner; gasta tokens UNA vez)

Sin esta cache, `_index_staged_for_rag` cae a un fallback que llama a
LiteLLM en cada `/auth/demo-start` — funciona pero gasta tokens y
añade ~400ms de latencia al arranque del demo.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

import asyncpg
import httpx

# Reusamos el catálogo canónico de staged para no duplicar la definición.
from src.api.database import _STAGED_RECURSOS, _init_conn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://cerebro:cerebro_db_pass@postgres:5432/cerebro_brain",
)
LITELLM_URL = os.environ.get("LITELLM_URL", "http://litellm:4000")
LITELLM_KEY = os.environ.get("LITELLM_KEY", "sk-cerebro-master-key")
EMBEDDINGS_MODEL = os.environ.get("STAGED_EMBEDDINGS_MODEL", "cerebro-embeddings")


async def _embed_one(http: httpx.AsyncClient, text: str) -> list[float]:
    """Una llamada a LiteLLM /v1/embeddings con la master key. Devuelve
    el vector como lista de floats. Lanza si la respuesta no es 200."""
    resp = await http.post(
        f"{LITELLM_URL}/v1/embeddings",
        headers={
            "Authorization": f"Bearer {LITELLM_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": EMBEDDINGS_MODEL,
            "input": text,
            "input_type": "passage",
        },
        timeout=20.0,
    )
    resp.raise_for_status()
    data = resp.json()
    return list(data["data"][0]["embedding"])


async def main() -> int:
    pool = await asyncpg.create_pool(
        DATABASE_URL, min_size=1, max_size=2, init=_init_conn,
    )
    inserted = 0
    try:
        async with httpx.AsyncClient() as http:
            async with pool.acquire() as conn:
                # Verifica que la tabla exista (migración 0011 aplicada).
                exists = await conn.fetchval(
                    """
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables
                         WHERE table_schema = 'cerebro'
                           AND table_name = 'staged_embeddings_cache'
                    )
                    """,
                )
                if not exists:
                    logger.error(
                        "Tabla cerebro.staged_embeddings_cache no existe. "
                        "Aplica migración 0011 primero."
                    )
                    return 1

                for idx, spec in enumerate(_STAGED_RECURSOS):
                    chunk_text = f"{spec['titulo']}\n\n{spec['resumen']}".strip()
                    logger.info("[%d] Embedding '%s'...", idx, spec["titulo"])
                    try:
                        vector = await _embed_one(http, chunk_text)
                    except Exception as exc:
                        logger.error("[%d] Fallo al embedder: %s", idx, exc)
                        continue

                    await conn.execute(
                        """
                        INSERT INTO cerebro.staged_embeddings_cache (
                            idx, titulo, resumen, categoria,
                            chunk_text, embedding, model, dims, updated_at
                        ) VALUES (
                            $1, $2, $3, $4, $5, $6, $7, $8, NOW()
                        )
                        ON CONFLICT (idx) DO UPDATE SET
                            titulo     = EXCLUDED.titulo,
                            resumen    = EXCLUDED.resumen,
                            categoria  = EXCLUDED.categoria,
                            chunk_text = EXCLUDED.chunk_text,
                            embedding  = EXCLUDED.embedding,
                            model      = EXCLUDED.model,
                            dims       = EXCLUDED.dims,
                            updated_at = NOW()
                        """,
                        idx,
                        spec["titulo"],
                        spec["resumen"],
                        spec["categoria"],
                        chunk_text,
                        vector,
                        EMBEDDINGS_MODEL,
                        len(vector),
                    )
                    inserted += 1
                    logger.info(
                        "[%d] OK — %d dims, modelo=%s",
                        idx, len(vector), EMBEDDINGS_MODEL,
                    )
    finally:
        await pool.close()

    logger.info(
        "Cache de staged poblada: %d/%d entradas.",
        inserted, len(_STAGED_RECURSOS),
    )
    return 0 if inserted == len(_STAGED_RECURSOS) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
