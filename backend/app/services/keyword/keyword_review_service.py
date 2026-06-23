# -*- coding: utf-8 -*-
"""关键词审查 service（06-23-tab）.

``run_review(task_id, card_ids)``:
1. 取这些 card 的所有 term（展开成 keyword 列表）。
2. 取该 task 所有 standard flow_records。
3. 逐行 × 逐词跑三层匹配，命中即记。只扫 ``counterparty_name`` + ``summary`` 两列
   （拼成待匹配文本）。
4. 重跑策略（简单）：先 ``DELETE FROM keyword_hits WHERE task_id=?``，再插新命中
   （同 task 可换卡片反复重审，结果即当前选中卡片集）。
5. 返回统计（扫描记录数 / 命中记录数 / 命中词数 / 高风险命中数）。

边界决策（prd §B）：standard 行被「捞回」改 record_type 后，其历史 keyword_hit
不级联清理——捞回不触发改命中，下次重跑自然按当前 standard 重算（重跑才同步）。
"""

import logging
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    FlowRecordRow,
    KeywordCard,
    KeywordHit,
    KeywordTerm,
)
from app.models.keyword import (
    FIELD_COUNTERPARTY,
    FIELD_SUMMARY,
    RISK_HIGH,
)
from app.services.keyword.matcher import KeywordMatcher

logger = logging.getLogger(__name__)


class KeywordReviewService:
    """Run task-level keyword matching and persist hits."""

    def __init__(self, fuzzy_threshold: int = 70):
        self.matcher = KeywordMatcher(fuzzy_threshold=fuzzy_threshold)

    async def run_review(
        self,
        db: AsyncSession,
        task_id: int,
        card_ids: list[int],
    ) -> dict:
        """
        Run keyword review for a task against the selected cards.

        Returns a stats dict:
        * ``scanned_records`` — 扫描的 standard 记录数。
        * ``hit_records`` — 命中的记录数（至少一个词命中）。
        * ``hit_terms`` — 命中词数（去重后的 keyword 数）。
        * ``high_risk_hits`` — 高风险命中数（卡片级 risk_level=高）。
        """
        # 1. 展开选中卡片的所有 term（keyword + risk_level from card + term id）。
        terms = await self._load_terms(db, card_ids)
        logger.info(
            "关键词审查开始: task=%s cards=%s terms=%d", task_id, card_ids, len(terms)
        )

        # 2. 取该 task 所有 standard flow_records。
        records = await self._load_standard_records(db, task_id)

        # 3. 重跑策略：先删该 task 旧命中，再插新命中。
        await db.execute(delete(KeywordHit).where(KeywordHit.task_id == task_id))

        hit_records = 0
        hit_term_ids: set[int] = set()
        high_risk_hits = 0
        new_hits: list[KeywordHit] = []

        for record in records:
            record_hit = False
            for term_row in terms:
                # 只扫 counterparty_name + summary 两列（逐列跑，记 matched_field）。
                for field_name, field_value in (
                    (FIELD_COUNTERPARTY, record.counterparty_name),
                    (FIELD_SUMMARY, record.summary),
                ):
                    text = str(field_value or "").strip()
                    if not text:
                        continue
                    result = self.matcher.match(term_row["term"], text)
                    if result is None:
                        continue
                    snippet = text[
                        result.position[0] : result.position[1]
                    ]
                    hit = KeywordHit(
                        task_id=task_id,
                        flow_record_id=record.id,
                        keyword_card_id=term_row["card_id"],
                        keyword_term_id=term_row["term_id"],
                        match_type=result.match_type.value,
                        confidence=result.confidence,
                        risk_level=term_row["risk_level"],
                        matched_field=field_name,
                        matched_snippet=snippet,
                        status="pending",
                    )
                    new_hits.append(hit)
                    record_hit = True
                    hit_term_ids.add(term_row["term_id"])
                    if term_row["risk_level"] == RISK_HIGH:
                        high_risk_hits += 1
                    # 逐行 × 逐词：一个词在一行可能同时命中两列——按 prd「命中即记」，
                    # 两列各记一条（matched_field 不同），保留完整审查线索。
            if record_hit:
                hit_records += 1

        for hit in new_hits:
            db.add(hit)
        await db.flush()

        logger.info(
            "关键词审查完成: task=%s 扫描=%d 命中记录=%d 命中词=%d 高风险=%d",
            task_id,
            len(records),
            hit_records,
            len(hit_term_ids),
            high_risk_hits,
        )

        return {
            "scanned_records": len(records),
            "hit_records": hit_records,
            "hit_terms": len(hit_term_ids),
            "high_risk_hits": high_risk_hits,
        }

    async def _load_terms(
        self, db: AsyncSession, card_ids: list[int]
    ) -> list[dict]:
        """展开选中卡片的所有 term。返回 ``{card_id, term_id, term, risk_level}`` 列表。"""
        if not card_ids:
            return []
        result = await db.execute(
            select(KeywordTerm, KeywordCard)
            .join(KeywordCard, KeywordTerm.card_id == KeywordCard.id)
            .where(KeywordTerm.card_id.in_(card_ids))
            .order_by(KeywordTerm.id.asc())
        )
        rows: list[dict] = []
        for term, card in result.all():
            rows.append(
                {
                    "card_id": card.id,
                    "term_id": term.id,
                    "term": term.term,
                    "risk_level": card.risk_level,
                }
            )
        return rows

    async def _load_standard_records(
        self, db: AsyncSession, task_id: int
    ) -> list[FlowRecordRow]:
        """取该 task 所有 standard flow_records（record_type=standard）。"""
        result = await db.execute(
            select(FlowRecordRow)
            .where(
                FlowRecordRow.task_id == task_id,
                FlowRecordRow.record_type == "standard",
            )
            .order_by(FlowRecordRow.id.asc())
        )
        return list(result.scalars().all())
