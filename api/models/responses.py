"""
Response envelope models.

Every API endpoint returns APIResponse[T] to ensure consistent
provenance metadata appears alongside all data payloads.
"""
from datetime import datetime
from typing import Generic, TypeVar
from pydantic import BaseModel

T = TypeVar("T")


class FuenteMeta(BaseModel):
    """Freshness record for one data source."""
    dataset_id: str
    nombre: str
    last_ingested_at: datetime | None = None
    record_count: int | None = None


class ResponseMeta(BaseModel):
    """Metadata block included in every API response."""
    fuentes: list[FuenteMeta]
    generated_at: datetime


class APIResponse(BaseModel, Generic[T]):
    """Standard response envelope wrapping any data payload."""
    data: T
    meta: ResponseMeta
