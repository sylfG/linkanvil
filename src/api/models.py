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


class UserResponse(BaseModel):
    id: UUID
    email: str
    tenant_id: str
    telegram_bot_active: bool
    created_at: datetime


class TelegramBotRequest(BaseModel):
    bot_token: str


class ChatMessage(BaseModel):
    role: str
    content: str = Field(..., max_length=32_000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(..., min_length=1, max_length=100)
    model: str = "cerebro-lite"
    use_rag: bool = True


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
