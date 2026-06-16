# -*- coding: utf-8 -*-
"""Permission checking utilities."""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Collaborator, Role, Task, User


async def check_task_permission(
    db: AsyncSession,
    user: User,
    task_id: int,
    required_role: Optional[str] = None,
) -> bool:
    """
    Check if user has permission to access a task.

    Args:
        db: Database session
        user: Current user
        task_id: Task ID to check
        required_role: Required collaborator role (read/write/admin), None means any access

    Returns:
        True if user has permission, False otherwise
    """
    # Check if user is task owner
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()

    if not task:
        return False

    if task.owner_id == user.id:
        return True

    if await check_admin_permission(db, user):
        return True

    # Check if user is a collaborator
    result = await db.execute(
        select(Collaborator).where(
            Collaborator.task_id == task_id,
            Collaborator.user_id == user.id
        )
    )
    collaborator = result.scalar_one_or_none()

    if not collaborator:
        return False

    # If specific role required, check it
    if required_role:
        role_hierarchy = {"read": 0, "write": 1, "admin": 2}
        user_level = role_hierarchy.get(collaborator.role, -1)
        required_level = role_hierarchy.get(required_role, 999)
        return user_level >= required_level

    return True


async def check_admin_permission(db: AsyncSession, user: User) -> bool:
    """Check if user has admin role."""
    result = await db.execute(select(Role).where(Role.id == user.role_id))
    role = result.scalar_one_or_none()
    return bool(role and role.name == "admin")
