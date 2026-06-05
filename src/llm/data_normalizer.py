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
给定文档画像、表头属性列表、以及若干行原始表格数据，输出标准化流水记录。

## 标准字段
1) transaction_time - 交易时间（日期或日期时间）
2) counterparty_name - 交易对手/商户名称
3) counterparty_account - 交易对手账号/卡号（仅纯数字/卡号，无则为空）
4) amount - 交易金额（正数，不含负号）
5) raw_amount - 原始金额（保留源文档原始正负号，如"-795.42"、"1200.00"，无符号则为原值）
6) summary - 摘要/备注/交易说明/商品信息
7) transaction_type - 收支类型（只允许"收入"或"支出"）
8) source_file - 来源文件名

## 标准字段映射参考（从左到右优先级递减）
transaction_time: 交易时间 > 交易日期 > 记账日期 > 入账日期 > 日期
counterparty_name: 对方户名 > 商户名称 > 交易对方 > 对方名称 > 交易描述
counterparty_account: 对方账号 > 对方卡号（仅数字/卡号，不含开户行名称）
amount: 交易金额 > 发生额 > 金额(元) > 金额 > 借方金额/贷方金额 > 收入/支出
summary: 摘要 > 备注 > 交易说明 > 商品说明 > 用途 > 交易描述
transaction_type: 收支 > 收/支 > 借贷方向 > 借方/贷方

## 铁规则
1. amount 始终为正数，禁止出现负号；raw_amount 保留原始正负号
2. transaction_type 只允许"收入"或"支出"
3. counterparty_account 仅填纯数字账号/卡号，禁止填入开户行、银行名称等非数字内容，无账号列为空
4. 过滤噪音行（合计/小计/总计/余额/页脚/页眉/空行），is_valid=false

## 收支方向判断（仅代码无法确定时由你判断）
代码已根据 amount_sign_rule + raw_amount 正负号确定收支方向的场景，你无需再判断。以下场景需你判断：
- amount_sign_rule=no_sign：无正负号，按摘要/收支列语义判断
- amount_sign_rule=split_cols：收入列→"收入"，支出列→"支出"
- amount_sign_rule=unknown：综合判断，正负号优先于摘要
- account_type=credit_card：按交易语义判断（消费→支出，还款/退款→收入）

## 字段清洗
1. 日期统一 "YYYY-MM-DD hh:mm:ss"，仅日期补 "00:00:00"，缺秒补 ":00"
2. 金额去除前缀（"RMB""￥""¥"", ""），amount 去负号，raw_amount 保留原值
3. 若只有一个"交易描述/商户名称"列，counterparty_name 与 summary 可相同

## 文档画像
画像数据在下方用户消息中提供，请参考画像信息进行标准化。

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
      "raw_amount": "...",
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
                    "raw_amount": {"type": "string"},
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
                    "raw_amount",
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

    def _render_prompt(self) -> str:
        """Return the normalizer system prompt, loading from config if available."""
        from ..config import get_config

        config = get_config()
        return config.prompt_normalizer or SYSTEM_PROMPT_DATA_NORMALIZER

    def normalize_rows(
        self,
        document_name: str,
        header_attributes: List[str],
        rows: List[Dict[str, Any]],
        source_file: str,
        document_portrait: Optional[Dict[str, Any]] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Normalize rows into standardized records.

        rows: list of {"row_index": int, "cells": [str,...]}
        document_portrait: structured portrait dict from DocumentPortraitExtractor.
            If None, fallback context is inferred from document_name.
        """
        system_prompt = self._render_prompt()

        payload = {
            "document_portrait": document_portrait,
            "header_attributes": header_attributes,
            "rows": rows,
            "source_file": source_file,
        }
        user_message = json.dumps(payload, ensure_ascii=False)
        result = self._make_request(system_prompt, user_message)
        if not result:
            return None

        return result.get("rows", [])

    def is_available(self) -> bool:
        return bool(self.api_key)

    @staticmethod
    def _infer_document_context(document_name: str) -> Dict[str, Any]:
        """
        Infer document context from file name (fallback when portrait extraction fails).

        Preserved as fallback for graceful degradation.
        """
        name = str(document_name or "").lower()
        if any(keyword in name for keyword in ["信用卡", "credit", "贷记卡"]):
            return {
                "account_type": "credit_card",
                "document_type": "credit_card_statement",
                "document_type_hints": [
                    "这是信用卡账单或信用卡交易明细",
                    "信用卡场景下，消费金额显示为正数也可能属于支出",
                    "应优先根据消费、还款、退款、手续费等交易语义判断收支方向",
                ],
            }
        if any(keyword in name for keyword in ["支付宝", "alipay"]):
            return {
                "account_type": "alipay",
                "document_type": "alipay_statement",
                "document_type_hints": [
                    "这是支付宝流水",
                    "优先结合交易对方、收支标记、商品说明判断收支方向",
                ],
            }
        if any(keyword in name for keyword in ["微信", "wechat", "weixin"]):
            return {
                "account_type": "wechat",
                "document_type": "wechat_statement",
                "document_type_hints": [
                    "这是微信流水",
                    "优先结合交易对方、收支标记、商品说明判断收支方向",
                ],
            }
        return {
            "account_type": "bank_general",
            "document_type": "bank_or_general_statement",
            "document_type_hints": [
                "这是普通银行流水或通用交易流水",
                "优先根据列名、借贷方向、收支标记、摘要语义综合判断收支方向",
            ],
        }
