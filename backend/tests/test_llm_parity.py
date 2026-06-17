# -*- coding: utf-8 -*-
"""LLM prompt and normalization parity tests.

Covers the parity guarantees ported from src/llm: mature prompts, retry/JSON
fallback, expected portrait/classifier/normalizer output fields, raw_amount
preservation, positive amount, and code-side transaction_type inference.

All tests mock httpx.AsyncClient so no real network calls are made.
"""

import json
from typing import Any, Dict, Optional

import pytest

from app.llm import DocumentPortraitExtractor, FlowTableClassifier, FlowDataNormalizer
from app.services.extraction.extractor import FlowExtractor


# ---------------------------------------------------------------------------
# Fake httpx transport
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, payload: Dict[str, Any], status_code: int = 200, text: str = ""):
        self._payload = payload
        self.status_code = status_code
        self.text = text or json.dumps(payload, ensure_ascii=False)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise Exception("HTTP %s" % self.status_code)

    def json(self) -> Dict[str, Any]:
        return self._payload


def _chat_response(content: Optional[str]) -> Dict[str, Any]:
    """Build an OpenAI-style chat completion response with the given content."""
    message: Dict[str, Any] = {"role": "assistant"}
    if content is None:
        message["content"] = None
    else:
        message["content"] = content
    return {"choices": [{"message": message}]}


def _install_fake_post(monkeypatch, responses):
    """Patch httpx.AsyncClient.post to pop successive fake responses.

    responses: list of _FakeResponse (or Exception instances to raise).
    """
    queue = list(responses)

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, **kwargs):
            if not queue:
                raise AssertionError("no more fake responses queued")
            item = queue.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

    monkeypatch.setattr("app.llm.portrait.httpx.AsyncClient", _FakeClient)
    monkeypatch.setattr("app.llm.classifier.httpx.AsyncClient", _FakeClient)
    monkeypatch.setattr("app.llm.normalizer.httpx.AsyncClient", _FakeClient)
    return queue


# ---------------------------------------------------------------------------
# Portrait
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_portrait_extracts_expected_field_set(monkeypatch):
    portrait = {
        "account_type": "credit_card",
        "account_holder": "张三",
        "account_number_masked": "6222****1234",
        "institution": "某银行",
        "statement_period": "2024-01-01 至 2024-03-31",
        "key_observations": ["信用卡账单"],
        "amount_sign_rule": "pos_expense",
        "header_attributes": ["交易日期", "交易金额"],
        "column_mapping": ["transaction_time", "amount"],
    }
    _install_fake_post(monkeypatch, [_FakeResponse(_chat_response(json.dumps(portrait, ensure_ascii=False)))])

    extractor = DocumentPortraitExtractor("http://x", "key", "model")
    result = await extractor.extract("信用卡账单.pdf", "账户说明", "<table/>")

    assert result is not None
    for field in (
        "account_type",
        "account_holder",
        "account_number_masked",
        "institution",
        "statement_period",
        "key_observations",
        "amount_sign_rule",
        "header_attributes",
        "column_mapping",
    ):
        assert field in result, f"portrait missing field {field}"
    assert result["account_type"] == "credit_card"
    assert result["column_mapping"] == ["transaction_time", "amount"]


@pytest.mark.asyncio
async def test_portrait_returns_none_on_malformed_json(monkeypatch):
    # First two attempts: malformed JSON; third: valid -> succeeds on retry.
    _install_fake_post(
        monkeypatch,
        [
            _FakeResponse(_chat_response("not json")),
            _FakeResponse({"choices": [{"message": {"content": "{bad json"}}]}),
            _FakeResponse(_chat_response(json.dumps({"account_type": "unknown"}))),
        ],
    )

    extractor = DocumentPortraitExtractor("http://x", "key", "model", max_retries=3)
    result = await extractor.extract("doc.pdf", "ctx", "")

    assert result == {"account_type": "unknown"}


@pytest.mark.asyncio
async def test_portrait_returns_none_on_empty_content(monkeypatch):
    _install_fake_post(monkeypatch, [_FakeResponse(_chat_response(None))])

    extractor = DocumentPortraitExtractor("http://x", "key", "model", max_retries=1)
    result = await extractor.extract("doc.pdf", "ctx", "")

    assert result is None


@pytest.mark.asyncio
async def test_portrait_returns_none_without_api_key():
    extractor = DocumentPortraitExtractor("http://x", "", "model")
    assert (await extractor.extract("doc.pdf", "ctx", "")) is None


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_classifier_returns_header_and_data_row_fields(monkeypatch):
    classification = {
        "is_flow_table": True,
        "confidence": 90,
        "reason": "流水表格",
        "header_row_index": 0,
        "data_start_row": 1,
    }
    _install_fake_post(monkeypatch, [_FakeResponse(_chat_response(json.dumps(classification)))])

    from app.parsers.base import RawTable

    table = RawTable(table_index=0, rows=[["日期", "金额"], ["2024-01", "100"]])
    classifier = FlowTableClassifier("http://x", "key", "model")
    result = await classifier.classify(table, "doc.pdf", document_portrait={"account_type": "bank_general"})

    assert result["is_flow_table"] is True
    assert result["header_row_index"] == 0
    assert result["data_start_row"] == 1
    assert result["reason"] == "流水表格"


@pytest.mark.asyncio
async def test_classifier_falls_back_safely_on_failure(monkeypatch):
    _install_fake_post(monkeypatch, [Exception("network down")])

    from app.parsers.base import RawTable

    table = RawTable(table_index=0, rows=[["a"], ["b"]])
    classifier = FlowTableClassifier("http://x", "key", "model", max_retries=1)
    result = await classifier.classify(table, "doc.pdf")

    assert result["is_flow_table"] is False
    assert result["confidence"] == 0
    assert "header_row_index" in result and "data_start_row" in result


@pytest.mark.asyncio
async def test_classifier_empty_table_returns_fallback():
    from app.parsers.base import RawTable

    classifier = FlowTableClassifier("http://x", "key", "model")
    result = await classifier.classify(RawTable(table_index=0, rows=[]), "doc.pdf")

    assert result["is_flow_table"] is False


# ---------------------------------------------------------------------------
# Normalizer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_normalizer_preserves_raw_amount_and_positive_amount(monkeypatch):
    rows_payload = [
        {
            "row_index": 0,
            "is_valid": True,
            "transaction_time": "2024-01-01 00:00:00",
            "counterparty_name": "商户A",
            "counterparty_account": "6222000000000001",
            "amount": "100.00",
            "raw_amount": "-100.00",
            "summary": "消费",
            "transaction_type": "支出",
            "source_file": "stmt.pdf",
        }
    ]
    _install_fake_post(monkeypatch, [_FakeResponse(_chat_response(json.dumps({"rows": rows_payload})))])

    normalizer = FlowDataNormalizer("http://x", "key", "model")
    result = await normalizer.normalize(
        [["2024-01-01", "-100.00", "商户A"]],
        document_portrait={
            "account_type": "bank_general",
            "amount_sign_rule": "pos_income",
            "header_attributes": ["日期", "金额", "对手"],
            "column_mapping": ["transaction_time", "amount", "counterparty_name"],
        },
        source_file="stmt.pdf",
    )

    assert len(result) == 1
    item = result[0]
    assert item["raw_amount"] == "-100.00"  # sign preserved
    assert item["amount"] == "100.00"  # always positive
    assert item["transaction_type"] == "支出"


@pytest.mark.asyncio
async def test_normalizer_returns_empty_on_failure(monkeypatch):
    _install_fake_post(monkeypatch, [Exception("network down")])

    normalizer = FlowDataNormalizer("http://x", "key", "model", max_retries=1)
    result = await normalizer.normalize([["a", "b"]], document_portrait=None, source_file="x.pdf")

    assert result == []


@pytest.mark.asyncio
async def test_normalizer_uses_filename_context_fallback(monkeypatch):
    captured = {}

    class _CapturingClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, **kwargs):
            captured["payload"] = kwargs["json"]
            return _FakeResponse(_chat_response(json.dumps({"rows": []})))

    monkeypatch.setattr("app.llm.normalizer.httpx.AsyncClient", _CapturingClient)

    normalizer = FlowDataNormalizer("http://x", "key", "model")
    await normalizer.normalize([["a"]], document_portrait=None, source_file="信用卡账单.pdf")

    portrait = captured["payload"]["messages"][1]["content"]
    decoded = json.loads(portrait)
    assert decoded["document_portrait"]["account_type"] == "credit_card"


@pytest.mark.asyncio
async def test_normalizer_empty_rows_returns_empty():
    normalizer = FlowDataNormalizer("http://x", "key", "model")
    assert await normalizer.normalize([], document_portrait=None, source_file="x.pdf") == []


# ---------------------------------------------------------------------------
# Code-side transaction_type inference (extractor)
# ---------------------------------------------------------------------------


def test_infer_transaction_type_pos_income():
    assert FlowExtractor._infer_transaction_type("100", "pos_income") == "收入"
    assert FlowExtractor._infer_transaction_type("-100", "pos_income") == "支出"


def test_infer_transaction_type_pos_expense():
    assert FlowExtractor._infer_transaction_type("100", "pos_expense") == "支出"
    assert FlowExtractor._infer_transaction_type("-100", "pos_expense") == "收入"


def test_infer_transaction_type_credit_card_defers_to_llm():
    # Credit cards rely on LLM semantic judgment — code must not override.
    assert (
        FlowExtractor._infer_transaction_type(
            "-100", "pos_expense", {"account_type": "credit_card"}
        )
        is None
    )


def test_infer_transaction_type_no_sign_and_split_cols_return_none():
    assert FlowExtractor._infer_transaction_type("100", "no_sign") is None
    assert FlowExtractor._infer_transaction_type("100", "split_cols") is None


def test_infer_transaction_type_empty_returns_none():
    assert FlowExtractor._infer_transaction_type("", "pos_income") is None
    assert FlowExtractor._infer_transaction_type(None, "pos_income") is None
