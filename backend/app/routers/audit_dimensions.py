# -*- coding: utf-8 -*-
"""审查维度 CRUD router (06-26-ai-agent).

* ``GET /api/audit-dimensions`` —— 列维度（所有登录用户可读）。
* ``POST /api/audit-dimensions`` —— 新建维度（admin）。
* ``GET /api/audit-dimensions/{id}`` —— 维度详情（所有登录用户可读）。
* ``PUT /api/audit-dimensions/{id}`` —— 编辑维度（admin）。
* ``DELETE /api/audit-dimensions/{id}`` —— 删维度（admin；删 system 需 admin，
  删 agent 建的需 owner/admin；已被 finding 引用 → 409）。

鉴权：CRUD 限 admin（删 system 维度仅 admin，删 agent 维度需 owner/admin=created_by
本人或 admin）。沿用 ``check_admin_permission``。复刻 ``keyword_library`` 路由结构。
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.dependencies import get_current_user
from ..auth.permissions import check_admin_permission
from ..database import get_db
from ..models import User
from ..schemas.audit import (
    AuditDimensionCreate,
    AuditDimensionDetail,
    AuditDimensionListItem,
    AuditDimensionUpdate,
)
from ..services.audit.dimension_service import dimension_service

router = APIRouter(prefix="/audit-dimensions", tags=["audit-dimensions"])


def _require_admin(db: AsyncSession, user: User):
    """Admin 鉴权辅助——失败抛 403。"""
    return check_admin_permission(db, user)


def _list_item(d: dict) -> AuditDimensionListItem:
    return AuditDimensionListItem(**d)


def _detail(d: dict) -> AuditDimensionDetail:
    return AuditDimensionDetail(**d)


@router.get("", response_model=list[AuditDimensionListItem])
async def list_audit_dimensions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出所有维度（所有登录用户可读）。"""
    dims = await dimension_service.list_dimensions(db)
    return [_list_item(d) for d in dims]


@router.get("/{dimension_id}", response_model=AuditDimensionDetail)
async def get_audit_dimension(
    dimension_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """维度详情（含 steps / judgment / prompt）。所有登录用户可读。"""
    d = await dimension_service.get_dimension(db, dimension_id)
    if d is None:
        raise HTTPException(status_code=404, detail="Dimension not found")
    return _detail(d)


@router.post("", response_model=AuditDimensionDetail, status_code=201)
async def create_audit_dimension(
    request: AuditDimensionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """新建维度（admin）。body: name/purpose/steps/judgment/severity/source?/enabled?."""
    if not await _require_admin(db, current_user):
        raise HTTPException(status_code=403, detail="Admin permission required")
    try:
        dim = await dimension_service.create_dimension(
            db,
            name=request.name,
            purpose=request.purpose,
            steps=[s.model_dump() for s in request.steps],
            judgment=request.judgment,
            severity=request.severity,
            created_by=current_user.id,
            source=request.source,
            enabled=request.enabled,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await db.commit()
    detail = await dimension_service.get_dimension(db, dim.id)
    return _detail(detail)  # type: ignore[arg-type]


@router.put("/{dimension_id}", response_model=AuditDimensionDetail)
async def update_audit_dimension(
    dimension_id: int,
    request: AuditDimensionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """编辑维度（admin）。可改 name/purpose/steps/judgment/severity/enabled。"""
    if not await _require_admin(db, current_user):
        raise HTTPException(status_code=403, detail="Admin permission required")
    try:
        await dimension_service.update_dimension(
            db,
            dimension_id,
            name=request.name,
            purpose=request.purpose,
            steps=[s.model_dump() for s in request.steps] if request.steps is not None else None,
            judgment=request.judgment,
            severity=request.severity,
            enabled=request.enabled,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await db.commit()
    detail = await dimension_service.get_dimension(db, dimension_id)
    return _detail(detail)  # type: ignore[arg-type]


@router.delete("/{dimension_id}", status_code=204)
async def delete_audit_dimension(
    dimension_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删维度（admin；删 system 需 admin，删 agent 建的需 owner/admin；
    已被 finding 引用 → 409）。agent 无删除工具——删维度全在 UI/后端做。"""
    if not await _require_admin(db, current_user):
        raise HTTPException(status_code=403, detail="Admin permission required")
    try:
        await dimension_service.delete_dimension(db, dimension_id, user=current_user)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        # 已被 finding 引用 → 409（对齐删已指派模型卡返 409）。
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await db.commit()
    return None
