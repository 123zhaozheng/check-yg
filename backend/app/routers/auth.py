# -*- coding: utf-8 -*-
"""Authentication router.

鉴权 cookie 化（硬底线 Q4）：access + refresh 存 httpOnly cookie，
``SameSite=Strict``、``Path=/``。``/login`` 与 ``/refresh`` ``Set-Cookie``，
``/refresh`` 优先从 cookie 读 refresh（body 兼容过渡），``/me`` 从 cookie 读
access（由 ``get_current_user`` 统一处理），``/logout`` 清 cookie。
同源前提由 B1 块5（FastAPI 挂 frontend/dist）保证。
"""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.dependencies import get_current_user
from ..auth.jwt import create_access_token, create_refresh_token, verify_token
from ..auth.password import verify_password
from ..config import settings
from ..database import get_db
from ..models import User, Role
from ..schemas.auth import LoginRequest, TokenResponse, RefreshRequest, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])

_COOKIE_KEY_ACCESS = "access_token"
_COOKIE_KEY_REFRESH = "refresh_token"
_COOKIE_SAMESITE = "strict"


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    """把 access/refresh 写进 httpOnly cookie。"""
    response.set_cookie(
        _COOKIE_KEY_ACCESS,
        access_token,
        httponly=True,
        samesite=_COOKIE_SAMESITE,
        secure=False,  # 本地 http；生产同源 https 时置 True
        path="/",
    )
    response.set_cookie(
        _COOKIE_KEY_REFRESH,
        refresh_token,
        httponly=True,
        samesite=_COOKIE_SAMESITE,
        secure=False,
        path="/",
    )


def _clear_auth_cookies(response: Response) -> None:
    """清除 access/refresh cookie。"""
    response.delete_cookie(_COOKIE_KEY_ACCESS, path="/")
    response.delete_cookie(_COOKIE_KEY_REFRESH, path="/")


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Login with username and password. Set access+refresh httpOnly cookies."""
    result = await db.execute(
        select(User).where(User.username == request.username)
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(request.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": 'Bearer realm="cookie"'},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )

    access_token = create_access_token(
        user_id=user.id,
        expires_delta=timedelta(minutes=settings.JWT_EXPIRE_MINUTES),
    )
    refresh_token = create_refresh_token(user_id=user.id)

    _set_auth_cookies(response, access_token, refresh_token)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user information (reads access_token from cookie/header)."""
    result = await db.execute(select(Role).where(Role.id == current_user.role_id))
    role = result.scalar_one_or_none()
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        role=role.name if role else "unknown",
        is_active=current_user.is_active,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: Request,
    response: Response,
    body: RefreshRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Refresh access token. Read refresh_token from cookie first, then body."""
    refresh_token_value = request.cookies.get(_COOKIE_KEY_REFRESH)
    if not refresh_token_value and body is not None:
        refresh_token_value = body.refresh_token

    if not refresh_token_value:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing refresh token",
            headers={"WWW-Authenticate": 'Bearer realm="cookie"'},
        )

    payload = verify_token(refresh_token_value)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": 'Bearer realm="cookie"'},
        )

    user_id = int(payload["sub"])
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or disabled",
            headers={"WWW-Authenticate": 'Bearer realm="cookie"'},
        )

    access_token = create_access_token(
        user_id=user.id,
        expires_delta=timedelta(minutes=settings.JWT_EXPIRE_MINUTES),
    )
    new_refresh_token = create_refresh_token(user_id=user.id)

    _set_auth_cookies(response, access_token, new_refresh_token)

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
    )


@router.post("/logout")
async def logout(response: Response):
    """Clear auth cookies (client-side logout)."""
    _clear_auth_cookies(response)
    return {"detail": "logged out"}
