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
根据文档名称与表格预览内容，判断是否为流水表格，并输出表头属性顺序列表。

## 关键判断要点
- 每行代表一笔交易，通常包含日期/时间、金额、对手方/商户、摘要/备注等
- 即使表格没有明显表头（分页续表），但行结构像流水，也应判断为流水表格
- 只有1-2行数据通常不是流水表格
- 账户信息/汇总统计/账单首页不是流水表格

## 各平台常见列名提示（供识别与归一）
银行储蓄卡：交易日期/交易时间/记账日期、对方户名/对方名称、对方账号、摘要/备注、收支/借贷、交易金额/发生额
信用卡账单：交易日期/记账日期/入账日期、交易描述/商户名称、交易金额/记账金额、币种
支付宝：交易时间、交易对方、对方账号、商品说明/备注、收/支、金额
微信：交易时间、交易对方/商户名称、交易类型/商品、收/支、金额(元)

## 表头输出规则
- 返回表头属性列表，顺序与原表格列顺序一致
- 如果明确存在表头行：表头属性为表头单元格原文（可简化去空格）
- 如果没有明确表头：根据列内容推断属性名称（如“交易时间”“交易对方”“金额”“摘要”“收支”），无法判断的列用空字符串
- 表头长度必须等于列数

## 返回JSON格式
{
  "is_flow_table": true或false,
  "confidence": 0-100整数,
  "reason": "判断理由",
  "header_row_index": 表头行索引（无表头则为-1）,
  "data_start_row": 数据开始行索引（无表头一般为0）,
  "header_attributes": ["列1表头","列2表头",...]
}
"""


CLASSIFIER_SCHEMA = {
    "type": "object",
    "properties": {
        "is_flow_table": {"type": "boolean"},
        "confidence": {"type": "integer"},
        "reason": {"type": "string"},
        "header_row_index": {"type": "integer"},
        "data_start_row": {"type": "integer"},
        "header_attributes": {
            "type": "array",
            "items": {"type": "string"}
        }
    },
    "required": [
        "is_flow_table",
        "confidence",
        "reason",
        "header_row_index",
        "data_start_row",
        "header_attributes"
    ],
    "additionalProperties": False
}


class FlowTableClassifier:
    """
    AI classifier for deciding whether a table is a flow table and extracting header attributes.
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
                content = data["choices"][0]["message"]["content"]
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

    def analyze_table(self, table: RawTable, document_name: str) -> Optional[Dict[str, Any]]:
        if not table.rows:
            return None

        preview_html = table.get_preview(self.preview_rows)
        user_message = (
            f"文档名称：{document_name}\n\n"
            f"请分析以下表格：\n\n{preview_html}"
        )
        result = self._make_request(SYSTEM_PROMPT_FLOW_TABLE_CLASSIFIER, user_message)
        if not result:
            return None

        return result

    def is_available(self) -> bool:
        return bool(self.api_key)
