"""Document schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class DocumentCreate(BaseModel):
    """Schema for creating a document."""

    filename: str
    original_path: str


class DocumentRead(BaseModel):
    """Schema for reading a document."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    filename: str
    original_path: str
    status: str
    extracted_tables: dict[str, Any] | None
    flow_tables: dict[str, Any] | None
    error_log: str | None
    created_at: datetime
