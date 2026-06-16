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


class ReportResponse(BaseModel):
    id: int
    task_id: int
    review_id: Optional[int] = None
    format: str
    content_path: str
    content: str = ""
    created_at: datetime


class ExportRunRequest(BaseModel):
    review_id: Optional[int] = None


class ExportResponse(BaseModel):
    id: int
    task_id: int
    review_id: Optional[int] = None
    format: str
    file_path: str
    created_at: datetime
