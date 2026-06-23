# -*- coding: utf-8 -*-
"""关键词库 + 关键词审查 pydantic schemas (06-23-tab)."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.keyword import (
    HIT_STATUSES,
    RISK_LEVELS,
    RISK_MEDIUM,
)


class KeywordTermItem(BaseModel):
    """单个关键词（详情/响应用）."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    term: str
    created_at: datetime


class KeywordCardBase(BaseModel):
    """卡片可写字段（新建/编辑共用）。"""

    name: str = Field(..., min_length=1, max_length=200)
    risk_level: str = Field(default=RISK_MEDIUM, pattern="^(%s)$" % "|".join(RISK_LEVELS))
    note: Optional[str] = None
    terms: list[str] = Field(default_factory=list)


class KeywordCardCreate(KeywordCardBase):
    """新建卡片请求体。"""

    pass


class KeywordCardUpdate(BaseModel):
    """编辑卡片请求体（所有字段可选；terms 全量替换）。"""

    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    risk_level: Optional[str] = Field(
        default=None, pattern="^(%s)$" % "|".join(RISK_LEVELS)
    )
    note: Optional[str] = None
    terms: Optional[list[str]] = None


class KeywordCardListItem(BaseModel):
    """卡片列表项（含 term 数 + 风险等级 + 备注）。"""

    id: int
    name: str
    risk_level: str
    note: Optional[str] = None
    term_count: int
    created_at: datetime
    updated_at: datetime


class KeywordCardDetail(BaseModel):
    """卡片详情（含 terms 列表）。"""

    id: int
    name: str
    risk_level: str
    note: Optional[str] = None
    terms: list[KeywordTermItem]
    created_at: datetime
    updated_at: datetime


class KeywordImportStats(BaseModel):
    """excel 导入统计。"""

    created_cards: int
    appended_cards: int
    new_terms: int
    skipped_terms: int
    rejected_rows: int


# ---------------------------------------------------------------------------
# 关键词审查（任务级）
# ---------------------------------------------------------------------------


class KeywordReviewRunRequest(BaseModel):
    """POST /api/tasks/{task_id}/keyword-review/run 请求体。"""

    card_ids: list[int] = Field(default_factory=list)


class KeywordReviewRunStats(BaseModel):
    """POST run 响应统计。"""

    scanned_records: int
    hit_records: int
    hit_terms: int
    high_risk_hits: int


class KeywordHitItem(BaseModel):
    """单个命中行（列表/响应用）."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    flow_record_id: int
    keyword_card_id: int
    keyword_term_id: int
    match_type: str
    confidence: int
    risk_level: str
    matched_field: str
    matched_snippet: str
    status: str
    note: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class KeywordHitListResponse(BaseModel):
    """命中分页列表。"""

    items: list[KeywordHitItem]
    total: int
    page: int
    page_size: int


class KeywordHitPatchRequest(BaseModel):
    """PATCH 命中请求体（status / note，均可选）。"""

    status: Optional[str] = None
    note: Optional[str] = None
