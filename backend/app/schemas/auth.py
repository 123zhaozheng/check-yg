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
    """Refresh token request.

    ``refresh_token`` 可选：cookie 模式下从 httpOnly cookie 读取，body 可空；
    过渡期或 API 测试也可通过 body 传。
    """

    refresh_token: str | None = None


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


class ChangePasswordRequest(BaseModel):
    """POST /api/auth/change-password 请求体."""

    old_password: str
    new_password: str


class UpdateMeRequest(BaseModel):
    """PATCH /api/users/me 请求体（个人信息，当前用户改自己）."""

    username: str | None = None
    email: str | None = None
