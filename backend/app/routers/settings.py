# -*- coding: utf-8 -*-
"""Settings management router."""

from datetime import datetime
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.dependencies import get_current_user
from ..auth.permissions import check_admin_permission
from ..database import get_db
from ..models import Setting, User

router = APIRouter(prefix="/settings", tags=["settings"])


class SettingResponse(BaseModel):
    key: str
    value: str
    category: str
    updated_at: datetime
    updated_by: int

    class Config:
        from_attributes = True


class SettingUpdate(BaseModel):
    value: str


class ConnectionTestResponse(BaseModel):
    ok: bool
    message: str


@router.get("/", response_model=list[SettingResponse])
async def list_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all settings."""
    result = await db.execute(select(Setting))
    settings = result.scalars().all()

    return [
        SettingResponse(
            key=s.key,
            value=s.value,
            category=s.category,
            updated_at=s.updated_at,
            updated_by=s.updated_by,
        )
        for s in settings
    ]


@router.get("/{key}", response_model=SettingResponse)
async def get_setting(
    key: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a specific setting."""
    result = await db.execute(select(Setting).where(Setting.key == key))
    setting = result.scalar_one_or_none()

    if not setting:
        raise HTTPException(status_code=404, detail="Setting not found")

    return SettingResponse(
        key=setting.key,
        value=setting.value,
        category=setting.category,
        updated_at=setting.updated_at,
        updated_by=setting.updated_by,
    )


@router.put("/{key}", response_model=SettingResponse)
async def update_setting(
    key: str,
    request: SettingUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a setting."""
    if not await check_admin_permission(db, current_user):
        raise HTTPException(status_code=403, detail="Admin permission required")

    result = await db.execute(select(Setting).where(Setting.key == key))
    setting = result.scalar_one_or_none()

    if not setting:
        setting = Setting(key=key, value=request.value, category="general", updated_by=current_user.id)
        db.add(setting)
    else:
        setting.value = request.value
        setting.updated_by = current_user.id

    await db.commit()
    await db.refresh(setting)

    return SettingResponse(
        key=setting.key,
        value=setting.value,
        category=setting.category,
        updated_at=setting.updated_at,
        updated_by=setting.updated_by,
    )


@router.post("/test-connection", response_model=ConnectionTestResponse)
async def test_connection(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Test configured LLM endpoint reachability."""
    result = await db.execute(select(Setting))
    settings_map = {s.key: s.value for s in result.scalars().all()}
    base_url = (settings_map.get("llm.base_url") or "").rstrip("/")
    api_key = settings_map.get("llm.api_key") or ""

    if not base_url:
        return ConnectionTestResponse(ok=False, message="LLM Base URL is not configured")

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = "Bearer %s" % api_key

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get("%s/models" % base_url, headers=headers)
        if response.status_code >= 400:
            return ConnectionTestResponse(
                ok=False,
                message="LLM endpoint returned HTTP %s" % response.status_code,
            )
        return ConnectionTestResponse(ok=True, message="LLM endpoint is reachable")
    except Exception as exc:
        return ConnectionTestResponse(ok=False, message=str(exc))
