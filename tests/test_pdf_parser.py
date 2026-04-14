# -*- coding: utf-8 -*-

import tempfile
import unittest
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

if "pikepdf" not in sys.modules:
    pikepdf_stub = types.ModuleType("pikepdf")

    class _DummyPasswordError(Exception):
        pass

    def _dummy_open(*args, **kwargs):
        class _DummyPdf:
            def close(self):
                return None

            def save(self, *save_args, **save_kwargs):
                return None

        return _DummyPdf()

    pikepdf_stub.PasswordError = _DummyPasswordError
    pikepdf_stub.open = _dummy_open
    sys.modules["pikepdf"] = pikepdf_stub

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

from src.parsers.pdf_parser import MinerUClient, PDFParser, PublicMinerUClient


class _FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._json_data


class PDFParserTests(unittest.TestCase):
    def test_pdf_parser_selects_client_by_mode(self) -> None:
        local_parser = PDFParser()
        public_parser = PDFParser(mineru_mode="public")

        self.assertIsInstance(local_parser.client, MinerUClient)
        self.assertIsInstance(public_parser.client, PublicMinerUClient)

    def test_public_client_upload_poll_and_download_markdown(self) -> None:
        client = PublicMinerUClient(
            base_url="https://mineru.net/api/v1/agent",
            timeout=5,
            max_retries=1,
            poll_interval=0,
        )

        client.session.request = MagicMock(side_effect=[
            _FakeResponse(json_data={
                "code": 0,
                "data": {
                    "task_id": "task-1",
                    "file_url": "https://upload.example.com/file.pdf?sign=1",
                },
            }),
            _FakeResponse(status_code=200),
            _FakeResponse(json_data={"code": 0, "data": {"task_id": "task-1", "state": "waiting-file"}}),
            _FakeResponse(json_data={"code": 0, "data": {"task_id": "task-1", "state": "running"}}),
            _FakeResponse(json_data={
                "code": 0,
                "data": {
                    "task_id": "task-1",
                    "state": "done",
                    "markdown_url": "https://cdn.example.com/full.md",
                },
            }),
            _FakeResponse(text="# Title\n\n|A|\n|---|\n|1|"),
        ])

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "demo.pdf"
            file_path.write_bytes(b"%PDF-1.4 test")

            markdown = client.get_markdown(file_path)

        self.assertIn("|A|", markdown)
        methods = [call.args[0] for call in client.session.request.call_args_list]
        self.assertEqual(["POST", "PUT", "GET", "GET", "GET", "GET"], methods)

    def test_public_client_raises_on_failed_task(self) -> None:
        client = PublicMinerUClient(
            base_url="https://mineru.net/api/v1/agent",
            timeout=5,
            max_retries=1,
            poll_interval=0,
        )

        client.session.request = MagicMock(side_effect=[
            _FakeResponse(json_data={
                "code": 0,
                "data": {
                    "task_id": "task-2",
                    "file_url": "https://upload.example.com/file.pdf?sign=2",
                },
            }),
            _FakeResponse(status_code=200),
            _FakeResponse(json_data={
                "code": 0,
                "data": {
                    "task_id": "task-2",
                    "state": "failed",
                    "err_msg": "file page count exceeds lightweight API limit",
                },
            }),
        ])

        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "demo.pdf"
            file_path.write_bytes(b"%PDF-1.4 test")

            with self.assertRaisesRegex(RuntimeError, "lightweight API limit"):
                client.get_markdown(file_path)


if __name__ == "__main__":
    unittest.main()
