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
from ..services.settings_service import (
    DEFAULT_SETTINGS,
    load_runtime_settings,
    setting_category,
    settings_schema,
)

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


class SettingSchemaItem(BaseModel):
    """设置项元数据（供前端表单渲染）."""

    key: str
    category: str
    type: str  # string | number | boolean | select
    label: str
    description: str
    value: str
    options: Optional[list[str]] = None


class ConnectionTestResponse(BaseModel):
    ok: bool
    message: str


@router.get("/schema", response_model=list[SettingSchemaItem])
async def get_settings_schema(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """返回设置项元数据列表（key/category/type/label/description/options/value）.

    供前端设置页按 type 渲染 input/number/toggle/select 分组表单。
    value 优先用 DB 已存值，否则用 DEFAULT_SETTINGS 兜底。
    """
    saved_map: dict[str, str] = {}
    result = await db.execute(select(Setting))
    for item in result.scalars().all():
        saved_map[item.key] = item.value
    return settings_schema(saved_map)


@router.get("/", response_model=list[SettingResponse])
async def list_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all settings."""
    result = await db.execute(select(Setting))
    saved_settings = {item.key: item for item in result.scalars().all()}

    responses = []
    for key, default in DEFAULT_SETTINGS.items():
        saved = saved_settings.pop(key, None)
        if saved:
            responses.append(
                SettingResponse(
                    key=saved.key,
                    value=saved.value,
                    category=saved.category,
                    updated_at=saved.updated_at,
                    updated_by=saved.updated_by,
                )
            )
        else:
            responses.append(
                SettingResponse(
                    key=key,
                    value=default["value"],
                    category=default["category"],
                    updated_at=datetime.now(),
                    updated_by=current_user.id,
                )
            )

    for saved in saved_settings.values():
        responses.append(
            SettingResponse(
                key=saved.key,
                value=saved.value,
                category=saved.category,
                updated_at=saved.updated_at,
                updated_by=saved.updated_by,
            )
        )

    return responses


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
        setting = Setting(
            key=key,
            value=request.value,
            category=DEFAULT_SETTINGS.get(key, {}).get("category", setting_category(key)),
            updated_by=current_user.id,
        )
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
    settings_map = await load_runtime_settings(db)
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
