# -*- coding: utf-8 -*-
"""Document portrait extractor using pydantic-ai.

提示词逐字搬运自 legacy ``src/llm/document_portrait.py``（硬底线：提示词
保真），只把调用层从自写 httpx 换成 pydantic-ai agent（output_type=
DocumentPortrait）。``extract()`` 对外契约不变：成功返 dict，失败返 None。
落地遵循 ``docs/research/pydantic-ai-conventions.md`` (v1.107.0)。
"""

import json
import logging
from typing import Any, Optional

from app.llm.agent_factory import get_agent
from app.llm.types import DocumentPortrait

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
9个标准字段：transaction_time, counterparty_name, counterparty_account, amount, raw_amount, summary, transaction_type, source_file, balance
映射规则：
- 原表头名与标准字段语义匹配时映射为对应标准字段名字符串
- 一对多时用数组，如"交易描述"同时映射到 ["counterparty_name","summary"]
- 无法映射时为 null
- split_cols 场景：借方金额/贷方金额两列都映射到 "amount"
- raw_amount 和 source_file 不需要映射（raw_amount 由标准化器从 amount 列推导，source_file 由代码填充）
- 源表头含「余额/账户余额/当前余额/结余」→ 映射为 "balance"（账户余额列，本笔交易后的账户余额）

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
  "header_attributes": ["交易日期", "对方户名", "对方账号", "摘要", "借贷", "交易金额", "账户余额", "币种"],
  "column_mapping": ["transaction_time", "counterparty_name", "counterparty_account", "summary", "transaction_type", "amount", "balance", null]
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

_MAX_TOKENS_PORTRAIT = 1500


class DocumentPortraitExtractor:
    """Extract a structured document portrait using a pydantic-ai agent.

    Output contract: a dict with the keys in :data:`PORTRAIT_FIELDS`, or ``None``
    when extraction fails (network error, invalid output, or empty content).
    """

    def __init__(
        self,
        api_url: str,
        api_key: str,
        model: str,
        timeout: int = 60,
        max_retries: int = 3,
        max_tokens: int = _MAX_TOKENS_PORTRAIT,
        thinking: Optional[str] = None,
        temperature: Optional[float] = None,
    ):
        self.api_url = api_url
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.max_tokens = max_tokens
        self.thinking = thinking
        self.temperature = temperature

    def _agent(self):
        return get_agent(
            DocumentPortrait,
            SYSTEM_PROMPT_DOCUMENT_PORTRAIT,
            base_url=self.api_url,
            api_key=self.api_key,
            model=self.model,
            timeout=self.timeout,
            max_tokens=self.max_tokens,
            thinking=self.thinking,
            temperature=self.temperature,
        )

    async def extract(
        self,
        document_name: str,
        non_table_context: str,
        content_preview: str = "",
    ) -> Optional[dict[str, Any]]:
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
            logger.warning(
                "文档画像提取跳过（未配置 LLM api_key → 返回 None，hover 将显示「画像待生成」）: "
                "document_name=%s",
                document_name,
            )
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

        try:
            result = await self._agent().run(user_message)
        except Exception as exc:
            # 失败诊断要够厚：画像生成失败的根因有好几种（reasoning 模型烧光
            # token 未输出 tool_call / 端点返回空壳 choices / 网络超时 / schema
            # 校验失败），光打 exc 看不出来。把类型+消息都打上，方便从控制台
            # 直接定位为什么 hover 还是「画像待生成」。
            logger.warning(
                "文档画像提取失败（将返回 None → hover 显示「画像待生成」）: "
                "document_name=%s, 异常类型=%s, 异常=%s",
                document_name,
                type(exc).__name__,
                exc,
            )
            return None

        portrait: DocumentPortrait = result.output
        data = portrait.model_dump()
        logger.info(
            "文档画像提取成功: document_name=%s, 画像结果=%s",
            document_name,
            json.dumps(data, ensure_ascii=False),
        )
        return data

    def is_available(self) -> bool:
        return bool(self.api_key)
