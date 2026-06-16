# -*- coding: utf-8 -*-
"""Review orchestration service."""

import logging
from dataclasses import dataclass
from typing import Any, Iterable, Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.matcher import MatchResult, MatchType, NameMatcher
from app.models import CustomerList, CustomerListItem, Document, Review, ReviewMatch, Task

logger = logging.getLogger(__name__)


FIELD_ALIASES = {
    "source_file": ["source_file", "来源文件"],
    "original_row": ["original_row", "row_index", "原始行号", "流水行号"],
    "transaction_time": ["transaction_time", "交易时间"],
    "counterparty_name": ["counterparty_name", "counterparty", "交易对手名", "对手名"],
    "counterparty_account": ["counterparty_account", "交易对手账号", "对手账号"],
    "amount": ["amount", "金额"],
    "summary": ["summary", "摘要"],
    "transaction_type": ["transaction_type", "收支类型"],
}


@dataclass
class FlowRecord:
    """Normalized flow record used by review/export services."""

    record_id: int
    source_file: str = ""
    original_row: int = 0
    transaction_time: str = ""
    counterparty_name: str = ""
    counterparty_account: str = ""
    amount: str = ""
    summary: str = ""
    transaction_type: str = ""
    payload: dict[str, Any] | None = None


class ReviewService:
    """Run task-level customer matching and persist review results."""

    def __init__(self, fuzzy_threshold: float = 0.6):
        self.matcher = NameMatcher(fuzzy_threshold=fuzzy_threshold)

    async def run_review(
        self,
        db: AsyncSession,
        task_id: int,
        customer_list_id: Optional[int] = None,
        match_config: Optional[dict[str, Any]] = None,
    ) -> Review:
        """Create and execute a review for a task."""
        config = dict(match_config or {})
        include_fuzzy = bool(config.get("include_fuzzy", True))
        threshold = config.get("fuzzy_threshold")
        if threshold is not None:
            self.matcher = NameMatcher(fuzzy_threshold=float(threshold))

        task = await self._get_task(db, task_id)
        customer_list = await self._get_customer_list(db, task, customer_list_id)
        customers = await self._load_customers(db, customer_list.id)
        records = await self.load_task_records(db, task_id)

        review = Review(
            task_id=task_id,
            customer_list_id=customer_list.id,
            match_config=config,
            status="running",
        )
        db.add(review)
        await db.flush()

        matches = self.match_records(records, customers, include_fuzzy=include_fuzzy)
        for record, match in matches:
            db.add(self._to_model(review.id, record, match))

        review.status = "completed"
        await db.flush()
        await db.refresh(review)
        logger.info("Review completed for task %s: %d matches", task_id, len(matches))
        return review

    async def get_review(self, db: AsyncSession, review_id: int) -> Optional[Review]:
        """Load review with task/customer relationships."""
        result = await db.execute(
            select(Review)
            .options(selectinload(Review.task), selectinload(Review.customer_list))
            .where(Review.id == review_id)
        )
        return result.scalar_one_or_none()

    async def list_matches(
        self,
        db: AsyncSession,
        review_id: int,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[ReviewMatch], int]:
        """List review matches with pagination."""
        base_query = select(ReviewMatch).where(ReviewMatch.review_id == review_id)
        total_result = await db.execute(select(func.count()).select_from(base_query.subquery()))
        total = total_result.scalar() or 0

        result = await db.execute(
            base_query.order_by(ReviewMatch.record_id.asc(), ReviewMatch.score.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all()), total

    async def delete_review_matches(self, db: AsyncSession, review_id: int) -> None:
        """Delete persisted matches for a review."""
        await db.execute(delete(ReviewMatch).where(ReviewMatch.review_id == review_id))

    async def load_task_records(self, db: AsyncSession, task_id: int) -> list[FlowRecord]:
        """Load normalized records from a task's documents."""
        result = await db.execute(select(Document).where(Document.task_id == task_id))
        records: list[FlowRecord] = []
        next_id = 1
        for document in result.scalars().all():
            for payload in self._extract_payload_records(document.flow_tables):
                record = self._payload_to_record(payload, next_id, document.filename)
                next_id += 1
                if record.counterparty_name:
                    records.append(record)
        return records

    def match_records(
        self,
        records: Iterable[FlowRecord],
        customers: Iterable[str],
        include_fuzzy: bool = True,
    ) -> list[tuple[FlowRecord, MatchResult]]:
        """Match each flow record to the best customer hit."""
        customer_names = [str(item or "").strip() for item in customers if str(item or "").strip()]
        matches: list[tuple[FlowRecord, MatchResult]] = []

        for record in records:
            best: Optional[MatchResult] = None
            for customer_name in customer_names:
                result = self.matcher.match(customer_name, record.counterparty_name, include_fuzzy=include_fuzzy)
                if result and self._is_better(result, best):
                    best = result
            if best:
                matches.append((record, best))

        return matches

    async def _get_task(self, db: AsyncSession, task_id: int) -> Task:
        result = await db.execute(select(Task).where(Task.id == task_id))
        task = result.scalar_one_or_none()
        if not task:
            raise ValueError("Task not found")
        return task

    async def _get_customer_list(
        self,
        db: AsyncSession,
        task: Task,
        customer_list_id: Optional[int],
    ) -> CustomerList:
        query = select(CustomerList)
        if customer_list_id is not None:
            query = query.where(CustomerList.id == customer_list_id)
        else:
            query = query.where(CustomerList.owner_id == task.owner_id).order_by(CustomerList.created_at.desc())
        result = await db.execute(query.limit(1))
        customer_list = result.scalar_one_or_none()
        if not customer_list:
            raise ValueError("Customer list not found")
        return customer_list

    async def _load_customers(self, db: AsyncSession, customer_list_id: int) -> list[str]:
        result = await db.execute(
            select(CustomerListItem.name)
            .where(CustomerListItem.list_id == customer_list_id)
            .order_by(CustomerListItem.id.asc())
        )
        return [name for name in result.scalars().all() if str(name or "").strip()]

    @staticmethod
    def _extract_payload_records(raw: Any) -> list[dict[str, Any]]:
        if not raw:
            return []
        if isinstance(raw, list):
            return [item for item in raw if isinstance(item, dict)]
        if not isinstance(raw, dict):
            return []

        for key in ("records", "flow_records", "items"):
            value = raw.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]

        tables = raw.get("flow_tables")
        if isinstance(tables, list):
            records: list[dict[str, Any]] = []
            for table in tables:
                if isinstance(table, dict):
                    rows = table.get("records") or table.get("rows") or []
                    records.extend(item for item in rows if isinstance(item, dict))
            return records

        if any(alias in raw for aliases in FIELD_ALIASES.values() for alias in aliases):
            return [raw]
        return []

    @staticmethod
    def _payload_to_record(payload: dict[str, Any], record_id: int, fallback_source: str) -> FlowRecord:
        original_row = _parse_int(_get_field(payload, "original_row")) or record_id
        return FlowRecord(
            record_id=record_id,
            source_file=_get_field(payload, "source_file") or fallback_source,
            original_row=original_row,
            transaction_time=_get_field(payload, "transaction_time"),
            counterparty_name=_get_field(payload, "counterparty_name"),
            counterparty_account=_get_field(payload, "counterparty_account"),
            amount=_get_field(payload, "amount"),
            summary=_get_field(payload, "summary"),
            transaction_type=_get_field(payload, "transaction_type"),
            payload=payload,
        )

    @staticmethod
    def _to_model(review_id: int, record: FlowRecord, match: MatchResult) -> ReviewMatch:
        return ReviewMatch(
            review_id=review_id,
            record_id=record.record_id,
            customer_name=match.customer_name,
            match_type=match.match_type.value,
            score=match.score,
            counterparty_name=record.counterparty_name,
            counterparty_account=record.counterparty_account,
            source_file=record.source_file,
            transaction_time=record.transaction_time,
            amount=record.amount,
            summary=record.summary,
            record_payload=record.payload,
        )

    @staticmethod
    def _is_better(candidate: MatchResult, current: Optional[MatchResult]) -> bool:
        if current is None:
            return True
        priority = {
            MatchType.EXACT: 3,
            MatchType.MASKED: 2,
            MatchType.FUZZY: 1,
        }
        return (priority[candidate.match_type], candidate.score) > (
            priority[current.match_type],
            current.score,
        )


def _get_field(payload: dict[str, Any], normalized_name: str) -> str:
    for key in FIELD_ALIASES.get(normalized_name, [normalized_name]):
        value = payload.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _parse_int(value: object) -> Optional[int]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return None
