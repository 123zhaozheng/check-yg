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
4) 你必须先结合 document_name、document_type、document_type_hints 判断文档属于哪一类：信用卡账单、借记卡/银行卡流水、支付宝/微信等支付账户流水。
5) amount 优先取“交易金额/发生额/金额(元)/支出/收入/借方/贷方”等列：
   - 若同时有收入/支出两列，优先取非空值，并据此推断 transaction_type
   - 不允许仅凭正负号机械判断 transaction_type，必须结合文档类型、列名、摘要/商户语义综合判断
6) credit card（信用卡）流水特殊规则，优先级高于正负号：
   - 信用卡账单中，消费/刷卡/付款/分期/手续费/利息/年费/取现/违约金，通常应判为“支出”，即使金额显示为正数
   - 信用卡账单中，还款/退款/退货/冲正/返现/调账转入/利息返还，通常应判为“收入”，即使金额显示形式与普通借记卡不同
   - 信用卡场景下，amount 保留原始金额文本，但 transaction_type 必须反映交易性质，而不是只反映金额正负号
   - 交易描述/商户名称 → counterparty_name
   - 若无明确摘要列，summary 可与 counterparty_name 相同
7) 借记卡/普通银行流水常见规则：
   - 若无更强语义线索，负数通常判为支出，正数通常判为收入
   - “借方/支出/转出/付款/消费/扣款”优先判为支出
   - “贷方/收入/转入/收款/入账”优先判为收入
8) 支付宝/微信常见：
   - 交易对方/商户名称 → counterparty_name
   - 商品/交易类型/备注 → summary
9) counterparty_account 仅在有明确账号/卡号列时填入，否则为空
10) 过滤噪音行：合计/小计/总计/余额/页脚/页眉/空行等，is_valid=false
11) 日期时间统一输出为 "YYYY-MM-DD hh:mm:ss"：
   - 只有日期时补全时间为 "00:00:00"
   - 有时间但缺少秒时补全为 ":00"
12) 金额清洗：去除金额前缀/符号（如 "RMB"、"￥"、"¥"、"," 逗号分隔符），只保留数值与正负号
13) 输出必须严格遵守 JSON 格式

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
        self.session = requests.Session()
        # 避免 requests 继承 Windows 系统代理，导致直连 LLM 接口前就在本地代理层失败。
        self.session.trust_env = False

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
                response = self.session.post(url, headers=headers, json=payload, timeout=self.timeout)
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
        document_context = self._infer_document_context(document_name)
        payload = {
            "document_name": document_name,
            "document_type": document_context["document_type"],
            "document_type_hints": document_context["document_type_hints"],
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

    @staticmethod
    def _infer_document_context(document_name: str) -> Dict[str, Any]:
        name = str(document_name or "").lower()
        if any(keyword in name for keyword in ["信用卡", "credit", "贷记卡"]):
            return {
                "document_type": "credit_card_statement",
                "document_type_hints": [
                    "这是信用卡账单或信用卡交易明细",
                    "信用卡场景下，消费金额显示为正数也可能属于支出",
                    "应优先根据消费、还款、退款、手续费等交易语义判断收支方向",
                ],
            }
        if any(keyword in name for keyword in ["支付宝", "alipay"]):
            return {
                "document_type": "alipay_statement",
                "document_type_hints": [
                    "这是支付宝流水",
                    "优先结合交易对方、收支标记、商品说明判断收支方向",
                ],
            }
        if any(keyword in name for keyword in ["微信", "wechat", "weixin"]):
            return {
                "document_type": "wechat_statement",
                "document_type_hints": [
                    "这是微信流水",
                    "优先结合交易对方、收支标记、商品说明判断收支方向",
                ],
            }
        return {
            "document_type": "bank_or_general_statement",
            "document_type_hints": [
                "这是普通银行流水或通用交易流水",
                "优先根据列名、借贷方向、收支标记、摘要语义综合判断收支方向",
            ],
        }
