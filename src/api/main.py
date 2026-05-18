import asyncio
import hashlib
import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator, Optional

import httpx
import redis.asyncio as aioredis
from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from src.api import database as db
from src.api.auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    CSRF_COOKIE,
    CSRF_HEADER,
    REFRESH_COOKIE,
    REFRESH_TOKEN_EXPIRE_DAYS,
    SESSION_COOKIE,
    TokenExpired,
    create_access_token,
    generate_csrf_token,
    generate_refresh_token,
    get_password_hash,
    hash_refresh_token,
    verify_password,
    verify_token,
)
from src.api.crypto import encrypt_llm_key
from src.api.llm_keys import invalidate_llm_key_cache, resolve_llm_key
from src.observability.logging import configure_json_logging
from src.api.models import (
    AuditPolicyRequest,
    ChatRequest,
    CfCookiesRequest,
    DemoTimelineEvent,
    DemoTimelineResponse,
    DemoTimelineSession,
    IngestRequest,
    LLMKeysRequest,
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

# Mismo namespace que `src/data/embedder_worker.py` para derivar el point
# id por (recurso, tenant). Si cambia allí, hay que cambiar aquí.
_QDRANT_POINT_NS = uuid.UUID("00000000-0000-0000-0000-000000000000")


def _qdrant_point_id(recurso_id: str, tenant_id: str) -> str:
    return str(uuid.uuid5(_QDRANT_POINT_NS, f"{recurso_id}:{tenant_id}"))


def _model_kind(model: str) -> str:
    """Mapea el alias del modelo del request (``cerebro-lite|pro|...``)
    a la kind de virtual key (``lite``/``pro``). Cualquier alias que
    contenga 'pro' va a la pro-key; el resto (incluyendo embeddings,
    lite, custom aliases) cae a 'lite'. Las embeddings tienen su
    propia kind y se resuelven directamente — no pasa por aquí."""
    return "pro" if "pro" in model.lower() else "lite"


async def _resolve_user_key(user_id: str, kind: str) -> str:
    """Wrapper que abre conn del pool y delega a resolve_llm_key.

    Slice 5: ahora keyea por ``user_id`` (no tenant_id) porque los
    sub-tenants efímeros del demo no tienen fila en ``usuarios``.
    El demo user es siempre el mismo (id estable), aunque su tenant
    cambie en cada login.

    Levanta HTTPException 402 si el user no es demo y no tiene keys
    configuradas. Cache TTL 60s vive en llm_keys.py.
    """
    p = await db.get_pool()
    async with p.acquire() as conn:
        return await resolve_llm_key(conn, user_id, kind)


def _tenant_ids_for(user: dict) -> list[str]:
    """Devuelve los tenant_ids que un usuario puede VER en lecturas.

    Slice 5:
    - Demo session (tenant_id empieza con 'demo_'): UNION con el seed
      tenant compartido (``user_demo_landing``) para que vea los 18
      recursos canónicos sin duplicarlos en BD ni Qdrant.
    - Resto: solo su propio tenant_id.

    Para ESCRITURAS (ingest, chat session save, notifications) usa
    ``user['tenant_id']`` directamente — el seed es inmutable.
    """
    if str(user.get("tenant_id", "")).startswith("demo_"):
        return [user["tenant_id"], db.DEMO_SEED_TENANT_ID]
    return [user["tenant_id"]]


def _is_demo_session(user: dict) -> bool:
    return str(user.get("tenant_id", "")).startswith("demo_")


async def _qdrant_delete_tenant_points(tenant_id: str) -> None:
    """Borra todos los Qdrant points filtrados por payload.tenant_id.

    Usado por el cleanup task tras expirar una sesión demo. Falla-soft:
    si Qdrant está caído logueamos y seguimos — el cleanup retrigea
    en el siguiente tick.
    """
    if _http is None:
        return
    filter_body = {
        "filter": {
            "must": [{"key": "tenant_id", "match": {"value": tenant_id}}]
        }
    }
    for collection in ("cerebro_chunks", "cerebro_recursos"):
        try:
            await _http.post(
                f"{QDRANT_URL}/collections/{collection}/points/delete",
                json=filter_body,
                timeout=10.0,
            )
        except Exception as exc:
            logger.warning(
                "qdrant delete %s/%s failed: %s", collection, tenant_id, exc
            )


async def _process_due_demo_audits() -> None:
    """Slice 6 — Lanza la auditoría intra-sesión para cada sub-tenant
    demo cuyo evento más antiguo ya cumple `fires_at <= NOW()`.

    Cada sesión se procesa en su propia transacción para que un fallo
    en una NO contamine a las demás. Se hace `SET LOCAL app.tenant_id`
    porque las tablas `recursos` / `usuario_recursos` tienen RLS forced
    con la policy `tenant_isolation` — sin el set_config un UPDATE
    devolvería 0 filas afectadas (silenciosamente).
    """
    from src.data.audit_cron import run_demo_audit_for_session

    try:
        due_tenants = await db.get_sessions_with_due_events()
    except Exception:
        logger.exception("demo audit: get_sessions_with_due_events failed")
        return

    if not due_tenants:
        return

    pool = await db.get_pool()
    for tenant_id in due_tenants:
        try:
            async with pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(
                        "SELECT set_config('app.tenant_id', $1, true)",
                        tenant_id,
                    )
                    result = await run_demo_audit_for_session(tenant_id, conn)
                    logger.info(
                        "demo audit fired: tenant=%s processed=%d "
                        "cuarentena=%d expirado=%d reminder=%d skipped=%d",
                        result["tenant_id"], result["processed"],
                        result["cuarentena"], result["expirado"],
                        result["reminder"], result["skipped"],
                    )
        except Exception:
            logger.exception("demo audit failed for tenant=%s", tenant_id)


async def _cleanup_demo_sessions_loop() -> None:
    """Background task que cada 60s:

    1. **Procesa audits intra-sesión** — para cada sesión demo con
       eventos pending (fires_at <= NOW()), aplica las transiciones
       (activo→cuarentena, activo→expirado) y emite outbox events para
       que el notifier pinte las notificaciones en el bell. Granularidad
       de 60s significa que un evento programado a +5min puede dispararse
       entre 5:00 y 5:59 — aceptable para una demo.

    2. **Limpia sesiones expiradas** — Qdrant first (puede fallar y
       reintentarse en el siguiente tick) → BD cascade (transaccional,
       una vez OK no se pierde el cleanup). El FK CASCADE de
       demo_session_events sobre demo_sessions hace que los eventos
       desaparezcan junto con la sesión.

    Si Qdrant falla quedarían points huérfanos (sin tenant válido). Es
    aceptable — un barrido manual semanal los limpia. Lo importante:
    BD queda consistente.
    """
    while True:
        try:
            # Slice 6: primero los audits intra-sesión, después la
            # limpieza. Si la sesión está expirando justo en este tick,
            # queremos que sus eventos hayan disparado al menos una vez
            # antes de borrarla (los reminders de +10min son inocuos si
            # llegan tarde, pero los transitions deben ejecutar).
            await _process_due_demo_audits()

            expired = await db.get_expired_demo_sessions()
            for s in expired:
                tenant_id = s["tenant_id"]
                await _qdrant_delete_tenant_points(tenant_id)
                result = await db.delete_demo_session_cascade(tenant_id)
                logger.info("demo session cleaned: %s", result)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("demo cleanup tick failed")
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            raise

_redis: Optional[aioredis.Redis] = None
_http: Optional[httpx.AsyncClient] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _redis, _http
    _redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    _http = httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=120.0, write=10.0, pool=10.0))

    # Sanity checks de configuración crítica al arrancar — visibles en logs
    # para que el operador detecte deriva entre cerebro-api y cerebro-n8n
    # (ambos leen AUDIT_CRON_TOKEN de la misma .env vía docker-compose, pero
    # un override manual puede romper el silencio).
    if not os.getenv("AUDIT_CRON_TOKEN", ""):
        logger.warning(
            "AUDIT_CRON_TOKEN no configurado — /admin/audit-cron devolverá 503 "
            "y el cron diario de n8n fallará en autenticación."
        )
    else:
        logger.info("AUDIT_CRON_TOKEN configurado (longitud=%d)", len(os.getenv("AUDIT_CRON_TOKEN", "")))

    # Slice 5: background task que limpia sub-tenants demo expirados.
    # Corre cada 60s — granularidad fina porque el TTL es de 15min y
    # queremos que los visitantes recién expirados se limpien rápido.
    # Se cancela limpiamente al shutdown.
    cleanup_task = asyncio.create_task(_cleanup_demo_sessions_loop())

    yield

    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass

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

    Emits a distinct 401 code for expired tokens so the frontend can
    transparently try /auth/refresh before forcing the user back to login.
    """
    token: str | None = None
    if cerebro_session:
        token = cerebro_session
    elif authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
    if not token:
        raise HTTPException(401, "Token requerido", headers={"X-Auth-Reason": "missing"})
    try:
        payload = verify_token(token)
    except TokenExpired:
        raise HTTPException(401, "Token expirado", headers={"X-Auth-Reason": "expired"})
    except ValueError:
        raise HTTPException(401, "Token inválido", headers={"X-Auth-Reason": "invalid"})
    user = await db.get_user_by_id(payload["sub"])
    if not user:
        raise HTTPException(401, "Usuario no encontrado", headers={"X-Auth-Reason": "no_user"})

    # Slice 5: si el JWT lleva un sub-tenant de demo (formato demo_<8hex>)
    # validamos que la fila exista en demo_sessions y no esté expirada.
    # Sobreescribimos user['tenant_id'] con el del JWT para que los
    # endpoints downstream operen en el namespace aislado del visitante.
    jwt_tenant = payload.get("tenant_id")
    if jwt_tenant and jwt_tenant.startswith("demo_"):
        session = await db.get_demo_session(jwt_tenant)
        if not session:
            raise HTTPException(
                401,
                {"error": "demo_session_invalid", "message": "Tu sesión demo ya no existe."},
                headers={"X-Auth-Reason": "demo_invalid"},
            )
        now = datetime.now(timezone.utc)
        expires_at = session["expires_at"]
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= now:
            raise HTTPException(
                401,
                {
                    "error": "demo_session_expired",
                    "message": (
                        "Tu sesión demo de 15 minutos ha expirado. "
                        "Recárgala desde /login para empezar otra."
                    ),
                },
                headers={"X-Auth-Reason": "demo_expired"},
            )
        # Override y memoizamos campos derivados para que /auth/me los
        # devuelva sin re-query.
        user = dict(user)
        user["tenant_id"] = jwt_tenant
        user["demo_session_expires_at"] = expires_at
        user["demo_session_seconds_remaining"] = max(
            0, int((expires_at - now).total_seconds())
        )

    return user


COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "lax")
COOKIE_DOMAIN = os.getenv("COOKIE_DOMAIN") or None
ACCESS_COOKIE_MAX_AGE_SEC = ACCESS_TOKEN_EXPIRE_MINUTES * 60
REFRESH_COOKIE_MAX_AGE_SEC = REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600

# Redis key prefix for refresh-token storage. Value = JSON with user_id,
# tenant_id, email; TTL = REFRESH_COOKIE_MAX_AGE_SEC so Redis enforces expiry.
REFRESH_REDIS_PREFIX = "refresh:"


def _set_session_cookies(response: Response, access_token: str) -> str:
    """Set the httpOnly access-token cookie + non-httpOnly CSRF cookie. Returns the CSRF token."""
    csrf = generate_csrf_token()
    response.set_cookie(
        SESSION_COOKIE,
        access_token,
        max_age=ACCESS_COOKIE_MAX_AGE_SEC,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        domain=COOKIE_DOMAIN,
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf,
        # CSRF cookie outlives access cookie so the JS layer still has it
        # when /auth/refresh is being called.
        max_age=REFRESH_COOKIE_MAX_AGE_SEC,
        httponly=False,  # the JS needs to read it
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        domain=COOKIE_DOMAIN,
        path="/",
    )
    return csrf


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    # path="/" so the cookie travels on any request from the same origin —
    # the browser sees URLs as /api/auth/... (Next.js proxies to FastAPI),
    # and we don't want to couple the cookie path to that rewrite.
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        max_age=REFRESH_COOKIE_MAX_AGE_SEC,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        domain=COOKIE_DOMAIN,
        path="/",
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", domain=COOKIE_DOMAIN)
    response.delete_cookie(CSRF_COOKIE, path="/", domain=COOKIE_DOMAIN)
    response.delete_cookie(REFRESH_COOKIE, path="/", domain=COOKIE_DOMAIN)


async def _issue_refresh_token(
    user: dict, session_tenant: Optional[str] = None,
) -> str:
    """Mint a new opaque refresh token, persist its hash in Redis, return raw.

    Slice 5: ``session_tenant`` permite atar el refresh a un sub-tenant
    demo. Sin esto, al refrescar habría que crear OTRA sesión demo (lo
    cual el usuario no espera — quiere mantener la suya hasta los 15min).
    Si es None, se usa user.tenant_id (comportamiento de registered).
    """
    raw = generate_refresh_token()
    if _redis is None:
        return raw
    payload = json.dumps({
        "user_id": str(user["id"]),
        "tenant_id": user["tenant_id"],   # seed para demo, real para registered
        "session_tenant": session_tenant,  # sub-tenant efímero o None
        "email": user["email"],
    })
    await _redis.set(
        f"{REFRESH_REDIS_PREFIX}{hash_refresh_token(raw)}",
        payload,
        ex=REFRESH_COOKIE_MAX_AGE_SEC,
    )
    return raw


async def _revoke_refresh_token(raw: str | None) -> None:
    if not raw or _redis is None:
        return
    await _redis.delete(f"{REFRESH_REDIS_PREFIX}{hash_refresh_token(raw)}")


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
        print(f"CSRF fail: cookie={cerebro_csrf}, header={x_csrf_token}"); raise HTTPException(403, "CSRF token mismatch")


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


# Slice 4: cuotas diarias del demo en dos capas (per-IP + global cap).
# Per-IP es la cuota natural del visitante individual. La global protege
# contra abuso distribuido cuando los IPs cambian (Tor, VPN rotativa, etc).
# El frontend lee estos límites vía GET /profile/quota para pintar el
# contador y desactivar el form cuando se alcanzan.
DEMO_QUOTAS = {
    "ingest": {"per_ip": 5, "global": 50},
    "chat":   {"per_ip": 20, "global": 200},
}


def _demo_quota_keys(op: str, ip: str) -> tuple[str, str]:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return (
        f"rl:demo:{op}:ip:{ip}:{today}",
        f"rl:demo:{op}:global:{today}",
    )


async def _demo_daily_quota(user: dict, ip: str, op: str) -> None:
    """Cuota diaria del tenant demo en dos capas (Slice 4).

    Antes (Slice 2a) era una sola clave compartida — 5 visitantes
    distintos podían agotar el cupo del demo entre todos. Ahora cada
    IP tiene su propio cupo razonable + un techo global como red de
    seguridad.

    Si el demo se topa con per-IP: ``scope=ip`` (mensaje "tu IP alcanzó").
    Si se topa con global: ``scope=global`` (mensaje "todos los visitantes").
    """
    if not user.get("is_demo") or _redis is None:
        return

    cfg = DEMO_QUOTAS.get(op)
    if not cfg:
        return  # operación sin cuota declarada

    ip_key, global_key = _demo_quota_keys(op, ip)
    per_ip_limit, global_limit = cfg["per_ip"], cfg["global"]

    # 1. Per-IP (cuota natural del visitante).
    ip_count = await _redis.incr(ip_key)
    if ip_count == 1:
        await _redis.expire(ip_key, 86460)  # 24h + 1min margen
    if ip_count > per_ip_limit:
        raise HTTPException(
            429,
            {
                "error": "demo_daily_quota_exceeded",
                "op": op,
                "scope": "ip",
                "limit": per_ip_limit,
                "used": ip_count - 1,
                "message": (
                    f"Tu IP alcanzó el límite diario del demo "
                    f"({per_ip_limit} {op}s). Regístrate y configura "
                    "tus claves para uso ilimitado."
                ),
            },
        )

    # 2. Global cap (sanity net).
    global_count = await _redis.incr(global_key)
    if global_count == 1:
        await _redis.expire(global_key, 86460)
    if global_count > global_limit:
        raise HTTPException(
            429,
            {
                "error": "demo_daily_quota_exceeded",
                "op": op,
                "scope": "global",
                "limit": global_limit,
                "message": (
                    "El demo público alcanzó su límite global diario "
                    "(suma de todos los visitantes). Regístrate para "
                    "uso ilimitado con tus propias claves."
                ),
            },
        )


async def rate_limit_login(request: Request) -> None:
    await _rate_limit(f"rl:login:{_client_ip(request)}", limit=5, window_seconds=60)


async def rate_limit_register(request: Request) -> None:
    await _rate_limit(f"rl:register:{_client_ip(request)}", limit=3, window_seconds=3600)


async def requires_byok(user: dict = Depends(get_current_user)) -> dict:
    """Guard para endpoints que consumen tokens de LLM (migración 0008).

    - Demo (``is_demo=true``): pasa siempre — usa las virtual-keys
      pre-configuradas por el owner en el seed. Quien acota su gasto
      son las cuotas diarias en ``_demo_daily_quota``.
    - Registrado con ``llm_keys_configured=true``: pasa.
    - Registrado sin keys: 402 con CTA al modal de configuración.
    """
    if user.get("is_demo"):
        return user
    if not user.get("llm_keys_configured"):
        raise HTTPException(
            402,
            {
                "error": "byok_required",
                "message": (
                    "Configura tus claves de LLM en el perfil para usar "
                    "el chat o ingestar URLs."
                ),
            },
        )
    return user


async def rate_limit_chat(
    request: Request,
    user: dict = Depends(requires_byok),
) -> dict:
    await _rate_limit(f"rl:chat:{user['tenant_id']}", limit=30, window_seconds=60)
    await _demo_daily_quota(user, ip=_client_ip(request), op="chat")
    return user


async def rate_limit_audit(user: dict = Depends(get_current_user)) -> dict:
    # 5 disparos por minuto y tenant es generoso: la lógica de audit_cron
    # es idempotente, pero cada run abre un pool nuevo de asyncpg y emite
    # eventos outbox. No queremos que la UI se spamee el endpoint.
    await _rate_limit(f"rl:audit:{user['tenant_id']}", limit=5, window_seconds=60)
    return user


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def _access_token_for(user: dict, tenant_id: Optional[str] = None) -> str:
    """Slice 5: ``tenant_id`` override permite emitir un JWT con un
    tenant distinto al del row de ``usuarios`` (necesario para sesiones
    demo que llevan sub-tenants efímeros, no el seed)."""
    effective_tenant = tenant_id if tenant_id is not None else user["tenant_id"]
    return create_access_token(
        {"sub": str(user["id"]), "tenant_id": effective_tenant, "email": user["email"]}
    )


@app.post("/auth/register")
async def register(req: RegisterRequest, response: Response, _=Depends(rate_limit_register)):
    if await db.get_user_by_email(req.email):
        raise HTTPException(409, "Email ya registrado")
    hashed = get_password_hash(req.password)
    user = await db.create_user(req.email, hashed)
    token = _access_token_for(user)
    csrf = _set_session_cookies(response, token)
    refresh = await _issue_refresh_token(user)
    _set_refresh_cookie(response, refresh)
    return {"access_token": token, "token_type": "bearer", "csrf_token": csrf}


@app.post("/auth/login")
async def login(
    req: LoginRequest,
    request: Request,
    response: Response,
    _=Depends(rate_limit_login),
):
    user = await db.get_user_by_email(req.email)
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(401, "Credenciales incorrectas")

    # Slice 6 — Separación total demo ↔ registered.
    # El usuario demo NO se loguea por el formulario tradicional. Existe
    # un endpoint dedicado `POST /auth/demo-start` que es lo que llama
    # el botón "Probar demo" de la landing (sin credenciales visibles).
    # Aquí rechazamos para que `/login` quede como vista exclusiva de
    # usuarios registrados y no haya credenciales demo expuestas.
    if user.get("is_demo"):
        raise HTTPException(
            403,
            {
                "error": "demo_use_dedicated_endpoint",
                "message": (
                    "Esta es la cuenta demo. Accede desde el botón "
                    "'Probar demo' de la landing."
                ),
                "redirect": "/demo",
            },
        )

    token = _access_token_for(user)
    csrf = _set_session_cookies(response, token)
    refresh = await _issue_refresh_token(user)
    _set_refresh_cookie(response, refresh)
    return {"access_token": token, "token_type": "bearer", "csrf_token": csrf}


# Email de la cuenta demo seed. Se centraliza aquí como constante para
# que `/auth/demo-start` no tenga que ir a la BD a buscarla cada vez
# (es estable a través del lifecycle del owner).
DEMO_EMAIL = os.getenv("DEMO_EMAIL", "demo@linkanvil.io")


async def rate_limit_demo_start(request: Request) -> None:
    # Más permisivo que login (5/min) porque el botón de la landing
    # puede ser legítimamente clicado por varios visitantes desde
    # ASN compartidos (universidades, ISPs grandes). Pero no infinito:
    # un bot que cree sesiones en masa quemaría el cupo global del seed.
    await _rate_limit(
        f"rl:demo_start:{_client_ip(request)}",
        limit=10, window_seconds=60,
    )


@app.post("/auth/demo-start")
async def demo_start(
    request: Request,
    response: Response,
    _=Depends(rate_limit_demo_start),
):
    """Slice 6 — Entry point del demo sin credenciales.

    Llamado por el botón "Probar demo" de la landing. Crea un sub-tenant
    efímero (TTL 15min) sobre la cuenta demo del owner, stagea 3 recursos
    sintéticos y programa 4 eventos (3 transiciones al +5min, 1 reminder
    al +10min). Devuelve el access token + redirect a `/demo`.

    No usa password — la cuenta demo es compartida y abierta. La cuota
    diaria por IP (5 ingests, 20 chats) más el global cap protegen
    contra abuso.

    Slice 6.3 — **una sola sesión demo por IP por día UTC**. Sin este
    límite, un visitante podía hacer logout y volver a pulsar "Probar
    demo" indefinidamente, agarrando 15 min fresquitos cada vez y
    saltándose las cuotas de la jornada. Ahora:

      - Si la sesión asociada a esta IP sigue viva → re-emitimos JWT y
        cookies para esa misma sesión (resumes con los minutos que le
        quedaban).
      - Si la sesión ya expiró pero la IP la consumió hoy → 429 con
        copy claro de "regístrate o vuelve mañana".
      - Si la IP no tiene marca para hoy → creamos sesión nueva y la
        marcamos con TTL 24h.

    Si el seed demo no existe (despliegue mal configurado) → 503.
    """
    user = await db.get_user_by_email(DEMO_EMAIL)
    if not user or not user.get("is_demo"):
        logger.warning(
            "demo_start: cuenta demo (%s) no encontrada o is_demo=false",
            DEMO_EMAIL,
        )
        raise HTTPException(
            503,
            {
                "error": "demo_unavailable",
                "message": (
                    "El demo no está disponible en este momento. "
                    "Inténtalo más tarde."
                ),
            },
        )

    ip = _client_ip(request)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    daily_key = f"demo_session_started:{ip}:{today}"

    # ── Gate per-IP por día UTC ───────────────────────────────────
    if _redis is not None:
        existing_tenant = await _redis.get(daily_key)
        if existing_tenant:
            session = await db.get_demo_session(existing_tenant)
            now = datetime.now(timezone.utc)
            if session:
                expires_at = session["expires_at"]
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
                if expires_at > now:
                    # Sesión sigue viva — resume con cookies frescas
                    # SIN crear otra sesión nueva (la cuenta atrás
                    # continúa desde donde estaba).
                    token = _access_token_for(user, tenant_id=existing_tenant)
                    csrf = _set_session_cookies(response, token)
                    refresh = await _issue_refresh_token(
                        user, session_tenant=existing_tenant,
                    )
                    _set_refresh_cookie(response, refresh)
                    remaining = int((expires_at - now).total_seconds())
                    logger.info(
                        "demo session resumed: tenant=%s ip=%s remaining=%ds",
                        existing_tenant, ip, remaining,
                    )
                    return {
                        "access_token": token,
                        "token_type": "bearer",
                        "csrf_token": csrf,
                        "redirect": "/demo",
                        "tenant_id": existing_tenant,
                        "expires_at": expires_at.isoformat(),
                        "resumed": True,
                        "seconds_remaining": remaining,
                    }
            # Sesión ya expiró (o la fila se borró por cleanup):
            # la IP ya gastó su cupo demo de hoy.
            raise HTTPException(
                429,
                {
                    "error": "demo_already_used_today",
                    "message": (
                        "Ya disfrutaste tu sesión demo de 15 minutos hoy. "
                        "Vuelve mañana o regístrate para uso ilimitado "
                        "con tus propias claves."
                    ),
                    "register_url": "/register",
                },
            )

    # ── Sesión nueva ──────────────────────────────────────────────
    session = await db.create_demo_session(str(user["id"]), ip=ip)
    effective_tenant = session["tenant_id"]
    logger.info(
        "demo session created via demo-start: tenant=%s ip=%s expires=%s",
        effective_tenant, ip, session["expires_at"].isoformat(),
    )

    # Marca per-IP por día UTC. TTL 24h cubre cualquier zona horaria
    # razonable; el día siguiente la IP queda libre. La clave guarda
    # el tenant_id para que el branch "session viva" de arriba pueda
    # resolverlo sin un query extra a demo_sessions.
    if _redis is not None:
        await _redis.set(daily_key, effective_tenant, ex=86400)

    token = _access_token_for(user, tenant_id=effective_tenant)
    csrf = _set_session_cookies(response, token)
    refresh = await _issue_refresh_token(user, session_tenant=effective_tenant)
    _set_refresh_cookie(response, refresh)
    return {
        "access_token": token,
        "token_type": "bearer",
        "csrf_token": csrf,
        "redirect": "/demo",
        "tenant_id": effective_tenant,
        "expires_at": session["expires_at"].isoformat(),
        "resumed": False,
    }


@app.post("/auth/refresh")
async def refresh_session(
    response: Response,
    cerebro_refresh: str | None = Cookie(None),
):
    """
    Validate the refresh cookie, rotate it (delete-old + issue-new),
    and emit a fresh access JWT + CSRF cookie. The frontend interceptor
    calls this transparently on 401(X-Auth-Reason=expired).
    """
    if not cerebro_refresh:
        raise HTTPException(401, "Refresh token requerido", headers={"X-Auth-Reason": "no_refresh"})
    if _redis is None:
        raise HTTPException(503, "Refresh store no disponible")

    key = f"{REFRESH_REDIS_PREFIX}{hash_refresh_token(cerebro_refresh)}"
    raw_payload = await _redis.get(key)
    if not raw_payload:
        raise HTTPException(401, "Refresh token inválido o expirado", headers={"X-Auth-Reason": "refresh_invalid"})

    # Rotate immediately to invalidate the presented refresh; if anything
    # downstream fails the user can re-login.
    await _redis.delete(key)

    try:
        meta = json.loads(raw_payload)
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(401, "Refresh token corrupto", headers={"X-Auth-Reason": "refresh_invalid"})

    user = await db.get_user_by_id(meta["user_id"])
    if not user:
        raise HTTPException(401, "Usuario inexistente", headers={"X-Auth-Reason": "no_user"})

    # Slice 5: si el refresh estaba atado a una sesión demo, validamos
    # que sigue viva. Si expiró, 401 — el usuario debe re-loguear (lo
    # que crea una sesión nueva). No auto-renovamos el TTL en refresh.
    session_tenant = meta.get("session_tenant")
    if user.get("is_demo"):
        if not session_tenant:
            # Token viejo sin session_tenant — fuerza re-login.
            raise HTTPException(
                401,
                {"error": "demo_session_expired"},
                headers={"X-Auth-Reason": "demo_expired"},
            )
        session = await db.get_demo_session(session_tenant)
        if not session:
            raise HTTPException(
                401,
                {"error": "demo_session_expired"},
                headers={"X-Auth-Reason": "demo_expired"},
            )
        now = datetime.now(timezone.utc)
        expires_at = session["expires_at"]
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= now:
            raise HTTPException(
                401,
                {"error": "demo_session_expired"},
                headers={"X-Auth-Reason": "demo_expired"},
            )

    token = _access_token_for(user, tenant_id=session_tenant)
    csrf = _set_session_cookies(response, token)
    new_refresh = await _issue_refresh_token(user, session_tenant=session_tenant)
    _set_refresh_cookie(response, new_refresh)
    return {"access_token": token, "token_type": "bearer", "csrf_token": csrf}


@app.post("/auth/logout")
async def logout(response: Response, cerebro_refresh: str | None = Cookie(None)):
    await _revoke_refresh_token(cerebro_refresh)
    _clear_auth_cookies(response)
    return {"status": "ok"}


@app.get("/auth/me", response_model=UserResponse)
async def me(user=Depends(get_current_user)):
    # audit_policy puede venir como dict (asyncpg JSONB) o str (algunos
    # drivers); en ambos casos UserResponse acepta dict directamente — el
    # raw string se decodifica defensivamente.
    raw_policy = user.get("audit_policy")
    if isinstance(raw_policy, str):
        try:
            raw_policy = json.loads(raw_policy)
        except Exception:
            raw_policy = None
    if not isinstance(raw_policy, dict):
        raw_policy = None  # cae al default de UserResponse (preset Equilibrado)
    kwargs = {
        "id": user["id"],
        "email": user["email"],
        "tenant_id": user["tenant_id"],
        "telegram_bot_active": user["telegram_bot_active"],
        "created_at": user["created_at"],
        # Migración 0008: el frontend usa estos dos campos para decidir
        # qué mostrar en el ProfileModal (card BYOK + banner de fricción).
        "is_demo": bool(user.get("is_demo", False)),
        "llm_keys_configured": bool(user.get("llm_keys_configured", False)),
    }
    # Slice 5: campos de sesión demo (TTL 15min). get_current_user los
    # adjunta a user si el JWT lleva un sub-tenant. Si no son demo o no
    # están seteados, quedan None y el frontend no pinta countdown.
    if user.get("demo_session_expires_at"):
        kwargs["demo_session_expires_at"] = user["demo_session_expires_at"].isoformat()
    if user.get("demo_session_seconds_remaining") is not None:
        kwargs["demo_session_seconds_remaining"] = user["demo_session_seconds_remaining"]
    if raw_policy is not None:
        kwargs["audit_policy"] = raw_policy
    return UserResponse(**kwargs)


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


@app.put("/profile/audit-policy")
async def update_audit_policy(
    req: AuditPolicyRequest,
    user=Depends(get_current_user),
    _csrf=Depends(verify_csrf),
):
    """Migración 0007: actualiza la policy de auditoría del tenant.

    El body debe contener las 6 keys exactas del JSONB (ver
    `AuditPolicyRequest.validate_policy`). Tres presets pueden usarse como
    atajo desde el frontend (Estricto / Equilibrado / Permisivo) que
    rellenan las 6 celdas, pero el servidor no distingue presets —
    persiste exactamente lo que recibe.

    Invalida la cache in-process del scraper para que el próximo ingest
    lea la nueva policy. El scraper corre en un container distinto y NO
    comparte memoria, así que la invalidación local del API es
    cosmética; el escalado real depende del TTL de 60s.
    """
    policy_json = json.dumps(req.policy)
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE usuarios SET audit_policy = $1::jsonb, updated_at = NOW() WHERE id = $2::uuid",
            policy_json, str(user["id"]),
        )
    try:
        from src.data.db import DatabaseManager
        DatabaseManager.invalidate_policy_cache(user["tenant_id"])
    except Exception:
        pass
    return {"status": "ok", "policy": req.policy}


@app.put("/profile/llm-keys")
async def update_llm_keys_endpoint(
    req: LLMKeysRequest,
    user=Depends(get_current_user),
    _csrf=Depends(verify_csrf),
):
    """BYOK per-tenant (migración 0008).

    Acepta hasta 3 virtual-keys de LiteLLM (lite/embeddings/pro). Cada
    key se valida pegándole un ``GET /v1/models`` antes de cifrar y
    guardar — si LiteLLM la rechaza con 401/403, devolvemos 400 con
    ``kind`` indicando qué key falló.

    PATCH semántico: campos ``None`` o vacíos NO tocan la columna
    correspondiente en BD (permite editar una sola key sin reenviar
    las otras dos).

    El demo (is_demo=true) no puede modificar sus claves — vienen
    pre-configuradas por el owner y son la garantía de free-tier
    para los visitantes. Devolvemos 403 con ``demo_account_locked``.
    """
    if user.get("is_demo"):
        raise HTTPException(
            403,
            {
                "error": "demo_account_locked",
                "message": (
                    "Esta es una cuenta demo compartida. Las claves "
                    "vienen pre-configuradas y no pueden cambiarse."
                ),
            },
        )

    # Validar cada key NO-None contra LiteLLM antes de cifrar.
    plaintexts = {
        "lite": req.key_lite,
        "embeddings": req.key_embeddings,
        "pro": req.key_pro,
    }
    encrypted: dict[str, Optional[str]] = {"lite": None, "embeddings": None, "pro": None}
    for kind, plaintext in plaintexts.items():
        if plaintext is None:
            continue
        try:
            r = await _http.get(
                f"{LITELLM_URL}/v1/models",
                headers={"Authorization": f"Bearer {plaintext}"},
                timeout=5.0,
            )
        except Exception as exc:
            logger.warning("LiteLLM /v1/models unreachable validating %s: %s", kind, exc)
            raise HTTPException(
                400,
                {"error": "litellm_unreachable", "kind": kind},
            )
        if r.status_code != 200:
            raise HTTPException(
                400,
                {
                    "error": "invalid_key",
                    "kind": kind,
                    "litellm_status": r.status_code,
                },
            )
        encrypted[kind] = encrypt_llm_key(plaintext)

    await db.update_llm_keys(
        str(user["id"]),
        encrypted["lite"],
        encrypted["embeddings"],
        encrypted["pro"],
    )
    # Forzar relectura en el cache de resolve_llm_key (TTL 60s podría
    # devolver datos viejos sin esto, frustrando el "guardar y probar").
    # Slice 5: el cache keyea por user.id (no tenant_id), para soportar
    # sub-tenants demo que no tienen fila en usuarios.
    invalidate_llm_key_cache(str(user["id"]))

    return {
        "status": "ok",
        "updated": [kind for kind, v in plaintexts.items() if v is not None],
    }


@app.get("/profile/quota")
async def get_profile_quota(
    request: Request,
    user=Depends(get_current_user),
):
    """Devuelve el estado de la cuota diaria del visitante (Slice 4).

    Endpoint barato — leer dos claves Redis. El frontend lo llama al
    montar la página de Ingest o el modal de perfil para pintar
    "3 / 5 ingests usados hoy" y desactivar el form cuando se topa.

    Para usuarios registrados no aplica cuota diaria (sólo rate-limit
    por minuto), así que devolvemos los campos a 0 con limit alto y
    el frontend simplemente no pinta el contador.

    Las claves de Redis incluyen la IP del visitante, así que si dos
    personas detrás de NAT comparten IP, comparten cuota — pero es
    raro en un demo público abierto a internet.
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ip = _client_ip(request)
    is_demo = bool(user.get("is_demo", False))

    async def _used(op: str) -> int:
        if not is_demo or _redis is None:
            return 0
        ip_key, _ = _demo_quota_keys(op, ip)
        val = await _redis.get(ip_key)
        return int(val) if val else 0

    ingest_used = await _used("ingest")
    chat_used = await _used("chat")

    return {
        "is_demo": is_demo,
        "today": today,
        "ip": ip if is_demo else None,
        "ingest": {
            "used": ingest_used,
            "limit": DEMO_QUOTAS["ingest"]["per_ip"] if is_demo else None,
        },
        "chat": {
            "used": chat_used,
            "limit": DEMO_QUOTAS["chat"]["per_ip"] if is_demo else None,
        },
    }


# ---------------------------------------------------------------------------
# Demo timeline (Slice 6) — frontend de la vista /demo
# ---------------------------------------------------------------------------

@app.get("/demo/timeline", response_model=DemoTimelineResponse)
async def get_demo_timeline(user=Depends(get_current_user)):
    """Devuelve la línea temporal completa de la sesión demo del usuario.

    Solo accesible para sesiones demo (tenant_id empieza con `demo_`).
    El frontend hace polling cada 5s para refrescar el `fired_at` de
    los eventos y repintar el timeline en vivo.

    Para usuarios registrados → 404 (no exponemos que el endpoint existe).
    """
    if not _is_demo_session(user):
        raise HTTPException(404, "not_found")

    session_row = await db.get_demo_session(user["tenant_id"])
    if not session_row:
        # Caso defensivo: get_current_user ya valida, pero por si la
        # sesión expiró entre el decode del JWT y este query.
        raise HTTPException(404, "demo_session_not_found")

    event_rows = await db.get_demo_session_events(user["tenant_id"])

    return DemoTimelineResponse(
        session=DemoTimelineSession(
            tenant_id=session_row["tenant_id"],
            created_at=session_row["created_at"],
            expires_at=session_row["expires_at"],
        ),
        events=[
            DemoTimelineEvent(
                id=e["id"],
                fires_at=e["fires_at"],
                fired_at=e["fired_at"],
                kind=e["kind"],
                recurso_id=e["recurso_id"],
                motivo=e["motivo"],
                description=e["description"],
            )
            for e in event_rows
        ],
    )


# ---------------------------------------------------------------------------
# Resources (KB)
# ---------------------------------------------------------------------------

@app.get("/resources")
async def get_resources(
    estado: str = "todos",
    limit: int = Query(100, gt=0, le=500),
    user=Depends(get_current_user),
):
    # Slice 5: para demo sessions, _tenant_ids_for añade el seed tenant.
    return await db.get_resources(_tenant_ids_for(user), estado, limit)


# ---------------------------------------------------------------------------
# Bandeja de cuarentena (F-05.2)
# ---------------------------------------------------------------------------

@app.get("/resources/quarantine")
async def list_quarantine(
    count_only: bool = False,
    limit: int = Query(100, gt=0, le=500),
    user=Depends(get_current_user),
):
    tenants = _tenant_ids_for(user)
    if count_only:
        return {"count": await db.count_quarantine(tenants)}
    items = await db.list_quarantine(tenants, limit)
    return {"items": items, "count": len(items)}


@app.get("/resources/expired")
async def list_expired_endpoint(
    count_only: bool = False,
    limit: int = Query(100, gt=0, le=500),
    user=Depends(get_current_user),
):
    tenants = _tenant_ids_for(user)
    if count_only:
        return {"count": await db.count_expired(tenants)}
    items = await db.list_expired(tenants, limit)
    return {"items": items, "count": len(items)}


# ---------------------------------------------------------------------------
# Notifications (F-05.3) — feed in-app de transiciones del ciclo de vida
# ---------------------------------------------------------------------------

@app.get("/notifications")
async def list_notifications_endpoint(
    count_only: bool = False,
    only_unread: bool = False,
    limit: int = Query(50, gt=0, le=200),
    user=Depends(get_current_user),
):
    tenants = _tenant_ids_for(user)
    if count_only:
        return {"count": await db.count_unread_notifications(tenants)}
    items = await db.list_notifications(tenants, limit, only_unread)
    return {"items": items, "count": len(items)}


@app.post("/notifications/{notification_id}/read")
async def mark_notification_read_endpoint(
    notification_id: str,
    user=Depends(get_current_user),
    _csrf=Depends(verify_csrf),
):
    ok = await db.mark_notification_read(user["tenant_id"], notification_id)
    if not ok:
        raise HTTPException(404, "Notificación no encontrada o ya leída")
    return {"status": "read", "id": notification_id}


@app.post("/notifications/read-all")
async def mark_all_read_endpoint(
    user=Depends(get_current_user),
    _csrf=Depends(verify_csrf),
):
    count = await db.mark_all_notifications_read(user["tenant_id"])
    return {"status": "ok", "marked": count}


@app.post("/resources/audit-now")
async def audit_now(
    user=Depends(rate_limit_audit),
    _csrf=Depends(verify_csrf),
):
    """Dispara la misma auditoría temporal que el cron diario, pero a
    petición del usuario. Reusa `run_audit_cron()` tal cual: las dos
    fases (caducidad → cuarentena → expirado) ya filtran por estado, así
    que un disparo manual es idempotente y bounded por SQL.

    Sin token administrativo — la autenticación es la del usuario. El
    rate-limit (5/min por tenant) evita abuso desde la UI."""
    from src.data.audit_cron import run_audit_cron
    result = await run_audit_cron()
    logger.info(
        "MANUAL_AUDIT tenant=%s trace=%s cuarentenados=%d expirados=%d",
        user["tenant_id"], result["trace_id"],
        result["cuarentenados"], result["expirados"],
    )
    return {"status": "ok", **result}


@app.post("/resources/{recurso_id}/rescue")
async def rescue_resource(
    recurso_id: str,
    user=Depends(get_current_user),
    _csrf=Depends(verify_csrf),
):
    row = await db.rescue_recurso(user["tenant_id"], recurso_id)
    if not row:
        raise HTTPException(404, "Recurso no encontrado o no rescatable")
    return {"status": "rescued", **{k: (v.isoformat() if hasattr(v, "isoformat") else str(v))
                                     for k, v in row.items()}}


@app.post("/resources/{recurso_id}/quarantine")
async def quarantine_resource(
    recurso_id: str,
    user=Depends(get_current_user),
    _csrf=Depends(verify_csrf),
):
    row = await db.quarantine_recurso(user["tenant_id"], recurso_id)
    if not row:
        raise HTTPException(404, "Recurso no encontrado o no está en estado cuarentenable")
    return {
        "status": "quarantined",
        "id": str(row["id"]),
        "url": row["url"],
        "quarantine_grace_until": row["quarantine_grace_until"].isoformat(),
    }


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
    # Limpieza Qdrant:
    # - Si el recurso desapareció globalmente: borra todos los puntos (todos
    #   los tenants) por filtro recurso_id.
    # - Si solo se desligó de este tenant: borra el punto concreto por
    #   point_id = uuid_v5(recurso_id, tenant_id) — sino quedaría huérfano.
    try:
        if result["deleted_globally"]:
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
        else:
            point_id = _qdrant_point_id(str(result["id"]), user["tenant_id"])
            await _http.post(
                f"{QDRANT_URL}/collections/{COLLECTION}/points/delete",
                json={"points": [point_id]},
                timeout=5.0,
            )
    except Exception as e:
        logger.warning(
            f"Qdrant cleanup failed for {result['id']} "
            f"(global={result['deleted_globally']}): {e}"
        )
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
async def ingest(
    req: IngestRequest,
    request: Request,
    user=Depends(requires_byok),
    _csrf=Depends(verify_csrf),
):
    # Migración 0008: cuota diaria adicional para el demo. El registered
    # ya pasó el guard de requires_byok — si llegó aquí tiene BYOK.
    # Slice 4: la cuota es per-IP (5/día) + cap global (50/día).
    await _demo_daily_quota(user, ip=_client_ip(request), op="ingest")

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


@app.get("/resources/stream")
async def resources_stream(token: str):
    """SSE para transiciones del ciclo de vida del recurso (cuarentena,
    expirado, rescatado). El notifier-worker publica a `resources:{tenant_id}`
    tras insertar la notificación; aquí lo reenviamos al cliente."""
    try:
        payload = verify_token(token)
    except ValueError:
        raise HTTPException(401, "Token inválido")
    tenant_id = payload.get("tenant_id", "")

    async def _events() -> AsyncGenerator[str, None]:
        pubsub = _redis.pubsub()
        await pubsub.subscribe(f"resources:{tenant_id}")
        try:
            yield 'data: {"type":"connected"}\n\n'
            async for msg in pubsub.listen():
                if msg["type"] == "message":
                    yield f"data: {msg['data']}\n\n"
        finally:
            await pubsub.unsubscribe(f"resources:{tenant_id}")
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
                # Migración 0008 + Slice 5: resolvemos la virtual-key
                # del usuario (no del tenant) para embeddings. Demo usa
                # sus keys pre-configuradas; registered con BYOK usa
                # las suyas. La key se asocia al user, no al tenant
                # — necesario para que sub-tenants demo (sin row en
                # usuarios) puedan resolverla.
                tenant_emb_key = await _resolve_user_key(
                    str(user["id"]), "embeddings"
                )
                headers = {
                    "Authorization": f"Bearer {tenant_emb_key}",
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
                    # Slice 5: para demo session, el filter incluye AMBOS
                    # tenants (session + seed) vía cláusula `should`.
                    # Qdrant: dentro de `must`, un sub-bloque `should`
                    # requiere que al menos una condición matchee. Esto
                    # nos da OR en tenant_id manteniendo AND con otros
                    # filtros futuros si los añadimos.
                    visible_tenants = _tenant_ids_for(user)
                    tenant_filter = {
                        "should": [
                            {"key": "tenant_id", "match": {"value": t}}
                            for t in visible_tenants
                        ]
                    }
                    search = {
                        "vector": vector,
                        "filter": {"must": [tenant_filter]},
                        "limit": 10,
                        "with_payload": True,
                    }
                    # Buscamos chunks de contenido (no resúmenes de recurso):
                    # cerebro_chunks tiene un punto por trozo de ~600 tokens con
                    # el texto literal en payload.chunk_text. Imprescindible para
                    # responder preguntas sobre detalles concretos (fechas, cifras).
                    qr = await _http.post(
                        f"{QDRANT_URL}/collections/cerebro_chunks/points/search",
                        json=search,
                        timeout=5.0,
                    )
                    if qr.status_code == 200:
                        raw_hits = qr.json().get("result", [])
                        if raw_hits:
                            recurso_ids = [
                                str(h.get("payload", {}).get("recurso_id"))
                                for h in raw_hits
                                if h.get("payload", {}).get("recurso_id")
                            ]
                            active_ids = await db.get_active_resource_ids(
                                visible_tenants,
                                recurso_ids,
                                include_archive=req.include_archive,
                            )
                            active_set = set(active_ids)
                            hits = [
                                h for h in raw_hits
                                if str(h.get("payload", {}).get("recurso_id")) in active_set
                            ]
                        if hits:
                            # Contexto = chunks ordenados por score; el texto ya
                            # viaja en el payload de Qdrant, sin roundtrip a PG.
                            frags = []
                            for h in hits:
                                p = h.get("payload") or {}
                                title = p.get("title") or p.get("url") or ""
                                chunk_txt = p.get("chunk_text", "")
                                if not chunk_txt:
                                    continue
                                frags.append(
                                    f"### {title}\n"
                                    f"URL: {p.get('url','')}\n"
                                    f"Fragmento (chunk {p.get('chunk_idx', 0)}):\n{chunk_txt}"
                                )
                            if frags:
                                context_block = (
                                    "## Contexto recuperado de tu base de conocimiento:\n\n"
                                    + "\n\n---\n\n".join(frags)
                                )
            except Exception as e:
                logger.warning(f"RAG error: {e}")

    if context_block:
        system_prompt = (
            "Eres un asistente experto. Tienes acceso al contexto extraído de la base "
            "de conocimiento del usuario, delimitado más abajo.\n\n"
            "REGLAS ESTRICTAS:\n"
            "1. Si la respuesta a la pregunta del usuario está total o parcialmente en "
            "el contexto, úsala como fuente principal y cita los datos textualmente "
            "(fechas, nombres, cifras) tal y como aparecen.\n"
            "2. NO digas que 'no hay información específica' si el dato aparece en el "
            "contexto, aunque esté de forma resumida o implícita.\n"
            "3. NO mezcles tu conocimiento general con el contexto a menos que el "
            "usuario lo pida explícitamente; si lo haces, distingue claramente qué "
            "viene del contexto y qué de tu conocimiento previo.\n"
            "4. Si tras leer el contexto sigues sin tener la respuesta, dilo de forma "
            "directa y ofrece tu conocimiento general indicándolo.\n\n"
            f"{context_block}"
        )
    else:
        system_prompt = (
            "Eres un asistente experto. La base de conocimiento del usuario no ha "
            "devuelto resultados relevantes para esta pregunta. Responde con tu "
            "conocimiento general e indícalo explícitamente."
        )

    llm_msgs = [{"role": "system", "content": system_prompt}]
    for m in req.messages[-10:]:
        llm_msgs.append({"role": m.role, "content": m.content})

    logger.info(
        "CHAT model=%s use_rag=%s hits=%d ctx_len=%d msgs=%d",
        req.model, req.use_rag, len(hits), len(context_block), len(llm_msgs),
    )

    # Migración 0008 + Slice 5: resolvemos la virtual-key per-USUARIO
    # (no per-tenant) según el alias del modelo (cerebro-pro → pro,
    # resto → lite). Slice 5 cambió de tenant_id a user_id para que
    # sub-tenants demo (sin row en usuarios) sigan resolviendo.
    tenant_chat_key = await _resolve_user_key(
        str(user["id"]), _model_kind(req.model)
    )
    litellm_headers = {"Authorization": f"Bearer {tenant_chat_key}", "Content-Type": "application/json"}

    rag_sources = []
    if req.use_rag and hits:
        # Dedupe por recurso: con chunks, varios hits pueden pertenecer al mismo
        # documento; nos quedamos con el score máximo por recurso para la UI.
        best_by_recurso: dict[str, dict] = {}
        for hit in hits:
            p = hit.get("payload") or {}
            rid = str(p.get("recurso_id") or "")
            if not rid:
                continue
            score = round(hit["score"], 3)
            prev = best_by_recurso.get(rid)
            if prev is None or score > prev["score"]:
                best_by_recurso[rid] = {
                    "title": p.get("title", ""),
                    "url": p.get("url", ""),
                    "score": score,
                }
        rag_sources = sorted(best_by_recurso.values(), key=lambda s: s["score"], reverse=True)

    async def _stream() -> AsyncGenerator[str, None]:
        if rag_sources:
            yield f"data: {json.dumps({'type': 'sources', 'sources': rag_sources})}\n\n"
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST",
                    f"{LITELLM_URL}/v1/chat/completions",
                    headers=litellm_headers,
                    json={"model": req.model, "messages": llm_msgs, "stream": True},
                ) as resp:
                    async for chunk in resp.aiter_text():
                        yield chunk
        except Exception as exc:
            logger.exception("CHAT stream failed: %s", exc)
            err_payload = json.dumps({"type": "error", "message": "Error generando respuesta del modelo."})
            yield f"data: {err_payload}\n\n"
            yield "data: [DONE]\n\n"

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


@app.post("/admin/cleanup-demo-sessions")
async def cleanup_demo_sessions(
    x_admin_token: str | None = Header(None, alias="X-Admin-Token"),
):
    """Slice 5: dispara manualmente la limpieza de sesiones demo
    expiradas. Útil para n8n cron de respaldo (el cleanup_task de la
    api ya corre cada 60s, este endpoint es para visibilidad y disaster
    recovery — un operador puede dispararlo para verificar inmediatamente
    sin esperar al tick).

    Idempotente: si no hay sesiones expiradas, devuelve cleaned=0.
    """
    if not AUDIT_CRON_TOKEN:
        raise HTTPException(503, "AUDIT_CRON_TOKEN no configurado")
    if x_admin_token != AUDIT_CRON_TOKEN:
        raise HTTPException(401, "Token administrativo inválido")

    expired = await db.get_expired_demo_sessions()
    details = []
    for s in expired:
        try:
            await _qdrant_delete_tenant_points(s["tenant_id"])
            res = await db.delete_demo_session_cascade(s["tenant_id"])
            details.append(res)
        except Exception as exc:
            logger.exception("cleanup failed for %s: %s", s["tenant_id"], exc)
            details.append({"tenant_id": s["tenant_id"], "error": str(exc)})
    return {"status": "ok", "cleaned": len(details), "details": details}


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
