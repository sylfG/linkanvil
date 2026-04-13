from pydantic import BaseModel, Field
from typing import Optional
import uuid

class IngestionRequest(BaseModel):
    url: str
    tenant_id: str
    source: Optional[str] = "api"
    trace_id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()))

class IngestionResponse(BaseModel):
    status: str
    trace_id: str
    is_duplicate: bool
    is_valid: bool
