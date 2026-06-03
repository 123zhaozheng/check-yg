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

from src.parsers.pdf_parser import MinerUClient, PDFDecryptor, PDFParser, PublicMinerUClient


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


class ExtractPasswordFromFilenameTests(unittest.TestCase):
    """测试 PDFDecryptor.extract_password_from_filename 括号提取规则"""

    def test_half_width_brackets(self) -> None:
        """半角括号"""
        self.assertEqual(PDFDecryptor.extract_password_from_filename("文件名(123456).pdf"), "123456")

    def test_full_width_brackets(self) -> None:
        """全角括号"""
        self.assertEqual(PDFDecryptor.extract_password_from_filename("文件名（123456）.pdf"), "123456")

    def test_multiple_brackets_take_last(self) -> None:
        """多括号取最后一个"""
        self.assertEqual(PDFDecryptor.extract_password_from_filename("文件(注释)(123456).pdf"), "123456")

    def test_mixed_brackets_multiple(self) -> None:
        """全角半角混合多括号"""
        self.assertEqual(PDFDecryptor.extract_password_from_filename("文件(注释)（123456）.pdf"), "123456")

    def test_mixed_bracket_pair(self) -> None:
        """混配括号（左半角右全角）"""
        self.assertEqual(PDFDecryptor.extract_password_from_filename("文件名(密码）.pdf"), "密码")

    def test_no_brackets(self) -> None:
        """无括号返回 None"""
        self.assertIsNone(PDFDecryptor.extract_password_from_filename("文件名.pdf"))

    def test_empty_brackets(self) -> None:
        """空括号返回 None"""
        self.assertIsNone(PDFDecryptor.extract_password_from_filename("文件().pdf"))

    def test_whitespace_stripped(self) -> None:
        """括号内空白被 strip"""
        self.assertEqual(PDFDecryptor.extract_password_from_filename("文件(  123  ).pdf"), "123")

    def test_old_format_no_brackets(self) -> None:
        """旧格式（开头数字无括号）不兼容，返回 None"""
        self.assertIsNone(PDFDecryptor.extract_password_from_filename("123456大丰xxx.pdf"))


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
