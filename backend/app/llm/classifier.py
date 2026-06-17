# -*- coding: utf-8 -*-
"""Flow table classifier using LLM.

Ports the mature ``src/llm/flow_table_classifier.py`` prompt and fallback
behavior into the FastAPI backend while keeping the backend's async ``httpx``
transport and the ``classify()`` contract consumed by the extraction pipeline.
"""

import json
import logging
from typing import Any, Dict, Optional

import httpx

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


class FlowTableClassifier:
    """Classify a table as a flow table or not using an OpenAI-compatible LLM.

    Output contract: a dict with ``is_flow_table``, ``confidence``, ``reason``,
    ``header_row_index`` and ``data_start_row``. Returns a safe fallback dict
    (``is_flow_table=False``) when classification fails.
    """

    FALLBACK_RESULT: Dict[str, Any] = {
        "is_flow_table": False,
        "confidence": 0,
        "reason": "classification unavailable",
        "header_row_index": -1,
        "data_start_row": 0,
    }

    def __init__(self, api_url: str, api_key: str, model: str, timeout: int = 60, max_retries: int = 3):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries

    async def _post(
        self,
        system_prompt: str,
        user_message: str,
    ) -> Optional[Dict[str, Any]]:
        """POST a chat completion and parse JSON content with retry + fallback."""
        if not self.api_key:
            logger.warning("No API key configured for classifier")
            return None

        url = f"{self.api_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": 0.1,
            "max_tokens": 1500,
            "response_format": {"type": "json_object"},
        }

        response = None
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
                    response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                message = data["choices"][0]["message"]
                content = (
                    message.get("content")
                    or message.get("reasoning_content")
                    or message.get("reasoning")
                )
                if not content:
                    raise ValueError(
                        "Empty message content: %s"
                        % json.dumps(message, ensure_ascii=False)[:500]
                    )
                return json.loads(content)
            except json.JSONDecodeError as exc:
                text = ""
                try:
                    text = response.text if response is not None else ""
                except Exception:
                    text = ""
                logger.warning(
                    "Classifier JSON decode failed: %s; response=%s",
                    exc,
                    text[:500],
                )
            except Exception as exc:
                logger.warning(
                    "Classifier request failed (attempt %d/%d): %s",
                    attempt + 1,
                    self.max_retries,
                    exc,
                )

        return None

    async def classify(
        self,
        table: RawTable,
        document_name: str,
        document_portrait: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
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

        result = await self._post(SYSTEM_PROMPT_FLOW_TABLE_CLASSIFIER, user_message)
        if not result:
            return dict(self.FALLBACK_RESULT)

        # Normalize required fields so downstream consumers never KeyError.
        result.setdefault("header_row_index", -1)
        result.setdefault("data_start_row", 0)
        result.setdefault("reason", "")
        result.setdefault("confidence", 0)
        result.setdefault("is_flow_table", False)
        return result

    def is_available(self) -> bool:
        return bool(self.api_key)
