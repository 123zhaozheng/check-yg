# -*- coding: utf-8 -*-
"""
Task manager for extraction checkpoints.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from ..config import get_config
from .checkpoint_manager import CheckpointManager

logger = logging.getLogger(__name__)


class TaskManager:
    """统一管理断点任务。"""

    def __init__(self, checkpoint_dir: Optional[Path] = None):
        config = get_config()
        base_dir = Path(checkpoint_dir) if checkpoint_dir else (config.config_dir / "checkpoints")
        self.checkpoints = CheckpointManager(base_dir)

    def title_exists(self, title: str) -> bool:
        """检查任务标题是否已存在。"""
        normalized_title = str(title or "").strip()
        if not normalized_title:
            return False
        try:
            for task in self.checkpoints.get_all_tasks_with_titles():
                existing_title = str(task.get("title", "") or "").strip()
                if existing_title == normalized_title:
                    return True
        except Exception as exc:
            logger.warning("检查标题是否存在失败: %s", exc)
        return False

    def create_task(self, title: str, document_folder: str) -> str:
        """创建任务并返回 task_id。"""
        normalized_title = str(title or "").strip()
        normalized_folder = str(document_folder or "").strip()
        if not normalized_title:
            raise ValueError("任务标题不能为空")
        if self.title_exists(normalized_title):
            raise ValueError("任务标题已存在")

        task_id = self._generate_task_id()
        self.checkpoints.start_task(
            task_id,
            documents=[],
            title=normalized_title,
            document_folder=normalized_folder,
        )
        self.checkpoints.update_task_status(task_id, "pending")
        return task_id

    def _generate_task_id(self) -> str:
        """生成不重复任务 ID。"""
        base = datetime.now().strftime("%Y%m%d_%H%M%S")
        candidate = base
        counter = 1
        existing_ids = set(self.checkpoints.list_all_tasks())
        while candidate in existing_ids:
            candidate = "{0}_{1:02d}".format(base, counter)
            counter += 1
        return candidate

    def list_tasks(self, status: Optional[str] = None) -> List[Dict]:
        """
        列出任务。

        Args:
            status: 可选状态过滤（pending/extracting/normalizing/completed/canceled/failed）。

        Returns:
            任务摘要列表。
        """
        tasks: List[Dict] = []
        try:
            for task_id in self.checkpoints.list_all_tasks():
                summary = self.checkpoints.get_task_summary(task_id)
                if not summary:
                    continue
                if status and summary.get("status") != status:
                    continue
                tasks.append(summary)
        except Exception as exc:
            logger.warning("列出任务失败: %s", exc)
            return []

        tasks.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        return tasks

    def get_task_detail(self, task_id: str) -> Optional[Dict]:
        """
        获取任务详情。

        Args:
            task_id: 任务 ID。

        Returns:
            任务详情，包含 summary、meta、documents。
        """
        try:
            summary = self.checkpoints.get_task_summary(task_id)
            if not summary:
                return None
            task_meta = self.checkpoints.load_task(task_id) or {}
            document_states = self.checkpoints.list_document_states(task_id)
            document_states.sort(key=lambda item: str(item.get("document_name", "")))
            return {
                "task_id": task_id,
                "summary": summary,
                "meta": task_meta,
                "documents": document_states,
            }
        except Exception as exc:
            logger.warning("获取任务详情失败 %s: %s", task_id, exc)
            return None

    def resume_task(self, task_id: str) -> Optional[Dict]:
        """
        获取可续跑任务信息。

        Args:
            task_id: 任务 ID。

        Returns:
            包含 can_resume 与可续跑文档列表的信息。
        """
        detail = self.get_task_detail(task_id)
        if not detail:
            return None

        summary = detail.get("summary", {}) or {}
        task_status = str(summary.get("status", "unknown"))
        document_states = detail.get("documents", []) or []

        resumable_documents: List[Dict] = []
        for state in document_states:
            status = str(state.get("status", "") or "")
            if status in ("stage1_done", "stage2_running", "normalizing", "canceled"):
                resumable_documents.append({
                    "document_name": state.get("document_name", ""),
                    "document_path": state.get("document_path", ""),
                    "status": status,
                    "processed_rows": int(state.get("processed_rows", 0) or 0),
                    "total_flow_rows": int(state.get("total_flow_rows", 0) or 0),
                })

        can_resume = bool(resumable_documents) and task_status != "completed"
        return {
            "task_id": task_id,
            "status": task_status,
            "can_resume": can_resume,
            "resumable_count": len(resumable_documents),
            "resumable_documents": resumable_documents,
        }

    def delete_task(self, task_id: str) -> bool:
        """
        删除任务及其 checkpoint。

        Args:
            task_id: 任务 ID。

        Returns:
            是否删除成功。
        """
        try:
            deleted = self.checkpoints.delete_task(task_id)
            if deleted:
                logger.info("已删除任务 checkpoint: %s", task_id)
            return deleted
        except Exception as exc:
            logger.warning("删除任务失败 %s: %s", task_id, exc)
            return False
