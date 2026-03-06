# -*- coding: utf-8 -*-

import json
import sys
import types
import unittest

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

from src.core.extraction_result import ExtractionResult
from src.parsers.base import FlowRecord


class ExtractionResultTests(unittest.TestCase):
    def test_to_dict_is_json_serializable(self) -> None:
        result = ExtractionResult(
            task_id="task_001",
            task_time="2026-03-05T10:00:00",
            document_folder="C:/docs",
            total_documents=1,
            processed_documents=1,
            total_tables=1,
            flow_tables=1,
            total_records=1,
            flow_records=[
                FlowRecord(
                    source_file="a.xlsx",
                    original_row=2,
                    transaction_time="2026-03-05",
                    counterparty_name="李四",
                    counterparty_account="6222",
                    amount="100",
                    summary="摘要",
                    transaction_type="收入",
                )
            ],
            errors=[{"stage": "x", "error": ValueError("bad")}],
        )

        data = result.to_dict()
        encoded = json.dumps(data, ensure_ascii=False)
        self.assertTrue(encoded)
        self.assertEqual("task_001", data.get("task_id"))
        self.assertIsInstance(data.get("errors")[0].get("error"), str)
        self.assertIn("flow_records", data)


if __name__ == "__main__":
    unittest.main()
