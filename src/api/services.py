# -*- coding: utf-8 -*-
"""Business services for the agent task API."""

import json
import logging
import re
import shutil
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests

from ..config import get_config
from ..core.checkpoint_manager import CheckpointManager
from ..core.extraction_result import ExtractionResult
from ..core.flow_extractor_v2 import FlowExtractorV2
from ..core.reviewer import ReviewMatch, ReviewResult, Reviewer
from ..export_flows import FlowExporter, SkillsExporter
from ..parsers.base import FLOW_EXCEL_COLUMNS, FlowRecord
from .storage import ApiStorage, FileStore, JobStore, TaskStore

logger = logging.getLogger(__name__)


class AgentTaskService:
    """High-level orchestration for the two-stage review pipeline."""

    def __init__(self):
        self.config = get_config()
        self.storage = ApiStorage()
        self.tasks = TaskStore(self.storage)
        self.jobs = JobStore(self.storage)
        self.files = FileStore(self.storage)

    def create_task(self, task_title: str) -> Dict:
        return self.tasks.create_task(task_title)

    def get_task_detail(self, task_id: str) -> Dict:
        task = self.tasks.get_task(task_id)
        if not task:
            raise FileNotFoundError(f"Task not found: {task_id}")
        return self._task_response(task)

    def save_uploaded_document(self, task_id: str, filename: str, content: bytes) -> Dict:
        self.tasks.validate_source_extension(filename)
        target = self.tasks.unique_file_path(self.tasks.documents_dir(task_id), filename)
        target.write_bytes(content)
        file_meta = self.files.register_file(
            task_id=task_id,
            category="original_document",
            path=target,
            original_name=filename,
        )
        document_meta = {
            "document_id": file_meta["file_id"],
            "file_name": file_meta["file_name"],
            "local_path": file_meta["path"],
            "source_type": "upload",
            "source_url": "",
            "size": file_meta["size"],
        }
        self.tasks.append_document(task_id, document_meta)
        return document_meta

    def save_document_from_url(self, task_id: str, url: str) -> Dict:
        parsed = urlparse(str(url or "").strip())
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(f"无效文档 URL: {url}")
        filename = Path(parsed.path).name or f"document_{task_id}.pdf"
        self.tasks.validate_source_extension(filename)

        try:
            response = requests.get(url, timeout=120, stream=True)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ValueError(f"下载文档失败: {url} - {exc}") from exc
        target = self.tasks.unique_file_path(self.tasks.documents_dir(task_id), filename)
        with target.open("wb") as f:
            for chunk in response.iter_content(chunk_size=1024 * 128):
                if chunk:
                    f.write(chunk)
        file_meta = self.files.register_file(
            task_id=task_id,
            category="original_document",
            path=target,
            original_name=filename,
            source_url=url,
        )
        document_meta = {
            "document_id": file_meta["file_id"],
            "file_name": file_meta["file_name"],
            "local_path": file_meta["path"],
            "source_type": "url",
            "source_url": url,
            "size": file_meta["size"],
        }
        self.tasks.append_document(task_id, document_meta)
        return document_meta

    def create_standardize_job(self, task_id: str) -> Dict:
        task = self.tasks.get_task(task_id)
        if not task:
            raise FileNotFoundError(f"Task not found: {task_id}")
        documents = list(task.get("documents", []) or [])
        if not documents:
            raise ValueError("任务下没有可处理文档")
        job = self.jobs.create_job(task_id, "standardize")
        standardized = dict(task.get("standardized", {}) or {})
        standardized["latest_job_id"] = job["job_id"]
        task["standardized"] = standardized
        task["status"] = "standardizing"
        self.tasks.save_task(task_id, task)
        worker = threading.Thread(
            target=self._run_standardize_job,
            args=(task_id, job["job_id"]),
            daemon=True,
        )
        worker.start()
        return {
            "job_id": job["job_id"],
            "task_id": task_id,
            "job_type": "standardize",
        }

    def create_review_job(
        self,
        task_id: str,
        *,
        review_source_type: str,
        uploaded_file_id: str,
        name_list_text: str,
    ) -> Dict:
        task = self.tasks.get_task(task_id)
        if not task:
            raise FileNotFoundError(f"Task not found: {task_id}")
        names = self.parse_name_list(name_list_text)
        if not names:
            raise ValueError("名单为空，无法启动审查")
        source_path, source_file_id = self._resolve_review_source(task_id, review_source_type, uploaded_file_id)
        self._validate_standardized_excel(source_path)

        job = self.jobs.create_job(task_id, "review")
        review = dict(task.get("review", {}) or {})
        review["latest_job_id"] = job["job_id"]
        review["source_type"] = review_source_type
        review["source_file_id"] = source_file_id
        review["source_download_url"] = self._file_download_url(source_file_id)
        task["review"] = review
        task["status"] = "reviewing"
        self.tasks.save_task(task_id, task)

        worker = threading.Thread(
            target=self._run_review_job,
            args=(task_id, job["job_id"], str(source_path), review_source_type, source_file_id, names),
            daemon=True,
        )
        worker.start()
        return {
            "job_id": job["job_id"],
            "task_id": task_id,
            "job_type": "review",
        }

    def upload_review_source(self, task_id: str, filename: str, content: bytes) -> Dict:
        task = self.tasks.get_task(task_id)
        if not task:
            raise FileNotFoundError(f"Task not found: {task_id}")
        if Path(filename).suffix.lower() not in {".xlsx", ".xls"}:
            raise ValueError("审查源仅支持 Excel 文件")
        target = self.tasks.unique_file_path(self.tasks.review_inputs_dir(task_id), filename)
        target.write_bytes(content)
        self._validate_standardized_excel(target)
        file_meta = self.files.register_file(
            task_id=task_id,
            category="review_source",
            path=target,
            original_name=filename,
        )
        return {
            "file_id": file_meta["file_id"],
            "file_name": file_meta["file_name"],
            "download_url": self._file_download_url(file_meta["file_id"]),
        }

    def export_skills(self, task_id: str) -> Dict:
        task = self.tasks.get_task(task_id)
        if not task:
            raise FileNotFoundError(f"Task not found: {task_id}")
        review_meta = dict(task.get("review", {}) or {})
        review_json_path = Path(str(review_meta.get("review_json_path", "") or ""))
        if not review_json_path.exists():
            raise ValueError("当前任务尚无可导出的审查结果")

        review_result = self._load_review_result(review_json_path)
        exporter = SkillsExporter()
        output_path = self.tasks.exports_dir(task_id) / f"审查Skills包_{task_id}.zip"
        exported = exporter.export_bundle(
            review_result,
            task_title=str(task.get("task_title", "") or task_id),
            task_id=task_id,
            report_text="",
            output_path=str(output_path),
        )
        file_meta = self.files.register_file(
            task_id=task_id,
            category="skills_bundle",
            path=exported,
            original_name=exported.name,
        )
        exports = dict(task.get("exports", {}) or {})
        exports["skills_file_id"] = file_meta["file_id"]
        exports["skills_download_url"] = self._file_download_url(file_meta["file_id"])
        task["exports"] = exports
        task["status"] = "skills_exported"
        self.tasks.save_task(task_id, task)
        return {
            "task_id": task_id,
            "file_id": file_meta["file_id"],
            "download_url": exports["skills_download_url"],
        }

    def get_job(self, job_id: str) -> Dict:
        job = self.jobs.get_job(job_id)
        if not job:
            raise FileNotFoundError(f"Job not found: {job_id}")
        return job

    def get_file(self, file_id: str) -> Dict:
        file_meta = self.files.get_file(file_id)
        if not file_meta:
            raise FileNotFoundError(f"File not found: {file_id}")
        return file_meta

    def parse_name_list(self, name_list_text: str) -> List[str]:
        tokens = re.split(r"[,，、;；\n\r\t]+", str(name_list_text or ""))
        names: List[str] = []
        seen = set()
        for token in tokens:
            name = str(token or "").strip()
            if not name or name in seen:
                continue
            names.append(name)
            seen.add(name)
        return names

    def _run_standardize_job(self, task_id: str, job_id: str) -> None:
        try:
            task = self.tasks.get_task(task_id)
            documents = [str(item.get("local_path", "") or "") for item in (task.get("documents", []) or [])]
            title = str(task.get("task_title", "") or task_id)
            checkpoint = CheckpointManager(self.config.config_dir / "checkpoints")
            checkpoint.clear_document_states(task_id)
            checkpoint.start_task(
                task_id,
                documents=documents,
                title=title,
                document_folder=str(self.tasks.documents_dir(task_id)),
            )
            checkpoint.update_task_status(task_id, "extracting")

            self.jobs.mark_running(job_id, "开始标准化任务")
            extractor = FlowExtractorV2()
            extractor.set_progress_callback(
                lambda message, current, total: self.jobs.update_progress(
                    job_id, message, current, total
                )
            )
            result = extractor.extract_flows(
                document_folder=str(self.tasks.documents_dir(task_id)),
                task_id=task_id,
                batch_size=self.config.flow_batch_size,
                confidence_threshold=self.config.flow_confidence_threshold,
                parallelism=self.config.flow_parallelism,
            )
            if not result.flow_records:
                raise RuntimeError("标准化完成，但未生成任何流水记录")

            standardized_dir = self.tasks.standardized_dir(task_id)
            exporter = FlowExporter(output_folder=standardized_dir)
            standardized_path = exporter.export(
                records=result.flow_records,
                task_id=task_id,
                filename=f"标准化流水_{task_id}.xlsx",
            )
            summary_path = standardized_dir / "standardize_result.json"
            with summary_path.open("w", encoding="utf-8") as f:
                json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)

            file_meta = self.files.register_file(
                task_id=task_id,
                category="standardized_excel",
                path=standardized_path,
                original_name=standardized_path.name,
            )
            task = self.tasks.get_task(task_id)
            standardized = dict(task.get("standardized", {}) or {})
            standardized.update({
                "ready": True,
                "latest_job_id": job_id,
                "file_id": file_meta["file_id"],
                "path": str(standardized_path),
                "download_url": self._file_download_url(file_meta["file_id"]),
                "record_count": int(result.total_records),
                "total_amount": float(result.total_amount),
                "summary_path": str(summary_path),
            })
            task["standardized"] = standardized
            task["status"] = "standardized"
            self.tasks.save_task(task_id, task)
            checkpoint.update_task_status(task_id, "completed")
            self.jobs.mark_succeeded(job_id, {
                "task_id": task_id,
                "standardized_excel_file_id": file_meta["file_id"],
                "standardized_excel_download_url": standardized["download_url"],
                "record_count": int(result.total_records),
                "total_amount": float(result.total_amount),
            })
        except Exception as exc:
            logger.exception("Standardize job failed: %s", exc)
            task = self.tasks.get_task(task_id)
            if task:
                task["status"] = "failed"
                self.tasks.save_task(task_id, task)
            self.jobs.mark_failed(job_id, str(exc))

    def _run_review_job(
        self,
        task_id: str,
        job_id: str,
        source_path: str,
        review_source_type: str,
        source_file_id: str,
        names: List[str],
    ) -> None:
        try:
            self.jobs.mark_running(job_id, "开始名单审查")
            source = Path(source_path)
            review_output_dir = self.tasks.review_outputs_dir(task_id)
            review_output_dir.mkdir(parents=True, exist_ok=True)
            working_path = self.tasks.unique_file_path(
                review_output_dir,
                f"最终审查流水_{task_id}.xlsx",
            )
            shutil.copy2(source, working_path)
            self.jobs.update_progress(job_id, "已准备审查输入文件", 10, 100)

            reviewer = Reviewer()
            result = reviewer.run_review(str(working_path), customers=names)
            self.jobs.update_progress(job_id, "名单审查完成，正在登记产物", 90, 100)

            review_json_path = self.config.config_dir / "reviews" / f"{result.review_id}.json"
            reviewed_file = self.files.register_file(
                task_id=task_id,
                category="reviewed_excel",
                path=working_path,
                original_name=working_path.name,
            )

            task = self.tasks.get_task(task_id)
            review = dict(task.get("review", {}) or {})
            review.update({
                "ready": True,
                "latest_job_id": job_id,
                "source_type": review_source_type,
                "source_file_id": source_file_id,
                "source_download_url": self._file_download_url(source_file_id),
                "review_id": result.review_id,
                "review_json_path": str(review_json_path),
                "reviewed_excel_file_id": reviewed_file["file_id"],
                "reviewed_excel_download_url": self._file_download_url(reviewed_file["file_id"]),
                "matched_customers": int(result.matched_customers),
                "total_matches": int(result.total_matches),
                "total_amount": float(result.total_amount),
            })
            task["review"] = review
            task["status"] = "reviewed"
            self.tasks.save_task(task_id, task)

            self.jobs.mark_succeeded(job_id, {
                "task_id": task_id,
                "review_id": result.review_id,
                "reviewed_excel_file_id": reviewed_file["file_id"],
                "reviewed_excel_download_url": review["reviewed_excel_download_url"],
                "matched_customers": int(result.matched_customers),
                "total_matches": int(result.total_matches),
                "total_amount": float(result.total_amount),
            })
        except Exception as exc:
            logger.exception("Review job failed: %s", exc)
            task = self.tasks.get_task(task_id)
            if task:
                task["status"] = "failed"
                self.tasks.save_task(task_id, task)
            self.jobs.mark_failed(job_id, str(exc))

    def _resolve_review_source(
        self,
        task_id: str,
        review_source_type: str,
        uploaded_file_id: str,
    ) -> Tuple[Path, str]:
        normalized_type = str(review_source_type or "").strip()
        if normalized_type == "task_standardized_excel":
            task = self.tasks.get_task(task_id)
            standardized = dict(task.get("standardized", {}) or {})
            file_id = str(standardized.get("file_id", "") or "")
            path = Path(str(standardized.get("path", "") or ""))
            if not file_id or not path.exists():
                raise ValueError("当前任务尚无可用的标准化 Excel")
            return path, file_id
        if normalized_type == "uploaded_excel":
            if not uploaded_file_id:
                raise ValueError("缺少 uploaded_excel 的 file_id")
            file_meta = self.get_file(uploaded_file_id)
            if str(file_meta.get("task_id", "")) != task_id:
                raise ValueError("上传的审查源文件不属于当前任务")
            return Path(str(file_meta.get("path", "") or "")), uploaded_file_id
        raise ValueError("review_source.type 仅支持 task_standardized_excel 或 uploaded_excel")

    def _validate_standardized_excel(self, excel_path: Path) -> None:
        import openpyxl

        path = Path(excel_path)
        if not path.exists():
            raise FileNotFoundError(f"Excel not found: {path}")
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        try:
            ws = wb.active
            headers = []
            for row in ws.iter_rows(min_row=1, max_row=1, values_only=True):
                headers = [str(cell).strip() if cell is not None else "" for cell in row]
                break
            missing = [header for header in FLOW_EXCEL_COLUMNS if header not in headers]
            if missing:
                raise ValueError(f"Excel 缺少标准字段: {', '.join(missing)}")
        finally:
            wb.close()

    def _task_response(self, task: Dict) -> Dict:
        documents = []
        for item in task.get("documents", []) or []:
            document = dict(item)
            document_id = str(document.get("document_id", "") or "")
            if document_id:
                document["download_url"] = self._file_download_url(document_id)
            documents.append(document)
        result = dict(task)
        result["documents"] = documents
        return result

    @staticmethod
    def _file_download_url(file_id: str) -> str:
        return f"/api/v1/files/{file_id}/download"

    @staticmethod
    def _load_review_result(review_json_path: Path) -> ReviewResult:
        data = json.loads(review_json_path.read_text(encoding="utf-8"))
        matches = [
            ReviewMatch(
                customer_name=str(item.get("customer_name", "") or ""),
                counterparty_name=str(item.get("counterparty_name", "") or ""),
                counterparty_account=str(item.get("counterparty_account", "") or ""),
                match_type=str(item.get("match_type", "") or ""),
                confidence=int(item.get("confidence", 0) or 0),
                source_file=str(item.get("source_file", "") or ""),
                row_index=int(item.get("row_index", 0) or 0),
                transaction_time=str(item.get("transaction_time", "") or ""),
                amount=str(item.get("amount", "") or ""),
                summary=str(item.get("summary", "") or ""),
            )
            for item in (data.get("matches", []) or [])
        ]
        return ReviewResult(
            review_id=str(data.get("review_id", "") or ""),
            review_time=str(data.get("review_time", "") or ""),
            flow_excel_path=str(data.get("flow_excel_path", "") or ""),
            customer_excel_path=str(data.get("customer_excel_path", "") or ""),
            total_customers=int(data.get("total_customers", 0) or 0),
            matched_customers=int(data.get("matched_customers", 0) or 0),
            total_matches=int(data.get("total_matches", 0) or 0),
            total_amount=float(data.get("total_amount", 0.0) or 0.0),
            matches=matches,
            writeback_error=str(data.get("writeback_error", "") or ""),
        )
