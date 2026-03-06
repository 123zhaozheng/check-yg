# -*- coding: utf-8 -*-

import tempfile
import unittest
import sys
import types
from pathlib import Path
from unittest.mock import patch

sys.modules.setdefault("pikepdf", types.ModuleType("pikepdf"))
if "bs4" not in sys.modules:
    bs4_stub = types.ModuleType("bs4")

    class _DummySoup:
        def __init__(self, *args, **kwargs):
            pass

        def find_all(self, *args, **kwargs):
            return []

    bs4_stub.BeautifulSoup = _DummySoup
    sys.modules["bs4"] = bs4_stub
if "docx" not in sys.modules:
    docx_stub = types.ModuleType("docx")

    def _dummy_document(*args, **kwargs):
        class _DummyDoc:
            paragraphs = []
            tables = []
        return _DummyDoc()

    docx_stub.Document = _dummy_document
    docx_table_stub = types.ModuleType("docx.table")

    class _DummyTable:
        rows = []

    docx_table_stub.Table = _DummyTable
    docx_stub.table = docx_table_stub
    sys.modules["docx"] = docx_stub
    sys.modules["docx.table"] = docx_table_stub

from src.core.checkpoint_manager import CheckpointManager
from src.core.extraction_result import ExtractionResult
from src.core.flow_extractor_v2 import FlowExtractorV2
from src.core.reviewer import Reviewer


class _DummyConfig:
    def __init__(self, base_dir: Path, keep_checkpoint: bool = False):
        self.config_dir = base_dir
        self.reports_folder = base_dir / "reports"
        self.mineru_url = "http://localhost:8000"
        self.mineru_timeout = 5
        self.llm_url = "http://localhost:8000/v1"
        self.llm_model = "test-model"
        self.llm_api_key = "test-key"
        self.llm_timeout = 5
        self.flow_preview_rows = 3
        self.flow_confidence_threshold = 70
        self.flow_parallelism = 1
        self.flow_checkpoint_interval = 1
        self.flow_keep_checkpoint_on_success = keep_checkpoint
        self.fuzzy_threshold = 60
        self.enable_exact_match = True
        self.enable_desensitized_match = True
        self.enable_fuzzy_match = False


class _SpyCheckpointManager(CheckpointManager):
    def __init__(self, base_dir: Path):
        super().__init__(base_dir)
        self.clear_called = False

    def clear_task(self, task_id: str) -> None:
        self.clear_called = True
        super().clear_task(task_id)


class _ResumeNormalizer:
    def __init__(self):
        self.called_row_indexes = []

    def is_available(self) -> bool:
        return True

    def normalize_rows(self, document_name, header_attributes, rows, source_file):
        self.called_row_indexes.extend([int(row["row_index"]) for row in rows])
        normalized = []
        for row in rows:
            normalized.append({
                "is_valid": True,
                "source_file": source_file,
                "row_index": int(row["row_index"]),
                "transaction_time": "",
                "counterparty_name": "A",
                "counterparty_account": "B",
                "amount": "1",
                "summary": "",
                "transaction_type": "",
            })
        return normalized


class _CancelAfterFirstNormalizer:
    def __init__(self, extractor: FlowExtractorV2):
        self.extractor = extractor
        self.called = 0

    def is_available(self) -> bool:
        return True

    def normalize_rows(self, document_name, header_attributes, rows, source_file):
        self.called += 1
        if self.called == 1:
            self.extractor.request_cancel()
        normalized = []
        for row in rows:
            normalized.append({
                "is_valid": True,
                "source_file": source_file,
                "row_index": int(row["row_index"]),
                "transaction_time": "",
                "counterparty_name": "A",
                "counterparty_account": "B",
                "amount": "1",
                "summary": "",
                "transaction_type": "",
            })
        return normalized


class _AlwaysAvailable:
    def is_available(self) -> bool:
        return True


class _EmptyScanner:
    def scan_directory(self, document_folder):
        return []


class FlowExtractorV2AndReviewerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self._tmpdir.name)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_stage2_resume_from_processed_rows(self) -> None:
        config = _DummyConfig(self.base_dir)
        extractor = FlowExtractorV2(config=config)
        extractor.checkpoints = CheckpointManager(config.config_dir / "checkpoints")
        normalizer = _ResumeNormalizer()
        extractor.data_normalizer = normalizer
        extractor._stage1_total_docs = 0

        task_id = "resume_task"
        doc_path = str(self.base_dir / "docs" / "流水.xlsx")
        extractor.checkpoints.start_task(task_id, [doc_path])
        extractor.checkpoints.save_document_state(
            task_id,
            "流水.xlsx",
            {
                "document_name": "流水.xlsx",
                "document_path": doc_path,
                "status": "stage2_running",
                "header_attributes": ["列1"],
                "flow_tables": [
                    {
                        "table_index": 0,
                        "data_start_row": 0,
                        "rows": [["r1"], ["r2"], ["r3"], ["r4"], ["r5"]],
                    }
                ],
                "total_flow_rows": 5,
                "processed_rows": 2,
                "records": [
                    {
                        "source_file": "流水.xlsx",
                        "original_row": 1,
                        "transaction_time": "",
                        "counterparty_name": "A",
                        "counterparty_account": "B",
                        "amount": "1",
                        "summary": "",
                        "transaction_type": "",
                    },
                    {
                        "source_file": "流水.xlsx",
                        "original_row": 2,
                        "transaction_time": "",
                        "counterparty_name": "A",
                        "counterparty_account": "B",
                        "amount": "1",
                        "summary": "",
                        "transaction_type": "",
                    },
                ],
            },
            document_path=doc_path,
        )

        result = ExtractionResult(
            task_id=task_id,
            task_time="2026-03-05T10:00:00",
            document_folder=str(self.base_dir),
            total_documents=1,
            processed_documents=1,
            total_tables=1,
            flow_tables=1,
            total_records=0,
        )
        records = extractor._process_documents_stage2(
            [doc_path], task_id, batch_size=1, workers=1, result=result, total_rows=5
        )

        self.assertEqual([3, 4, 5], normalizer.called_row_indexes)
        self.assertEqual(5, len(records))
        saved_state = extractor.checkpoints.load_document_state(
            task_id, "流水.xlsx", document_path=doc_path
        )
        self.assertEqual("completed", saved_state.get("status"))
        self.assertEqual(5, int(saved_state.get("processed_rows", 0)))

    def test_stage2_cancel_saves_canceled_status(self) -> None:
        config = _DummyConfig(self.base_dir)
        extractor = FlowExtractorV2(config=config)
        extractor.checkpoints = CheckpointManager(config.config_dir / "checkpoints")
        extractor.data_normalizer = _CancelAfterFirstNormalizer(extractor)
        extractor._stage1_total_docs = 0

        task_id = "cancel_task"
        doc_path = str(self.base_dir / "docs" / "流水.xlsx")
        extractor.checkpoints.start_task(task_id, [doc_path])
        extractor.checkpoints.save_document_state(
            task_id,
            "流水.xlsx",
            {
                "document_name": "流水.xlsx",
                "document_path": doc_path,
                "status": "stage1_done",
                "header_attributes": ["列1"],
                "flow_tables": [{"table_index": 0, "data_start_row": 0, "rows": [["a"], ["b"], ["c"]]}],
                "total_flow_rows": 3,
            },
            document_path=doc_path,
        )

        result = ExtractionResult(
            task_id=task_id,
            task_time="2026-03-05T10:00:00",
            document_folder=str(self.base_dir),
            total_documents=1,
            processed_documents=1,
            total_tables=1,
            flow_tables=1,
            total_records=0,
        )
        records = extractor._process_documents_stage2(
            [doc_path], task_id, batch_size=1, workers=1, result=result, total_rows=3
        )

        self.assertEqual(1, len(records))
        saved_state = extractor.checkpoints.load_document_state(
            task_id, "流水.xlsx", document_path=doc_path
        )
        self.assertEqual("canceled", saved_state.get("status"))
        self.assertEqual(1, int(saved_state.get("processed_rows", 0)))
        self.assertEqual(1, len(saved_state.get("records", [])))

    def test_keep_checkpoint_config_controls_clear(self) -> None:
        keep_config = _DummyConfig(self.base_dir / "keep", keep_checkpoint=True)
        keep_extractor = FlowExtractorV2(config=keep_config)
        keep_extractor.table_classifier = _AlwaysAvailable()
        keep_extractor.data_normalizer = _AlwaysAvailable()
        keep_extractor.scanner = _EmptyScanner()
        keep_checkpoints = _SpyCheckpointManager(keep_config.config_dir / "checkpoints")
        keep_extractor.checkpoints = keep_checkpoints
        keep_extractor.extract_flows(document_folder=str(self.base_dir), task_id="keep_task")
        self.assertFalse(keep_checkpoints.clear_called)

        clear_config = _DummyConfig(self.base_dir / "clear", keep_checkpoint=False)
        clear_extractor = FlowExtractorV2(config=clear_config)
        clear_extractor.table_classifier = _AlwaysAvailable()
        clear_extractor.data_normalizer = _AlwaysAvailable()
        clear_extractor.scanner = _EmptyScanner()
        clear_checkpoints = _SpyCheckpointManager(clear_config.config_dir / "checkpoints")
        clear_extractor.checkpoints = clear_checkpoints
        clear_extractor.extract_flows(document_folder=str(self.base_dir), task_id="clear_task")
        self.assertTrue(clear_checkpoints.clear_called)

    def test_reviewer_saves_history_after_run(self) -> None:
        config = _DummyConfig(self.base_dir)
        reviewer = Reviewer(config=config)
        with patch.object(reviewer, "load_flows", return_value=[]), \
                patch.object(reviewer, "_write_back_results", return_value=None), \
                patch.object(reviewer.review_history, "save_review_result", return_value=None) as save_mock:
            result = reviewer.run_review("flow.xlsx", customers=["张三"])
            self.assertIsNotNone(result.review_id)
            self.assertTrue(save_mock.called)


if __name__ == "__main__":
    unittest.main()
