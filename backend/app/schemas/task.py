"""Task schemas."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class TaskCreate(BaseModel):
    """Schema for creating a task."""

    title: str
    description: str | None = None
    config: dict[str, Any] | None = None


class TaskRead(BaseModel):
    """Schema for reading a task."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None
    owner_id: int
    status: str
    config: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class TaskList(BaseModel):
    """Schema for task list item."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    status: str
    owner_id: int
    created_at: datetime
    updated_at: datetime
