import os
import uuid
import json
import asyncio
import sys
import streamlit as st
import httpx
import logging
import redis
import zipfile
from io import BytesIO

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

def check_chat_rate_limit(t_id: str, limit: int = 15, window: int = 60) -> bool:
    """F-06.4 Noisy Neighbor Defense para LLM (Estrangulamiento local)."""
    if not r_client:
        return True
    try:
        key = f"chat_limit:{t_id}"
        current = r_client.get(key)
        if current and int(current) >= limit:
            return False
            
        pipe = r_client.pipeline()
        pipe.incr(key)
        if not current:
            pipe.expire(key, window)
        pipe.execute()
        return True
    except Exception as e:
        logger.error(f"Fallback en limite de RAG: {e}")
        return True

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
view_mode = st.sidebar.radio("Modo / Vista", ["Chatbot RAG", "🚧 Bandeja de Cuarentena", "📊 Dashboard Administrativo"])

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

async def fetch_all_resources_for_export(t_id: str) -> list[dict]:
    db = DatabaseManager()
    await db.connect()
    try:
        async with db.pool.acquire() as conn:
            # Seleccionamos información detallada para exportación Markdown F-03.5
            rows = await conn.fetch(
                "SELECT id, url, titulo, resumen, categoria, tags, volatilidad, estado, created_at, fecha_caducidad FROM recursos WHERE tenant_id = $1 ORDER BY created_at DESC", 
                t_id
            )
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"Error fetching ALL resources for tenant {t_id}: {e}")
        return []
    finally:
        await db.close()

async def fetch_resources_for_audit(t_id: str, limit: int = 10) -> list[dict]:
    db = DatabaseManager()
    await db.connect()
    try:
        async with db.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, titulo, url, estado, volatilidad, fecha_caducidad FROM recursos WHERE tenant_id = $1 ORDER BY updated_at DESC LIMIT $2", 
                t_id, limit
            )
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"Error fetching resources for audit: {e}")
        return []
    finally:
        await db.close()

async def fetch_dashboard_metrics(t_id: str) -> dict:
    db = DatabaseManager()
    await db.connect()
    metrics = {"activo": 0, "cuarentena": 0, "obsoleto": 0, "procesando": 0, "outbox_pending": 0}
    try:
        async with db.pool.acquire() as conn:
            rows = await conn.fetch("SELECT estado, COUNT(*) as count FROM recursos WHERE tenant_id = $1 GROUP BY estado", t_id)
            for r in rows:
                metrics[r['estado']] = r['count']
                
            outbox_count = await conn.fetchval(
                "SELECT COUNT(*) FROM outbox_eventos WHERE tenant_id = $1 AND procesado = FALSE", t_id
            )
            metrics["outbox_pending"] = outbox_count or 0
    except Exception as e:
        logger.error(f"Error fetching dashboard metrics: {e}")
    finally:
        await db.close()
    return metrics

async def async_get_session_context(t_id: str, s_id: str) -> str:
    db = DatabaseManager()
    await db.connect()
    try:
        return await db.get_session_context(t_id, s_id)
    finally:
        await db.close()

async def async_update_session_context(t_id: str, s_id: str, ctx: str):
    db = DatabaseManager()
    await db.connect()
    try:
        await db.update_session_context(t_id, s_id, ctx)
    finally:
        await db.close()

async def fetch_historico_rag_crudo(t_id: str, query: str) -> str:
    db = DatabaseManager()
    await db.connect()
    try:
        async with db.pool.acquire() as conn:
            await conn.execute(f"SET LOCAL app.current_tenant = '{t_id}'")
            # Búsqueda ILIKE cruda en resúmenes para rebatir ambigüedad
            rows = await conn.fetch(
                "SELECT titulo, url, resumen, estado FROM recursos WHERE tenant_id = $1 AND (resumen ILIKE $2 OR titulo ILIKE $2) LIMIT 3", 
                t_id, f"%{query}%"
            )
            if not rows:
                return "No se encontraron coincidencias en el histórico crudo."
            
            res_text = ""
            for r in rows:
                res_text += f"- Título: {r['titulo']}\n  URL: {r['url']}\n  Estado: {r['estado']}\n  Resumen Crudo: {r['resumen']}\n\n"
            return res_text
    except Exception as e:
        logger.error(f"Error fetch_historico_rag_crudo: {e}")
        return f"Error consultando el histórico RAG crudo: {e}"
    finally:
        await db.close()

@trace_operation("execute_chat_completion")
def execute_chat_completion(messages: list[dict], trace_id: str, tools: list[dict] = None, tenant_id: str = None) -> str:
    payload = {
        "model": "cerebro-gpt",
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 1000
    }
    if tools:
        payload["tools"] = tools
        
    logger.info(f"[{trace_id}] LLM Call")
    req_headers = llm_headers.copy()
    req_headers["traceparent"] = trace_id
    response = httpx.post(f"{LITELLM_URL}/v1/chat/completions", headers=req_headers, json=payload, timeout=60.0)
    
    if response.status_code != 200:
        logger.error(f"LLM Error: {response.text}")
    
    response.raise_for_status()
    resp_msg = response.json()["choices"][0]["message"]
    
    if resp_msg.get("tool_calls"):
        messages.append(resp_msg)
        for tool_call in resp_msg["tool_calls"]:
            if tool_call["function"]["name"] == "consultar_historico_rag_crudo":
                args = json.loads(tool_call["function"]["arguments"])
                logger.info(f"[{trace_id}] Function Calling RAG crudo: {args['query']}")
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                crudo_resultado = loop.run_until_complete(fetch_historico_rag_crudo(tenant_id, args["query"]))
                messages.append({
                    "role": "tool",
                    "name": "consultar_historico_rag_crudo",
                    "tool_call_id": tool_call["id"],
                    "content": crudo_resultado
                })
        
        # Second call to LLM after tool usage
        payload["messages"] = messages
        if "tools" in payload:
            del payload["tools"]
        logger.info(f"[{trace_id}] Segundo LLM Call post-tool")
        response2 = httpx.post(f"{LITELLM_URL}/v1/chat/completions", headers=req_headers, json=payload, timeout=60.0)
        response2.raise_for_status()
        return response2.json()["choices"][0]["message"]["content"]
    
    return resp_msg["content"]

if view_mode == "Chatbot RAG":
    # Render previous messages
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
    
    if user_input := st.chat_input("Escribe tu pregunta..."):
        trace_id = str(uuid.uuid4())
        logger.info(f"[{trace_id}] Nuevo mensaje: {user_input}")
        
        # F-06.4: Throttling / límite automático de cuota por Tenant
        if not check_chat_rate_limit(tenant_id, limit=5, window=60):
            st.error("⚠️ Cuota transaccional agotada. Has superado el límite de 5 consultas por minuto en RAG. Throttling activo para evitar ataque o Noisy Neighbor.")
            st.stop()
        
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
                    )

                    # 3.1. Compactación de Largo Contexto (Sliding Window Relacional F-04.4)
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_closed(): raise RuntimeError
                    except:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                    
                    historial_comprimido = loop.run_until_complete(async_get_session_context(tenant_id, session_id))
                    if historial_comprimido:
                        system_prompt += f"\n--- Resumen Histórico de esta sesión: ---\n{historial_comprimido}\n--------------------\n"
                        
                    system_prompt += f"\nContexto DDBB:\n {context_str}"
                    
                    # Armar el pipeline de memoria del LLM (últimos N)
                    llm_messages = [{"role": "system", "content": system_prompt}]
                    
                    window_size = 5
                    # Compactación si el historial excede el doble de la ventana visual
                    if len(st.session_state.messages) > window_size * 2:
                        # Extraer los mensajes q rebasan la ventana para compactarlos
                        to_compact = st.session_state.messages[:-window_size]
                        
                        prompt_compactacion = (
                            "Resume la conversación hasta ahora en máximo 3 párrafos, "
                            f"incorporando este conocimiento previo: {historial_comprimido}\n\n"
                        )
                        for m in to_compact:
                            prompt_compactacion += f"{m['role'].upper()}: {m['content']}\n"
                            
                        nuevo_resumen_msg = execute_chat_completion([{"role": "user", "content": prompt_compactacion}], trace_id)
                        loop.run_until_complete(async_update_session_context(tenant_id, session_id, nuevo_resumen_msg))
                        
                        # Actualizar para inyectarlo en el LLM actual (así no se pierde este contexto)
                        historial_comprimido = nuevo_resumen_msg
                        
                        # Reiniciar la sesión en Redis a solo la ventana
                        st.session_state.messages = st.session_state.messages[-window_size:]
                        save_session(session_key, st.session_state.messages)
                        
                        # Re-preparar si cambió
                        llm_messages[0]["content"] = system_prompt.replace(f"--- Resumen Histórico de esta sesión: ---\n{historial_comprimido}\n--------------------\n", "")
                        llm_messages[0]["content"] += f"\n--- Resumen Histórico de esta sesión: ---\n{historial_comprimido}\n--------------------\n"

                    # Anexar historial visual actual
                    for sm in st.session_state.messages[-window_size:]: 
                        llm_messages.append(sm)
                        
                    # Tools setup para Function Calling Activo F-04.5
                    llm_tools = [
                        {
                            "type": "function",
                            "function": {
                                "name": "consultar_historico_rag_crudo",
                                "description": "Consulta el histórico RAG crudo almacenado. Úsalo soberanamente para obtener el texto completo de recursos o rebatir ambigüedad a petición expresa o contexto insuficiente.",
                                "parameters": {
                                    "type": "object",
                                    "properties": {
                                        "query": {
                                            "type": "string",
                                            "description": "Una palabra clave o frase a buscar en los títulos o resúmenes de la base de conocimiento cruda."
                                        }
                                    },
                                    "required": ["query"]
                                }
                            }
                        }
                    ]
                        
                    # 4. LLM Generation
                    response_text = execute_chat_completion(llm_messages, trace_id, tools=llm_tools, tenant_id=tenant_id)
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

elif view_mode == "📊 Dashboard Administrativo":
    st.subheader("📊 Dashboard Administrativo Unificado")
    st.markdown("Métricas locales y estado general del sistema orientado a eventos (F-04.3).")
    
    with st.spinner("Cargando métricas del clúster..."):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            metrics = loop.run_until_complete(fetch_dashboard_metrics(tenant_id))
            
            # Sesiones activas desde Redis
            active_sessions = 0
            if r_client:
                try:
                    keys = r_client.keys(f"chat_session:{tenant_id}:*")
                    active_sessions = len(keys)
                except Exception as ex:
                    logger.error(f"Error contando sesiones Redis: {ex}")
        except Exception as e:
            logger.error(e)
            metrics = {"activo": 0, "cuarentena": 0, "obsoleto": 0, "procesando": 0, "outbox_pending": 0}
            active_sessions = 0
    
    col1, col2, col3 = st.columns(3)
    col1.metric(label="🟢 Recursos Activos", value=metrics.get('activo', 0))
    col2.metric(label="⚙️ En Procesamiento", value=metrics.get('procesando', 0))
    
    # Manejar quarantena y obsoleto
    q_count = metrics.get('cuarentena', 0) + metrics.get('obsoleto', 0)
    col3.metric(label="⚠️ Cuarentena/Obsoleto", value=q_count)
    
    st.divider()
    col4, col5 = st.columns(2)
    col4.metric(label="📬 Eventos Outbox Pendientes", value=metrics.get('outbox_pending', 0))
    col5.metric(label="💬 Sesiones de Chat Activas", value=active_sessions)
    
    st.info("Estas métricas están particionadas mediante políticas de Row-Level Security (RLS), garantizando el aislamiento absoluto del Tenant.")

    st.divider()
    st.subheader("🤖 Auditoría Exhaustiva Basada en IA (F-05.3)")
    st.markdown("Auditoría bajo encargo de la higiene documental actual de la base de conocimiento. Detecta ruido, duplicidades semánticas aparentes y evalúa los plazos de cuarentena.")
    
    if st.button("🔍 Ejecutar Auditoría IA"):
        trace_id = str(uuid.uuid4())
        with st.spinner("Analizando la base de conocimiento y consultando al LLM (puede tardar unos segundos)..."):
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                audit_items = loop.run_until_complete(fetch_resources_for_audit(tenant_id, 20))
                
                if not audit_items:
                    st.warning("No hay suficientes registros activos para generar un perfil de auditoría.")
                else:
                    prompt = "Actúa como un Auditor de Conocimiento de Máximo Nivel.\n"
                    prompt += f"Tu tarea es encontrar posibles colisiones, incoherencias o recursos que necesiten purga inmediata, analizando su volatilidad, fechas y estados.\n"
                    prompt += "Retorna un reporte estructurado en 3 secciones en Markdown:\n1) Resumen de Higiene\n2) Alertas Críticas (Documentos Cuarentenados/Vencidos)\n3) Recomendación de Curación Estratégica.\n\n"
                    prompt += f"Registro transaccional de {len(audit_items)} documentos recientes (Tenant: {tenant_id}):\n"
                    
                    for item in audit_items:
                        prompt += f"- ID: {str(item['id'])[:8]} | ESTADO: {item['estado'].upper()} | VOLATILIDAD: {item['volatilidad']} | FECHA EXP: {item['fecha_caducidad']} | TITULO: {item['titulo']} | URL: {item['url']}\n"
                        
                    llm_messages = [{"role": "system", "content": prompt}]
                    audit_result = execute_chat_completion(llm_messages, trace_id)
                    
                    st.success("Auditoría generada exitosamente.")
                    st.markdown(audit_result)
            except Exception as e:
                logger.error(f"[{trace_id}] Audit Error: {e}")
                st.error(f"Fallo en la conexión P2P con el Motor LLM: {e}")

    st.divider()
    st.subheader("📦 Exportación Masiva Local (F-03.5)")
    st.markdown("Exporta toda la base de conocimiento del Tenant actual como archivos Markdown empaquetados en un ZIP, evitando el vendor lock-in.")
    
    if st.button("📥 Generar Exportación ZIP"):
        with st.spinner("Compilando recursos en Markdown..."):
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                # Fetch all resources for the tenant
                resources = loop.run_until_complete(fetch_all_resources_for_export(tenant_id))
                
                if not resources:
                    st.warning("No hay recursos para exportar en este Tenant.")
                else:
                    zip_buffer = BytesIO()
                    with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
                        for res in resources:
                            # Cleanup and formatting for Markdown
                            safe_title = "".join(c for c in (res['titulo'] or f"resource_{res['id']}") if c.isalnum() or c in " _-").strip()
                            filename = f"{safe_title}_{str(res['id'])[:8]}.md"
                            
                            md_content = f"# {res['titulo'] or 'Sin Título'}\n\n"
                            md_content += f"- **ID**: {res['id']}\n"
                            md_content += f"- **URL**: {res['url']}\n"
                            md_content += f"- **Estado**: {res['estado']}\n"
                            md_content += f"- **Categoría**: {res['categoria'] or 'N/A'}\n"
                            md_content += f"- **Volatilidad**: {res['volatilidad']}\n"
                            md_content += f"- **Creado**: {res['created_at']}\n"
                            md_content += f"- **Etiquetas**: {res['tags']}\n\n"
                            
                            md_content += "## Resumen\n"
                            md_content += f"{res['resumen'] or 'Sin contenido resumido.'}\n"
                            
                            zip_file.writestr(filename, md_content)
                            
                    st.success(f"¡Exportados {len(resources)} documentos con éxito!")
                    st.download_button(
                        label="💾 Descargar Archivo ZIP",
                        data=zip_buffer.getvalue(),
                        file_name=f"exportacion_tenant_{tenant_id}.zip",
                        mime="application/zip"
                    )
            except Exception as e:
                logger.error(f"Export Error: {e}")
                st.error(f"Fallo al generar la exportación: {e}")

