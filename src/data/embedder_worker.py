import asyncio
import aio_pika
import httpx
import json
import logging
import os
import sys
import uuid
from typing import Optional

import redis.asyncio as aioredis

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from src.telemetry import configure_telemetry, trace_operation
from src.data.db import DatabaseManager
from src.data.heartbeat import start_heartbeat

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# OTel
configure_telemetry("embedder-worker")

LITELLM_URL = os.getenv("LITELLM_EMBEDDINGS_URL", "http://litellm:4000/v1/embeddings")
LITELLM_KEY = os.getenv("LITELLM_API_KEY", "sk-cerebro-master-key-CHANGE_ME")
QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
# Namespace fijo para derivar IDs UUID v5 de Qdrant a partir de (recurso_id, tenant_id).
# Qdrant solo acepta enteros o UUID como point id; usamos v5 determinista para que
# el mismo par siempre genere el mismo id (idempotencia en upserts).
_QDRANT_POINT_NS = uuid.UUID("00000000-0000-0000-0000-000000000000")


def _qdrant_point_id(recurso_id: str, tenant_id: str) -> str:
    return str(uuid.uuid5(_QDRANT_POINT_NS, f"{recurso_id}:{tenant_id}"))
RABBIT_URL = os.getenv("RABBITMQ_URL", "amqp://cerebro:cerebro_pass@localhost:5672/cerebro")
EXCHANGE_NAME = os.getenv("RABBITMQ_EXCHANGE_PROCESAMIENTO", "cerebro.procesamiento")
QUEUE_NAME = "q.recurso.embedder"
DLQ_ROUTING_KEY = "dlq.url.fallidas"
REDIS_URL = os.getenv("REDIS_URL", "redis://:cerebro_redis_pass@redis:6379")

class EmbedderWorker:
    def __init__(self):
        self.connection: Optional[aio_pika.RobustConnection] = None
        self.channel: Optional[aio_pika.RobustChannel] = None
        self.queue: Optional[aio_pika.RobustQueue] = None
        self.db = DatabaseManager()
        self.redis: Optional[aioredis.Redis] = None
        self.http: Optional[httpx.AsyncClient] = None
        self.heartbeat_task: Optional[asyncio.Task] = None

    async def connect(self):
        await self.db.connect()
        self.redis = aioredis.from_url(REDIS_URL, decode_responses=True)
        self.http = httpx.AsyncClient(timeout=30.0)
        self.heartbeat_task = start_heartbeat(self.redis, "embedder")
        self.connection = await aio_pika.connect_robust(RABBIT_URL)
        self.channel = await self.connection.channel()
        await self.channel.set_qos(prefetch_count=10) # Paralelismo
        
        exchange = await self.channel.get_exchange(EXCHANGE_NAME)
        
        # Declarar Q asíncrona de embedder
        queue = await self.channel.declare_queue(
            QUEUE_NAME, 
            durable=True,
            arguments={
                "x-dead-letter-exchange": "",
                "x-dead-letter-routing-key": DLQ_ROUTING_KEY
            }
        )
        await queue.bind(exchange, routing_key="")
        self.queue = queue

    async def _generate_embedding(self, text: str, trace_id: str) -> list[float]:
        headers = {"Authorization": f"Bearer {LITELLM_KEY}", "Content-Type": "application/json"}
        payload = {"model": "cerebro-embeddings", "input": text, "input_type": "passage"}
        resp = await self.http.post(LITELLM_URL, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["data"][0]["embedding"]

    async def _inject_to_qdrant(self, recurso_id: str, tenant_id: str, vector: list[float], extracted_info: dict, url: str, trace_id: str):
        point_id = _qdrant_point_id(recurso_id, tenant_id)
        points_payload = {
            "points": [
                {
                    "id": point_id,
                    "vector": vector,
                    "payload": {
                        "tenant_id": tenant_id,
                        "recurso_id": recurso_id,
                        "url": url,
                        "title": extracted_info.get("title", ""),
                        "category": extracted_info.get("category", "other"),
                        "volatility": extracted_info.get("volatility_score", "media")
                    }
                }
            ]
        }

        resp = await self.http.put(
            f"{QDRANT_URL}/collections/cerebro_recursos/points?wait=true",
            json=points_payload,
        )
        resp.raise_for_status()

    async def _fetch_existing_vector_for_recurso(self, recurso_id: str) -> Optional[dict]:
        """Busca cualquier punto Qdrant con el mismo recurso_id (cualquier tenant)
        y devuelve su vector y payload. Sirve para clonar embeddings entre tenants."""
        body = {
            "filter": {
                "must": [{"key": "recurso_id", "match": {"value": recurso_id}}]
            },
            "limit": 1,
            "with_vector": True,
            "with_payload": True,
        }
        resp = await self.http.post(
            f"{QDRANT_URL}/collections/cerebro_recursos/points/scroll",
            json=body,
        )
        resp.raise_for_status()
        data = resp.json()
        points = data.get("result", {}).get("points", [])
        if not points:
            return None
        p = points[0]
        return {"vector": p.get("vector"), "payload": p.get("payload", {})}

    async def _classify_collision_type(self, trace_id: str, tenant_id: str, new_info: dict, old_id: str) -> str:
        # Fetch the old document info from the DB. `recursos` es global → no se filtra por tenant.
        if not self.db.pool:
            await self.db.connect()

        async with self.db.pool.acquire() as conn:
            old_row = await conn.fetchrow(
                "SELECT titulo, resumen FROM recursos WHERE id = $1::uuid",
                old_id,
            )

        if not old_row:
            return "ASOCIACION_GENERAL"
            
        old_info = {"title": old_row["titulo"], "summary": old_row["resumen"]}
        
        prompt = f"""
        Como un evaluador experto, compara el nuevo documento con el antiguo.
        Documento Nuevo (ID Reciente):
        Título: {new_info.get('title', '')}
        Resumen: {new_info.get('summary', '')}
        
        Documento Antiguo (ID Existente):
        Título: {old_info.get('title', '')}
        Resumen: {old_info.get('summary', '')}
        
        Tipifica la relación como UNA ÚNICA PALABRA: 'ES_UN', 'CONTRADICE', 'EXTIENDE', 'VUELVE_OBSOLETO' o 'ASOCIACION_GENERAL'.
        """
        
        headers = {"Authorization": f"Bearer {LITELLM_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": "cerebro-llm",  # Ajusta al modelo que uses para chat, o el que esté ruteado por litellm
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "max_tokens": 10
        }
        
        try:
            url_chat = LITELLM_URL.replace("/embeddings", "/chat/completions")
            resp = await self.http.post(url_chat, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            tipo = data["choices"][0]["message"]["content"].strip().upper()

            for t in ["VUELVE_OBSOLETO", "CONTRADICE", "EXTIENDE", "ES_UN"]:
                if t in tipo:
                    return t
            return "ASOCIACION_GENERAL"
        except Exception as e:
            logger.warning(f"[{trace_id}] Fallo de IA en tipificación (fallback): {e}")
            return "ASOCIACION_GENERAL"

    async def _compute_semantic_collisions(self, recurso_id: str, tenant_id: str, vector: list[float], extracted_info: dict, trace_id: str):
        payload = {
            "vector": vector,
            "filter": {
                "must": [
                    {"key": "tenant_id", "match": {"value": tenant_id}}
                ]
            },
            "limit": 10,
            "score_threshold": 0.92,
            "with_payload": True,
        }

        resp = await self.http.post(
            f"{QDRANT_URL}/collections/cerebro_recursos/points/search",
            json=payload,
        )
        if resp.status_code != 200:
            logger.error(f"[{trace_id}] Error consultando Qdrant para similitud: {resp.text}")
            return
        results = resp.json().get("result", [])

        collisions = []
        for r in results:
            # Los IDs de punto son UUID v5 derivados de (recurso_id, tenant_id);
            # el recurso real está en payload.recurso_id.
            other_recurso_id = (r.get("payload") or {}).get("recurso_id")
            if not other_recurso_id or other_recurso_id == recurso_id:
                continue

            tipo_relacion = await self._classify_collision_type(trace_id, tenant_id, extracted_info, other_recurso_id)

            collisions.append({
                "recurso_destino": other_recurso_id,
                "similitud": r["score"],
                "tipo_relacion": tipo_relacion,
            })
        
        if not collisions:
            logger.info(f"[{trace_id}] Sin colisiones semánticas > 0.92 para {recurso_id}")
            return
            
        logger.info(f"[{trace_id}] Encontradas {len(collisions)} colisiones semánticas para {recurso_id}")
        await self.db.save_semantic_collisions(tenant_id, recurso_id, collisions)

    @trace_operation("process_embedder_message")
    async def process_message(self, message: aio_pika.IncomingMessage):
        async with message.process(requeue=False, ignore_processed=True):
            payload = json.loads(message.body.decode())
            trace_id = payload.get("trace_id") or ("-".join(dict(message.headers).get("traceparent", "00-unknown-00-00").split("-")[1:3]) if "traceparent" in (message.headers or {}) else (message.headers.get("trace_id", "unknown-trace") if message.headers else "unknown-trace"))
            tenant_id = payload.get("tenant_id", "default_tenant")
            recurso_id = payload.get("recurso_id")
            url = payload.get("url", "")
            ext_info = payload.get("extracted_info", {})
            reused = bool(payload.get("reused"))

            if not recurso_id:
                logger.error(f"[{trace_id}] Payload inválido: sin recurso_id")
                raise ValueError("Missing recurso_id in payload")

            try:
                if reused:
                    # Rama reuso: copiar vector de un punto existente del mismo recurso
                    # (otro tenant) en vez de re-embeber. El embedding depende solo del
                    # contenido público de la URL, así que es seguro y determinista.
                    src = await self._fetch_existing_vector_for_recurso(recurso_id)
                    if not src or not src.get("vector"):
                        logger.warning(
                            f"[{trace_id}] Reuso solicitado pero no hay punto fuente para "
                            f"recurso {recurso_id}; cayendo a re-embedding."
                        )
                        ext_info = await self._fetch_recurso_ext_info(recurso_id) or ext_info
                        keywords_str = ','.join(ext_info.get('keywords', []))
                        text_to_embed = f"{ext_info.get('title', '')} | {ext_info.get('summary', '')} | Tags: {keywords_str}"
                        vector = await self._generate_embedding(text_to_embed, trace_id)
                    else:
                        vector = src["vector"]
                        # Heredamos title/category/volatility del payload origen para que
                        # la nueva fila Qdrant sea coherente con la del primer tenant.
                        src_payload = src.get("payload", {})
                        ext_info = {
                            "title": src_payload.get("title", ""),
                            "category": src_payload.get("category", "other"),
                            "volatility_score": src_payload.get("volatility", "media"),
                            "summary": "",
                            "keywords": [],
                        }
                        logger.info(
                            f"[{trace_id}] [TENANT:{tenant_id}] Vector copiado de punto existente "
                            f"(recurso {recurso_id}); sin llamada al embedder."
                        )

                    await self._inject_to_qdrant(recurso_id, tenant_id, vector, ext_info, url, trace_id)
                    await self._compute_semantic_collisions(recurso_id, tenant_id, vector, ext_info, trace_id)
                    # `estado` es global: ya estará en 'activo' por el primer tenant.
                else:
                    # Rama normal: nuevo recurso global, generar embedding desde cero.
                    keywords_str = ','.join(ext_info.get('keywords', []))
                    text_to_embed = f"{ext_info.get('title', '')} | {ext_info.get('summary', '')} | Tags: {keywords_str}"
                    logger.info(f"[{trace_id}] [TENANT:{tenant_id}] Generando embedding. Text Length: {len(text_to_embed)}")

                    vector = await self._generate_embedding(text_to_embed, trace_id)
                    logger.info(f"[{trace_id}] Generado vector de {len(vector)} dimensiones")

                    await self._inject_to_qdrant(recurso_id, tenant_id, vector, ext_info, url, trace_id)
                    logger.info(f"[{trace_id}] Vector inyectado exitosamente en Qdrant. Aislado a tenant_id: {tenant_id}")

                    await self._compute_semantic_collisions(recurso_id, tenant_id, vector, ext_info, trace_id)
                    logger.info(f"[{trace_id}] Cruces en SQL procesados (F-03.3).")

                    await self.db.update_recurso_estado(recurso_id, "activo")
                    logger.info(f"[{trace_id}] Estado actualizado a 'activo' para ID {recurso_id}")

                # Notificar completado vía Redis pub/sub (para SSE en cerebro-api)
                if self.redis:
                    titulo = ext_info.get("title") or url
                    completion = json.dumps({
                        "recurso_id": recurso_id,
                        "url": url,
                        "titulo": titulo,
                        "estado": "activo",
                    })
                    await self.redis.publish(f"ingest:complete:{tenant_id}", completion)
                    logger.info(f"[{trace_id}] Publicado evento ingest:complete para tenant {tenant_id}")

            except Exception as e:
                logger.error(f"[{trace_id}] F-03.2 Fallo crítico procesando embedding/qdrant: {e}")
                raise e

    async def _fetch_recurso_ext_info(self, recurso_id: str) -> Optional[dict]:
        """Lee título/resumen/categoría/volatilidad del recurso global desde Postgres.
        Usado como fallback si el reuso de vector Qdrant falla y hay que re-embeber."""
        if not self.db.pool:
            await self.db.connect()
        async with self.db.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT titulo, resumen, categoria, volatilidad, tags FROM recursos WHERE id = $1::uuid",
                recurso_id,
            )
        if not row:
            return None
        try:
            tags = json.loads(row["tags"]) if isinstance(row["tags"], str) else (row["tags"] or [])
        except Exception:
            tags = []
        return {
            "title": row["titulo"] or "",
            "summary": row["resumen"] or "",
            "category": row["categoria"] or "other",
            "volatility_score": row["volatilidad"] or "media",
            "keywords": tags,
        }

    async def consume(self):
        if not self.channel:
            await self.connect()
        logger.info(f"Iniciando consumo en EmbedderWorker cola '{QUEUE_NAME}'")
        await self.queue.consume(self.process_message)

    async def close(self):
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
        if self.connection:
            await self.connection.close()
        if self.redis:
            await self.redis.aclose()
        if self.http:
            await self.http.aclose()
        await self.db.close()

async def run_worker():
    worker = EmbedderWorker()
    await worker.connect()
    await worker.consume()
    try:
        await asyncio.Future()
    except asyncio.CancelledError:
        pass
    finally:
        await worker.close()

if __name__ == '__main__':
    asyncio.run(run_worker())
