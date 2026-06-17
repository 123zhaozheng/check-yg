# -*- coding: utf-8 -*-
"""Runtime orchestration for FastAPI extraction jobs."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict

from sqlalchemy import delete, select

from app.database import async_session
from app.models import Document, Task, TaskLog
from app.services.settings_service import load_runtime_settings
from app.websocket.notifications import notify_user

from .extractor import FlowExtractor
from .progress import ProgressReport

logger = logging.getLogger(__name__)


class ExtractionTaskRunner:
    """Run extraction jobs in-process and expose pause/resume/cancel controls."""

    def __init__(self) -> None:
        self._extractors: Dict[int, FlowExtractor] = {}
        self._jobs: Dict[int, asyncio.Task] = {}

    def is_running(self, task_id: int) -> bool:
        """Return whether a task has a live background job."""
        job = self._jobs.get(task_id)
        return bool(job and not job.done())

    async def start(
        self,
        task_id: int,
        owner_id: int,
        document_folder: str,
        batch_size: int = 20,
        confidence_threshold: int = 70,
        append: bool = False,
    ) -> None:
        """Start or append an extraction job."""
        if self.is_running(task_id):
            raise ValueError("Task is already running")

        async with async_session() as session:
            runtime_settings = await load_runtime_settings(session)

        extractor = FlowExtractor(runtime_settings=runtime_settings)
        loop = asyncio.get_running_loop()

        def report_progress(report: ProgressReport) -> None:
            loop.create_task(
                notify_user(
                    owner_id,
                    event="task.progress",
                    title="任务进度",
                    message=report.message,
                    resource={
                        "task_id": task_id,
                        "stage": report.stage,
                        "current": report.current,
                        "total": report.total,
                        "percentage": report.percentage,
                    },
                )
            )

        extractor.set_progress_callback(report_progress)
        self._extractors[task_id] = extractor

        job = asyncio.create_task(
            self._run_job(
                task_id=task_id,
                owner_id=owner_id,
                extractor=extractor,
                document_folder=document_folder,
                batch_size=batch_size,
                confidence_threshold=confidence_threshold,
                append=append,
            )
        )
        self._jobs[task_id] = job

    async def pause(self, task_id: int) -> bool:
        """Pause a running task."""
        extractor = self._extractors.get(task_id)
        if not extractor:
            return False
        extractor.request_pause(True)
        return True

    async def resume(self, task_id: int) -> bool:
        """Resume a paused task."""
        extractor = self._extractors.get(task_id)
        if not extractor:
            return False
        extractor.request_pause(False)
        return True

    async def cancel(self, task_id: int) -> bool:
        """Cancel a running task."""
        extractor = self._extractors.get(task_id)
        if not extractor:
            return False
        extractor.request_cancel()
        return True

    async def _run_job(
        self,
        task_id: int,
        owner_id: int,
        extractor: FlowExtractor,
        document_folder: str,
        batch_size: int,
        confidence_threshold: int,
        append: bool,
    ) -> None:
        try:
            if append:
                existing_paths = await self._load_existing_document_paths(task_id)
                result = await extractor.extract_flows_append(
                    task_id=str(task_id),
                    new_folder=document_folder,
                    batch_size=batch_size,
                    confidence_threshold=confidence_threshold,
                    existing_document_paths=existing_paths,
                )
            else:
                result = await extractor.extract_flows(
                    document_folder=document_folder,
                    task_id=str(task_id),
                    batch_size=batch_size,
                    confidence_threshold=confidence_threshold,
                )
            await self._mark_finished(task_id, owner_id, result.to_dict(), append=append)
        except Exception as exc:
            logger.exception("Extraction task %s failed", task_id)
            await self._mark_failed(task_id, owner_id, str(exc))
        finally:
            self._extractors.pop(task_id, None)
            self._jobs.pop(task_id, None)

    @staticmethod
    async def _load_existing_document_paths(task_id: int) -> list:
        """Return full paths already processed for a task, for append dedup."""
        async with async_session() as session:
            db_result = await session.execute(select(Task).where(Task.id == task_id))
            task = db_result.scalar_one_or_none()
            if not task:
                return []
            last_result = (task.config or {}).get("last_result") or {}
            return list(last_result.get("processed_document_paths", []) or [])

    async def _mark_finished(self, task_id: int, owner_id: int, result: dict, append: bool = False) -> None:
        status = "failed" if result.get("failed_documents") or result.get("errors") else "completed"
        async with async_session() as session:
            db_result = await session.execute(select(Task).where(Task.id == task_id))
            task = db_result.scalar_one_or_none()
            if not task:
                return
            final_result = result
            if append:
                previous_result = (task.config or {}).get("last_result") or {}
                final_result = self._merge_results(previous_result, result)
            if task.status == "cancelled":
                status = "cancelled"
            task.status = status
            task.completed_at = datetime.now(timezone.utc)
            task.config = {
                **(task.config or {}),
                "last_result": final_result,
            }
            await self._persist_result_documents(session, task_id, final_result)
            session.add(
                TaskLog(
                    task_id=task_id,
                    level="info" if status == "completed" else "warning",
                    message="Extraction finished with status: %s" % status,
                )
            )
            await session.commit()

        await notify_user(
            owner_id,
            event="task.%s" % status,
            title="任务已完成" if status == "completed" else "任务结束",
            message="抽取记录数: %s" % final_result.get("total_records", 0),
            resource={"task_id": task_id, "status": status},
        )

    @staticmethod
    async def _persist_result_documents(session, task_id: int, result: dict) -> None:
        """Persist normalized records into Document rows for review/report services."""
        records_by_source = {}
        for record in result.get("flow_records", []) or []:
            if not isinstance(record, dict):
                continue
            source_file = str(record.get("source_file") or "unknown").strip() or "unknown"
            records_by_source.setdefault(source_file, []).append(record)

        await session.execute(delete(Document).where(Document.task_id == task_id))

        for source_file, records in records_by_source.items():
            session.add(
                Document(
                    task_id=task_id,
                    filename=source_file,
                    original_path=source_file,
                    status="completed",
                    flow_tables={"records": records},
                )
            )

    async def _mark_failed(self, task_id: int, owner_id: int, error: str) -> None:
        async with async_session() as session:
            db_result = await session.execute(select(Task).where(Task.id == task_id))
            task = db_result.scalar_one_or_none()
            if not task:
                return
            task.status = "failed"
            task.completed_at = datetime.now(timezone.utc)
            task.config = {
                **(task.config or {}),
                "last_error": error,
            }
            session.add(TaskLog(task_id=task_id, level="error", message=error))
            await session.commit()

        await notify_user(
            owner_id,
            event="task.failed",
            title="任务失败",
            message=error,
            resource={"task_id": task_id, "status": "failed"},
        )

    @staticmethod
    def _merge_results(previous: dict, current: dict) -> dict:
        """Merge append extraction output with the previous task result.

        Aligns with the original append semantics:

        * Document identity is the full path, not the filename — same-named
          files in different folders are distinct and both are kept.
        * ``processed_document_paths`` accumulates every processed path so the
          next append can skip already-extracted files.
        * Previous per-document stats are preserved; stats for genuinely new
          documents are added.
        * ``append_runs`` accumulates every append folder, not just the last.
        """
        if not previous:
            return current

        merged = dict(current)
        previous_records = previous.get("flow_records", []) or []
        current_records = current.get("flow_records", []) or []

        # The append stage already filtered out already-processed documents by
        # full path, so current records are genuinely new — concatenate.
        merged["flow_records"] = previous_records + current_records
        merged["total_records"] = len(merged["flow_records"])

        merged["total_documents"] = int(previous.get("total_documents", 0) or 0) + int(
            current.get("total_documents", 0) or 0
        )
        merged["processed_documents"] = int(previous.get("processed_documents", 0) or 0) + int(
            current.get("processed_documents", 0) or 0
        )
        merged["total_tables"] = int(previous.get("total_tables", 0) or 0) + int(
            current.get("total_tables", 0) or 0
        )
        merged["flow_tables"] = int(previous.get("flow_tables", 0) or 0) + int(
            current.get("flow_tables", 0) or 0
        )

        # Dedup failed_documents by name (display-level).
        prev_failed = previous.get("failed_documents", []) or []
        curr_failed = current.get("failed_documents", []) or []
        seen_failed = set(prev_failed)
        merged["failed_documents"] = prev_failed + [
            f for f in curr_failed if f not in seen_failed
        ]

        merged["errors"] = (previous.get("errors", []) or []) + (current.get("errors", []) or [])

        # Preserve previous per-document stats; only add stats for new documents.
        prev_stats = dict(previous.get("per_document_stats", {}) or {})
        curr_stats = current.get("per_document_stats", {}) or {}
        for doc_name, stat in curr_stats.items():
            if doc_name not in prev_stats:
                prev_stats[doc_name] = stat
        merged["per_document_stats"] = prev_stats

        # Accumulate processed full paths (deduped, path-aware).
        prev_paths = list(previous.get("processed_document_paths", []) or [])
        curr_paths = list(current.get("processed_document_paths", []) or [])
        seen_paths = set(prev_paths)
        merged["processed_document_paths"] = prev_paths + [
            p for p in curr_paths if p not in seen_paths
        ]

        merged["append_runs"] = (previous.get("append_runs", []) or []) + [
            {
                "task_time": current.get("task_time"),
                "document_folder": current.get("document_folder"),
                "total_records": current.get("total_records", 0),
            }
        ]
        return merged


runner = ExtractionTaskRunner()
