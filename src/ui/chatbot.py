import os
import uuid
import json
import asyncio
import sys
import streamlit as st
import httpx
import logging
import redis

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from data.db import DatabaseManager
from telemetry import configure_telemetry, trace_operation

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuramos telemetria para la UI
configure_telemetry("cerebro-ui")

LITELLM_URL = os.getenv("LITELLM_URL", "http://litellm:4000")
LITELLM_KEY = os.getenv("LITELLM_MASTER_KEY", "sk-cerebro-master-key-CHANGE_ME")
QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)
REDIS_TTL = int(os.getenv("REDIS_TTL", "3600"))

@st.cache_resource
def get_redis_client():
    return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD, decode_responses=True)

try:
    r_client = get_redis_client()
except Exception as e:
    logger.error(f"Redis initialization failed: {e}")
    r_client = None

# Funciones de Cuarentena (F-05.2)
async def fetch_obsoletos(t_id: str) -> list[dict]:
    db = DatabaseManager()
    await db.connect()
    try:
        async with db.pool.acquire() as conn:
            rows = await conn.fetch("SELECT id, titulo, url, fecha_caducidad FROM recursos WHERE tenant_id = $1 AND estado = 'obsoleto'", t_id)
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"Error fetching obsoletos: {e}")
        return []
    finally:
        await db.close()

async def renew_item(t_id: str, id_uuid: str, tr_id: str):
    db = DatabaseManager()
    await db.connect()
    try:
        async with db.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("UPDATE recursos SET estado = 'procesando', fecha_caducidad = NOW() + INTERVAL '30 days', updated_at = NOW() WHERE id = $1 AND tenant_id = $2", id_uuid, t_id)
                outbox_payload = {"event_origin": "quarantine_ui", "trace_id": tr_id, "recurso_id": str(id_uuid), "motivo": "renovado_manualmente"}
                await conn.execute("INSERT INTO outbox_eventos (tenant_id, agregado_tipo, agregado_id, evento_tipo, payload) VALUES ($1, 'recurso', $2, 'recurso.recuperado', $3::jsonb)", t_id, id_uuid, json.dumps(outbox_payload))
                logger.info(f"[{tr_id}] Recurso {id_uuid} renovado.")
    finally:
        await db.close()

async def delete_item(t_id: str, id_uuid: str, tr_id: str):
    db = DatabaseManager()
    await db.connect()
    try:
        async with db.pool.acquire() as conn:
            async with conn.transaction():
                # El outbox debe grabarse ANTES de borrar el recurso (o si hay foreign key constraight) 
                # pero no lo hay, outbox_eventos solo apunta lógicamente
                outbox_payload = {"event_origin": "quarantine_ui", "trace_id": tr_id, "recurso_id": str(id_uuid), "motivo": "borrado_definitivo"}
                await conn.execute("INSERT INTO outbox_eventos (tenant_id, agregado_tipo, agregado_id, evento_tipo, payload) VALUES ($1, 'recurso', $2, 'recurso.eliminado', $3::jsonb)", t_id, id_uuid, json.dumps(outbox_payload))
                await conn.execute("DELETE FROM recursos WHERE id = $1 AND tenant_id = $2", id_uuid, t_id)
                logger.info(f"[{tr_id}] Recurso {id_uuid} borrado.")
    finally:
        await db.close()

st.set_page_config(page_title="RAG Chatbot - Cerebro", page_icon="🧠", layout="centered")

st.title("🧠 Cerebro - Chatbot RAG Multi-Tenant")
st.markdown("Interactúa con tus documentos sincronizados en tiempo real.")

tenant_id = st.sidebar.selectbox("Seleccionar Tenant", ["tenant_A", "tenant_B"], index=0)
session_id = st.sidebar.text_input("ID de Sesión (Persistencia Redis)", value=st.session_state.get("session_id", str(uuid.uuid4())[:8]))
st.session_state.session_id = session_id
session_key = f"chat_session:{tenant_id}:{session_id}"

st.sidebar.markdown("---")
view_mode = st.sidebar.radio("Modo / Vista", ["Chatbot RAG", "🚧 Bandeja de Cuarentena"])

def load_session(key):
    if not r_client: return []
    try:
        data = r_client.get(key)
        if data:
            return json.loads(data)
    except Exception as e:
        logger.error(f"Error cargando sesión de Redis: {e}")
    return []

def save_session(key, messages):
    if not r_client: return
    try:
        r_client.setex(key, REDIS_TTL, json.dumps(messages))
    except Exception as e:
        logger.error(f"Error guardando sesión en Redis: {e}")

if "messages" not in st.session_state or st.session_state.get("current_session_key") != session_key:
    st.session_state.messages = load_session(session_key)
    st.session_state.current_session_key = session_key

# Configurar headers
llm_headers = {
    "Authorization": f"Bearer {LITELLM_KEY}",
    "Content-Type": "application/json"
}

def generate_embedding(text: str) -> list[float]:
    payload = {"model": "cerebro-embeddings", "input": text}
    response = httpx.post(f"{LITELLM_URL}/v1/embeddings", headers=llm_headers, json=payload, timeout=30.0)
    response.raise_for_status()
    return response.json()["data"][0]["embedding"]

def search_qdrant(vector: list[float], t_id: str, trace_id: str) -> list[dict]:
    search_payload = {
        "vector": vector,
        "filter": {
            "must": [
                {
                    "key": "tenant_id",
                    "match": {"value": t_id}
                }
            ]
        },
        "limit": 3,
        "with_payload": True
    }
    logger.info(f"[{trace_id}] Buscando en Qdrant para tenant {t_id}")
    
    # Qdrant is open on port 6333, no auth configured in this project
    resp = httpx.post(f"{QDRANT_URL}/collections/cerebro_recursos/points/search", json=search_payload, timeout=10.0, headers={"traceparent": trace_id})
    try:
        resp.raise_for_status()
    except Exception as e:
        logger.error(f"[{trace_id}] Error buscando en qdrant: {e}")
        return []
    
    return resp.json().get("result", [])

@trace_operation("execute_chat_completion")
def execute_chat_completion(messages: list[dict], trace_id: str) -> str:
    payload = {
        "model": "cerebro-gpt",
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 1000
    }
    logger.info(f"[{trace_id}] LLM Call")
    # Propagar el trace header hacia litellm
    req_headers = llm_headers.copy()
    req_headers["traceparent"] = trace_id
    response = httpx.post(f"{LITELLM_URL}/v1/chat/completions", headers=req_headers, json=payload, timeout=60.0)
    
    if response.status_code != 200:
        logger.error(f"LLM Error: {response.text}")
    
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]

if view_mode == "Chatbot RAG":
    # Render previous messages
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
    
    if user_input := st.chat_input("Escribe tu pregunta..."):
        trace_id = str(uuid.uuid4())
        logger.info(f"[{trace_id}] Nuevo mensaje: {user_input}")
        
        st.session_state.messages.append({"role": "user", "content": user_input})
        save_session(session_key, st.session_state.messages)
        
        with st.chat_message("user"):
            st.markdown(user_input)
    
        with st.chat_message("assistant"):
            with st.spinner("🧠 Pensando y conectando con el panel RAG..."):
                try:
                    # 1. Embedding
                    query_vector = generate_embedding(user_input)
                    
                    # 2. Búsqueda Semántica
                    qdrant_results = search_qdrant(query_vector, tenant_id, trace_id)
                    
                    # 3. Context Builder
                    context_texts = []
                    for point in qdrant_results:
                        score = point.get("score", 0)
                        pl = point.get("payload", {})
                        title = pl.get("title", "Desconocido")
                        url = pl.get("url", "#")
                        category = pl.get("category", "")
                        context_texts.append(f"- Título: {title} (Cat: {category})\n  Score: {score:.2f}\n  Enlace: {url}")
                    
                    context_str = "\n".join(context_texts) if context_texts else "No se encontraron documentos relevantes."
                    
                    system_prompt = (
                        "Eres Cerebro, un asistente conversacional RAG inteligente.\n"
                        "Responde a la pregunta del usuario utilizando EXCLUSIVAMENTE el siguiente contexto recuperado.\n"
                        "Si el contexto está vacío ('No se encontraron documentos relevantes.'), indica que no posees la información.\n"
                        f"Contexto:\n {context_str}"
                    )
                    
                    # Armar el pipeline de memoria del LLM
                    llm_messages = [{"role": "system", "content": system_prompt}]
                    # Anexar historial 
                    for sm in st.session_state.messages[-5:]: # sliding window visual context (last 5 messages)
                        llm_messages.append(sm)
                        
                    # 4. LLM Generation
                    response_text = execute_chat_completion(llm_messages, trace_id)
                    st.markdown(response_text)
                    
                    # Expandable sources
                    if qdrant_results:
                        with st.expander("Ver Fuentes Consultadas"):
                            st.markdown(context_str)
                            
                    st.session_state.messages.append({"role": "assistant", "content": response_text})
                    save_session(session_key, st.session_state.messages)
    
                except httpx.HTTPStatusError as e:
                    err_msg = f"Error en pasarela (Posible Fallback fallido o Caída): {e}"
                    st.error(err_msg)
                    logger.error(f"[{trace_id}] {err_msg}")
                except Exception as e:
                    st.error(f"Ocurrió un error inesperado al procesar el mensaje: {e}")
                    logger.error(f"[{trace_id}] {e}")

elif view_mode == "🚧 Bandeja de Cuarentena":
    st.subheader("🚫 Cuarentena Temporal de Conocimiento")
    st.info("Estos recursos han expirado su fecha de caducidad. Si no actúas, serán invisibles para Cerebro (LLM) hasta su purgado definitivo.")
    
    # Ejecutamos el asíncrono desde el síncrono de Streamlit
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        obsoletos = loop.run_until_complete(fetch_obsoletos(tenant_id))
    except Exception as e:
        logger.error(e)
        obsoletos = []
    
    if not obsoletos:
        st.success(f"Todo en orden. No hay recursos obsoletos para {tenant_id}.")
    else:
        for obs in obsoletos:
            # Crear un panel dinámico para cada recurso obsoleto
            with st.expander(f"⚠️ {obs.get('titulo', 'Sin título')} (Caducado el: {obs.get('fecha_caducidad')})"):
                st.write(f"**URL:** [Abrir Fuente]({obs.get('url', '#')})")
                col1, col2 = st.columns(2)
                
                with col1:
                    btn_renew = st.button("♻️ Renovar (Extender 30 días)", key=f"ren_{obs['id']}")
                    if btn_renew:
                        t_id = str(uuid.uuid4())
                        loop.run_until_complete(renew_item(tenant_id, obs['id'], t_id))
                        st.success("¡Recurso renovado! Estará disponible en tus respuestas.")
                        # Rerun para refrescar la lista
                        st.rerun()
                
                with col2:
                    btn_del = st.button("🗑️ Eliminar Definitivamente", key=f"del_{obs['id']}")
                    if btn_del:
                        t_id = str(uuid.uuid4())
                        loop.run_until_complete(delete_item(tenant_id, obs['id'], t_id))
                        st.error("¡Recurso borrado de la base de conocimiento!")
                        # Rerun para refrescar
                        st.rerun()

