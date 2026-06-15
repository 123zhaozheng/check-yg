"""User schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UserCreate(BaseModel):
    """Schema for creating a user."""

    username: str
    email: str
    password: str
    role_id: int


class UserRead(BaseModel):
    """Schema for reading a user."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str
    role_id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class UserUpdate(BaseModel):
    """Schema for updating a user."""

    email: str | None = None
    is_active: bool | None = None
    role_id: int | None = None
