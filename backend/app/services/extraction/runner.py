# -*- coding: utf-8 -*-
"""Runtime orchestration for FastAPI extraction jobs."""

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from sqlalchemy import delete, select

from app.database import async_session
from app.models import Document, FlowRecordRow, Task, TaskLog
from app.models.llm_model_assignment import ACTIVE_STAGES
from app.services.llm_model_service import load_stage_models
from app.services.settings_service import get_int_setting, load_runtime_settings
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
        mineru_concurrency: Optional[int] = None,
        llm_concurrency: Optional[int] = None,
    ) -> None:
        """Start an extraction job that runs a batch loop.

        Reads ``extraction.mineru_concurrency`` / ``extraction.llm_concurrency``
        from runtime settings (unless overridden by the explicit args) and
        threads them into the extractor. The batch loop processes every pending
        document across all the task's upload folders, then re-checks for files
        uploaded mid-run; new uploads are picked up by the next loop iteration
        without restarting the runner.
        """
        if self.is_running(task_id):
            raise ValueError("Task is already running")

        async with async_session() as session:
            runtime_settings = await load_runtime_settings(session)
            # 查 classification/portrait/normalization 三阶段指派的卡片（一次查完，
            # 避免 extractor 内访问 DB）。未指派返回 None → extractor 回退兜底。
            stage_models = await load_stage_models(session, ACTIVE_STAGES)

        if mineru_concurrency is None:
            mineru_concurrency = get_int_setting(
                runtime_settings, "extraction.mineru_concurrency", 1, 1, 16
            )
        if llm_concurrency is None:
            llm_concurrency = get_int_setting(
                runtime_settings, "extraction.llm_concurrency", 2, 1, 16
            )

        extractor = FlowExtractor(
            runtime_settings=runtime_settings,
            stage_models=stage_models,
        )
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
                mineru_concurrency=mineru_concurrency,
                llm_concurrency=llm_concurrency,
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
        mineru_concurrency: int = 1,
        llm_concurrency: int = 2,
    ) -> None:
        """Run the batch loop until no new pending documents remain.

        Each iteration processes every not-yet-processed document across all the
        task's upload folders (the ``document_folder`` plus every entry in
        ``append_document_folders``), path-deduped against
        ``processed_document_paths``. After a round, if new files were uploaded
        mid-run (new pending Document rows whose path isn't yet processed),
        another round runs to pick them up — the runner is never restarted,
        the loop just continues. When no new work appears, the task finishes.
        """
        try:
            first_round = not append
            ran_a_round = False
            while True:
                if extractor._cancel_requested:
                    break

                pending_docs = await self._collect_pending_documents(
                    task_id, document_folder, extractor
                )
                if not pending_docs:
                    break

                ran_a_round = True
                logger.info(
                    "批循环轮次：待处理文档 %d 个 (task=%s)",
                    len(pending_docs),
                    task_id,
                )

                # Reuse extract_flows with a pre-filtered document set so the
                # path-aware dedup (skip already-processed full paths) is done
                # here via _collect_pending_documents; the extractor then runs
                # stage1+stage2 with concurrency limits.
                result = await extractor.extract_flows(
                    document_folder=document_folder,
                    task_id=str(task_id),
                    batch_size=batch_size,
                    confidence_threshold=confidence_threshold,
                    documents=pending_docs,
                    mineru_concurrency=mineru_concurrency,
                    llm_concurrency=llm_concurrency,
                )

                await self._mark_finished(
                    task_id, owner_id, result.to_dict(), append=not first_round
                )
                first_round = False

                # Loop continues: _collect_pending_documents re-reads pending
                # Document rows + processed_document_paths, so files uploaded
                # during this round surface as new pending docs next iteration.
                # If none remain, the while-break above exits.

            # No pending documents from the start (e.g. task already processed,
            # or start pressed on a task whose uploads were all handled). The
            # start endpoint already flipped status to "running"; mark it
            # completed with an empty result so the task doesn't stick in
            # running forever.
            if not ran_a_round and not extractor._cancel_requested:
                from .extractor import ExtractionResult

                empty = ExtractionResult(task_id=str(task_id), document_folder=document_folder)
                await self._mark_finished(
                    task_id, owner_id, empty.to_dict(), append=append
                )
        except Exception as exc:
            logger.exception("Extraction task %s failed", task_id)
            await self._mark_failed(task_id, owner_id, str(exc))
        finally:
            self._extractors.pop(task_id, None)
            self._jobs.pop(task_id, None)

    async def _collect_pending_documents(
        self, task_id: int, document_folder: str, extractor: FlowExtractor
    ) -> list:
        """Return Path list of documents not yet processed for this task.

        Scans every folder the task has uploaded into (``document_folder`` plus
        ``append_document_folders``) and filters out full paths already in
        ``processed_document_paths`` (path-aware dedup — same-named files in
        different run dirs stay distinct). This is the batch loop's work queue:
        a file uploaded mid-run appears here next iteration, so the loop picks
        it up without a runner restart.
        """
        async with async_session() as session:
            db_result = await session.execute(select(Task).where(Task.id == task_id))
            task = db_result.scalar_one_or_none()
            if not task:
                return []
            config = task.config or {}
            last_result = config.get("last_result") or {}
            processed = {
                str(Path(p).as_posix())
                for p in (last_result.get("processed_document_paths") or [])
            }
            folders = []
            if config.get("document_folder"):
                folders.append(config["document_folder"])
            for folder in (config.get("append_document_folders") or []):
                if folder and folder not in folders:
                    folders.append(folder)

        scanner = extractor.scanner  # reuse the extractor's DocumentScanner
        all_docs: list = []
        for folder in folders:
            folder_path = Path(folder)
            if not folder_path.exists() or not folder_path.is_dir():
                continue
            all_docs.extend(scanner.scan_directory(str(folder_path)))

        return [d for d in all_docs if d.as_posix() not in processed]
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
        # Current-run extracted_records (standard + unparsed + excluded) with
        # raw_payload. Persisted separately from the merged final_result so
        # append runs only insert new documents' records (path-aware filter in
        # the extractor already excluded already-processed docs), never
        # re-inserting previous runs' rows.
        current_extracted_records = list(result.get("extracted_records", []) or [])
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
            await self._persist_result_documents(
                session, task_id, final_result, append=append,
                extracted_records=current_extracted_records,
            )
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
    async def _persist_result_documents(
        session,
        task_id: int,
        result: dict,
        append: bool = False,
        extracted_records: list | None = None,
    ) -> None:
        """Persist normalized records into Document rows for review/report services.

        Rows pre-created at upload time (with channel/size_bytes, status="pending")
        are matched by filename and **updated** in place — their channel and
        size_bytes are preserved. Rows without a pre-created match (e.g. legacy
        rows, fallback from a checkpoint-only run) are created with channel=None.

        Soft-deleted rows (status="deleted") are never touched, honoring the
        不删减 hard line — we do not delete any Document row here.

        S5 不删减: ``extracted_records`` (standard + unparsed + excluded, each
        with ``raw_payload``) are persisted into the ``flow_records`` table as
        the record-of-truth. Non-append runs clear prior non-restored rows for
        this task first (restored rows are never touched — 不删减). Append runs
        only insert the current run's records (never delete), mirroring the
        path-aware append dedup in the extractor.
        """
        records_by_source = {}
        for record in result.get("flow_records", []) or []:
            if not isinstance(record, dict):
                continue
            source_file = str(record.get("source_file") or "unknown").strip() or "unknown"
            records_by_source.setdefault(source_file, []).append(record)

        # Per-document portrait (stage-1 generated), keyed by filename. May be
        # None for a doc whose portrait extraction failed — written through so
        # the import page hover card can show 「画像待生成」 for those rows.
        portraits_by_name: dict[str, dict | None] = {
            str(name): portrait
            for name, portrait in (result.get("per_document_portraits") or {}).items()
        }

        # Load existing non-deleted documents for this task, keyed by filename so
        # we can update the pre-created row instead of deleting + recreating.
        existing_result = await session.execute(
            select(Document).where(
                Document.task_id == task_id,
                Document.status != "deleted",
            )
        )
        existing_by_name: dict[str, list[Document]] = {}
        for doc in existing_result.scalars().all():
            existing_by_name.setdefault(doc.filename, []).append(doc)

        consumed_ids: set[int] = set()
        for source_file, records in records_by_source.items():
            candidates = existing_by_name.get(source_file) or []
            target = next((d for d in candidates if d.id not in consumed_ids), None)
            if target is not None:
                # Update the pre-created row in place; preserve channel/size_bytes.
                target.flow_tables = {"records": records}
                target.status = "completed"
                target.error_log = None
                if source_file in portraits_by_name:
                    target.portrait = portraits_by_name[source_file]
                consumed_ids.add(target.id)
            else:
                # No pre-created row (legacy / fallback) — create one with no channel.
                session.add(
                    Document(
                        task_id=task_id,
                        filename=source_file,
                        original_path=source_file,
                        status="completed",
                        flow_tables={"records": records},
                        portrait=portraits_by_name.get(source_file),
                    )
                )

        # Mark pre-created rows whose extraction failed (filename in
        # failed_documents) as "failed" with the first matching error message,
        # so the frontend's polling can stop and surface a Retry affordance.
        failed_documents = result.get("failed_documents", []) or []
        errors = result.get("errors", []) or []
        if failed_documents:
            error_by_doc: dict[str, str] = {}
            for err in errors:
                if not isinstance(err, dict):
                    continue
                doc_name = str(err.get("document") or "").strip()
                if doc_name:
                    error_by_doc.setdefault(doc_name, str(err.get("error") or ""))
            for failed_name in failed_documents:
                name = str(failed_name).strip()
                if not name:
                    continue
                candidates = existing_by_name.get(name) or []
                target = next((d for d in candidates if d.id not in consumed_ids), None)
                if target is not None:
                    target.status = "failed"
                    target.error_log = error_by_doc.get(name)
                    consumed_ids.add(target.id)

        # Documents that were processed but produced no flow records (e.g. a PDF
        # with no extractable tables, or a portrait-only document) have no entry
        # in flow_records or failed_documents. Mark their pre-created rows as
        # completed with empty flow_tables so the frontend's polling stops —
        # otherwise those rows stay "pending" forever and the import page polls
        # indefinitely. This run finished, so any still-pending row is settled.
        for candidates in existing_by_name.values():
            for doc in candidates:
                if doc.id in consumed_ids:
                    continue
                if doc.status == "pending":
                    doc.status = "completed"
                    doc.flow_tables = {"records": []}
                    # A portrait-only / no-flow-tables doc still has a stage-1
                    # portrait (the extractor captured it even with empty
                    # flow_tables). Write it through so the hover card shows it.
                    if doc.filename in portraits_by_name:
                        doc.portrait = portraits_by_name[doc.filename]
                    consumed_ids.add(doc.id)

        # S5 不删减: persist every extracted row (standard + unparsed + excluded)
        # into the flow_records table with raw_payload. The task's documents are
        # keyed by filename; records carry source_file so we can map back to the
        # document_id. Restored rows are never touched (不删减).
        await ExtractionTaskRunner._persist_flow_records(
            session,
            task_id,
            extracted_records or [],
            append=append,
            existing_by_name=existing_by_name,
            consumed_ids=consumed_ids,
        )

    @staticmethod
    async def _persist_flow_records(
        session,
        task_id: int,
        extracted_records: list,
        *,
        append: bool,
        existing_by_name: dict[str, list[Document]],
        consumed_ids: set[int],
    ) -> None:
        """Write the unified record list into the ``flow_records`` table.

        Non-append: delete this task's prior ``flow_records`` rows whose status
        is not ``restored`` (restored rows are never touched — 不删减), then
        insert the current run's rows. This rebuilds the table per run while
        preserving user-restored rows.

        Append: only insert the current run's rows (the extractor already
        filtered out already-processed documents by full path, so these are
        genuinely new). Never delete on append — 不删减.
        """
        if not append:
            await session.execute(
                delete(FlowRecordRow).where(
                    FlowRecordRow.task_id == task_id,
                    FlowRecordRow.status != "restored",
                )
            )

        for record in extracted_records:
            if not isinstance(record, dict):
                continue
            source_file = str(record.get("source_file") or "").strip()
            doc_id: int | None = None
            channel: str | None = None
            if source_file:
                candidates = existing_by_name.get(source_file) or []
                target = next((d for d in candidates if d.id in consumed_ids), None)
                if target is not None:
                    doc_id = target.id
                    channel = target.channel
            raw_payload = record.get("raw_payload")
            if raw_payload is not None and not isinstance(raw_payload, dict):
                raw_payload = None
            session.add(
                FlowRecordRow(
                    task_id=task_id,
                    document_id=doc_id,
                    channel=channel,
                    record_type=str(record.get("record_type") or "standard"),
                    row_index=int(record.get("row_index") or 0),
                    is_valid=bool(record.get("is_valid", True)),
                    transaction_time=record.get("transaction_time") or None,
                    counterparty_name=record.get("counterparty_name") or None,
                    counterparty_account=record.get("counterparty_account") or None,
                    amount=record.get("amount") or None,
                    raw_amount=record.get("raw_amount") or None,
                    summary=record.get("summary") or None,
                    transaction_type=record.get("transaction_type") or None,
                    raw_payload=raw_payload,
                    status="active",
                    exclude_reason=record.get("exclude_reason") or None,
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
            # Flip any still-pending pre-created Document rows to "failed" so the
            # import page's polling stops — otherwise a crashed extraction leaves
            # rows pending forever and the UI polls indefinitely. Soft-deleted
            # rows are never touched (不删减 hard line).
            docs_result = await session.execute(
                select(Document).where(
                    Document.task_id == task_id,
                    Document.status == "pending",
                )
            )
            for doc in docs_result.scalars().all():
                doc.status = "failed"
                doc.error_log = error
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

        # S5 不删减: extracted_records (standard + unparsed + excluded with
        # raw_payload) accumulate across runs — append never overwrites prior
        # rows. The flow_records table is the record-of-truth; this merged list
        # mirrors it in task.config.last_result for traceability.
        prev_extracted = previous.get("extracted_records", []) or []
        curr_extracted = current.get("extracted_records", []) or []
        merged["extracted_records"] = prev_extracted + curr_extracted

        # Preserve previous per-document stats; only add stats for new documents.
        prev_stats = dict(previous.get("per_document_stats", {}) or {})
        curr_stats = current.get("per_document_stats", {}) or {}
        for doc_name, stat in curr_stats.items():
            if doc_name not in prev_stats:
                prev_stats[doc_name] = stat
        merged["per_document_stats"] = prev_stats

        # Merge per-document portraits: keep previous, add current's new docs.
        # Same-named files in different folders are distinct documents (path-
        # aware identity), but portraits are keyed by filename for Document-row
        # matching, so a current entry for an existing name refreshes it.
        prev_portraits = dict(previous.get("per_document_portraits") or {})
        curr_portraits = current.get("per_document_portraits") or {}
        prev_portraits.update(curr_portraits)
        merged["per_document_portraits"] = prev_portraits

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
