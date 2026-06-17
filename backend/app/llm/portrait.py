# -*- coding: utf-8 -*-
"""Document portrait extractor using LLM.

Ports the mature ``src/llm/document_portrait.py`` prompt and fallback behavior
into the FastAPI backend while keeping the backend's async ``httpx`` transport
and the ``extract()`` contract consumed by the extraction pipeline.
"""

import json
import logging
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)


SYSTEM_PROMPT_DOCUMENT_PORTRAIT = """你是一个银行/支付文档画像提取专家。

## 任务
根据文档名称、非表格文本内容与表格数据预览，提取文档的结构化画像信息，以及流水表格的表头属性列表及其与标准字段的映射关系。

## 画像字段说明
- account_type: 账户类型，必须为 credit_card/debit_card/alipay/wechat/bank_general/unknown 之一
- account_holder: 户名/持卡人/账户名，无法确定则为空
- account_number_masked: 脱敏账号/卡号，无法确定则为空
- institution: 银行/支付机构名称，无法确定则为空
- statement_period: 账单周期/流水时间范围，无法确定则为空
- key_observations: 关键观察列表，包含文档中的特殊标识、关键特征词等
- amount_sign_rule: 金额符号规则，必须为以下英文标识之一：
  - pos_income: 正数=收入，负数=支出（如"收入/支出金额"列，正数对应存入/转入）
  - pos_expense: 正数=支出，负数=收入（如信用卡账单，正数对应消费/刷卡）
  - no_sign: 金额无正负号，靠摘要/收支列判断
  - split_cols: 收入/支出分两列（或借方/贷方双列）
  - unknown: 无法判断
- header_attributes: 有序数组，按列顺序列出流水表格的表头名
- column_mapping: 有序数组，与 header_attributes 一一对应，值为标准字段名/数组/null

## 判断要点
- 文件名中的"信用卡/贷记卡/Credit"→ account_type=credit_card
- 文件名中的"储蓄卡/借记卡"→ account_type=debit_card
- 文件名中的"支付宝/Alipay"→ account_type=alipay
- 文件名中的"微信/WeChat"→ account_type=wechat
- 非表格文本中的账户信息、账单周期、机构名称等也应提取
- 特别注意提取年份信息：非表格文本中出现的年份（如"2025年"、"2026年"）、账单出账日、结算周期等，这些信息对后续流水日期标准化至关重要，务必记录到 statement_period 或 key_observations 中
- 无法确定的字段留空，不要猜测
- 观察金额列数值是否包含负号：如有负号，判断正数和负数分别对应什么交易类型
- 若金额列全部为正数或绝对值，无负号 → no_sign
- 若存在"收入金额"+"支出金额"或"借方金额"+"贷方金额"两列 → split_cols
- 若正数行对应存入/转入/贷款发放等，负数行对应扣款/转出/还款等 → pos_income
- 若正数行对应消费/刷卡/分期等，负数行对应还款/退款等（信用卡常见） → pos_expense

## 映射指导
8个标准字段：transaction_time, counterparty_name, counterparty_account, amount, raw_amount, summary, transaction_type, source_file
映射规则：
- 原表头名与标准字段语义匹配时映射为对应标准字段名字符串
- 一对多时用数组，如"交易描述"同时映射到 ["counterparty_name","summary"]
- 无法映射时为 null
- split_cols 场景：借方金额/贷方金额两列都映射到 "amount"
- raw_amount 和 source_file 不需要映射（raw_amount 由标准化器从 amount 列推导，source_file 由代码填充）

## 输入
输入数据（文档名称、非表格内容、表格数据预览）在下方用户消息中以JSON格式提供。

## 返回JSON格式
{
  "account_type": "credit_card | debit_card | alipay | wechat | bank_general | unknown",
  "account_holder": "",
  "account_number_masked": "",
  "institution": "",
  "statement_period": "",
  "key_observations": [],
  "amount_sign_rule": "pos_income | pos_expense | no_sign | split_cols | unknown",
  "header_attributes": ["交易日期", "对方户名", "对方账号", "摘要", "借贷", "交易金额", "币种"],
  "column_mapping": ["transaction_time", "counterparty_name", "counterparty_account", "summary", "transaction_type", "amount", null]
}
"""


# Portrait output contract — documents the fields the normalizer and extractor rely on.
PORTRAIT_FIELDS = (
    "account_type",
    "account_holder",
    "account_number_masked",
    "institution",
    "statement_period",
    "key_observations",
    "amount_sign_rule",
    "header_attributes",
    "column_mapping",
)


class DocumentPortraitExtractor:
    """Extract a structured document portrait using an OpenAI-compatible LLM.

    Output contract: a dict with the keys in :data:`PORTRAIT_FIELDS`, or ``None``
    when extraction fails (network error, malformed JSON, or empty content).
    """

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
            logger.warning("No API key configured for portrait extractor")
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
                    "Portrait JSON decode failed: %s; response=%s",
                    exc,
                    text[:500],
                )
            except Exception as exc:
                logger.warning(
                    "Portrait request failed (attempt %d/%d): %s",
                    attempt + 1,
                    self.max_retries,
                    exc,
                )

        return None

    async def extract(
        self,
        document_name: str,
        non_table_context: str,
        content_preview: str = "",
    ) -> Optional[Dict[str, Any]]:
        """
        提取文档结构化画像

        Args:
            document_name: 文档文件名
            non_table_context: 从文档中提取的非表格文本内容
            content_preview: 表格数据预览（用于金额符号规则识别）

        Returns:
            画像 dict（成功）或 None（失败）
        """
        if not self.api_key:
            return None

        logger.info(
            "请求文档画像提取: document_name=%s, context_length=%d",
            document_name,
            len(non_table_context or ""),
        )

        user_message = json.dumps(
            {
                "document_name": document_name,
                "non_table_context": non_table_context or "",
                "content_preview": content_preview or "",
            },
            ensure_ascii=False,
        )

        result = await self._post(SYSTEM_PROMPT_DOCUMENT_PORTRAIT, user_message)
        if result is not None:
            logger.info(
                "文档画像提取成功: document_name=%s, 画像结果=%s",
                document_name,
                json.dumps(result, ensure_ascii=False),
            )
        return result

    def is_available(self) -> bool:
        return bool(self.api_key)
