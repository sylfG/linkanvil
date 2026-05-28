from pydantic import BaseModel, Field, field_validator
from typing import Optional
import uuid

from ._url_safety import validate_url, UnsafeURLError


class IngestionRequest(BaseModel):
    # Mantenemos url como `str` para que viaje sin coercer hasta Redis y
    # la DLQ (json.dumps + Bloom filter no aceptan tipos custom). La
    # validacion anti-SSRF cubre lo que aportaba AnyHttpUrl (scheme
    # http/https) y mas: hostnames internos del compose, sufijos
    # *.localhost / *.internal, IPs privadas/loopback/link-local en
    # literales y resolucion DNS para tapar rebinding.
    url: str
    tenant_id: str
    source: Optional[str] = "api"
    trace_id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()))

    @field_validator("url")
    @classmethod
    def _safe_url(cls, v: str) -> str:
        try:
            validate_url(v)
        except UnsafeURLError as e:
            raise ValueError(f"URL rechazada: {e}") from e
        return v


class IngestionResponse(BaseModel):
    status: str
    trace_id: str
    is_duplicate: bool
    is_valid: bool
