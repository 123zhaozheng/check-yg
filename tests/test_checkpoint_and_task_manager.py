# -*- coding: utf-8 -*-

import tempfile
import unittest
from pathlib import Path

from src.core.checkpoint_manager import CheckpointManager
from src.core.task_manager import TaskManager


class CheckpointAndTaskManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self._tmpdir.name) / "checkpoints"
        self.checkpoints = CheckpointManager(self.base_dir)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_doc_hash_uses_document_path(self) -> None:
        task_id = "task_hash"
        self.checkpoints.start_task(task_id, ["a/流水.xlsx", "b/流水.xlsx"])

        state_a = {
            "document_name": "流水.xlsx",
            "document_path": "a/流水.xlsx",
            "status": "stage1_done",
            "flow_tables": [],
        }
        state_b = {
            "document_name": "流水.xlsx",
            "document_path": "b/流水.xlsx",
            "status": "stage1_done",
            "flow_tables": [],
        }
        self.checkpoints.save_document_state(
            task_id, "流水.xlsx", state_a, document_path="a/流水.xlsx"
        )
        self.checkpoints.save_document_state(
            task_id, "流水.xlsx", state_b, document_path="b/流水.xlsx"
        )

        loaded_a = self.checkpoints.load_document_state(
            task_id, "流水.xlsx", document_path="a/流水.xlsx"
        )
        loaded_b = self.checkpoints.load_document_state(
            task_id, "流水.xlsx", document_path="b/流水.xlsx"
        )
        self.assertIsNotNone(loaded_a)
        self.assertIsNotNone(loaded_b)
        self.assertEqual("a/流水.xlsx", loaded_a.get("document_path"))
        self.assertEqual("b/流水.xlsx", loaded_b.get("document_path"))
        self.assertEqual(2, len(self.checkpoints.list_document_states(task_id)))

    def test_task_summary_and_delete(self) -> None:
        task_id = "task_summary"
        self.checkpoints.start_task(task_id, ["doc1", "doc2"])
        self.checkpoints.save_document_state(
            task_id,
            "doc1",
            {"document_name": "doc1", "status": "completed", "total_flow_rows": 2},
        )
        self.checkpoints.save_document_state(
            task_id,
            "doc2",
            {"document_name": "doc2", "status": "stage2_running", "processed_rows": 1},
        )

        all_tasks = self.checkpoints.list_all_tasks()
        self.assertIn(task_id, all_tasks)

        summary = self.checkpoints.get_task_summary(task_id)
        self.assertIsNotNone(summary)
        self.assertEqual("normalizing", summary.get("status"))
        self.assertEqual(2, summary.get("total_documents"))
        self.assertEqual(1, summary.get("completed_documents"))

        self.assertTrue(self.checkpoints.delete_task(task_id))
        self.assertFalse(self.checkpoints.delete_task(task_id))

    def test_task_manager_resume(self) -> None:
        task_id = "task_resume"
        self.checkpoints.start_task(task_id, ["doc1", "doc2"])
        self.checkpoints.save_document_state(
            task_id,
            "doc1",
            {
                "document_name": "doc1",
                "document_path": "a/doc1.xlsx",
                "status": "stage2_running",
                "processed_rows": 10,
                "total_flow_rows": 30,
            },
            document_path="a/doc1.xlsx",
        )
        self.checkpoints.save_document_state(
            task_id,
            "doc2",
            {"document_name": "doc2", "status": "completed", "total_flow_rows": 12},
        )

        manager = TaskManager(checkpoint_dir=self.base_dir)
        tasks = manager.list_tasks()
        self.assertEqual(1, len(tasks))

        detail = manager.get_task_detail(task_id)
        self.assertIsNotNone(detail)
        self.assertEqual(task_id, detail.get("task_id"))

        resume_info = manager.resume_task(task_id)
        self.assertIsNotNone(resume_info)
        self.assertTrue(resume_info.get("can_resume"))
        self.assertEqual(1, resume_info.get("resumable_count"))

        self.assertTrue(manager.delete_task(task_id))

    def test_start_task_persists_title_and_document_folder(self) -> None:
        task_id = "task_with_title"
        self.checkpoints.start_task(
            task_id,
            ["doc1.xlsx"],
            title="2026年度审计",
            document_folder="C:/data/docs",
        )

        meta = self.checkpoints.load_task(task_id)
        self.assertIsNotNone(meta)
        self.assertEqual("2026年度审计", meta.get("title"))
        self.assertEqual("C:/data/docs", meta.get("document_folder"))
        self.assertEqual("pending", meta.get("status"))

        summary = self.checkpoints.get_task_summary(task_id)
        self.assertIsNotNone(summary)
        self.assertEqual("2026年度审计", summary.get("title"))
        self.assertEqual("C:/data/docs", summary.get("document_folder"))

    def test_update_task_status_and_list_with_titles(self) -> None:
        task_id = "task_status_update"
        self.checkpoints.start_task(task_id, ["doc1"], title="状态测试", document_folder="D:/docs")
        self.assertTrue(self.checkpoints.update_task_status(task_id, "extracting"))
        self.assertTrue(self.checkpoints.update_task_status(task_id, "normalizing"))
        self.assertFalse(self.checkpoints.update_task_status(task_id, "invalid-status"))

        summary = self.checkpoints.get_task_summary(task_id)
        self.assertIsNotNone(summary)
        self.assertEqual("normalizing", summary.get("status"))

        tasks = self.checkpoints.get_all_tasks_with_titles()
        self.assertTrue(any(item.get("title") == "状态测试" for item in tasks))

    def test_task_manager_create_task_and_title_unique(self) -> None:
        manager = TaskManager(checkpoint_dir=self.base_dir)
        task_id = manager.create_task("唯一标题任务", "E:/audit/docs")
        self.assertTrue(task_id)
        self.assertTrue(manager.title_exists("唯一标题任务"))

        detail = manager.get_task_detail(task_id)
        self.assertIsNotNone(detail)
        self.assertEqual("唯一标题任务", detail.get("meta", {}).get("title"))
        self.assertEqual("E:/audit/docs", detail.get("meta", {}).get("document_folder"))
        self.assertEqual("pending", detail.get("summary", {}).get("status"))

        with self.assertRaises(ValueError):
            manager.create_task("唯一标题任务", "E:/audit/docs")


if __name__ == "__main__":
    unittest.main()
