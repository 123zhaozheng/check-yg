# -*- coding: utf-8 -*-
"""User management router (admin only)."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.dependencies import get_current_user
from ..auth.password import hash_password
from ..auth.permissions import check_admin_permission
from ..database import get_db
from ..models import Role, User
from ..schemas.auth import UpdateMeRequest, UserResponse

router = APIRouter(prefix="/users", tags=["users"])


class UserCreate(BaseModel):
    """Create user request schema."""
    username: str
    email: EmailStr
    password: str
    role: str = "auditor"  # admin, auditor, viewer


class UserUpdate(BaseModel):
    """Update user request schema."""
    email: EmailStr | None = None
    role: str | None = None
    is_active: bool | None = None


class UserResponse(BaseModel):
    """User response schema."""
    id: int
    username: str
    email: str
    role: str
    is_active: bool

    class Config:
        from_attributes = True


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    request: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new user (admin only)."""
    # Check admin permission
    if not await check_admin_permission(db, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can create users",
        )

    # Check if username exists
    result = await db.execute(
        select(User).where(User.username == request.username)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists",
        )

    # Check if email exists
    result = await db.execute(
        select(User).where(User.email == request.email)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already exists",
        )

    # Get role
    result = await db.execute(
        select(Role).where(Role.name == request.role)
    )
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Role '{request.role}' does not exist",
        )

    # Create user
    user = User(
        username=request.username,
        email=request.email,
        hashed_password=hash_password(request.password),
        role_id=role.id,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        role=request.role,
        is_active=user.is_active,
    )


@router.patch("/me", response_model=UserResponse)
async def update_me(
    request: UpdateMeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """当前用户改自己的个人信息（username/email，非 admin-only）.

    不允许改 role/hashed_password（敏感字段走 admin 路由或 change-password）.
    username 冲突→409；email 冲突→409.
    """
    result = await db.execute(select(User).where(User.id == current_user.id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if request.username is not None and request.username != user.username:
        existing = await db.execute(
            select(User).where(User.username == request.username, User.id != user.id)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username already exists",
            )
        user.username = request.username

    if request.email is not None and request.email != user.email:
        existing = await db.execute(
            select(User).where(User.email == request.email, User.id != user.id)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already exists",
            )
        user.email = request.email

    await db.commit()
    await db.refresh(user)

    role_result = await db.execute(select(Role).where(Role.id == user.role_id))
    role = role_result.scalar_one_or_none()
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        role=role.name if role else "unknown",
        is_active=user.is_active,
    )


@router.get("/", response_model=List[UserResponse])
async def list_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all users (admin only)."""
    if not await check_admin_permission(db, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can list users",
        )

    result = await db.execute(select(User))
    users = result.scalars().all()

    user_responses = []
    for user in users:
        role_result = await db.execute(select(Role).where(Role.id == user.role_id))
        role = role_result.scalar_one_or_none()
        user_responses.append(
            UserResponse(
                id=user.id,
                username=user.username,
                email=user.email,
                role=role.name if role else "unknown",
                is_active=user.is_active,
            )
        )

    return user_responses


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get user details (admin only or self)."""
    # Allow users to view their own profile
    if current_user.id != user_id and not await check_admin_permission(db, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view this user",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    role_result = await db.execute(select(Role).where(Role.id == user.role_id))
    role = role_result.scalar_one_or_none()
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        role=role.name if role else "unknown",
        is_active=user.is_active,
    )


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    request: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update user (admin only)."""
    if not await check_admin_permission(db, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can update users",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Update fields
    if request.email is not None:
        # Check if email exists
        existing = await db.execute(
            select(User).where(User.email == request.email, User.id != user_id)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already exists",
            )
        user.email = request.email

    if request.role is not None:
        result = await db.execute(
            select(Role).where(Role.name == request.role)
        )
        role = result.scalar_one_or_none()
        if not role:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Role '{request.role}' does not exist",
            )
        user.role_id = role.id

    if request.is_active is not None:
        user.is_active = request.is_active

    await db.commit()
    await db.refresh(user)

    role_result = await db.execute(select(Role).where(Role.id == user.role_id))
    role = role_result.scalar_one_or_none()
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        role=role.name if role else "unknown",
        is_active=user.is_active,
    )


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete user (admin only)."""
    if not await check_admin_permission(db, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can delete users",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Prevent deleting self
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account",
        )

    await db.delete(user)
    await db.commit()
