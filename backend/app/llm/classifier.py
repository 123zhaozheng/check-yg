# -*- coding: utf-8 -*-
"""Flow table classifier using pydantic-ai.

提示词逐字搬运自 legacy ``src/llm/flow_table_classifier.py``（硬底线：提示词
保真），只把调用层从自写 httpx 换成 pydantic-ai agent（output_type=
FlowClassification）。``classify()`` 对外契约不变：成功返 dict（含
is_flow_table/confidence/reason/header_row_index/data_start_row），失败返
安全兜底 ``FALLBACK_RESULT``。落地遵循 ``docs/research/pydantic-ai-conventions.md``
(v1.107.0)。
"""

import json
import logging
from typing import Any, Optional

from app.llm.agent_factory import get_agent
from app.llm.types import FlowClassification
from ..parsers.base import RawTable

logger = logging.getLogger(__name__)


SYSTEM_PROMPT_FLOW_TABLE_CLASSIFIER = """你是一个银行/支付流水表格识别专家，熟悉中国各大银行、信用卡、支付宝、微信等流水格式。

## 任务
根据文档画像与表格预览内容，判断是否为流水表格。

## 关键判断要点
- 每行代表一笔交易，通常包含日期/时间、金额、对手方/商户、摘要/备注等
- 即使表格没有明显表头（分页续表），但行结构像流水，也应判断为流水表格
- 只有1-2行数据通常不是流水表格
- 账户信息/汇总统计/账单首页不是流水表格

## 文档画像参考
画像数据在下方用户消息中提供，请参考画像信息进行判断。

## 内容预览
预览数据在下方用户消息中提供，请参考预览内容进行判断。

## 返回JSON格式
{
  "is_flow_table": true或false,
  "confidence": 0-100整数,
  "reason": "判断理由",
  "header_row_index": 表头行索引（无表头则为-1）,
  "data_start_row": 数据开始行索引（无表头一般为0）
}
"""

_MAX_TOKENS_CLASSIFIER = 1500


class FlowTableClassifier:
    """Classify a table as a flow table or not using a pydantic-ai agent.

    Output contract: a dict with ``is_flow_table``, ``confidence``, ``reason``,
    ``header_row_index`` and ``data_start_row``. Returns a safe fallback dict
    (``is_flow_table=False``) when classification fails.
    """

    FALLBACK_RESULT: dict[str, Any] = {
        "is_flow_table": False,
        "confidence": 0,
        "reason": "classification unavailable",
        "header_row_index": -1,
        "data_start_row": 0,
    }

    def __init__(self, api_url: str, api_key: str, model: str, timeout: int = 60, max_retries: int = 3):
        self.api_url = api_url
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries

    def _agent(self):
        return get_agent(
            FlowClassification,
            SYSTEM_PROMPT_FLOW_TABLE_CLASSIFIER,
            base_url=self.api_url,
            api_key=self.api_key,
            model=self.model,
            timeout=self.timeout,
            max_tokens=_MAX_TOKENS_CLASSIFIER,
        )

    async def classify(
        self,
        table: RawTable,
        document_name: str,
        document_portrait: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        判断表格是否为流水表格

        Args:
            table: 原始表格数据
            document_name: 文档文件名
            document_portrait: 文档画像（可选，供判断参考）

        Returns:
            分类结果 dict，含 is_flow_table/confidence/reason/header_row_index/data_start_row。
            失败时返回安全兜底结果（is_flow_table=False）。
        """
        if not table.rows:
            return dict(self.FALLBACK_RESULT, reason="empty table")

        preview = table.get_preview(max_rows=10)
        user_message = (
            f"文档名称：{document_name}\n\n"
            f"文档画像：{json.dumps(document_portrait, ensure_ascii=False) if document_portrait else '无'}\n\n"
            f"请分析以下表格：\n\n{preview}"
        )

        try:
            result = await self._agent().run(user_message)
        except Exception as exc:
            logger.warning("Classifier agent.run 失败: %s", exc)
            return dict(self.FALLBACK_RESULT)

        classification: FlowClassification = result.output
        # 保持与旧实现一致的 dict 契约 + setdefault 兜底语义。
        return {
            "is_flow_table": classification.is_flow_table,
            "confidence": classification.confidence,
            "reason": classification.reason,
            "header_row_index": classification.header_row_index,
            "data_start_row": classification.data_start_row,
        }

    def is_available(self) -> bool:
        return bool(self.api_key)
