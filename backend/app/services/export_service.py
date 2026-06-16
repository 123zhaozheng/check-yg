# -*- coding: utf-8 -*-
"""Export generation service."""

import json
import zipfile
from pathlib import Path
from typing import Any

import openpyxl
from openpyxl.styles import Font, PatternFill
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import ExportFile, Review, ReviewMatch, Task
from app.services.review_service import FlowRecord, ReviewService


class ExportService:
    """Generate Excel and skills-bundle artifacts for a task."""

    def __init__(self, output_dir: str | None = None):
        self.output_dir = Path(output_dir or settings.OUTPUT_DIR) / "exports"
        self.review_service = ReviewService()

    async def export_excel(self, db: AsyncSession, task_id: int, review_id: int | None = None) -> ExportFile:
        """Export standardized records and matches to an Excel workbook."""
        task = await self._load_task(db, task_id)
        review = await self._load_review(db, task_id, review_id)
        records = await self.review_service.load_task_records(db, task_id)
        matches = await self._load_matches(db, review.id if review else None)

        export_dir = self.output_dir / str(task_id)
        export_dir.mkdir(parents=True, exist_ok=True)
        path = export_dir / f"task_{task_id}_review.xlsx"

        wb = openpyxl.Workbook()
        try:
            self._write_records_sheet(wb.active, records, matches)
            self._write_matches_sheet(wb, matches)
            wb.save(path)
        finally:
            wb.close()

        export = ExportFile(
            task_id=task.id,
            review_id=review.id if review else None,
            format="excel",
            file_path=str(path),
        )
        db.add(export)
        await db.flush()
        await db.refresh(export)
        return export

    async def export_bundle(self, db: AsyncSession, task_id: int, review_id: int | None = None) -> ExportFile:
        """Export a minimal task skills bundle ZIP."""
        task = await self._load_task(db, task_id)
        review = await self._load_review(db, task_id, review_id)
        matches = await self._load_matches(db, review.id if review else None)

        export_dir = self.output_dir / str(task_id)
        export_dir.mkdir(parents=True, exist_ok=True)
        path = export_dir / f"task_{task_id}_skills_bundle.zip"

        manifest = {
            "bundle_type": "employee_customer_audit_skill",
            "bundle_version": "1.0.0",
            "task_id": task.id,
            "task_title": task.title,
            "review_id": review.id if review else None,
            "match_count": len(matches),
        }
        review_payload = {
            "task": {"id": task.id, "title": task.title, "status": task.status},
            "review": {"id": review.id, "status": review.status} if review else None,
            "matches": [self._match_to_dict(match) for match in matches],
        }

        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("skill_manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            zf.writestr("current_task/review_result.json", json.dumps(review_payload, ensure_ascii=False, indent=2))
            zf.writestr("SKILL.md", self._skill_markdown(task, len(matches)))

        export = ExportFile(
            task_id=task.id,
            review_id=review.id if review else None,
            format="bundle",
            file_path=str(path),
        )
        db.add(export)
        await db.flush()
        await db.refresh(export)
        return export

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

    def _write_records_sheet(
        self,
        ws,
        records: list[FlowRecord],
        matches: list[ReviewMatch],
    ) -> None:
        ws.title = "标准化流水"
        best_by_record = {match.record_id: match for match in matches}
        headers = [
            "来源文件",
            "原始行号",
            "交易时间",
            "交易对手名",
            "交易对手账号",
            "金额",
            "摘要",
            "收支类型",
            "匹配用户",
            "匹配度",
            "匹配类型",
        ]
        self._write_header(ws, headers)
        for row_index, record in enumerate(records, 2):
            match = best_by_record.get(record.record_id)
            values: list[Any] = [
                record.source_file,
                record.original_row,
                record.transaction_time,
                record.counterparty_name,
                record.counterparty_account,
                record.amount,
                record.summary,
                record.transaction_type,
                match.customer_name if match else "",
                match.score if match else "",
                match.match_type if match else "",
            ]
            for col_index, value in enumerate(values, 1):
                ws.cell(row=row_index, column=col_index, value=value)

    def _write_matches_sheet(self, wb, matches: list[ReviewMatch]) -> None:
        ws = wb.create_sheet("匹配详情")
        headers = [
            "流水记录ID",
            "匹配用户",
            "匹配度",
            "匹配类型",
            "来源文件",
            "交易时间",
            "交易对手名",
            "交易对手账号",
            "金额",
            "摘要",
        ]
        self._write_header(ws, headers)
        for row_index, match in enumerate(matches, 2):
            values = [
                match.record_id,
                match.customer_name,
                match.score,
                match.match_type,
                match.source_file or "",
                match.transaction_time or "",
                match.counterparty_name or "",
                match.counterparty_account or "",
                match.amount or "",
                match.summary or "",
            ]
            for col_index, value in enumerate(values, 1):
                ws.cell(row=row_index, column=col_index, value=value)

    @staticmethod
    def _write_header(ws, headers: list[str]) -> None:
        fill = PatternFill(start_color="1F2937", end_color="1F2937", fill_type="solid")
        font = Font(color="FFFFFF", bold=True)
        for col_index, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_index, value=header)
            cell.fill = fill
            cell.font = font
            ws.column_dimensions[cell.column_letter].width = max(12, min(len(header) + 8, 30))
        ws.freeze_panes = "A2"

    @staticmethod
    def _match_to_dict(match: ReviewMatch) -> dict[str, Any]:
        return {
            "record_id": match.record_id,
            "customer_name": match.customer_name,
            "match_type": match.match_type,
            "score": match.score,
            "counterparty_name": match.counterparty_name,
            "counterparty_account": match.counterparty_account,
            "source_file": match.source_file,
            "transaction_time": match.transaction_time,
            "amount": match.amount,
            "summary": match.summary,
        }

    @staticmethod
    def _skill_markdown(task: Task, match_count: int) -> str:
        return (
            "# 员工客户流水审查 Skills\n\n"
            f"- 任务：{task.title}\n"
            f"- 命中记录：{match_count}\n\n"
            "使用 `current_task/review_result.json` 回答审查命中、证据明细和复核建议问题。\n"
        )


async def load_export(db: AsyncSession, export_id: int) -> ExportFile | None:
    """Load export artifact by id."""
    result = await db.execute(select(ExportFile).where(ExportFile.id == export_id))
    return result.scalar_one_or_none()
