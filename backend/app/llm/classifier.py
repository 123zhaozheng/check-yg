# -*- coding: utf-8 -*-
"""Flow table classifier using LLM."""

import json
import logging
from typing import Any, Dict

import httpx

from ..parsers.base import RawTable

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """你是一个银行流水表格识别专家。请判断给定的表格是否为银行/支付流水表格。

判断标准：
1. 表格包含交易记录（日期、金额、对手方等）
2. 表格是结构化的（有明确的列和行）
3. 表格内容是金融交易相关

请返回JSON格式：
{
    "is_flow_table": true/false,
    "confidence": 0-100的置信度,
    "reason": "判断理由"
}"""


class FlowTableClassifier:
    """Classify tables as flow tables or not using LLM."""

    def __init__(self, api_url: str, api_key: str, model: str, timeout: int = 30):
        self.api_url = api_url
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    async def classify(self, table: RawTable, document_name: str) -> Dict[str, Any]:
        """Classify a table as flow table or not."""
        preview = table.get_preview(max_rows=10)
        prompt = f"文档名称: {document_name}\n\n表格预览:\n{preview}"

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
            logger.error("Failed to classify table: %s", e)
            return {"is_flow_table": False, "confidence": 0, "reason": str(e)}
