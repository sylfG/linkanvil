import hashlib
import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

import httpx
import redis.asyncio as aioredis
from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from src.api import database as db
from src.api.auth import (
    CSRF_COOKIE,
    CSRF_HEADER,
    SESSION_COOKIE,
    create_access_token,
    generate_csrf_token,
    get_password_hash,
    verify_password,
    verify_token,
)
from src.observability.logging import configure_json_logging
from src.api.models import (
    ChatRequest,
    CfCookiesRequest,
    IngestRequest,
    LoginRequest,
    MessageIn,
    MessageOut,
    RegisterRequest,
    SessionResponse,
    TelegramBotRequest,
    TokenResponse,
    UserResponse,
)

configure_json_logging("cerebro-api")
logger = logging.getLogger(__name__)

LITELLM_URL = os.getenv("LITELLM_URL", "http://litellm:4000")
LITELLM_KEY = os.getenv("LITELLM_KEY", "sk-cerebro-master-key")
QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
INGESTION_URL = os.getenv("INGESTION_URL", "http://ingestion-api:8000")
REDIS_URL = os.getenv("REDIS_URL", "redis://:cerebro_redis_pass@redis:6379")
PUBLIC_INGESTION_URL = os.getenv("PUBLIC_INGESTION_URL", "")
COLLECTION = "cerebro_recursos"

_redis: Optional[aioredis.Redis] = None
_http: Optional[httpx.AsyncClient] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _redis, _http
    _redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    _http = httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=120.0, write=10.0, pool=10.0))
    yield
    if _redis:
        await _redis.aclose()
    if _http:
        await _http.aclose()
    await db.close_pool()


app = FastAPI(title="Cerebro Auth API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------

async def get_current_user(
    authorization: str = Header(None),
    cerebro_session: str | None = Cookie(None),
) -> dict:
    """
    Read the session token from either an httpOnly cookie (preferred for
    browser flows) or the Authorization: Bearer header (legacy / Telegram).
    """
    token: str | None = None
    if cerebro_session:
        token = cerebro_session
    elif authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
    if not token:
        raise HTTPException(401, "Token requerido")
    try:
        payload = verify_token(token)
    except ValueError:
        raise HTTPException(401, "Token inválido")
    user = await db.get_user_by_id(payload["sub"])
    if not user:
        raise HTTPException(401, "Usuario no encontrado")
    return user


COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "lax")
COOKIE_DOMAIN = os.getenv("COOKIE_DOMAIN") or None
COOKIE_MAX_AGE_SEC = 24 * 3600


def _set_session_cookies(response: Response, token: str) -> str:
    """Set the httpOnly session cookie + a non-httpOnly CSRF cookie. Returns the CSRF token."""
    csrf = generate_csrf_token()
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=COOKIE_MAX_AGE_SEC,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        domain=COOKIE_DOMAIN,
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf,
        max_age=COOKIE_MAX_AGE_SEC,
        httponly=False,  # the JS needs to read it
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        domain=COOKIE_DOMAIN,
        path="/",
    )
    return csrf


async def verify_csrf(
    request: Request,
    x_csrf_token: str | None = Header(None, alias=CSRF_HEADER),
    cerebro_csrf: str | None = Cookie(None),
    cerebro_session: str | None = Cookie(None),
) -> None:
    """
    Double-submit cookie CSRF check. Only enforced when the request is
    cookie-authenticated; pure Bearer-token requests (Telegram, scripts)
    skip the check, since they cannot be triggered cross-site.
    """
    if not cerebro_session:
        return
    if not cerebro_csrf or not x_csrf_token or cerebro_csrf != x_csrf_token:
        raise HTTPException(403, "CSRF token mismatch")


# ---------------------------------------------------------------------------
# Rate limiting (Redis INCR with per-key TTL — atomic, low overhead).
# Fails open if Redis is unavailable so a degraded cache never causes
# a customer-visible outage.
# ---------------------------------------------------------------------------

def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


async def _rate_limit(key: str, limit: int, window_seconds: int) -> None:
    if _redis is None:
        return
    count = await _redis.incr(key)
    if count == 1:
        await _redis.expire(key, window_seconds)
    if count > limit:
        raise HTTPException(429, "Too Many Requests")


async def rate_limit_login(request: Request) -> None:
    await _rate_limit(f"rl:login:{_client_ip(request)}", limit=5, window_seconds=60)


async def rate_limit_register(request: Request) -> None:
    await _rate_limit(f"rl:register:{_client_ip(request)}", limit=3, window_seconds=3600)


async def rate_limit_chat(user: dict = Depends(get_current_user)) -> dict:
    await _rate_limit(f"rl:chat:{user['tenant_id']}", limit=30, window_seconds=60)
    return user


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@app.post("/auth/register")
async def register(req: RegisterRequest, response: Response, _=Depends(rate_limit_register)):
    if await db.get_user_by_email(req.email):
        raise HTTPException(409, "Email ya registrado")
    hashed = get_password_hash(req.password)
    user = await db.create_user(req.email, hashed)
    token = create_access_token(
        {"sub": str(user["id"]), "tenant_id": user["tenant_id"], "email": user["email"]}
    )
    csrf = _set_session_cookies(response, token)
    # The access_token is still in the body so the legacy Authorization
    # header path keeps working until the frontend fully migrates.
    return {"access_token": token, "token_type": "bearer", "csrf_token": csrf}


@app.post("/auth/login")
async def login(req: LoginRequest, response: Response, _=Depends(rate_limit_login)):
    user = await db.get_user_by_email(req.email)
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(401, "Credenciales incorrectas")
    token = create_access_token(
        {"sub": str(user["id"]), "tenant_id": user["tenant_id"], "email": user["email"]}
    )
    csrf = _set_session_cookies(response, token)
    return {"access_token": token, "token_type": "bearer", "csrf_token": csrf}


@app.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/", domain=COOKIE_DOMAIN)
    response.delete_cookie(CSRF_COOKIE, path="/", domain=COOKIE_DOMAIN)
    return {"status": "ok"}


@app.get("/auth/me", response_model=UserResponse)
async def me(user=Depends(get_current_user)):
    return UserResponse(
        id=user["id"],
        email=user["email"],
        tenant_id=user["tenant_id"],
        telegram_bot_active=user["telegram_bot_active"],
        created_at=user["created_at"],
    )


# ---------------------------------------------------------------------------
# Profile / Telegram
# ---------------------------------------------------------------------------

@app.put("/profile/telegram")
async def update_telegram(
    req: TelegramBotRequest,
    user=Depends(get_current_user),
    _csrf=Depends(verify_csrf),
):
    resp = await _http.get(
        f"https://api.telegram.org/bot{req.bot_token}/getMe", timeout=10.0
    )
    if resp.status_code != 200:
        raise HTTPException(400, "Token de bot inválido")
    bot_info = resp.json().get("result", {})

    token_hash = hashlib.sha256(req.bot_token.encode()).hexdigest()
    await db.update_telegram_bot(str(user["id"]), req.bot_token, token_hash)

    if _redis:
        await _redis.set(f"telegram:{token_hash}", user["tenant_id"])

    base = PUBLIC_INGESTION_URL or INGESTION_URL
    webhook_url = f"{base}/webhook/telegram/{token_hash}"
    await _http.get(
        f"https://api.telegram.org/bot{req.bot_token}/setWebhook?url={webhook_url}",
        timeout=10.0,
    )

    return {
        "status": "ok",
        "bot_username": bot_info.get("username"),
        "webhook_url": webhook_url,
    }


# ---------------------------------------------------------------------------
# Resources (KB)
# ---------------------------------------------------------------------------

@app.get("/resources")
async def get_resources(
    estado: str = "todos",
    limit: int = Query(100, gt=0, le=500),
    user=Depends(get_current_user),
):
    return await db.get_resources(user["tenant_id"], estado, limit)


# ---------------------------------------------------------------------------
# Bandeja de cuarentena (F-05.2)
# ---------------------------------------------------------------------------

@app.get("/resources/quarantine")
async def list_quarantine(
    count_only: bool = False,
    limit: int = Query(100, gt=0, le=500),
    user=Depends(get_current_user),
):
    if count_only:
        return {"count": await db.count_quarantine(user["tenant_id"])}
    items = await db.list_quarantine(user["tenant_id"], limit)
    return {"items": items, "count": len(items)}


@app.post("/resources/{recurso_id}/rescue")
async def rescue_resource(
    recurso_id: str,
    user=Depends(get_current_user),
    _csrf=Depends(verify_csrf),
):
    row = await db.rescue_recurso(user["tenant_id"], recurso_id)
    if not row:
        raise HTTPException(404, "Recurso no encontrado o no está en cuarentena")
    return {"status": "rescued", **{k: (v.isoformat() if hasattr(v, "isoformat") else str(v))
                                     for k, v in row.items()}}


@app.post("/resources/{recurso_id}/expire")
async def expire_resource(
    recurso_id: str,
    user=Depends(get_current_user),
    _csrf=Depends(verify_csrf),
):
    row = await db.expire_recurso(user["tenant_id"], recurso_id)
    if not row:
        raise HTTPException(404, "Recurso no encontrado")
    return {"status": "expired", "id": str(row["id"]), "url": row["url"]}


@app.delete("/resources/{recurso_id}")
async def delete_resource(
    recurso_id: str,
    user=Depends(get_current_user),
    _csrf=Depends(verify_csrf),
):
    result = await db.delete_recurso_for_tenant(user["tenant_id"], recurso_id)
    if not result:
        raise HTTPException(404, "Recurso no encontrado")
    # Si la fila global desapareció, limpiamos también el punto en Qdrant.
    # Esto vive fuera de la transacción SQL para no acoplar el commit a un
    # servicio externo: si Qdrant falla, el SQL ya está y un GC posterior
    # limpiará el punto huérfano.
    if result["deleted_globally"]:
        try:
            await _http.post(
                f"{QDRANT_URL}/collections/{COLLECTION}/points/delete",
                json={
                    "filter": {
                        "must": [
                            {"key": "recurso_id", "match": {"value": str(result["id"])}}
                        ]
                    }
                },
                timeout=5.0,
            )
        except Exception as e:
            logger.warning(f"Qdrant cleanup failed for {result['id']}: {e}")
    return {
        "status": "deleted",
        "id": str(result["id"]),
        "url": result["url"],
        "deleted_globally": result["deleted_globally"],
    }


# ---------------------------------------------------------------------------
# Ingest (proxy to ingestion-api)
# ---------------------------------------------------------------------------

@app.post("/ingest")
async def ingest(req: IngestRequest, user=Depends(get_current_user), _csrf=Depends(verify_csrf)):
    payload = {
        "url": req.url,
        "tenant_id": user["tenant_id"],
        "source": req.source,
        "trace_id": str(uuid.uuid4()),
    }
    resp = await _http.post(f"{INGESTION_URL}/ingest", json=payload, timeout=15.0)
    return resp.json()


# ---------------------------------------------------------------------------
# SSE: reactive ingest stream
# ---------------------------------------------------------------------------

@app.get("/ingest/stream")
async def ingest_stream(token: str):
    try:
        payload = verify_token(token)
    except ValueError:
        raise HTTPException(401, "Token inválido")
    tenant_id = payload.get("tenant_id", "")

    async def _events() -> AsyncGenerator[str, None]:
        pubsub = _redis.pubsub()
        await pubsub.subscribe(f"ingest:complete:{tenant_id}")
        try:
            yield 'data: {"type":"connected"}\n\n'
            async for msg in pubsub.listen():
                if msg["type"] == "message":
                    yield f"data: {msg['data']}\n\n"
        finally:
            await pubsub.unsubscribe(f"ingest:complete:{tenant_id}")
            await pubsub.aclose()

    return StreamingResponse(
        _events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Chat (RAG + LiteLLM proxy with streaming)
# ---------------------------------------------------------------------------

@app.post("/chat")
async def chat(req: ChatRequest, user=Depends(rate_limit_chat), _csrf=Depends(verify_csrf)):
    context_block = ""
    hits: list = []

    if req.use_rag and req.messages:
        last_user = next(
            (m.content for m in reversed(req.messages) if m.role == "user"), ""
        )
        if last_user:
            try:
                headers = {
                    "Authorization": f"Bearer {LITELLM_KEY}",
                    "Content-Type": "application/json",
                }
                er = await _http.post(
                    f"{LITELLM_URL}/v1/embeddings",
                    headers=headers,
                    json={"model": "cerebro-embeddings", "input": last_user, "input_type": "query"},
                    timeout=15.0,
                )
                if er.status_code == 200:
                    vector = er.json()["data"][0]["embedding"]
                    search = {
                        "vector": vector,
                        "filter": {
                            "must": [
                                {"key": "tenant_id", "match": {"value": user["tenant_id"]}}
                            ]
                        },
                        "limit": 5,
                        "with_payload": True,
                    }
                    qr = await _http.post(
                        f"{QDRANT_URL}/collections/{COLLECTION}/points/search",
                        json=search,
                        timeout=5.0,
                    )
                    if qr.status_code == 200:
                        raw_hits = qr.json().get("result", [])
                        if raw_hits:
                            # Los IDs de punto son UUID v5 derivados de (recurso_id, tenant_id);
                            # `recurso_id` real está en el payload.
                            recurso_ids = [
                                str(h.get("payload", {}).get("recurso_id"))
                                for h in raw_hits
                                if h.get("payload", {}).get("recurso_id")
                            ]
                            active_ids = await db.get_active_resource_ids(
                                user["tenant_id"],
                                recurso_ids,
                            )
                            active_set = set(active_ids)
                            hits = [
                                h for h in raw_hits
                                if str(h.get("payload", {}).get("recurso_id")) in active_set
                            ]
                        if hits:
                            frags = [
                                f"- **{h['payload'].get('title','')}** — "
                                f"{h['payload'].get('url','')} "
                                f"[score: {h['score']:.2f}]"
                                for h in hits
                            ]
                            context_block = "### Contexto:\n" + "\n".join(frags)
            except Exception as e:
                logger.warning(f"RAG error: {e}")

    system_prompt = (
        "Eres un asistente experto. Responde usando el contexto de la base de conocimiento "
        "del usuario. Si no hay contexto relevante, responde con tu conocimiento general e indícalo."
    )
    if context_block:
        system_prompt += f"\n\n{context_block}"

    llm_msgs = [{"role": "system", "content": system_prompt}]
    for m in req.messages[-10:]:
        llm_msgs.append({"role": m.role, "content": m.content})

    h = {"Authorization": f"Bearer {LITELLM_KEY}", "Content-Type": "application/json"}

    rag_sources = []
    if req.use_rag and hits:
        rag_sources = [
            {"title": h["payload"].get("title", ""), "url": h["payload"].get("url", ""), "score": round(h["score"], 3)}
            for h in hits
        ]

    async def _stream() -> AsyncGenerator[str, None]:
        if rag_sources:
            yield f"data: {json.dumps({'type': 'sources', 'sources': rag_sources})}\n\n"
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{LITELLM_URL}/v1/chat/completions",
                headers=h,
                json={"model": req.model, "messages": llm_msgs, "stream": True},
            ) as resp:
                async for chunk in resp.aiter_text():
                    yield chunk

    return StreamingResponse(_stream(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Admin: audit-cron trigger (n8n / cron externo)
# ---------------------------------------------------------------------------

AUDIT_CRON_TOKEN = os.getenv("AUDIT_CRON_TOKEN", "")


@app.post("/admin/audit-cron")
async def trigger_audit_cron(x_admin_token: str | None = Header(None, alias="X-Admin-Token")):
    """Dispara la auditoría temporal en dos fases (caducidad → cuarentena →
    expirado). Pensado para un workflow n8n cron diario; se autentica por
    header `X-Admin-Token` contra la env `AUDIT_CRON_TOKEN`."""
    if not AUDIT_CRON_TOKEN:
        raise HTTPException(503, "AUDIT_CRON_TOKEN no configurado")
    if x_admin_token != AUDIT_CRON_TOKEN:
        raise HTTPException(401, "Token administrativo inválido")
    # Import diferido: el cron toca DatabaseManager (asyncpg directo) en
    # vez del pool de la API, así que no compartimos conexiones.
    from src.data.audit_cron import run_audit_cron
    result = await run_audit_cron()
    return {"status": "ok", **result}


@app.post("/admin/cf-cookies")
async def set_cf_cookies(req: CfCookiesRequest, user=Depends(get_current_user), _csrf=Depends(verify_csrf)):
    cookies = [{"name": "cf_clearance", "value": req.cf_clearance,
                "domain": req.domain, "path": "/"}]
    if req.extra:
        cookies.extend([
            {"name": k, "value": v, "domain": req.domain, "path": "/"}
            for k, v in req.extra.items()
        ])
    await _redis.setex(f"cf:cookies:{req.domain}", req.ttl_hours * 3600, json.dumps(cookies))
    return {"status": "ok", "domain": req.domain, "expires_in_hours": req.ttl_hours}


@app.delete("/admin/cf-cookies/{domain}")
async def clear_cf_cookies(domain: str, user=Depends(get_current_user), _csrf=Depends(verify_csrf)):
    await _redis.delete(f"cf:cookies:{domain}")
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Chat sessions & messages
# ---------------------------------------------------------------------------

def _session_out(row: dict) -> dict:
    return {
        "id": row["id"],
        "titulo": row.get("titulo"),
        "ultimo_acceso": row["ultimo_acceso"],
        "created_at": row["created_at"],
    }


def _message_out(row: dict) -> dict:
    return {
        "id": row["id"],
        "role": row["rol"],
        "content": row["contenido"],
        "sources": row.get("fuentes") or [],
        "created_at": row["created_at"],
    }


@app.post("/chats", response_model=SessionResponse)
async def create_chat(user=Depends(get_current_user), _csrf=Depends(verify_csrf)):
    session = await db.create_chat_session(user["tenant_id"])
    return _session_out(session)


@app.get("/chats")
async def list_chats(
    limit: int = Query(50, gt=0, le=200),
    offset: int = Query(0, ge=0),
    user=Depends(get_current_user),
):
    sessions = await db.list_chat_sessions(user["tenant_id"], limit=limit, offset=offset)
    total = await db.count_chat_sessions(user["tenant_id"])
    return {
        "items": [_session_out(s) for s in sessions],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@app.get("/chats/{session_id}", response_model=SessionResponse)
async def get_chat(session_id: str, user=Depends(get_current_user)):
    session = await db.get_chat_session(user["tenant_id"], session_id)
    if not session:
        raise HTTPException(404, "Sesión no encontrada")
    return _session_out(session)


@app.delete("/chats/{session_id}")
async def delete_chat(session_id: str, user=Depends(get_current_user), _csrf=Depends(verify_csrf)):
    deleted = await db.delete_chat_session(user["tenant_id"], session_id)
    if not deleted:
        raise HTTPException(404, "Sesión no encontrada")
    return {"status": "ok"}


@app.get("/chats/{session_id}/messages", response_model=list[MessageOut])
async def get_messages(session_id: str, user=Depends(get_current_user)):
    session = await db.get_chat_session(user["tenant_id"], session_id)
    if not session:
        raise HTTPException(404, "Sesión no encontrada")
    messages = await db.get_chat_messages(user["tenant_id"], session_id)
    return [_message_out(m) for m in messages]


@app.post("/chats/{session_id}/messages", response_model=list[MessageOut])
async def append_messages(
    session_id: str, body: list[MessageIn], user=Depends(get_current_user), _csrf=Depends(verify_csrf)
):
    session = await db.get_chat_session(user["tenant_id"], session_id)
    if not session:
        raise HTTPException(404, "Sesión no encontrada")
    saved = await db.append_chat_messages(
        user["tenant_id"],
        session_id,
        [{"role": m.role, "content": m.content, "sources": m.sources} for m in body],
    )
    return [_message_out(m) for m in saved]


@app.get("/health")
async def health():
    return {"status": "ok"}
