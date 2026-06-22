# -*- coding: utf-8 -*-
"""LLM prompt and normalization parity tests.

Covers the parity guarantees ported from src/llm: mature prompts, retry/JSON
fallback, expected portrait/classifier/normalizer output fields, raw_amount
preservation, positive amount, and code-side transaction_type inference.

换框架后（pydantic-ai）的 mock 策略：三模块内部用 pydantic-ai agent，测试
不再 patch ``httpx.AsyncClient``，而是 patch 各模块的 agent 获取方法
（``_agent`` / ``_get_agent``）返回一个 fake agent，其 ``run`` 返回带
``.output`` 的对象。断言逐字保留——它们就是"换框架前后输出契约一致"的验收线。
"""

import json
from types import SimpleNamespace
from typing import Any

import pytest

from app.llm import DocumentPortraitExtractor, FlowTableClassifier, FlowDataNormalizer
from app.llm.types import DocumentPortrait, FlowClassification, NormalizedRow, NormalizedRows
from app.services.extraction.extractor import FlowExtractor


# ---------------------------------------------------------------------------
# Fake pydantic-ai agent
# ---------------------------------------------------------------------------


class _FakeAgent:
    """模拟 pydantic-ai agent：``run`` 返回 ``SimpleNamespace(output=...)``。

    ``outputs`` 是一个队列：每次 ``run`` 弹一个；元素为 output 对象或
    ``Exception``（抛出模拟失败）。
    """

    def __init__(self, outputs: list[Any]):
        self._outputs = list(outputs)
        self.captured_prompts: list[str] = []

    async def run(self, prompt: str, **kwargs):
        self.captured_prompts.append(prompt)
        if not self._outputs:
            raise AssertionError("no more fake outputs queued")
        item = self._outputs.pop(0)
        if isinstance(item, Exception):
            raise item
        return SimpleNamespace(output=item)


def _patch_portrait(monkeypatch, outputs):
    agent = _FakeAgent(outputs)
    monkeypatch.setattr(DocumentPortraitExtractor, "_agent", lambda self: agent)
    return agent


def _patch_classifier(monkeypatch, outputs):
    agent = _FakeAgent(outputs)
    monkeypatch.setattr(FlowTableClassifier, "_agent", lambda self: agent)
    return agent


def _patch_normalizer(monkeypatch, outputs):
    agent = _FakeAgent(outputs)
    monkeypatch.setattr(FlowDataNormalizer, "_get_agent", lambda self: agent)
    return agent


# ---------------------------------------------------------------------------
# Portrait
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_portrait_extracts_expected_field_set(monkeypatch):
    portrait = DocumentPortrait(
        account_type="credit_card",
        account_holder="张三",
        account_number_masked="6222****1234",
        institution="某银行",
        statement_period="2024-01-01 至 2024-03-31",
        key_observations=["信用卡账单"],
        amount_sign_rule="pos_expense",
        header_attributes=["交易日期", "交易金额"],
        column_mapping=["transaction_time", "amount"],
    )
    _patch_portrait(monkeypatch, [portrait])

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
async def test_portrait_returns_dict_on_success(monkeypatch):
    # pydantic-ai 的 output 重试由 agent 内部接管（output_type schema 校验失败
    # 才重试），模块层只做 try/except。这里验证：agent.run 成功返 valid
    # portrait → 模块透传为 dict（含默认值补全，如 key_observations 缺省 []）。
    portrait = DocumentPortrait(account_type="unknown")
    _patch_portrait(monkeypatch, [portrait])

    extractor = DocumentPortraitExtractor("http://x", "key", "model", max_retries=3)
    result = await extractor.extract("doc.pdf", "ctx", "")

    assert result is not None
    assert result["account_type"] == "unknown"
    # 默认值补全：缺省字段应为空列表/空串，而非缺失。
    assert result["key_observations"] == []
    assert result["header_attributes"] == []


@pytest.mark.asyncio
async def test_portrait_returns_none_on_empty_content(monkeypatch):
    # agent.run 抛错（模拟空内容/校验失败）→ 模块层兜底返 None。
    _patch_portrait(monkeypatch, [RuntimeError("empty content")])

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
    classification = FlowClassification(
        is_flow_table=True,
        confidence=90,
        reason="流水表格",
        header_row_index=0,
        data_start_row=1,
    )
    _patch_classifier(monkeypatch, [classification])

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
    _patch_classifier(monkeypatch, [RuntimeError("network down")])

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
    rows_payload = NormalizedRows(
        rows=[
            NormalizedRow(
                row_index=0,
                is_valid=True,
                transaction_time="2024-01-01 00:00:00",
                counterparty_name="商户A",
                counterparty_account="6222000000000001",
                amount="100.00",
                raw_amount="-100.00",
                summary="消费",
                transaction_type="支出",
                source_file="stmt.pdf",
            )
        ]
    )
    _patch_normalizer(monkeypatch, [rows_payload])

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
    _patch_normalizer(monkeypatch, [RuntimeError("network down")])

    normalizer = FlowDataNormalizer("http://x", "key", "model", max_retries=1)
    result = await normalizer.normalize([["a", "b"]], document_portrait=None, source_file="x.pdf")

    assert result == []


@pytest.mark.asyncio
async def test_normalizer_uses_filename_context_fallback(monkeypatch):
    # portrait=None 时走 _infer_document_context，文件名"信用卡账单.pdf"应推成
    # credit_card。捕获 user_message 验证 portrait 兜底生效。
    agent = _patch_normalizer(monkeypatch, [NormalizedRows(rows=[])])

    normalizer = FlowDataNormalizer("http://x", "key", "model")
    await normalizer.normalize([["a"]], document_portrait=None, source_file="信用卡账单.pdf")

    assert agent.captured_prompts, "normalizer should have called agent.run"
    decoded = json.loads(agent.captured_prompts[0])
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
