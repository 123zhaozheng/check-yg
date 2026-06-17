# -*- coding: utf-8 -*-
"""MinerU PDF parser parity tests.

Covers MinerU client selection, markdown-to-table extraction, non-table context
stripping, encrypted-PDF fallback, and runtime settings wiring — without making
real network calls.
"""

from pathlib import Path

import pytest

from app.parsers import HTMLTableParser, PDFParser
from app.parsers.pdf_parser import MinerUClient, PublicMinerUClient, PDFDecryptor


# ---------------------------------------------------------------------------
# Client selection
# ---------------------------------------------------------------------------


def test_default_parser_uses_local_mineru_client():
    parser = PDFParser()

    assert parser.mineru_mode == "local"
    assert isinstance(parser.client, MinerUClient)


def test_public_mode_uses_public_mineru_client():
    parser = PDFParser(mineru_mode="public", mineru_public_api_key="secret-key")

    assert parser.mineru_mode == "public"
    assert isinstance(parser.client, PublicMinerUClient)
    assert parser.client.api_key == "secret-key"


def test_public_url_and_api_key_propagated_to_public_client():
    parser = PDFParser(
        mineru_mode="public",
        mineru_public_url="https://example.net/api/v1/agent",
        mineru_public_api_key="k",
    )

    assert parser.client.base_url == "https://example.net/api/v1/agent"
    assert parser.client.session.headers["Authorization"] == "Bearer k"


def test_local_url_propagated_to_local_client():
    parser = PDFParser(mineru_mode="local", mineru_url="http://mineru-host:9000")

    assert parser.client.base_url == "http://mineru-host:9000"


def test_timeout_propagated_to_client():
    parser = PDFParser(timeout=120)

    assert parser.client.timeout == 120


# ---------------------------------------------------------------------------
# Markdown -> raw tables (HTMLTableParser)
# ---------------------------------------------------------------------------


def test_html_parser_extracts_tables_from_markdown():
    html = """
    <p>账户说明文字</p>
    <table>
      <tr><th>交易时间</th><th>金额</th></tr>
      <tr><td>2024-01-01</td><td>100.00</td></tr>
      <tr><td>2024-01-02</td><td>-50.00</td></tr>
    </table>
    <table></table>
    """
    parser = HTMLTableParser()
    tables = parser.extract_raw_tables_from_html(html)

    # 第二个表没有 <tr>，无行，应被过滤
    assert len(tables) == 1
    table = tables[0]
    assert table.table_index == 0
    assert table.rows[0] == ["交易时间", "金额"]
    assert table.rows[1] == ["2024-01-01", "100.00"]
    assert "<table" in table.html_content


def test_html_parser_handles_empty_content():
    parser = HTMLTableParser()

    assert parser.extract_raw_tables_from_html("") == []
    assert parser.extract_raw_tables_from_html("<p>no tables here</p>") == []


def test_extract_raw_tables_uses_mineru_markdown(tmp_path, monkeypatch):
    pdf_path = tmp_path / "statement.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 not a real pdf")

    markdown = """
    <table><tr><th>日期</th><th>金额</th></tr><tr><td>2024-03</td><td>200</td></tr></table>
    """

    parser = PDFParser()
    monkeypatch.setattr(parser.client, "get_markdown", lambda path: markdown)
    # PDF is not really encrypted; ensure decryptor reports False so we skip that path.
    monkeypatch.setattr(PDFDecryptor, "is_encrypted", staticmethod(lambda path: False))

    tables = parser.extract_raw_tables(pdf_path)

    assert len(tables) == 1
    assert tables[0].rows[0] == ["日期", "金额"]


# ---------------------------------------------------------------------------
# Non-table context stripping
# ---------------------------------------------------------------------------


def test_extract_non_table_context_strips_tables_and_truncates(tmp_path, monkeypatch):
    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    markdown = (
        "账户名称：测试账户\n开户行：某银行\n\n"
        "<table><tr><td>a</td></tr><tr><td>b</td></tr></table>\n\n"
        "说明文字" + "x" * 5000
    )

    parser = PDFParser()
    monkeypatch.setattr(parser.client, "get_markdown", lambda path: markdown)
    monkeypatch.setattr(PDFDecryptor, "is_encrypted", staticmethod(lambda path: False))

    context = parser.extract_non_table_context(pdf_path, max_chars=100)

    assert "<table" not in context
    assert "测试账户" in context
    assert len(context) <= 100


def test_extract_non_table_context_returns_empty_on_failure(tmp_path, monkeypatch):
    pdf_path = tmp_path / "bad.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    def raise_error(path):
        raise RuntimeError("mineru down")

    parser = PDFParser()
    monkeypatch.setattr(parser.client, "get_markdown", raise_error)

    assert parser.extract_non_table_context(pdf_path) == ""
    # raw-table extraction also swallows the failure and returns []
    assert parser.extract_raw_tables(pdf_path) == []


# ---------------------------------------------------------------------------
# Encrypted PDF fallback
# ---------------------------------------------------------------------------


def test_decryptor_extracts_password_from_filename():
    assert PDFDecryptor.extract_password_from_filename("对账单(123456).pdf") == "123456"
    assert PDFDecryptor.extract_password_from_filename("文件(注释)(654321).pdf") == "654321"
    # full-width parentheses
    assert PDFDecryptor.extract_password_from_filename("对账单（888888）.pdf") == "888888"
    # no parentheses -> None
    assert PDFDecryptor.extract_password_from_filename("plain.pdf") is None


def test_extract_raw_tables_decrypts_with_filename_password(tmp_path, monkeypatch):
    pdf_path = tmp_path / "statement(123456).pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    calls = {"decrypted_path": None}

    def fake_decrypt(file_path, password=""):
        # Mirror the real (temp_path, None) success contract.
        assert password == "123456", "should use filename-extracted password"
        temp = tmp_path / "decrypted.pdf"
        temp.write_bytes(b"%PDF-1.4 decrypted")
        calls["decrypted_path"] = temp
        return temp, None

    monkeypatch.setattr(PDFDecryptor, "is_encrypted", staticmethod(lambda path: True))
    monkeypatch.setattr(PDFDecryptor, "decrypt", staticmethod(fake_decrypt))

    def fake_get_markdown(path):
        # Confirm the parser handed the decrypted file to MinerU, not the original.
        assert path == calls["decrypted_path"], "should parse decrypted temp file"
        return "<table><tr><th>x</th></tr><tr><td>1</td></tr></table>"

    parser = PDFParser()
    monkeypatch.setattr(parser.client, "get_markdown", fake_get_markdown)

    tables = parser.extract_raw_tables(pdf_path)

    assert len(tables) == 1
    assert tables[0].rows == [["x"], ["1"]]


def test_extract_raw_tables_fails_when_no_password_callback(tmp_path, monkeypatch):
    pdf_path = tmp_path / "nopw.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    monkeypatch.setattr(PDFDecryptor, "is_encrypted", staticmethod(lambda path: True))
    # No filename password and no callback -> ValueError surfaced, swallowed to [].
    monkeypatch.setattr(
        PDFDecryptor, "extract_password_from_filename", staticmethod(lambda name: None)
    )

    parser = PDFParser()  # no password callback set

    assert parser.extract_raw_tables(pdf_path) == []


# ---------------------------------------------------------------------------
# Runtime settings wiring
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extractor_wires_mineru_runtime_settings(monkeypatch):
    """The extractor must pass DB/runtime MinerU settings into the PDF parser."""
    from app.services.extraction.extractor import FlowExtractor

    runtime_settings = {
        "mineru.mode": "public",
        "mineru.url": "http://ignored:8000",
        "mineru.public_url": "https://mineru.example/api/v1/agent",
        "mineru.public_api_key": "rt-key",
        "mineru.timeout": "180",
    }

    extractor = FlowExtractor(runtime_settings=runtime_settings)

    assert extractor.pdf_parser.mineru_mode == "public"
    assert isinstance(extractor.pdf_parser.client, PublicMinerUClient)
    assert extractor.pdf_parser.client.base_url == "https://mineru.example/api/v1/agent"
    assert extractor.pdf_parser.client.api_key == "rt-key"
    assert extractor.pdf_parser.client.timeout == 180


def test_default_settings_include_mineru_keys():
    from app.services.settings_service import DEFAULT_SETTINGS

    for key in (
        "mineru.mode",
        "mineru.url",
        "mineru.public_url",
        "mineru.public_api_key",
        "mineru.timeout",
    ):
        assert key in DEFAULT_SETTINGS, f"missing default setting {key}"
        assert DEFAULT_SETTINGS[key]["category"] == "mineru"


def test_default_settings_drop_decorative_flow_keys():
    """flow.* settings are not consumed by the start/append runtime path,
    so they must not appear in DEFAULT_SETTINGS (no decorative settings)."""
    from app.services.settings_service import DEFAULT_SETTINGS

    assert "flow.batch_size" not in DEFAULT_SETTINGS
    assert "flow.confidence_threshold" not in DEFAULT_SETTINGS
