# -*- coding: utf-8 -*-
"""Flow data normalizer using LLM."""

import json
import logging
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """你是一个银行流水数据标准化专家。请将原始流水行数据标准化为统一格式。

标准化规则：
1. 交易时间: 统一为 YYYY-MM-DD HH:MM:SS 格式
2. 金额: 统一为数字，收入为正，支出为负
3. 收支类型: 统一为 "收入" 或 "支出"
4. 交易对手: 清理多余空格和符号
5. 摘要: 清理多余空格和符号

请返回JSON格式：
{
    "rows": [
        {
            "transaction_time": "2024-01-01 12:00:00",
            "counterparty_name": "张三",
            "counterparty_account": "6222000000000000",
            "amount": "100.00",
            "summary": "转账",
            "transaction_type": "收入"
        }
    ]
}"""


class FlowDataNormalizer:
    """Normalize flow table data using LLM."""

    def __init__(self, api_url: str, api_key: str, model: str, timeout: int = 60):
        self.api_url = api_url
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    async def normalize(
        self,
        rows: List[List[str]],
        document_portrait: Optional[Dict[str, Any]] = None,
        source_file: str = "",
    ) -> List[Dict[str, Any]]:
        """Normalize raw table rows."""
        prompt = f"原始数据行:\n{json.dumps(rows, ensure_ascii=False)}"
        if document_portrait:
            prompt += f"\n\n文档画像:\n{json.dumps(document_portrait, ensure_ascii=False)}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.api_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.1,
                        "response_format": {"type": "json_object"},
                    },
                )
                response.raise_for_status()
                result = response.json()
                content = result["choices"][0]["message"]["content"]
                data = json.loads(content)
                return data.get("rows", [])
        except Exception as e:
            logger.error("Failed to normalize rows: %s", e)
            return []

    @staticmethod
    def infer_transaction_type(raw_amount: str, amount_sign_rule: str) -> Optional[str]:
        """Infer transaction type from raw amount and sign rule."""
        if not raw_amount:
            return None

        raw = str(raw_amount).strip()
        has_negative = raw.startswith("-")

        if amount_sign_rule == "pos_income":
            return "支出" if has_negative else "收入"
        elif amount_sign_rule == "pos_expense":
            return "收入" if has_negative else "支出"
        elif amount_sign_rule == "split_cols":
            return None  # LLM should handle this
        elif amount_sign_rule == "no_sign":
            return None  # Must rely on LLM/summary

        return None
