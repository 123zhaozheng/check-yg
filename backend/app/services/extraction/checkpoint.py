# -*- coding: utf-8 -*-
"""Checkpoint manager for resumable extraction."""

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class CheckpointManager:
    """Manage extraction checkpoints for resumability.

    Document identity is path-aware: a checkpoint is keyed by
    ``name|path`` (path normalized to posix), mirroring
    ``src/core/checkpoint_manager.py``. Two files with the same name in
    different folders therefore get distinct checkpoints instead of
    colliding.
    """

    def __init__(self, base_dir: str = "data/checkpoints"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _task_dir(self, task_id: str) -> Path:
        """Get task-specific checkpoint directory."""
        task_dir = self.base_dir / task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        return task_dir

    @staticmethod
    def _doc_key(document_name: str, document_path: Optional[str] = None) -> str:
        """Build a stable, path-aware checkpoint key for a document.

        Uses ``name|posix_path`` when a path is supplied so same-named files
        in different folders do not collide. Falls back to the name only for
        backward compatibility when callers omit the path.
        """
        doc_id = str(document_name or "")
        if document_path:
            normalized_path = Path(str(document_path)).as_posix()
            doc_id = f"{doc_id}|{normalized_path}"
        return hashlib.md5(doc_id.encode("utf-8")).hexdigest()[:16]

    def _checkpoint_file(
        self,
        task_id: str,
        document_name: str,
        document_path: Optional[str] = None,
    ) -> Path:
        """Get checkpoint file for a specific document."""
        return self._task_dir(task_id) / f"doc_{self._doc_key(document_name, document_path)}.json"

    def load_checkpoint(
        self,
        task_id: str,
        document_name: str,
        document_path: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Load checkpoint for a document."""
        checkpoint_file = self._checkpoint_file(task_id, document_name, document_path)
        if not checkpoint_file.exists():
            return None

        try:
            with open(checkpoint_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Failed to load checkpoint %s: %s", checkpoint_file, e)
            return None

    def save_checkpoint(
        self,
        task_id: str,
        document_name: str,
        state: Dict[str, Any],
        document_path: Optional[str] = None,
    ) -> None:
        """Save checkpoint for a document."""
        checkpoint_file = self._checkpoint_file(task_id, document_name, document_path)
        state["updated_at"] = datetime.now().isoformat()

        try:
            with open(checkpoint_file, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("Failed to save checkpoint %s: %s", checkpoint_file, e)

    def clear_checkpoint(
        self,
        task_id: str,
        document_name: str,
        document_path: Optional[str] = None,
    ) -> None:
        """Clear checkpoint for a document."""
        checkpoint_file = self._checkpoint_file(task_id, document_name, document_path)
        if checkpoint_file.exists():
            try:
                checkpoint_file.unlink()
            except Exception as e:
                logger.warning("Failed to clear checkpoint %s: %s", checkpoint_file, e)

    def clear_task(self, task_id: str) -> None:
        """Clear all checkpoints for a task."""
        task_dir = self._task_dir(task_id)
        if task_dir.exists():
            try:
                for file in task_dir.glob("*.json"):
                    file.unlink()
                task_dir.rmdir()
            except Exception as e:
                logger.warning("Failed to clear task directory %s: %s", task_dir, e)

    def list_task_checkpoints(self, task_id: str) -> List[Path]:
        """List all checkpoint files for a task."""
        task_dir = self._task_dir(task_id)
        if not task_dir.exists():
            return []
        return list(task_dir.glob("*.json"))
