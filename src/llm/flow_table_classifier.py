# -*- coding: utf-8 -*-
"""
AI flow table classifier for V2 extraction.
"""

import json
import logging
from typing import Any, Dict, List, Optional

import requests

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


CLASSIFIER_SCHEMA = {
    "type": "object",
    "properties": {
        "is_flow_table": {"type": "boolean"},
        "confidence": {"type": "integer"},
        "reason": {"type": "string"},
        "header_row_index": {"type": "integer"},
        "data_start_row": {"type": "integer"}
    },
    "required": [
        "is_flow_table",
        "confidence",
        "reason",
        "header_row_index",
        "data_start_row"
    ],
    "additionalProperties": False
}


class FlowTableClassifier:
    """
    AI classifier for deciding whether a table is a flow table.
    """

    def __init__(
        self,
        api_url: str,
        model: str,
        api_key: str,
        timeout: int = 60,
        preview_rows: int = 10,
        max_retries: int = 3,
    ):
        self.api_url = api_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.preview_rows = preview_rows
        self.max_retries = max_retries

    def _post(self, system_prompt: str, user_message: str, response_format: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not self.api_key:
            logger.warning("No API key configured for classifier")
            return None

        url = f"{self.api_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            "temperature": 0.1,
            "max_tokens": 1500,
            "response_format": response_format
        }

        for attempt in range(self.max_retries):
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
                response.raise_for_status()
                data = response.json()
                message = data["choices"][0]["message"]
                content = (
                    message.get("content")
                    or message.get("reasoning_content")
                    or message.get("reasoning")
                )
                if not content:
                    raise ValueError(f"Empty message content: {json.dumps(message, ensure_ascii=False)[:500]}")
                return json.loads(content)
            except json.JSONDecodeError as exc:
                text = ""
                try:
                    text = response.text
                except Exception:
                    text = ""
                logger.warning("Classifier JSON decode failed: %s; response=%s", exc, text[:500])
            except Exception as exc:
                logger.warning("Classifier request failed (attempt %d/%d): %s", attempt + 1, self.max_retries, exc)

        return None

    def _make_request(self, system_prompt: str, user_message: str) -> Optional[Dict[str, Any]]:
        object_format = {"type": "json_object"}
        return self._post(system_prompt, user_message, object_format)

    def _render_prompt(self) -> str:
        """Return the classifier system prompt, loading from config if available."""
        from ..config import get_config

        config = get_config()
        return config.prompt_classifier or SYSTEM_PROMPT_FLOW_TABLE_CLASSIFIER

    def analyze_table(
        self,
        table: RawTable,
        document_name: str,
        document_portrait: Optional[Dict[str, Any]] = None,
        content_preview: str = "",
    ) -> Optional[Dict[str, Any]]:
        if not table.rows:
            return None

        system_prompt = self._render_prompt()

        preview_html = table.get_preview(self.preview_rows)
        user_message = (
            f"文档名称：{document_name}\n\n"
            f"文档画像：{json.dumps(document_portrait, ensure_ascii=False) if document_portrait else '无'}\n\n"
            f"内容预览：{content_preview or '无'}\n\n"
            f"请分析以下表格：\n\n{preview_html}"
        )
        result = self._make_request(system_prompt, user_message)
        if not result:
            return None

        return result

    def is_available(self) -> bool:
        return bool(self.api_key)
