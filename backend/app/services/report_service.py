# -*- coding: utf-8 -*-
"""Audit report generation service."""

from collections import Counter
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models import Report, Review, ReviewMatch, Task


class ReportService:
    """Generate deterministic task review reports."""

    def __init__(self, output_dir: str | None = None):
        self.output_dir = Path(output_dir or settings.OUTPUT_DIR) / "reports"

    async def generate_report(self, db: AsyncSession, task_id: int, review_id: int | None = None) -> Report:
        """Generate a Markdown report and persist metadata."""
        task = await self._load_task(db, task_id)
        review = await self._load_review(db, task_id, review_id)
        matches = await self._load_matches(db, review.id if review else None)

        content = self._build_fallback_report(task, review, matches)
        report_dir = self.output_dir / str(task_id)
        report_dir.mkdir(parents=True, exist_ok=True)
        path = report_dir / f"report_{review.id if review else 'task'}.md"
        path.write_text(content, encoding="utf-8")

        report = Report(
            task_id=task_id,
            review_id=review.id if review else None,
            format="markdown",
            content_path=str(path),
        )
        db.add(report)
        await db.flush()
        await db.refresh(report)
        return report

    async def read_report_content(self, report: Report) -> str:
        """Read report file content if available."""
        path = Path(report.content_path)
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    async def _load_task(self, db: AsyncSession, task_id: int) -> Task:
        result = await db.execute(select(Task).where(Task.id == task_id))
        task = result.scalar_one_or_none()
        if not task:
            raise ValueError("Task not found")
        return task

    async def _load_review(self, db: AsyncSession, task_id: int, review_id: int | None) -> Review | None:
        query = select(Review).where(Review.task_id == task_id)
        if review_id is not None:
            query = query.where(Review.id == review_id)
        else:
            query = query.order_by(Review.created_at.desc())
        result = await db.execute(query.limit(1))
        return result.scalar_one_or_none()

    async def _load_matches(self, db: AsyncSession, review_id: int | None) -> list[ReviewMatch]:
        if review_id is None:
            return []
        result = await db.execute(
            select(ReviewMatch)
            .where(ReviewMatch.review_id == review_id)
            .order_by(ReviewMatch.record_id.asc())
        )
        return list(result.scalars().all())

    def _build_fallback_report(
        self,
        task: Task,
        review: Review | None,
        matches: list[ReviewMatch],
    ) -> str:
        match_type_counts = Counter(match.match_type for match in matches)
        customer_counts = Counter(match.customer_name for match in matches)
        lines = [
            f"# 审计报告 - {task.title}",
            "",
            "## 一、基本信息",
            "",
            f"- 任务编号：{task.id}",
            f"- 任务状态：{task.status}",
            f"- 审查编号：{review.id if review else '暂无'}",
            f"- 命中流水数：{len(matches)}",
            f"- 命中客户数：{len(customer_counts)}",
            "",
            "## 二、匹配情况说明",
            "",
        ]
        if match_type_counts:
            for match_type, count in sorted(match_type_counts.items()):
                lines.append(f"- {match_type}：{count} 条")
        else:
            lines.append("- 当前未发现客户名单命中记录。")

        lines.extend(["", "## 三、重点命中对象", ""])
        for customer_name, count in customer_counts.most_common(10):
            lines.append(f"- {customer_name}：{count} 条")
        if not customer_counts:
            lines.append("- 暂无重点命中对象。")

        lines.extend(["", "## 四、建议", ""])
        if matches:
            lines.append("- 建议结合原始凭证复核命中流水的交易背景、金额合理性和业务授权依据。")
        else:
            lines.append("- 建议确认客户名单和标准化流水是否完整后再进行复核。")
        return "\n".join(lines) + "\n"


async def load_report(db: AsyncSession, report_id: int) -> Report | None:
    """Load report by id."""
    result = await db.execute(
        select(Report)
        .options(selectinload(Report.task), selectinload(Report.review))
        .where(Report.id == report_id)
    )
    return result.scalar_one_or_none()
