import os
import uuid
import httpx
import psycopg2
import psycopg2.extras
import streamlit as st

LITELLM_URL   = os.getenv("LITELLM_URL", "http://litellm:4000")
LITELLM_KEY   = os.getenv("LITELLM_MASTER_KEY", "sk-cerebro-master-key")
QDRANT_URL    = os.getenv("QDRANT_URL", "http://qdrant:6333")
INGESTION_URL = os.getenv("INGESTION_URL", "http://ingestion-api:8000")
COLLECTION    = "cerebro_recursos"

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://cerebro:cerebro_db_pass@postgres:5432/cerebro_brain")

st.set_page_config(page_title="LinkAnvil Chat", page_icon="🧠", layout="wide")
st.title("🧠 LinkAnvil — Segundo Cerebro")

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Configuración")
    model = st.selectbox("Modelo", ["cerebro-lite", "cerebro-pro"], index=0,
                         help="lite → rápido y económico | pro → razonamiento complejo")
    use_rag = st.toggle("Usar RAG (buscar en tu base)", value=True)
    tenant_id = st.text_input("Tenant ID", value="default")
    top_k = st.slider("Resultados RAG", 1, 10, 5)
    st.divider()
    if st.button("🗑️ Limpiar conversación"):
        st.session_state.messages = []
        st.rerun()
    st.divider()
    st.caption(f"LiteLLM: `{LITELLM_URL}`")
    st.caption(f"Qdrant: `{QDRANT_URL}`")
    st.caption(f"Ingestion: `{INGESTION_URL}`")

# ---------------------------------------------------------------------------
# Estado de sesión
# ---------------------------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def ingest_url(url: str, tenant_id: str, source: str = "ui") -> dict:
    payload = {"url": url, "tenant_id": tenant_id, "source": source, "trace_id": str(uuid.uuid4())}
    r = httpx.post(f"{INGESTION_URL}/ingest", json=payload, timeout=10.0)
    r.raise_for_status()
    return r.json()


def qdrant_search(query_vector: list[float], tenant_id: str, top_k: int) -> list[dict]:
    try:
        payload = {
            "vector": query_vector,
            "filter": {"must": [{"key": "tenant_id", "match": {"value": tenant_id}}]},
            "limit": top_k,
            "with_payload": True,
        }
        r = httpx.post(f"{QDRANT_URL}/collections/{COLLECTION}/points/search", json=payload, timeout=5.0)
        if r.status_code == 200:
            return r.json().get("result", [])
    except Exception:
        pass
    return []


def embed_text(text: str) -> list[float] | None:
    try:
        headers = {"Authorization": f"Bearer {LITELLM_KEY}", "Content-Type": "application/json"}
        r = httpx.post(f"{LITELLM_URL}/v1/embeddings", headers=headers,
                       json={"model": "cerebro-embeddings", "input": text}, timeout=10.0)
        if r.status_code == 200:
            return r.json()["data"][0]["embedding"]
    except Exception:
        pass
    return None


def chat_completion(messages: list[dict], model: str = "cerebro-lite") -> str:
    headers = {"Authorization": f"Bearer {LITELLM_KEY}", "Content-Type": "application/json"}
    try:
        r = httpx.post(f"{LITELLM_URL}/v1/chat/completions", headers=headers,
                       json={"model": model, "messages": messages, "stream": False}, timeout=60.0)
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"]
        return f"⚠️ Error del modelo ({r.status_code}): {r.text[:300]}"
    except httpx.TimeoutException:
        return "⚠️ Timeout al conectar con LiteLLM."
    except Exception as e:
        return f"⚠️ Error: {e}"

# ---------------------------------------------------------------------------
# Pestañas
# ---------------------------------------------------------------------------
tab_chat, tab_ingest, tab_kb = st.tabs(["💬 Chat", "🔗 Ingestar URLs", "📚 Base de Conocimiento"])

# ── Pestaña Chat ────────────────────────────────────────────────────────────
with tab_chat:
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("Escribe tu pregunta..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Pensando..."):
                context_block = ""

                if use_rag:
                    with st.status("🔍 Buscando en la base de conocimiento...", expanded=False) as status:
                        vector = embed_text(prompt)
                        if vector:
                            hits = qdrant_search(vector, tenant_id, top_k)
                            if hits:
                                fragments = []
                                for h in hits:
                                    p = h.get("payload", {})
                                    fragments.append(
                                        f"- **{p.get('title','Sin título')}** — {p.get('url','')} "
                                        f"[similitud: {h.get('score',0):.2f}]"
                                    )
                                context_block = "### Contexto de tu base:\n" + "\n".join(fragments)
                                status.update(label=f"✅ {len(hits)} documentos encontrados", state="complete")
                            else:
                                status.update(label="ℹ️ Sin resultados relevantes en la base", state="complete")
                        else:
                            status.update(label="⚠️ No se pudo generar embedding", state="error")

                system_prompt = (
                    "Eres un asistente experto que responde usando el contexto de la base de conocimiento del usuario. "
                    "Si no hay contexto relevante, responde con tu conocimiento general e indícalo."
                )
                if context_block:
                    system_prompt += f"\n\n{context_block}"

                llm_messages = [{"role": "system", "content": system_prompt}]
                for m in st.session_state.messages[-10:]:
                    llm_messages.append(m)

                reply = chat_completion(llm_messages, model)
                st.markdown(reply)

        st.session_state.messages.append({"role": "assistant", "content": reply})

# ── Pestaña Ingestar URLs ───────────────────────────────────────────────────
with tab_ingest:
    st.subheader("🔗 Añadir URLs a tu base de conocimiento")
    st.caption("Las URLs se procesan en segundo plano: scraping → LLM → vectorización → base.")

    col1, col2 = st.columns([3, 1])
    with col1:
        urls_input = st.text_area(
            "URLs (una por línea)",
            placeholder="https://ejemplo.com/articulo\nhttps://otro.com/doc",
            height=150,
        )
    with col2:
        source_label = st.text_input("Fuente", value="ui",
                                     help="Etiqueta de origen (ui, manual, rss…)")
        st.write("")
        st.write("")
        submit = st.button("📥 Ingestar", use_container_width=True, type="primary")

    if submit and urls_input.strip():
        urls = [u.strip() for u in urls_input.strip().splitlines() if u.strip()]
        st.write(f"Procesando **{len(urls)}** URL(s)…")

        results = []
        for url in urls:
            try:
                resp = ingest_url(url, tenant_id, source_label)
                status_val = resp.get("status", "?")
                is_dup = resp.get("is_duplicate", False)
                if is_dup:
                    results.append(("⏭️", url, "Duplicado — ya estaba en la base"))
                elif "Accepted" in status_val:
                    results.append(("✅", url, "Encolada para procesar"))
                else:
                    results.append(("ℹ️", url, status_val))
            except httpx.HTTPStatusError as e:
                results.append(("❌", url, f"Error {e.response.status_code}: {e.response.text[:100]}"))
            except Exception as e:
                results.append(("❌", url, str(e)))

        for icon, url, msg in results:
            st.write(f"{icon} `{url}` — {msg}")

        ok = sum(1 for r in results if r[0] == "✅")
        if ok:
            st.success(f"{ok} URL(s) encoladas. El pipeline las procesará en segundo plano.")
            st.info("Podrás preguntarle al chat sobre ellas en cuanto termine el scraping y la vectorización (~30s por URL).")
    elif submit:
        st.warning("Introduce al menos una URL.")

# ── Pestaña Base de Conocimiento ────────────────────────────────────────────
with tab_kb:
    st.subheader("📚 Base de Conocimiento")

    @st.cache_data(ttl=30, show_spinner=False)
    def load_tenants() -> list[str]:
        try:
            conn = psycopg2.connect(DATABASE_URL)
            cur = conn.cursor()
            cur.execute("SELECT DISTINCT tenant_id FROM recursos ORDER BY tenant_id")
            tenants = [r[0] for r in cur.fetchall()]
            cur.close()
            conn.close()
            return tenants or ["default"]
        except Exception:
            return ["default"]

    @st.cache_data(ttl=30, show_spinner=False)
    def load_recursos(tenant: str, estado_filtro: str) -> list[dict]:
        try:
            conn = psycopg2.connect(DATABASE_URL)
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            query = """
                SELECT id, url, titulo, resumen, categoria, tags, estado,
                       volatilidad, fecha_caducidad, created_at, updated_at
                FROM recursos
                WHERE tenant_id = %s
            """
            params = [tenant]
            if estado_filtro != "todos":
                query += " AND estado = %s"
                params.append(estado_filtro)
            query += " ORDER BY created_at DESC LIMIT 200"
            cur.execute(query, params)
            rows = [dict(r) for r in cur.fetchall()]
            cur.close()
            conn.close()
            return rows
        except Exception as e:
            st.error(f"Error conectando a PostgreSQL: {e}")
            return []

    tenants_disponibles = load_tenants()
    default_idx = tenants_disponibles.index(tenant_id) if tenant_id in tenants_disponibles else 0

    col_f1, col_f2, col_f3, col_f4 = st.columns([2, 1, 1, 1])
    with col_f1:
        search_term = st.text_input("🔍 Buscar en títulos / URLs", placeholder="palabra clave...")
    with col_f2:
        kb_tenant = st.selectbox("Tenant", tenants_disponibles, index=default_idx, key="kb_tenant")
    with col_f3:
        estado_filtro = st.selectbox("Estado", ["todos", "activo", "procesando", "completado", "expirado"])
    with col_f4:
        st.write("")
        st.write("")
        if st.button("🔄 Actualizar", use_container_width=True):
            st.cache_data.clear()

    recursos = load_recursos(kb_tenant, estado_filtro)

    if search_term:
        t = search_term.lower()
        recursos = [r for r in recursos if t in (r.get("titulo") or "").lower()
                    or t in (r.get("url") or "").lower()
                    or t in (r.get("resumen") or "").lower()]

    if not recursos:
        st.info("No hay recursos en la base para este tenant y filtro.")
    else:
        st.caption(f"{len(recursos)} recurso(s) encontrado(s)")

        # Inicializar selección
        if "kb_selected" not in st.session_state:
            st.session_state.kb_selected = None

        # Lista de recursos
        for rec in recursos:
            titulo = rec.get("titulo") or rec.get("url") or "Sin título"
            estado = rec.get("estado", "?")
            categoria = rec.get("categoria", "")
            emoji = {"completado": "✅", "procesando": "⏳", "expirado": "🗑️"}.get(estado, "❓")

            col_a, col_b = st.columns([5, 1])
            with col_a:
                if st.button(f"{emoji} {titulo[:80]}", key=str(rec["id"]), use_container_width=True):
                    st.session_state.kb_selected = rec
            with col_b:
                st.caption(f"`{categoria}`")

        # Panel de detalle
        if st.session_state.kb_selected:
            st.divider()
            r = st.session_state.kb_selected
            st.markdown(f"### {r.get('titulo') or 'Sin título'}")
            st.markdown(f"🔗 [{r.get('url')}]({r.get('url')})")

            col1, col2, col3 = st.columns(3)
            col1.metric("Estado", r.get("estado", "—"))
            col2.metric("Categoría", r.get("categoria", "—"))
            col3.metric("Volatilidad", r.get("volatilidad", "—"))

            if r.get("resumen"):
                st.markdown("**Resumen:**")
                st.markdown(r["resumen"])

            if r.get("tags"):
                import json as _json
                try:
                    tags = _json.loads(r["tags"]) if isinstance(r["tags"], str) else r["tags"]
                    if tags:
                        st.markdown("**Tags:** " + " ".join(f"`{t}`" for t in tags))
                except Exception:
                    pass

            cols = st.columns(2)
            cols[0].caption(f"Creado: {r.get('created_at','—')}")
            cols[1].caption(f"Caduca: {r.get('fecha_caducidad','—')}")
