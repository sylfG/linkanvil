from pydantic import BaseModel, Field, field_validator, AnyHttpUrl
from typing import Optional
import uuid

from ._url_safety import validate_url, UnsafeURLError


class IngestionRequest(BaseModel):
    # AnyHttpUrl ya restringe scheme a http/https. La validacion anti-SSRF
    # adicional cubre hostnames internos, IPs privadas y DNS rebinding.
    url: AnyHttpUrl
    tenant_id: str
    source: Optional[str] = "api"
    trace_id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()))

    @field_validator("url")
    @classmethod
    def _no_internal(cls, v: AnyHttpUrl) -> AnyHttpUrl:
        try:
            validate_url(str(v))
        except UnsafeURLError as e:
            raise ValueError(f"URL rechazada: {e}") from e
        return v


class IngestionResponse(BaseModel):
    status: str
    trace_id: str
    is_duplicate: bool
    is_valid: bool
