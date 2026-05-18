from __future__ import annotations
import re
from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field, field_validator

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RegisterRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if not _EMAIL_RE.match(v.strip()):
            raise ValueError("Email inválido")
        return v.strip().lower()


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        return v.strip().lower()


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


_POLICY_KEYS = (
    "evento_pasado_alto",
    "evento_pasado_medio",
    "evento_pasado_nulo",
    "referencia_pasada_alto",
    "referencia_pasada_medio",
    "referencia_pasada_nulo",
)
_POLICY_VALUES = ("activo", "cuarentena", "expirado")
_DEFAULT_POLICY = {
    "evento_pasado_alto": "expirado",
    "evento_pasado_medio": "cuarentena",
    "evento_pasado_nulo": "cuarentena",
    "referencia_pasada_alto": "expirado",
    "referencia_pasada_medio": "cuarentena",
    "referencia_pasada_nulo": "cuarentena",
}


class UserResponse(BaseModel):
    id: UUID
    email: str
    tenant_id: str
    telegram_bot_active: bool
    created_at: datetime
    # Policy de auditoría por celda (migración 0007). Decide qué hacer con
    # recursos pasados según class × valor_archivistico. Default = preset
    # Equilibrado. 6 keys: {evento_pasado|referencia_pasada}_{alto|medio|nulo}.
    audit_policy: dict[str, str] = Field(default_factory=lambda: dict(_DEFAULT_POLICY))
    # Migración 0008: BYOK + cuenta demo.
    # `is_demo=true` desactiva el PUT /profile/llm-keys y activa cuotas
    # diarias. `llm_keys_configured=true` cuando hay al menos una virtual
    # key cifrada en BD — el frontend lo usa para decidir si mostrar el
    # banner "Sin claves, no puedes ingestar/chatear" o no.
    is_demo: bool = False
    llm_keys_configured: bool = False
    # Slice 5: cuando el usuario está en una sesión demo efímera, estos
    # campos llevan la info del countdown (TTL 15min desde el login).
    # Ausentes (None) para usuarios registrados. El frontend pinta el
    # banner de cuenta atrás y un modal de re-login cuando llega a 0.
    demo_session_expires_at: Optional[str] = None
    demo_session_seconds_remaining: Optional[int] = None


class TelegramBotRequest(BaseModel):
    bot_token: str


class LLMKeysRequest(BaseModel):
    """Payload de PUT /profile/llm-keys (migración 0008).

    Cada campo es opcional — el endpoint aplica PATCH semántico, sólo
    actualiza los keys no-None. Esto permite editar una key sin tener
    que reenviar las otras dos. Si los tres llegan None, no hay efecto.

    Las keys son virtual-keys emitidas por el LiteLLM proxy del owner
    (no API keys de OpenAI/Anthropic). El validador rechaza strings
    vacíos y trims whitespace.
    """
    key_lite: Optional[str] = None
    key_embeddings: Optional[str] = None
    key_pro: Optional[str] = None

    @field_validator("key_lite", "key_embeddings", "key_pro")
    @classmethod
    def _trim_or_none(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        if len(v) > 256:
            raise ValueError("LLM key demasiado larga (máx 256 chars)")
        return v


class AuditPolicyRequest(BaseModel):
    """Payload de PUT /profile/audit-policy. Exige las 6 keys del JSONB con
    valores enum; rechaza extras para evitar drift silencioso del schema."""
    policy: dict[str, str]

    @field_validator("policy")
    @classmethod
    def validate_policy(cls, v: dict[str, str]) -> dict[str, str]:
        if not isinstance(v, dict):
            raise ValueError("policy debe ser un objeto JSON")
        missing = [k for k in _POLICY_KEYS if k not in v]
        if missing:
            raise ValueError(f"policy: faltan keys requeridas: {', '.join(missing)}")
        extra = [k for k in v if k not in _POLICY_KEYS]
        if extra:
            raise ValueError(f"policy: keys desconocidas: {', '.join(extra)}")
        for k in _POLICY_KEYS:
            val = v[k]
            if val not in _POLICY_VALUES:
                raise ValueError(
                    f"policy[{k}]: '{val}' inválido (esperado {_POLICY_VALUES})"
                )
        return {k: v[k] for k in _POLICY_KEYS}  # normaliza orden


class ChatMessage(BaseModel):
    role: str
    content: str = Field(..., max_length=32_000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(..., min_length=1, max_length=100)
    model: str = "cerebro-lite"
    use_rag: bool = True
    # Migración 0006: si True, el RAG también considera recursos en estado
    # `expirado` (que ahora se llama "Archivo histórico"). Toggle del chat.
    include_archive: bool = False


class IngestRequest(BaseModel):
    url: str
    source: str = "web"


class CfCookiesRequest(BaseModel):
    domain: str
    cf_clearance: str
    extra: Optional[dict[str, str]] = None
    ttl_hours: int = 168  # 7 días


class SessionResponse(BaseModel):
    id: UUID
    titulo: Optional[str]
    ultimo_acceso: datetime
    created_at: datetime


class MessageIn(BaseModel):
    role: str
    content: str
    sources: list[dict] = []

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in ("user", "assistant", "system"):
            raise ValueError("role debe ser user, assistant o system")
        return v


class MessageOut(BaseModel):
    id: UUID
    role: str
    content: str
    sources: list[dict]
    created_at: datetime
