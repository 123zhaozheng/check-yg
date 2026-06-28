# -*- coding: utf-8 -*-
"""Review/report/export schemas."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


class ReviewRunRequest(BaseModel):
    customer_list_id: Optional[int] = None
    match_config: dict[str, Any] | None = None


class ReviewResponse(BaseModel):
    id: int
    task_id: int
    customer_list_id: int
    status: str
    match_config: dict[str, Any] | None
    created_at: datetime
    total_matches: int = 0


class ReviewMatchResponse(BaseModel):
    id: int
    review_id: int
    record_id: int
    customer_name: str
    match_type: str
    score: float
    counterparty_name: Optional[str] = None
    counterparty_account: Optional[str] = None
    source_file: Optional[str] = None
    transaction_time: Optional[str] = None
    amount: Optional[str] = None
    summary: Optional[str] = None


class ReviewMatchListResponse(BaseModel):
    items: list[ReviewMatchResponse]
    total: int
    page: int
    page_size: int


class ReportRunRequest(BaseModel):
    review_id: Optional[int] = None


class ReportChapterResponse(BaseModel):
    """One chapter of a chaptered review report (S7)."""

    id: int
    report_id: int
    title: str
    content: str
    order_index: int
    generated_at: datetime


class ReportAnnotationResponse(BaseModel):
    """One review annotation on a report chapter (S7)."""

    id: int
    report_id: int
    chapter_id: Optional[int] = None
    author: str
    content: str
    resolved: bool
    created_at: datetime


class ReportResponse(BaseModel):
    id: int
    task_id: int
    review_id: Optional[int] = None
    format: str
    content_path: str
    content: str = ""
    # S7/S8 软态 draft|generating|generated|failed|final + 章节化 + 批注列表。
    status: str = "draft"
    chapters: list[ReportChapterResponse] = []
    annotations: list[ReportAnnotationResponse] = []
    created_at: datetime


class ReportChapterPatchRequest(BaseModel):
    """行内编辑章节 content（纯文本 Markdown，定稿 409）."""

    content: str


class ReportChapterReorderItem(BaseModel):
    """拖拽排序单项：chapter_id + 新 order_index."""

    chapter_id: int
    order_index: int


class ReportAnnotationCreateRequest(BaseModel):
    """新建章节级批注（定稿 409）."""

    chapter_id: Optional[int] = None
    content: str


class ExportRunRequest(BaseModel):
    review_id: Optional[int] = None


class ExportResponse(BaseModel):
    id: int
    task_id: int
    review_id: Optional[int] = None
    format: str
    file_path: str
    # S8 导出范围：report / raw / standard / findings（旧 excel/bundle 行 null 兼容）.
    scope: Optional[str] = None
    created_at: datetime


# ---------------------------------------------------------------------------
# S8 导出扩展：报告多格式 + 数据多范围 + 历史 + 预览
# ---------------------------------------------------------------------------


class ReportExportRequest(BaseModel):
    """POST /tasks/{id}/export/report 请求体."""

    format: str  # "pdf" | "docx" | "html"
    include_annotations: bool = False


class DataExportRequest(BaseModel):
    """POST /tasks/{id}/export/data 请求体."""

    scope: str  # "raw" | "standard" | "findings"
    format: str  # "excel" | "csv"


class ExportListItem(BaseModel):
    """导出历史列表单项."""

    id: int
    task_id: int
    review_id: Optional[int] = None
    format: str
    scope: Optional[str] = None
    file_path: str
    created_at: datetime


class ExportPreviewResponse(BaseModel):
    """GET /tasks/{id}/export/preview 取样响应（不生成产物）."""

    scope: str
    # report: 前 2 章 content 文本 + 批注数; data: 前 20 行 JSON 序列化.
    sample: Any
    annotation_count: Optional[int] = None
