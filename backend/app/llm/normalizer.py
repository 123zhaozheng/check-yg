# -*- coding: utf-8 -*-
"""Flow data normalizer using pydantic-ai.

提示词逐字搬运自 legacy ``src/llm/data_normalizer.py``（硬底线：提示词
保真），只把调用层从自写 httpx 换成 pydantic-ai agent（output_type=
NormalizedRows）。``normalize()`` 对外契约不变：成功返 list[row dict]（含
raw_amount/is_valid），失败返 []。保留 ``_infer_document_context`` 文件名
兜底。落地遵循 ``docs/research/pydantic-ai-conventions.md`` (v1.107.0)。

Parity guarantees versus the original prompt:

* ``amount`` is always positive (no sign); ``raw_amount`` preserves the source sign.
* ``transaction_type`` is restricted to "收入" / "支出".
* Date normalization includes missing-year inference from the portrait.
* Noise rows (totals/balances/headers) are filtered via ``is_valid=false``.
* A filename-based document context fallback is preserved for graceful degradation.
"""

import json
import logging
from typing import Any, Optional

from pydantic_ai import ModelRetry

from app.llm.agent_factory import get_agent
from app.llm.types import NormalizedRow, NormalizedRows

logger = logging.getLogger(__name__)


SYSTEM_PROMPT_DATA_NORMALIZER = """你是一个银行/支付流水数据标准化专家。

## 任务
给定文档画像（含列映射）以及若干行原始表格数据，输出标准化流水记录。

## 标准字段
1) transaction_time - 交易时间（日期或日期时间）
2) counterparty_name - 交易对手/商户名称
3) counterparty_account - 交易对手账号/卡号（仅纯数字/卡号，无则为空）
4) amount - 交易金额（正数，不含负号）
5) raw_amount - 原始金额（保留源文档原始正负号，如"-795.42"、"1200.00"，无符号则为原值）
6) summary - 摘要/备注/交易说明/商品信息
7) transaction_type - 收支类型（只允许"收入"或"支出"）
8) source_file - 来源文件名

## 列映射规则
用户消息中 document_portrait 包含 header_attributes 和 column_mapping 两个有序数组，一一对应。
- 严格按 column_mapping 填充，映射到的列内容原封不动还原（不做改写/缩写/翻译）
- 映射值为 null 的列忽略
- 映射值为数组的列，该列内容填入数组中所有目标字段
- transaction_type：允许语义归纳（如"借"→"支出"，"贷"→"收入"，"收"→"收入"）
- summary：允许从多列拼接或提炼关键词
- 其余字段（transaction_time, counterparty_name, counterparty_account, amount）必须原封不动还原原文档内容
- 若 column_mapping 缺失，尽力根据行内容自行判断映射

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
2. 日期缺年推断：若表格日期仅含月日无年份（如"12/15"、"1月3日"），必须结合画像信息推断年份：
   - 优先使用 statement_period 中的年份或日期范围
   - 若 account_type=credit_card 且画像含出账单日/账单周期：注意账单跨年场景（如1月出账单覆盖上年12月消费，则12月日期应为上一年）
   - 参考 key_observations 中的年份提示
   - 无法推断年份时保持原样，禁止猜测
3. 金额去除前缀（"RMB""￥""¥"", ""），amount 去负号，raw_amount 保留原值
4. 若只有一个"交易描述/商户名称"列，counterparty_name 与 summary 可相同

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

_MAX_TOKENS_NORMALIZER = 4000

_VALID_TRANSACTION_TYPES = {"收入", "支出"}


def _validate_normalized_rows(output: NormalizedRows) -> NormalizedRows:
    """output_validator：兜底字段完整性 + 铁规则（呼应"清洗不删减"底线）。

    校验失败抛 ``ModelRetry``，反馈给模型重试（消耗 1 次 output 重试预算）。
    字段完整性由 pydantic schema 保证（缺字段直接校验失败），这里补铁规则：
    transaction_type 只允许"收入"/"支出"、amount 不含负号。
    """
    for row in output.rows:
        if row.transaction_type and row.transaction_type not in _VALID_TRANSACTION_TYPES:
            raise ModelRetry(
                f"transaction_type 只允许'收入'或'支出'，收到: {row.transaction_type!r} (row_index={row.row_index})"
            )
        if row.amount and "-" in row.amount:
            raise ModelRetry(
                f"amount 必须为正数不含负号，收到: {row.amount!r} (row_index={row.row_index})"
            )
    return output


class FlowDataNormalizer:
    """Normalize raw flow table rows into standardized records via a pydantic-ai agent.

    Output contract: a list of row dicts, each with ``is_valid`` and the standard
    fields including ``raw_amount`` (preserving the source sign) and positive
    ``amount``. Returns an empty list when normalization fails.
    """

    def __init__(self, api_url: str, api_key: str, model: str, timeout: int = 60, max_retries: int = 3):
        self.api_url = api_url
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self._agent = None  # lazy-build，注册 output_validator

    def _get_agent(self):
        if self._agent is None:
            agent = get_agent(
                NormalizedRows,
                SYSTEM_PROMPT_DATA_NORMALIZER,
                base_url=self.api_url,
                api_key=self.api_key,
                model=self.model,
                timeout=self.timeout,
                max_tokens=_MAX_TOKENS_NORMALIZER,
            )

            @agent.output_validator
            async def _validator(_ctx, output: NormalizedRows) -> NormalizedRows:
                return _validate_normalized_rows(output)

            self._agent = agent
        return self._agent

    async def normalize(
        self,
        rows: list[list[str]],
        document_portrait: Optional[dict[str, Any]] = None,
        source_file: str = "",
    ) -> list[dict[str, Any]]:
        """
        将原始表格行标准化为统一流水记录

        Args:
            rows: 原始行数据（每行为单元格字符串列表）
            document_portrait: 文档画像，含 header_attributes 与 column_mapping。
                为 None 时退化为基于文件名的上下文推断。
            source_file: 来源文件名

        Returns:
            标准化记录列表，每项含 is_valid 与标准字段（含 raw_amount）。
            失败时返回空列表。
        """
        if not rows:
            return []

        portrait = document_portrait
        if portrait is None:
            portrait = self._infer_document_context(source_file)

        # Convert flat string rows into {row_index, cells} payloads so the
        # column_mapping rules in the prompt can resolve columns by position.
        payload_rows = [
            {"row_index": index, "cells": [str(cell) for cell in row]}
            for index, row in enumerate(rows)
        ]
        user_message = json.dumps(
            {
                "document_portrait": portrait,
                "rows": payload_rows,
                "source_file": source_file,
            },
            ensure_ascii=False,
        )

        try:
            result = await self._get_agent().run(user_message)
        except Exception as exc:
            logger.warning("Normalizer agent.run 失败: source_file=%s, %s", source_file, exc)
            return []

        normalized: NormalizedRows = result.output
        return [row.model_dump() for row in normalized.rows]

    @staticmethod
    def _infer_document_context(document_name: str) -> dict[str, Any]:
        """
        从文件名推断文档上下文（画像提取失败时的兜底）

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

    def is_available(self) -> bool:
        return bool(self.api_key)
