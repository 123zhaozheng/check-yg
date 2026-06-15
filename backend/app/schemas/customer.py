"""Customer schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CustomerListCreate(BaseModel):
    """Schema for creating a customer list."""

    name: str


class CustomerListRead(BaseModel):
    """Schema for reading a customer list."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    owner_id: int
    row_count: int
    created_at: datetime


class CustomerListItemCreate(BaseModel):
    """Schema for creating a customer list item."""

    name: str
    notes: str | None = None


class CustomerListItemRead(BaseModel):
    """Schema for reading a customer list item."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    list_id: int
    name: str
    notes: str | None
