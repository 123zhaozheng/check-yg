# -*- coding: utf-8 -*-
"""
Checkpoint manager for resumable extraction.
"""

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class CheckpointManager:
    """
    Manage checkpoint files under ~/.check-yg/checkpoints/{task_id}/
    """

    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _task_dir(self, task_id: str) -> Path:
        task_dir = self.base_dir / task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        return task_dir

    @staticmethod
    def _doc_hash(document_name: str) -> str:
        return hashlib.md5(document_name.encode("utf-8")).hexdigest()[:16]

    def _doc_path(self, task_id: str, document_name: str) -> Path:
        return self._task_dir(task_id) / f"doc_{self._doc_hash(document_name)}.json"

    def _task_meta_path(self, task_id: str) -> Path:
        return self._task_dir(task_id) / "task.json"

    def start_task(self, task_id: str, documents: List[str]) -> None:
        meta_path = self._task_meta_path(task_id)
        if meta_path.exists():
            return
        data = {
            "task_id": task_id,
            "created_at": datetime.now().isoformat(),
            "documents": documents,
        }
        self._write_json(meta_path, data)

    def load_task(self, task_id: str) -> Optional[Dict]:
        meta_path = self._task_meta_path(task_id)
        if not meta_path.exists():
            return None
        return self._read_json(meta_path)

    def save_document_state(self, task_id: str, document_name: str, state: Dict) -> None:
        state = dict(state)
        state.setdefault("document_name", document_name)
        state.setdefault("updated_at", datetime.now().isoformat())
        self._write_json(self._doc_path(task_id, document_name), state)

    def load_document_state(self, task_id: str, document_name: str) -> Optional[Dict]:
        doc_path = self._doc_path(task_id, document_name)
        if not doc_path.exists():
            return None
        return self._read_json(doc_path)

    def list_document_states(self, task_id: str) -> List[Dict]:
        task_dir = self._task_dir(task_id)
        results: List[Dict] = []
        for doc_file in task_dir.glob("doc_*.json"):
            data = self._read_json(doc_file)
            if data:
                results.append(data)
        return results

    def clear_task(self, task_id: str) -> None:
        task_dir = self._task_dir(task_id)
        for file_path in task_dir.glob("*"):
            try:
                file_path.unlink()
            except Exception as exc:
                logger.warning("Failed to delete checkpoint %s: %s", file_path, exc)
        try:
            task_dir.rmdir()
        except Exception:
            pass

    @staticmethod
    def _read_json(path: Path) -> Optional[Dict]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logger.warning("Failed to read checkpoint %s: %s", path, exc)
            return None

    @staticmethod
    def _write_json(path: Path, data: Dict) -> None:
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.warning("Failed to write checkpoint %s: %s", path, exc)
