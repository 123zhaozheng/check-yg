# -*- coding: utf-8 -*-
"""
AI data normalizer for converting raw flow rows into standardized records.
"""

import json
import logging
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


SYSTEM_PROMPT_DATA_NORMALIZER = """你是一个银行/支付流水数据标准化专家。

## 任务
给定文档名称、表头属性列表、以及若干行原始表格数据，输出标准化流水记录。

## 标准字段
1) transaction_time - 交易时间（日期或日期时间）
2) counterparty_name - 交易对手/商户名称
3) counterparty_account - 交易对手账号/卡号（无则为空）
4) amount - 交易金额（保留原始正负或金额文本）
5) summary - 摘要/备注/交易说明/商品信息
6) transaction_type - 收支类型（收入/支出/转账/退款/其他）
7) source_file - 来源文件名

## 关键规则（必须遵守）
1) 若存在明确“对方/商户/交易对手”列，则优先填入 counterparty_name
2) “摘要/备注/交易说明/商品/用途”等列优先填入 summary
3) 若只有一个“交易描述/商户名称”列，且无法区分，对 counterparty_name 与 summary 可相同
4) amount 优先取“交易金额/发生额/金额(元)/支出/收入/借方/贷方”等列：
   - 若同时有收入/支出两列，优先取非空值，并据此推断 transaction_type
   - 若金额为负数，transaction_type 为支出；正数为收入
5) credit card（信用卡）流水常见：
   - 交易描述/商户名称 → counterparty_name
   - 若无明确摘要列，summary 可与 counterparty_name 相同
6) 支付宝/微信常见：
   - 交易对方/商户名称 → counterparty_name
   - 商品/交易类型/备注 → summary
7) counterparty_account 仅在有明确账号/卡号列时填入，否则为空
8) 过滤噪音行：合计/小计/总计/余额/页脚/页眉/空行等，is_valid=false
9) 日期时间统一输出为 "YYYY-MM-DD hh:mm:ss"：
   - 只有日期时补全时间为 "00:00:00"
   - 有时间但缺少秒时补全为 ":00"
10) 金额正负与收入/支出方向要一致：
   - 支出/消费/付款/借方/转出/扣款/手续费 等应为负数
   - 收入/收款/入账/贷方/退款/返现/利息 等应为正数
11) 金额清洗：去除金额前缀/符号（如 "RMB"、"￥"、"¥"、"," 逗号分隔符），只保留数值与正负号
12) 输出必须严格遵守 JSON 格式

## 返回JSON格式
{
  "rows": [
    {
      "row_index": 原始行号,
      "is_valid": true或false,
      "transaction_time": "...",
      "counterparty_name": "...",
      "counterparty_account": "...",
      "amount": "...",
      "summary": "...",
      "transaction_type": "...",
      "source_file": "..."
    }
  ]
}
"""


NORMALIZER_SCHEMA = {
    "type": "object",
    "properties": {
        "rows": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "row_index": {"type": "integer"},
                    "is_valid": {"type": "boolean"},
                    "transaction_time": {"type": "string"},
                    "counterparty_name": {"type": "string"},
                    "counterparty_account": {"type": "string"},
                    "amount": {"type": "string"},
                    "summary": {"type": "string"},
                    "transaction_type": {"type": "string"},
                    "source_file": {"type": "string"}
                },
                "required": [
                    "row_index",
                    "is_valid",
                    "transaction_time",
                    "counterparty_name",
                    "counterparty_account",
                    "amount",
                    "summary",
                    "transaction_type",
                    "source_file"
                ],
                "additionalProperties": False
            }
        }
    },
    "required": ["rows"],
    "additionalProperties": False
}


class FlowDataNormalizer:
    """
    AI normalizer for raw flow table rows.
    """

    def __init__(
        self,
        api_url: str,
        model: str,
        api_key: str,
        timeout: int = 60,
        max_retries: int = 3,
    ):
        self.api_url = api_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries

    def _post(self, system_prompt: str, user_message: str, response_format: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not self.api_key:
            logger.warning("No API key configured for normalizer")
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
            "max_tokens": 4000,
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
                logger.warning("Normalizer JSON decode failed: %s; response=%s", exc, text[:500])
            except Exception as exc:
                logger.warning("Normalizer request failed (attempt %d/%d): %s", attempt + 1, self.max_retries, exc)

        return None

    def _make_request(self, system_prompt: str, user_message: str) -> Optional[Dict[str, Any]]:
        object_format = {"type": "json_object"}
        return self._post(system_prompt, user_message, object_format)

    def normalize_rows(
        self,
        document_name: str,
        header_attributes: List[str],
        rows: List[Dict[str, Any]],
        source_file: str
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Normalize rows into standardized records.

        rows: list of {"row_index": int, "cells": [str,...]}
        """
        payload = {
            "document_name": document_name,
            "header_attributes": header_attributes,
            "rows": rows,
            "source_file": source_file
        }
        user_message = json.dumps(payload, ensure_ascii=False)
        result = self._make_request(SYSTEM_PROMPT_DATA_NORMALIZER, user_message)
        if not result:
            return None

        return result.get("rows", [])

    def is_available(self) -> bool:
        return bool(self.api_key)
