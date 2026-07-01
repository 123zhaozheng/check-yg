# -*- coding: utf-8 -*-
"""关键词库 CRUD + excel 导入/导出 router (06-23-tab).

* ``GET /api/keyword-library/cards`` — 列出卡片（含每卡 term 数、风险等级）。所有登录用户可读。
* ``POST /api/keyword-library/cards`` — 新建卡片（admin）。
* ``PUT /api/keyword-library/cards/{id}`` — 编辑卡片（admin；terms 全量替换）。
* ``DELETE /api/keyword-library/cards/{id}`` — 删卡（admin，级联删 terms）。已被命中引用 → 409。
* ``POST /api/keyword-library/import`` — excel 导入（admin，multipart）。
* ``GET /api/keyword-library/export`` — excel 导出（所有登录用户可读）。
* ``GET /api/keyword-library/cards/{id}`` — 卡片详情（含 terms 列表）。

鉴权：CRUD/导入限 admin；列表/导出/详情所有登录用户可读。沿用 ``check_admin_permission``。
"""

import io

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.dependencies import get_current_user
from ..auth.permissions import check_admin_permission
from ..database import get_db
from ..models import User
from ..schemas.keyword import (
    KeywordCardCreate,
    KeywordCardDetail,
    KeywordCardListItem,
    KeywordCardUpdate,
    KeywordImportStats,
    KeywordGenerateTermsRequest,
    KeywordGenerateTermsResponse,
)
from ..services.keyword.keyword_library_service import KeywordLibraryService

# AI 关键词生成（07-01-ai-50）
from app.llm.keyword_generator import generate_terms

router = APIRouter(prefix="/keyword-library", tags=["keyword-library"])

_service = KeywordLibraryService()


def _require_admin(db: AsyncSession, user: User):
    """Admin 鉴权辅助——失败抛 403。"""
    return check_admin_permission(db, user)


def _card_list_item(card_dict: dict) -> KeywordCardListItem:
    return KeywordCardListItem(
        id=card_dict["id"],
        name=card_dict["name"],
        risk_level=card_dict["risk_level"],
        note=card_dict["note"],
        term_count=card_dict["term_count"],
        created_at=card_dict["created_at"],
        updated_at=card_dict["updated_at"],
    )


def _card_detail(card_dict: dict) -> KeywordCardDetail:
    return KeywordCardDetail(
        id=card_dict["id"],
        name=card_dict["name"],
        risk_level=card_dict["risk_level"],
        note=card_dict["note"],
        terms=card_dict["terms"],
        created_at=card_dict["created_at"],
        updated_at=card_dict["updated_at"],
    )


@router.get("/cards", response_model=list[KeywordCardListItem])
async def list_keyword_cards(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出所有卡片（含每卡 term 数、风险等级）。所有登录用户可读。"""
    cards = await _service.list_cards(db)
    return [_card_list_item(c) for c in cards]


@router.get("/cards/{card_id}", response_model=KeywordCardDetail)
async def get_keyword_card(
    card_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """卡片详情（含 terms 列表）。所有登录用户可读。"""
    card = await _service.get_card(db, card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Keyword card not found")
    return _card_detail(card)


@router.post("/cards", response_model=KeywordCardDetail, status_code=201)
async def create_keyword_card(
    request: KeywordCardCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """新建卡片（admin）。body: name/risk_level/note + terms[]。"""
    if not await _require_admin(db, current_user):
        raise HTTPException(status_code=403, detail="Admin permission required")
    try:
        card = await _service.create_card(
            db, request.name, request.risk_level, request.note, request.terms
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await db.commit()
    detail = await _service.get_card(db, card.id)
    return _card_detail(detail)  # type: ignore[arg-type]


@router.put("/cards/{card_id}", response_model=KeywordCardDetail)
async def update_keyword_card(
    card_id: int,
    request: KeywordCardUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """编辑卡片（admin）。name/risk_level/note 可改；terms 全量替换。"""
    if not await _require_admin(db, current_user):
        raise HTTPException(status_code=403, detail="Admin permission required")
    try:
        await _service.update_card(
            db,
            card_id,
            request.name,
            request.risk_level,
            request.note,
            request.terms,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await db.commit()
    detail = await _service.get_card(db, card_id)
    return _card_detail(detail)  # type: ignore[arg-type]


@router.delete("/cards/{card_id}", status_code=204)
async def delete_keyword_card(
    card_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删卡（admin，级联删 terms）。已被命中引用 → 409，提示先解除关联。"""
    if not await _require_admin(db, current_user):
        raise HTTPException(status_code=403, detail="Admin permission required")
    try:
        await _service.delete_card(db, card_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        # 已被命中引用 → 409（对齐删已指派模型卡返 409）。
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await db.commit()
    return None


@router.post("/import", response_model=KeywordImportStats)
async def import_keyword_library(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """excel 导入（admin，multipart）。合并追加去重，返统计。"""
    if not await _require_admin(db, current_user):
        raise HTTPException(status_code=403, detail="Admin permission required")
    file_bytes = await file.read()
    try:
        stats = await _service.import_excel(db, file_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await db.commit()
    return KeywordImportStats(**stats)


@router.get("/export")
async def export_keyword_library(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """excel 导出（所有登录用户可读）。返 xlsx 流，表头 ``卡片名称,关键词,风险等级,备注``。"""
    file_bytes = await _service.export_excel(db)
    return StreamingResponse(
        io.BytesIO(file_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="keyword_library.xlsx"'
        },
    )


@router.post("/generate-terms", response_model=KeywordGenerateTermsResponse)
async def generate_keyword_terms(
    request: KeywordGenerateTermsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """AI 生成关键词（admin）。body: name/risk_level/note → terms[]。

    生成结果只填前端表单态，不自动落库；用户仍需点「保存」才建卡。
    失败（LLM 不可用/超时/返回过少）时返回空列表，不改动用户已手敲的 terms。
    """
    if not await _require_admin(db, current_user):
        raise HTTPException(status_code=403, detail="Admin permission required")

    clean_name = (request.name or "").strip()
    if not clean_name:
        raise HTTPException(status_code=422, detail="卡片名称不能为空")

    risk = (request.risk_level or "").strip()
    if risk not in ("高", "中", "低"):
        raise HTTPException(status_code=422, detail="风险等级必须为 高/中/低")

    try:
        # 阶段卡片接线：keyword_generation → env 兜底
        from app.llm.keyword_generator import get_keyword_generation_model

        stage_model = await get_keyword_generation_model(db)
        terms = await generate_terms(
            clean_name,
            risk,
            request.note,
            model=stage_model,
        )
    except Exception as exc:
        # 任何异常都吞掉，返回空列表（前端保持原 terms 不变，只给提示）
        # 避免把 LLM 错误直接暴露成 500 影响 dialog 其他操作。
        raise HTTPException(
            status_code=422,
            detail=f"AI 生成失败：{exc}",
        ) from exc

    # 后端去重保序（对齐 service._dedup_terms 逻辑，避免 LLM 自己重复输出）
    from app.services.keyword.keyword_library_service import KeywordLibraryService

    deduped = KeywordLibraryService._dedup_terms(terms)
    return KeywordGenerateTermsResponse(terms=deduped)
