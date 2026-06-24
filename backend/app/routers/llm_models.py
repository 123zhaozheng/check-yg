# -*- coding: utf-8 -*-
"""LLM 模型卡片 CRUD + 阶段指派 router (06-23-llm-model-card).

* ``GET /api/llm-models`` 列表（所有登录用户可读，api_key 脱敏）。
* ``POST /api/llm-models`` 新建（admin）。
* ``PUT /api/llm-models/{id}`` 更新（admin；api_key 空/脱敏串不改原值）。
* ``DELETE /api/llm-models/{id}`` 删除（admin；被指派的卡片拒绝删除返 409）。
* ``GET /api/llm-model-assignments`` 列出 6 阶段 + 各自指派（所有登录用户可读）。
* ``PUT /api/llm-model-assignments/{stage}`` 指派/解除（admin）。

鉴权：CRUD/指派限 admin；列表所有登录用户可读。沿用 ``check_admin_permission``。
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..auth.dependencies import get_current_user
from ..auth.permissions import check_admin_permission
from ..database import get_db
from ..models import LLMModel, LLMModelAssignment, User
from ..models.llm_model_assignment import STAGES
from ..schemas.llm_model import (
    LLMModelAssignmentResponse,
    LLMModelAssignmentUpdate,
    LLMModelCreate,
    LLMModelResponse,
    LLMModelUpdate,
    is_masked_api_key,
    is_valid_stage,
    mask_api_key,
)

router = APIRouter(tags=["llm-models"])


def _require_admin(db: AsyncSession, user: User):
    """Admin 鉴权辅助——失败抛 403。"""
    return check_admin_permission(db, user)


def _to_response(model: LLMModel) -> LLMModelResponse:
    """构造脱敏响应（api_key 不返明文）。"""
    return LLMModelResponse(
        id=model.id,
        display_name=model.display_name,
        model_name=model.model_name,
        provider_base_url=model.provider_base_url,
        api_key=mask_api_key(model.api_key or ""),
        context_length=model.context_length,
        max_output=model.max_output,
        supports_tool_call=model.supports_tool_call,
        supports_tool_choice_required=model.supports_tool_choice_required,
        is_reasoning=model.is_reasoning,
        supports_streaming=model.supports_streaming,
        default_thinking=model.default_thinking,
        default_max_tokens=model.default_max_tokens,
        default_temperature=model.default_temperature,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


# ---------------------------------------------------------------------------
# 模型卡片 CRUD
# ---------------------------------------------------------------------------


@router.get("/llm-models", response_model=list[LLMModelResponse])
async def list_llm_models(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出所有模型卡片（所有登录用户可读，api_key 脱敏）。"""
    result = await db.execute(select(LLMModel).order_by(LLMModel.id.asc()))
    return [_to_response(m) for m in result.scalars().all()]


@router.post("/llm-models", response_model=LLMModelResponse, status_code=201)
async def create_llm_model(
    request: LLMModelCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """新建模型卡片（admin）。"""
    if not await _require_admin(db, current_user):
        raise HTTPException(status_code=403, detail="Admin permission required")

    model = LLMModel(
        display_name=request.display_name,
        model_name=request.model_name,
        provider_base_url=request.provider_base_url,
        api_key=request.api_key or "",
        context_length=request.context_length,
        max_output=request.max_output,
        supports_tool_call=request.supports_tool_call,
        supports_tool_choice_required=request.supports_tool_choice_required,
        is_reasoning=request.is_reasoning,
        supports_streaming=request.supports_streaming,
        default_thinking=request.default_thinking,
        default_max_tokens=request.default_max_tokens,
        default_temperature=request.default_temperature,
    )
    db.add(model)
    await db.commit()
    await db.refresh(model)
    return _to_response(model)


@router.put("/llm-models/{model_id}", response_model=LLMModelResponse)
async def update_llm_model(
    model_id: int,
    request: LLMModelUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新模型卡片（admin）。api_key 字段为空/脱敏串时保持原值不变。"""
    if not await _require_admin(db, current_user):
        raise HTTPException(status_code=403, detail="Admin permission required")

    result = await db.execute(select(LLMModel).where(LLMModel.id == model_id))
    model = result.scalar_one_or_none()
    if model is None:
        raise HTTPException(status_code=404, detail="LLM model not found")

    data = request.model_dump(exclude_unset=True)
    for field, value in data.items():
        if field == "api_key":
            # 空/脱敏串 → 不改原值（避免误清空或写入脱敏占位）。
            if is_masked_api_key(value):
                continue
            model.api_key = value
        else:
            setattr(model, field, value)

    await db.commit()
    await db.refresh(model)
    return _to_response(model)


@router.delete("/llm-models/{model_id}", status_code=204)
async def delete_llm_model(
    model_id: int,
    force: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除模型卡片（admin）。

    被某阶段指派的卡片默认拒绝删除，返 409 提示先解除指派。``force=true``
    时先解除所有引用该卡片的阶段指派（llm_model_id 置 null）再删除——供
    前端「解除指派并删除」一键操作调用，避免用户手动逐阶段解绑。
    """
    if not await _require_admin(db, current_user):
        raise HTTPException(status_code=403, detail="Admin permission required")

    result = await db.execute(select(LLMModel).where(LLMModel.id == model_id))
    model = result.scalar_one_or_none()
    if model is None:
        raise HTTPException(status_code=404, detail="LLM model not found")

    # 检查是否被某阶段指派。
    assigned_result = await db.execute(
        select(LLMModelAssignment).where(LLMModelAssignment.llm_model_id == model_id)
    )
    assigned = assigned_result.scalars().all()
    if assigned:
        stages = ", ".join(a.stage for a in assigned)
        if not force:
            # 默认拒绝删除（grill 决策：返 409 提示先解除指派）。
            raise HTTPException(
                status_code=409,
                detail="该卡片被阶段 [%s] 指派，请先解除指派再删除" % stages,
            )
        # force=true：先解除所有引用该卡片的阶段指派，再删除。
        for a in assigned:
            a.llm_model_id = None
        await db.flush()

    await db.delete(model)
    await db.commit()
    return None


# ---------------------------------------------------------------------------
# 阶段指派
# ---------------------------------------------------------------------------


@router.get("/llm-model-assignments", response_model=list[LLMModelAssignmentResponse])
async def list_llm_model_assignments(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出 6 阶段 + 各自指派的卡片（所有登录用户可读，api_key 脱敏）。

    未在 DB 建行的阶段也返回（llm_model=None），保证前端拿到完整 6 阶段列表。
    """
    result = await db.execute(
        select(LLMModelAssignment).options(selectinload(LLMModelAssignment.llm_model))
    )
    by_stage = {a.stage: a for a in result.scalars().all()}

    responses: list[LLMModelAssignmentResponse] = []
    for stage in STAGES:
        assignment = by_stage.get(stage)
        if assignment is None:
            responses.append(LLMModelAssignmentResponse(stage=stage, llm_model=None))
        else:
            responses.append(
                LLMModelAssignmentResponse(
                    id=assignment.id,
                    stage=assignment.stage,
                    llm_model_id=assignment.llm_model_id,
                    llm_model=_to_response(assignment.llm_model)
                    if assignment.llm_model is not None
                    else None,
                    created_at=assignment.created_at,
                    updated_at=assignment.updated_at,
                )
            )
    return responses


@router.put(
    "/llm-model-assignments/{stage}", response_model=LLMModelAssignmentResponse
)
async def upsert_llm_model_assignment(
    stage: str,
    request: LLMModelAssignmentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """指派/解除该阶段的卡片（admin）。``llm_model_id`` 为 null 表示解除指派。"""
    if not await _require_admin(db, current_user):
        raise HTTPException(status_code=403, detail="Admin permission required")
    if not is_valid_stage(stage):
        raise HTTPException(status_code=422, detail="Invalid stage: %s" % stage)

    # 校验指派的卡片存在（解除指派 llm_model_id=null 不校验）。
    llm_model = None
    if request.llm_model_id is not None:
        model_result = await db.execute(
            select(LLMModel).where(LLMModel.id == request.llm_model_id)
        )
        llm_model = model_result.scalar_one_or_none()
        if llm_model is None:
            raise HTTPException(status_code=404, detail="LLM model not found")

    result = await db.execute(
        select(LLMModelAssignment).where(LLMModelAssignment.stage == stage)
    )
    assignment = result.scalar_one_or_none()
    if assignment is None:
        assignment = LLMModelAssignment(stage=stage, llm_model_id=request.llm_model_id)
        db.add(assignment)
    else:
        assignment.llm_model_id = request.llm_model_id

    await db.commit()
    await db.refresh(assignment)

    return LLMModelAssignmentResponse(
        id=assignment.id,
        stage=assignment.stage,
        llm_model_id=assignment.llm_model_id,
        llm_model=_to_response(llm_model) if llm_model is not None else None,
        created_at=assignment.created_at,
        updated_at=assignment.updated_at,
    )
