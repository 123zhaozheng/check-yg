"""Common schemas."""

from pydantic import BaseModel


class PaginationParams(BaseModel):
    """Pagination parameters."""

    page: int = 1
    page_size: int = 20


class PaginatedResponse(BaseModel):
    """Paginated response wrapper."""

    total: int
    page: int
    page_size: int
    items: list


class MessageResponse(BaseModel):
    """Simple message response."""

    message: str
