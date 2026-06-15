# -*- coding: utf-8 -*-
"""Document portrait extractor using LLM."""

import json
import logging
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """你是一个文档画像提取专家。请从文档内容中提取结构化画像信息。

提取字段：
1. account_type: 账户类型 (credit_card/debit_card/alipay/wechat/bank_general/unknown)
2. account_holder: 账户持有人
3. account_number_masked: 脱敏账号
4. institution: 机构名称
5. statement_period: 账单周期
6. key_observations: 关键观察
7. amount_sign_rule: 金额符号规则 (pos_income/pos_expense/no_sign/split_cols/unknown)
8. header_attributes: 表头属性列表
9. column_mapping: 列映射

请返回JSON格式：
{
    "account_type": "bank_general",
    "account_holder": "",
    "account_number_masked": "",
    "institution": "",
    "statement_period": "",
    "key_observations": [],
    "amount_sign_rule": "pos_income",
    "header_attributes": ["交易时间", "交易对手", "金额", "收支", "摘要"],
    "column_mapping": ["transaction_time", "counterparty_name", "amount", "transaction_type", "summary"]
}"""


class DocumentPortraitExtractor:
    """Extract document portrait using LLM."""

    def __init__(self, api_url: str, api_key: str, model: str, timeout: int = 30):
        self.api_url = api_url
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    async def extract(
        self,
        document_name: str,
        non_table_context: str,
        content_preview: str = "",
    ) -> Optional[Dict[str, Any]]:
        """Extract document portrait."""
        prompt = f"文档名称: {document_name}\n\n非表格内容:\n{non_table_context}"
        if content_preview:
            prompt += f"\n\n内容预览:\n{content_preview}"

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
                return json.loads(content)
        except Exception as e:
            logger.error("Failed to extract portrait: %s", e)
            return None
