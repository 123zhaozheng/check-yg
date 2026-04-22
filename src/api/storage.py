# -*- coding: utf-8 -*-
"""Persistence helpers for the agent task API."""

import json
import logging
import mimetypes
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from ..config import get_config

logger = logging.getLogger(__name__)


def utcnow_iso() -> str:
    return datetime.now().isoformat()


class JsonRepository:
    """Simple JSON repository backed by files."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def read(self, path: Path) -> Dict[str, Any]:
        if not path.exists():
            return {}
        try:
            with path.open("r", encoding="utf-8") as f:
                return json.load(f) or {}
        except Exception as exc:
            logger.warning("Failed to read json %s: %s", path, exc)
            return {}

    def write(self, path: Path, data: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            with path.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)


class ApiStorage:
    """Root directories used by the agent task API."""

    def __init__(self, base_dir: Optional[Path] = None):
        config = get_config()
        self.base_dir = Path(base_dir) if base_dir else (config.config_dir / "agent_api")
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.tasks_root = self.base_dir / "tasks"
        self.jobs_root = self.base_dir / "jobs"
        self.files_root = self.base_dir / "files"
        self.tasks_root.mkdir(parents=True, exist_ok=True)
        self.jobs_root.mkdir(parents=True, exist_ok=True)
        self.files_root.mkdir(parents=True, exist_ok=True)


class TaskStore:
    """Task metadata and task-scoped filesystem layout."""

    SUPPORTED_SOURCE_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".xls"}

    def __init__(self, storage: ApiStorage):
        self.storage = storage
        self.repo = JsonRepository(storage.tasks_root)
        self._lock = threading.RLock()

    def generate_task_id(self) -> str:
        base = datetime.now().strftime("%Y%m%d_%H%M%S")
        candidate = base
        counter = 1
        while self._meta_path(candidate).exists():
            candidate = f"{base}_{counter:02d}"
            counter += 1
        return candidate

    def create_task(self, task_title: str) -> Dict[str, Any]:
        task_id = self.generate_task_id()
        root = self.task_root(task_id)
        for subdir in (
            "documents",
            "standardized",
            "review_inputs",
            "review_outputs",
            "exports",
        ):
            (root / subdir).mkdir(parents=True, exist_ok=True)
        now = utcnow_iso()
        data = {
            "task_id": task_id,
            "task_title": str(task_title or "").strip() or task_id,
            "status": "created",
            "created_at": now,
            "updated_at": now,
            "documents": [],
            "standardized": {
                "ready": False,
                "latest_job_id": "",
                "file_id": "",
                "path": "",
                "download_url": "",
                "record_count": 0,
                "total_amount": 0.0,
                "summary_path": "",
            },
            "review": {
                "ready": False,
                "latest_job_id": "",
                "source_type": "",
                "source_file_id": "",
                "source_download_url": "",
                "review_id": "",
                "review_json_path": "",
                "reviewed_excel_file_id": "",
                "reviewed_excel_download_url": "",
                "matched_customers": 0,
                "total_matches": 0,
                "total_amount": 0.0,
            },
            "exports": {
                "skills_file_id": "",
                "skills_download_url": "",
            },
        }
        self.repo.write(self._meta_path(task_id), data)
        return data

    def get_task(self, task_id: str) -> Dict[str, Any]:
        return self.repo.read(self._meta_path(task_id))

    def save_task(self, task_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        data = dict(data or {})
        data["task_id"] = task_id
        data["updated_at"] = utcnow_iso()
        self.repo.write(self._meta_path(task_id), data)
        return data

    def update_task(self, task_id: str, **updates: Any) -> Dict[str, Any]:
        with self._lock:
            current = self.get_task(task_id)
            if not current:
                raise FileNotFoundError(f"Task not found: {task_id}")
            for key, value in updates.items():
                current[key] = value
            return self.save_task(task_id, current)

    def append_document(self, task_id: str, document_meta: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            current = self.get_task(task_id)
            if not current:
                raise FileNotFoundError(f"Task not found: {task_id}")
            documents = list(current.get("documents", []) or [])
            documents.append(document_meta)
            current["documents"] = documents
            current["status"] = "documents_ready"
            return self.save_task(task_id, current)

    def task_root(self, task_id: str) -> Path:
        return self.storage.tasks_root / task_id

    def documents_dir(self, task_id: str) -> Path:
        return self.task_root(task_id) / "documents"

    def standardized_dir(self, task_id: str) -> Path:
        return self.task_root(task_id) / "standardized"

    def review_inputs_dir(self, task_id: str) -> Path:
        return self.task_root(task_id) / "review_inputs"

    def review_outputs_dir(self, task_id: str) -> Path:
        return self.task_root(task_id) / "review_outputs"

    def exports_dir(self, task_id: str) -> Path:
        return self.task_root(task_id) / "exports"

    def unique_file_path(self, directory: Path, filename: str) -> Path:
        safe_name = self._sanitize_filename(filename)
        candidate = directory / safe_name
        if not candidate.exists():
            return candidate
        stem = candidate.stem
        suffix = candidate.suffix
        counter = 1
        while True:
            next_candidate = directory / f"{stem}_{counter}{suffix}"
            if not next_candidate.exists():
                return next_candidate
            counter += 1

    @classmethod
    def validate_source_extension(cls, filename: str) -> str:
        suffix = Path(str(filename or "")).suffix.lower()
        if suffix not in cls.SUPPORTED_SOURCE_EXTENSIONS:
            raise ValueError(
                "仅支持 pdf/docx/xlsx/xls 文档"
            )
        return suffix

    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        cleaned = str(filename or "").strip().replace("\\", "_").replace("/", "_")
        if not cleaned:
            cleaned = f"file_{uuid4().hex[:8]}"
        return cleaned

    def _meta_path(self, task_id: str) -> Path:
        return self.task_root(task_id) / "task.json"


class JobStore:
    """Background job metadata persistence."""

    def __init__(self, storage: ApiStorage):
        self.storage = storage
        self.repo = JsonRepository(storage.jobs_root)
        self._lock = threading.RLock()

    def create_job(self, task_id: str, job_type: str) -> Dict[str, Any]:
        job_id = f"job_{job_type}_{uuid4().hex[:12]}"
        now = utcnow_iso()
        data = {
            "job_id": job_id,
            "task_id": task_id,
            "job_type": job_type,
            "status": "pending",
            "progress": 0,
            "message": "",
            "created_at": now,
            "updated_at": now,
            "result": {},
            "error": "",
        }
        self.repo.write(self._job_path(job_id), data)
        return data

    def get_job(self, job_id: str) -> Dict[str, Any]:
        return self.repo.read(self._job_path(job_id))

    def update_job(self, job_id: str, **updates: Any) -> Dict[str, Any]:
        with self._lock:
            current = self.get_job(job_id)
            if not current:
                raise FileNotFoundError(f"Job not found: {job_id}")
            for key, value in updates.items():
                current[key] = value
            current["updated_at"] = utcnow_iso()
            self.repo.write(self._job_path(job_id), current)
            return current

    def mark_running(self, job_id: str, message: str = "") -> Dict[str, Any]:
        return self.update_job(job_id, status="running", message=message or "")

    def update_progress(self, job_id: str, message: str, current: int, total: int) -> Dict[str, Any]:
        progress = 0
        if total > 0:
            progress = max(0, min(100, int(current * 100 / total)))
        return self.update_job(job_id, status="running", message=message, progress=progress)

    def mark_succeeded(self, job_id: str, result: Dict[str, Any]) -> Dict[str, Any]:
        return self.update_job(job_id, status="succeeded", progress=100, result=result, error="")

    def mark_failed(self, job_id: str, error: str) -> Dict[str, Any]:
        return self.update_job(job_id, status="failed", error=str(error or ""), message=str(error or ""))

    def _job_path(self, job_id: str) -> Path:
        return self.storage.jobs_root / f"{job_id}.json"


class FileStore:
    """File metadata registry used by download endpoints."""

    def __init__(self, storage: ApiStorage):
        self.storage = storage
        self.repo = JsonRepository(storage.files_root)

    def register_file(
        self,
        *,
        task_id: str,
        category: str,
        path: Path,
        original_name: Optional[str] = None,
        source_url: str = "",
    ) -> Dict[str, Any]:
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        file_id = f"file_{uuid4().hex[:12]}"
        content_type, _ = mimetypes.guess_type(str(file_path))
        data = {
            "file_id": file_id,
            "task_id": task_id,
            "category": str(category or "").strip(),
            "path": str(file_path),
            "file_name": str(original_name or file_path.name),
            "content_type": content_type or "application/octet-stream",
            "size": int(file_path.stat().st_size),
            "source_url": str(source_url or ""),
            "created_at": utcnow_iso(),
        }
        self.repo.write(self._file_path(file_id), data)
        return data

    def get_file(self, file_id: str) -> Dict[str, Any]:
        return self.repo.read(self._file_path(file_id))

    def _file_path(self, file_id: str) -> Path:
        return self.storage.files_root / f"{file_id}.json"
