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
    TASK_STATUSES = {
        "pending",
        "extracting",
        "normalizing",
        "completed",
        "canceled",
        "failed",
    }

    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _task_dir(self, task_id: str, create: bool = True) -> Path:
        task_dir = self.base_dir / task_id
        if create:
            task_dir.mkdir(parents=True, exist_ok=True)
        return task_dir

    @staticmethod
    def _doc_hash(document_name: str, document_path: Optional[str] = None) -> str:
        doc_id = str(document_name or "")
        if document_path:
            normalized_path = Path(str(document_path)).as_posix()
            doc_id = f"{doc_id}|{normalized_path}"
        return hashlib.md5(doc_id.encode("utf-8")).hexdigest()[:16]

    def _doc_path(
        self,
        task_id: str,
        document_name: str,
        document_path: Optional[str] = None,
        create_task_dir: bool = True
    ) -> Path:
        task_dir = self._task_dir(task_id, create=create_task_dir)
        return task_dir / f"doc_{self._doc_hash(document_name, document_path)}.json"

    def _task_meta_path(self, task_id: str, create_task_dir: bool = True) -> Path:
        return self._task_dir(task_id, create=create_task_dir) / "task.json"

    def _normalize_document_folder(self, folder) -> List[str]:
        """将 document_folder 统一为 List[str]，兼容旧数据中字符串格式。"""
        if isinstance(folder, list):
            return [str(f) for f in folder if str(f).strip()]
        folder_str = str(folder or "").strip()
        return [folder_str] if folder_str else []

    def start_task(
        self,
        task_id: str,
        documents: List[str],
        title: Optional[str] = None,
        document_folder: Optional[str] = None
    ) -> None:
        meta_path = self._task_meta_path(task_id)
        now = datetime.now().isoformat()
        normalized_title = str(title or "").strip() or task_id
        normalized_folder = str(document_folder or "").strip()
        folder_list = [normalized_folder] if normalized_folder else []
        incoming_documents = [str(item) for item in documents or []]
        if meta_path.exists():
            data = self._read_json(meta_path) or {}
            changed = False
            if data.get("task_id") != task_id:
                data["task_id"] = task_id
                changed = True
            if not str(data.get("title", "")).strip():
                data["title"] = normalized_title
                changed = True
            existing_folders = self._normalize_document_folder(data.get("document_folder"))
            if "document_folder" not in data:
                data["document_folder"] = []
                changed = True
            elif not existing_folders and folder_list:
                data["document_folder"] = folder_list
                changed = True
            elif existing_folders != self._normalize_document_folder(data.get("document_folder")):
                data["document_folder"] = existing_folders
                changed = True
            if normalized_folder and normalized_folder not in existing_folders:
                existing_folders.append(normalized_folder)
                data["document_folder"] = existing_folders
                changed = True
            if "status" not in data:
                data["status"] = "pending"
                changed = True
            existing_documents = [str(item) for item in (data.get("documents", []) or [])]
            if incoming_documents and incoming_documents != existing_documents:
                data["documents"] = incoming_documents
                changed = True
            if changed:
                data["updated_at"] = now
                self._write_json(meta_path, data)
            return
        data = {
            "task_id": task_id,
            "title": normalized_title,
            "status": "pending",
            "created_at": now,
            "updated_at": now,
            "document_folder": folder_list,
            "documents": incoming_documents,
        }
        self._write_json(meta_path, data)

    def load_task(self, task_id: str) -> Optional[Dict]:
        meta_path = self._task_meta_path(task_id, create_task_dir=False)
        if not meta_path.exists():
            return None
        data = self._read_json(meta_path)
        if not data:
            return None
        data.setdefault("task_id", task_id)
        data.setdefault("title", task_id)
        data.setdefault("status", "pending")
        data.setdefault("documents", [])
        data.setdefault("created_at", "")
        data.setdefault("updated_at", data.get("created_at", ""))
        # Backward compat: string document_folder → list
        data["document_folder"] = self._normalize_document_folder(data.get("document_folder"))
        return data

    def update_task_status(self, task_id: str, status: str) -> bool:
        """更新任务整体状态并持久化到 task.json。"""
        normalized_status = str(status or "").strip().lower()
        if normalized_status not in self.TASK_STATUSES:
            logger.warning("Invalid task status %s for task %s", status, task_id)
            return False

        meta = self.load_task(task_id) or {
            "task_id": task_id,
            "title": task_id,
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "updated_at": "",
            "document_folder": [],
            "documents": [],
        }
        meta["status"] = normalized_status
        meta["updated_at"] = datetime.now().isoformat()
        self._write_json(self._task_meta_path(task_id), meta)
        return True

    def save_document_state(
        self,
        task_id: str,
        document_name: str,
        state: Dict,
        document_path: Optional[str] = None
    ) -> None:
        state = dict(state)
        state.setdefault("document_name", document_name)
        state["updated_at"] = datetime.now().isoformat()
        final_doc_path = document_path or state.get("document_path")
        self._write_json(self._doc_path(task_id, document_name, final_doc_path), state)

    def load_document_state(
        self,
        task_id: str,
        document_name: str,
        document_path: Optional[str] = None
    ) -> Optional[Dict]:
        doc_path = self._doc_path(
            task_id,
            document_name,
            document_path=document_path,
            create_task_dir=False
        )
        if not doc_path.exists():
            if document_path:
                legacy_path = self._doc_path(
                    task_id,
                    document_name,
                    document_path=None,
                    create_task_dir=False
                )
                if not legacy_path.exists():
                    return None
                return self._read_json(legacy_path)
            return None
        return self._read_json(doc_path)

    def list_document_states(self, task_id: str) -> List[Dict]:
        task_dir = self._task_dir(task_id, create=False)
        if not task_dir.exists():
            return []
        results: List[Dict] = []
        for doc_file in task_dir.glob("doc_*.json"):
            data = self._read_json(doc_file)
            if data:
                results.append(data)
        return results

    def clear_task(self, task_id: str) -> None:
        task_dir = self._task_dir(task_id, create=False)
        if not task_dir.exists():
            return
        for file_path in task_dir.glob("*"):
            try:
                file_path.unlink()
            except Exception as exc:
                logger.warning("Failed to delete checkpoint %s: %s", file_path, exc)
        try:
            task_dir.rmdir()
        except Exception:
            pass

    def clear_document_states(self, task_id: str) -> None:
        """清理任务的文档断点文件，但保留 task.json 任务元数据。"""
        task_dir = self._task_dir(task_id, create=False)
        if not task_dir.exists():
            return

        for file_path in task_dir.glob("doc_*.json"):
            try:
                file_path.unlink()
            except Exception as exc:
                logger.warning("Failed to delete checkpoint %s: %s", file_path, exc)

    def list_all_tasks(self) -> List[str]:
        """列出所有任务 ID。"""
        if not self.base_dir.exists():
            return []
        task_ids: List[str] = []
        for item in self.base_dir.iterdir():
            if item.is_dir():
                task_ids.append(item.name)
        return sorted(task_ids)

    def get_task_summary(self, task_id: str) -> Optional[Dict]:
        """获取任务摘要信息。"""
        task_dir = self._task_dir(task_id, create=False)
        if not task_dir.exists():
            return None

        task_meta = self.load_task(task_id) or {}
        states = self.list_document_states(task_id)
        documents = task_meta.get("documents", []) or []
        total_documents = len(documents) if documents else len(states)
        processed_documents = 0
        completed_documents = 0
        failed_documents = 0
        canceled_documents = 0
        resumable_documents = 0
        status_counts: Dict[str, int] = {}
        updated_at = str(task_meta.get("updated_at", "") or task_meta.get("created_at", ""))

        for state in states:
            doc_status = str(state.get("status", "unknown"))
            status_counts[doc_status] = status_counts.get(doc_status, 0) + 1
            if doc_status in (
                "stage1_done",
                "stage2_running",
                "extracting",
                "normalizing",
                "completed",
                "failed",
                "canceled",
            ):
                processed_documents += 1
            if doc_status == "completed":
                completed_documents += 1
            if doc_status == "failed":
                failed_documents += 1
            if doc_status == "canceled":
                canceled_documents += 1
            if doc_status in ("stage1_done", "stage2_running", "normalizing", "canceled"):
                resumable_documents += 1
            state_updated_at = str(state.get("updated_at", "") or "")
            if state_updated_at and state_updated_at > updated_at:
                updated_at = state_updated_at

        inferred_status = "pending"
        if total_documents > 0 and completed_documents >= total_documents:
            inferred_status = "completed"
        elif failed_documents > 0:
            inferred_status = "failed"
        elif canceled_documents > 0:
            inferred_status = "canceled"
        elif status_counts.get("normalizing", 0) > 0 or status_counts.get("stage2_running", 0) > 0:
            inferred_status = "normalizing"
        elif status_counts.get("extracting", 0) > 0 or status_counts.get("stage1_done", 0) > 0:
            inferred_status = "extracting"
        elif states:
            inferred_status = "extracting"

        status = str(task_meta.get("status", "") or "").strip().lower()
        if status not in self.TASK_STATUSES:
            status = inferred_status
        elif status in ("completed", "failed", "canceled"):
            pass
        elif inferred_status in ("completed", "failed", "canceled"):
            status = inferred_status
        elif status == "pending" and inferred_status != "pending":
            status = inferred_status

        return {
            "task_id": task_id,
            "status": status,
            "title": str(task_meta.get("title", "") or task_id),
            "document_folder": self._normalize_document_folder(task_meta.get("document_folder")),
            "created_at": task_meta.get("created_at", ""),
            "updated_at": updated_at,
            "total_documents": total_documents,
            "processed_documents": processed_documents,
            "completed_documents": completed_documents,
            "failed_documents": failed_documents,
            "canceled_documents": canceled_documents,
            "resumable_documents": resumable_documents,
            "status_counts": status_counts,
        }

    def get_all_tasks_with_titles(self) -> List[Dict]:
        """返回所有任务摘要（包含标题信息）。"""
        tasks: List[Dict] = []
        for task_id in self.list_all_tasks():
            summary = self.get_task_summary(task_id)
            if summary:
                tasks.append(summary)
        tasks.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
        return tasks

    def append_documents(
        self,
        task_id: str,
        new_folder: str,
        new_documents: List[str]
    ) -> None:
        """追加新文件夹和新文档到已有任务，状态更新为 extracting。

        - 将 new_folder 追加到 document_folder 列表（去重）
        - 将 new_documents 追加到 documents 列表（按路径去重跳过已有文档）
        - 为新文档创建断点文件（status=pending）
        - 任务状态更新为 extracting
        """
        meta = self.load_task(task_id)
        if not meta:
            logger.warning("append_documents: 任务 %s 不存在", task_id)
            return

        existing_folders: List[str] = list(meta.get("document_folder", []) or [])
        existing_docs: List[str] = [str(d) for d in (meta.get("documents", []) or [])]
        existing_doc_set = set(existing_docs)

        normalized_folder = str(new_folder or "").strip()
        if normalized_folder and normalized_folder not in existing_folders:
            existing_folders.append(normalized_folder)

        truly_new_docs = [
            str(d) for d in (new_documents or [])
            if str(d) not in existing_doc_set
        ]
        all_docs = existing_docs + truly_new_docs

        meta["document_folder"] = existing_folders
        meta["documents"] = all_docs
        meta["status"] = "extracting"
        meta["updated_at"] = datetime.now().isoformat()
        self._write_json(self._task_meta_path(task_id), meta)

        # 为新文档创建断点文件
        for doc_path_str in truly_new_docs:
            doc_name = Path(doc_path_str).name
            self.save_document_state(
                task_id,
                doc_name,
                {
                    "document_name": doc_name,
                    "document_path": doc_path_str,
                    "status": "pending",
                    "flow_tables": [],
                    "total_tables": 0,
                    "flow_tables_count": 0,
                    "total_flow_rows": 0,
                    "errors": []
                },
                document_path=doc_path_str
            )

    def delete_task(self, task_id: str) -> bool:
        """删除任务目录及所有 checkpoint 文件。"""
        task_dir = self._task_dir(task_id, create=False)
        if not task_dir.exists():
            return False
        self.clear_task(task_id)
        return True

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
