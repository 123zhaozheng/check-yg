# -*- coding: utf-8 -*-
"""S5 清洗标准化 不删减 regression tests (决策3).

Fixed input + fake LLM: monkeypatch classifier/normalizer/parser to return
deterministic outputs, run the modified extractor, and assert:

* standard records match the pre-change logic field-by-field.
* unparsed rows = fake normalizer's is_valid=false rows (never dropped).
* excluded rows = fake classifier's non-flow tables' rows (never dropped).
* every record carries raw_payload with the original cells.

No real LLM is called. ``test_llm_parity.py`` (提示词保真) stays green separately.
"""

from pathlib import Path

import pytest

from app.parsers.base import RawTable
from app.services.extraction.extractor import FlowExtractor


class _FakeParser:
    """Returns canned raw tables + empty non-table context, no MinerU."""

    def __init__(self, tables):
        self._tables = tables

    def extract_tables_and_context(self, file_path, max_chars=None):
        return self._tables, ""

    def extract_raw_tables(self, file_path):
        return self._tables

    def extract_non_table_context(self, file_path, max_chars=None):
        return ""


@pytest.mark.asyncio
async def test_extract_does_not_drop_unparsed_or_excluded_rows(monkeypatch):
    """清洗不删减: standard + unparsed + excluded all persisted with raw_payload.

    One document with two tables:
      * table #0: classified as flow (confidence 90) → normalizer returns 3
        rows, two is_valid=true (standard) + one is_valid=false (unparsed).
      * table #1: classified as non-flow (confidence 20, below threshold 70)
        → all 2 raw rows become excluded.

    Assert: 2 standard + 1 unparsed + 2 excluded = 5 total, none dropped, and
    every raw_payload contains the original cells.
    """
    extractor = FlowExtractor()

    table1 = RawTable(
        table_index=0,
        rows=[
            ["日期", "对手", "金额"],
            ["2026-06-17", "商户A", "100.00"],
            ["", "", "合计 250.00"],
            ["2026-06-18", "商户B", "150.00"],
        ],
    )
    table2 = RawTable(
        table_index=1,
        rows=[
            ["账户信息", "账号 6222****1234"],
            ["开户行", "某银行"],
        ],
    )
    fake_parser = _FakeParser([table1, table2])
    monkeypatch.setattr(extractor, "_get_parser_for_file", lambda path: fake_parser)

    async def fake_classify(table, document_name, document_portrait=None):
        if table.table_index == 0:
            return {
                "is_flow_table": True,
                "confidence": 90,
                "reason": "flow",
                "header_row_index": 0,
                "data_start_row": 1,
            }
        return {
            "is_flow_table": False,
            "confidence": 20,
            "reason": "not flow",
            "header_row_index": -1,
            "data_start_row": 0,
        }

    async def fake_normalize(batch, portrait, source_file=""):
        out = []
        for idx, row in enumerate(batch):
            cells = [str(c) for c in row]
            if idx == 1:
                out.append(
                    {
                        "row_index": idx,
                        "is_valid": False,
                        "transaction_time": "",
                        "counterparty_name": "",
                        "counterparty_account": "",
                        "amount": "",
                        "raw_amount": "",
                        "summary": "合计",
                        "transaction_type": "",
                        "source_file": source_file,
                    }
                )
            else:
                out.append(
                    {
                        "row_index": idx,
                        "is_valid": True,
                        "transaction_time": "2026-06-17 10:00:00",
                        "counterparty_name": cells[1] if len(cells) > 1 else "",
                        "counterparty_account": "",
                        "amount": cells[2] if len(cells) > 2 else "",
                        "raw_amount": cells[2] if len(cells) > 2 else "",
                        "summary": "消费",
                        "transaction_type": "支出",
                        "source_file": source_file,
                    }
                )
        return out

    async def fake_portrait(document_name, non_table_context, content_preview):
        return {
            "account_type": "bank_general",
            "amount_sign_rule": "pos_income",
            "header_attributes": ["日期", "对手", "金额"],
            "column_mapping": ["transaction_time", "counterparty_name", "amount"],
        }

    monkeypatch.setattr(extractor.classifier, "classify", fake_classify)
    monkeypatch.setattr(extractor.normalizer, "normalize", fake_normalize)
    monkeypatch.setattr(extractor.portrait_extractor, "extract", fake_portrait)

    doc_path = Path("stmt.pdf")
    doc_result = await extractor._process_document_stage1(
        doc_path, task_id="t1", confidence_threshold=70,
    )

    # Stage 1 must have produced excluded records for table #1's 2 rows.
    excluded_dicts = doc_result.get("excluded_records") or []
    assert len(excluded_dicts) == 2
    for ex in excluded_dicts:
        assert ex["record_type"] == "excluded"
        assert ex["is_valid"] is False
        assert ex["exclude_reason"] == "classifier: not flow table"
        assert "cells" in ex["raw_payload"]
    assert excluded_dicts[0]["raw_payload"]["cells"] == ["账户信息", "账号 6222****1234"]
    assert excluded_dicts[1]["raw_payload"]["cells"] == ["开户行", "某银行"]

    stage2 = await extractor._process_document_stage2(doc_result, task_id="t1", batch_size=20)

    standard_dicts = [r for r in stage2["extracted_records"] if r["record_type"] == "standard"]
    unparsed_dicts = [r for r in stage2["extracted_records"] if r["record_type"] == "unparsed"]

    assert len(stage2["records"]) == 2  # FlowRecord list (standard only)
    assert len(standard_dicts) == 2
    assert len(unparsed_dicts) == 1
    # 总计 5 = 2 standard + 1 unparsed + 2 excluded，无丢失。
    assert len(standard_dicts) + len(unparsed_dicts) + len(excluded_dicts) == 5

    # Standard field-by-field: matches pre-change logic. Code-side inference:
    # pos_income + positive raw_amount "100.00" → "收入" (corrects LLM "支出").
    first = standard_dicts[0]
    assert first["transaction_time"] == "2026-06-17 10:00:00"
    assert first["counterparty_name"] == "商户A"
    assert first["amount"] == "100.00"
    assert first["raw_amount"] == "100.00"
    assert first["transaction_type"] == "收入"
    assert first["raw_payload"]["cells"] == ["2026-06-17", "商户A", "100.00"]

    # Unparsed: noise row kept with raw_payload (合计 row).
    noise = unparsed_dicts[0]
    assert noise["is_valid"] is False
    assert noise["exclude_reason"].startswith("normalizer: noise row")
    assert noise["raw_payload"]["cells"] == ["", "", "合计 250.00"]


@pytest.mark.asyncio
async def test_extract_standard_output_equivalent_to_pre_change(monkeypatch):
    """Standard records' field values match the pre-change extractor output.

    The pre-change logic built FlowRecord(original_row=data_start_row+i+off,
    transaction_time/counterparty_name/.../transaction_type from the normalizer
    item). The post-change logic must produce identical field values for
    standard rows — only the is_valid=false (unparsed) path is new.
    """
    extractor = FlowExtractor()

    table = RawTable(
        table_index=0,
        rows=[
            ["日期", "对手", "金额"],
            ["2026-06-17", "张三", "100.00"],
            ["2026-06-18", "李四", "200.00"],
        ],
    )
    fake_parser = _FakeParser([table])
    monkeypatch.setattr(extractor, "_get_parser_for_file", lambda path: fake_parser)

    async def fake_classify(table, document_name, document_portrait=None):
        return {
            "is_flow_table": True,
            "confidence": 95,
            "reason": "flow",
            "header_row_index": 0,
            "data_start_row": 1,
        }

    async def fake_normalize(batch, portrait, source_file=""):
        out = []
        for idx, row in enumerate(batch):
            cells = [str(c) for c in row]
            out.append(
                {
                    "row_index": idx,
                    "is_valid": True,
                    "transaction_time": cells[0],
                    "counterparty_name": cells[1],
                    "counterparty_account": "",
                    "amount": cells[2],
                    "raw_amount": "-" + cells[2],
                    "summary": "备注",
                    "transaction_type": "支出",
                    "source_file": source_file,
                }
            )
        return out

    async def fake_portrait(document_name, non_table_context, content_preview):
        return {
            "account_type": "bank_general",
            "amount_sign_rule": "pos_income",
            "header_attributes": ["日期", "对手", "金额"],
            "column_mapping": ["transaction_time", "counterparty_name", "amount"],
        }

    monkeypatch.setattr(extractor.classifier, "classify", fake_classify)
    monkeypatch.setattr(extractor.normalizer, "normalize", fake_normalize)
    monkeypatch.setattr(extractor.portrait_extractor, "extract", fake_portrait)

    doc_path = Path("stmt.pdf")
    doc_result = await extractor._process_document_stage1(
        doc_path, task_id="t2", confidence_threshold=70,
    )
    stage2 = await extractor._process_document_stage2(doc_result, task_id="t2", batch_size=20)

    # FlowRecord list matches the pre-change contract field-by-field.
    records = stage2["records"]
    assert len(records) == 2
    assert records[0].source_file == "stmt.pdf"
    assert records[0].original_row == 1  # data_start_row(1) + i(0) + off(0)
    assert records[0].transaction_time == "2026-06-17"
    assert records[0].counterparty_name == "张三"
    assert records[0].amount == "100.00"
    # raw_amount="-100.00" + pos_income → "支出" (matches LLM, no correction).
    assert records[0].transaction_type == "支出"
    assert records[1].original_row == 2
    assert records[1].counterparty_name == "李四"

    # extracted_records standard rows mirror the FlowRecord fields + raw_payload.
    std = [r for r in stage2["extracted_records"] if r["record_type"] == "standard"]
    assert len(std) == 2
    assert std[0]["row_index"] == 1
    assert std[0]["raw_amount"] == "-100.00"  # sign preserved in raw_amount
    assert std[0]["amount"] == "100.00"  # amount positive
    assert std[0]["raw_payload"]["cells"] == ["2026-06-17", "张三", "100.00"]
