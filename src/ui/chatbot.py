import os
import uuid
import streamlit as st
import httpx
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

LITELLM_URL = os.getenv("LITELLM_URL", "http://litellm:4000")
LITELLM_KEY = os.getenv("LITELLM_MASTER_KEY", "sk-cerebro-master-key-CHANGE_ME")
QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")

st.set_page_config(page_title="RAG Chatbot - Cerebro", page_icon="🧠", layout="centered")

st.title("🧠 Cerebro - Chatbot RAG Multi-Tenant")
st.markdown("Interactúa con tus documentos sincronizados en tiempo real.")

tenant_id = st.sidebar.selectbox("Seleccionar Tenant", ["tenant_A", "tenant_B"], index=0)

if "messages" not in st.session_state:
    st.session_state.messages = []

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
    resp = httpx.post(f"{QDRANT_URL}/collections/cerebro_recursos/points/search", json=search_payload, timeout=10.0)
    try:
        resp.raise_for_status()
    except Exception as e:
        logger.error(f"[{trace_id}] Error buscando en qdrant: {e}")
        return []
    
    return resp.json().get("result", [])

def execute_chat_completion(messages: list[dict], trace_id: str) -> str:
    payload = {
        "model": "cerebro-gpt",
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 1000
    }
    logger.info(f"[{trace_id}] LLM Call")
    response = httpx.post(f"{LITELLM_URL}/v1/chat/completions", headers=llm_headers, json=payload, timeout=60.0)
    
    if response.status_code != 200:
        logger.error(f"LLM Error: {response.text}")
    
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]

# Render previous messages
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if user_input := st.chat_input("Escribe tu pregunta..."):
    trace_id = str(uuid.uuid4())
    logger.info(f"[{trace_id}] Nuevo mensaje: {user_input}")
    
    st.session_state.messages.append({"role": "user", "content": user_input})
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

            except httpx.HTTPStatusError as e:
                err_msg = f"Error en pasarela (Posible Fallback fallido o Caída): {e}"
                st.error(err_msg)
                logger.error(f"[{trace_id}] {err_msg}")
            except Exception as e:
                st.error(f"Ocurrió un error inesperado al procesar el mensaje: {e}")
                logger.error(f"[{trace_id}] {e}")
