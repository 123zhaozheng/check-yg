"""Auth schemas."""

from pydantic import BaseModel


class LoginRequest(BaseModel):
    """Login request."""

    username: str
    password: str


class TokenResponse(BaseModel):
    """JWT token response."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    """Refresh token request."""

    refresh_token: str


class UserResponse(BaseModel):
    """User info response."""

    id: int
    username: str
    email: str
    role: str
    is_active: bool

    class Config:
        from_attributes = True


class TokenPayload(BaseModel):
    """JWT token payload."""

    sub: str
    type: str
    exp: int
