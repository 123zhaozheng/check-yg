# -*- coding: utf-8 -*-
"""AI analysis agent skeleton using pydantic-ai (S6).

这是 S6 的新 agent（非 legacy 搬运）——``SYSTEM_PROMPT_ANALYSIS`` 是**占位
instructions**，明确标注"用户后续接真实审查逻辑"。本切片 agent 接入点结构
按 ``docs/research/pydantic-ai-conventions.md`` (v1.107.0) 落地：

* ``AuditDeps`` dataclass：``db: AsyncSession`` + ``task_id: int``。
* ``get_analysis_agent()``：复用 ``agent_factory.get_agent``（模块级单例）。
* ``@agent.tool`` 工具签名（留接口，实现查 flow_records ``record_type="standard"``
  记录，**只读不改**——呼应"不删减"底线）：
  - ``query_transactions(ctx, *, channel?, limit?)``
  - ``query_by_counterparty(ctx, *, counterparty)``
  - ``query_by_amount_range(ctx, *, min_amount, max_amount)``
  每个工具 docstring 成工具描述，参数成 JSON schema。
* ``run_analysis(deps)``：**占位返回** AnalysisResult（不调真实 LLM——占位 prompt
  会产生垃圾输出，结构对了即可；TODO 用户后续接真实 agent.run）。
* ``chat(deps, message_history_json, user_msg)``：用 ``ModelMessagesTypeAdapter``
  反序列化 history → 占位回复 + 序列化新 history 存回 Task.config
  (决策3)。本切片不强制调真实 LLM。

提示词保真：本文件**不触碰** normalizer/classifier/portrait 的 SYSTEM_PROMPT。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from pydantic_ai import Agent, ModelMessagesTypeAdapter, RunContext
from pydantic_core import to_json
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.agent_factory import get_agent
from app.llm.types import AnalysisResult
from app.models import FlowRecordRow
from app.models.llm_model import LLMModel
from app.models.llm_model_assignment import STAGE_AI_ANALYSIS, STAGE_AI_QA
from app.services.llm_model_service import get_stage_model

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Deps — per-request 数据走 deps=（conventions.md：deps_type 传类型，deps= 传实例）
# ---------------------------------------------------------------------------


@dataclass
class AuditDeps:
    """per-request deps for the analysis agent (conventions.md)."""

    db: AsyncSession
    task_id: int


# ---------------------------------------------------------------------------
# 占位 instructions — 结构对齐 conventions.md（任务/工具说明/输出格式）。
# 明确标注"占位"，用户后续接真实审查逻辑。**禁改** normalizer/classifier/portrait
# 的 SYSTEM_PROMPT（本文件只新增此常量）。
# ---------------------------------------------------------------------------

SYSTEM_PROMPT_ANALYSIS = """你是银行/支付流水审计异常发现助手（占位骨架）。

## 任务
对标准化流水（flow_records.record_type="standard"）运行审计异常发现，输出
异常发现列表 + 整体摘要。

## 工具说明
你可以调用以下只读查询工具获取标准化流水（不修改任何记录）：
- query_transactions: 查询标准化交易记录，可按渠道过滤、限制返回条数。
- query_by_counterparty: 按交易对手名称查询。
- query_by_amount_range: 按金额区间查询。

## 输出格式
输出 AnalysisResult：findings 列表（每项 type/severity/description/counterparty/
amount/confidence）+ summary（整体推理摘要）。severity 取 high|medium|low。

## 注意
本 instructions 为占位骨架，用户后续接入真实审查逻辑（异常检测规则、风险
阈值、推理链路等）。
"""

_MAX_TOKENS_ANALYSIS = 2000


# ---------------------------------------------------------------------------
# 阶段模型卡片预留接线（06-23-llm-model-card）
# ---------------------------------------------------------------------------
# ai_analysis / ai_qa 阶段当前是占位（不调真实 LLM）。本切片只确保它们**能**
# 按阶段读卡片（预留接线函数），等后续任务接真实 agent.run 时生效。


async def get_analysis_model(db: AsyncSession) -> Optional[LLMModel]:
    """ai_analysis 阶段指派的卡片（预留接线，占位阶段当前不调真实 LLM）。

    Returns:
        指派的 ``LLMModel`` 或 None（未指派 → 后续接真实 LLM 时回退兜底）。
    """
    return await get_stage_model(db, STAGE_AI_ANALYSIS)


async def get_ai_qa_model(db: AsyncSession) -> Optional[LLMModel]:
    """ai_qa 阶段指派的卡片（预留接线，占位阶段当前不调真实 LLM）。"""
    return await get_stage_model(db, STAGE_AI_QA)


# ---------------------------------------------------------------------------
# Agent 构造 + @agent.tool 注册（只读查 flow_records standard 记录）
# ---------------------------------------------------------------------------


def get_analysis_agent() -> Agent:
    """复用 agent_factory.get_agent 建模块级单例 agent，首调注册只读 tools。

    工具在 agent 上只能注册一次（pydantic-ai 会抛 Tool name conflicts），
    而 ``get_agent`` 按 (base_url, api_key, model, timeout, max_tokens,
    output_type, instructions, deps_type) 缓存——同 key 返回同一个 agent
    实例。所以用 agent 实例上的 ``_analysis_tools_registered`` sentinel 避免
    重复注册。``deps_type=AuditDeps`` 传类型（conventions.md），运行时
    ``agent.run(..., deps=AuditDeps(...))`` 传实例。
    """
    agent = get_agent(
        AnalysisResult,
        SYSTEM_PROMPT_ANALYSIS,
        max_tokens=_MAX_TOKENS_ANALYSIS,
        deps_type=AuditDeps,
    )
    if getattr(agent, "_analysis_tools_registered", False):
        return agent
    _register_analysis_tools(agent)
    agent._analysis_tools_registered = True  # type: ignore[attr-defined]
    return agent


def _register_analysis_tools(agent: Agent) -> None:
    """在 agent 上注册 3 个只读查询工具（查 flow_records standard 记录）。

    工具只读不改（不增删改任何 flow_records 行）——呼应"不删减"底线。
    docstring 成工具描述，参数成 JSON schema（conventions.md）。
    """

    @agent.tool
    async def query_transactions(
        ctx: RunContext[AuditDeps],
        *,
        channel: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """查询标准化流水交易记录（record_type="standard"）。

        可选按渠道过滤，默认最多返回 50 条。只读不改。

        Args:
            channel: 可选，按渠道过滤（如"银行流水"/"支付渠道"），为空则不限。
            limit: 返回条数上限，默认 50。
        """
        db = ctx.deps.db
        task_id = ctx.deps.task_id
        stmt = (
            select(FlowRecordRow)
            .where(
                FlowRecordRow.task_id == task_id,
                FlowRecordRow.record_type == "standard",
            )
            .order_by(FlowRecordRow.id.asc())
            .limit(limit)
        )
        if channel:
            stmt = stmt.where(FlowRecordRow.channel == channel)
        result = await db.execute(stmt)
        rows = result.scalars().all()
        return [_row_to_dict(r) for r in rows]

    @agent.tool
    async def query_by_counterparty(
        ctx: RunContext[AuditDeps],
        *,
        counterparty: str,
    ) -> list[dict]:
        """按交易对手名称查询标准化流水记录（record_type="standard"）。

        只读不改。

        Args:
            counterparty: 交易对手名称（精确匹配 counterparty_name）。
        """
        db = ctx.deps.db
        task_id = ctx.deps.task_id
        stmt = (
            select(FlowRecordRow)
            .where(
                FlowRecordRow.task_id == task_id,
                FlowRecordRow.record_type == "standard",
                FlowRecordRow.counterparty_name == counterparty,
            )
            .order_by(FlowRecordRow.id.asc())
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()
        return [_row_to_dict(r) for r in rows]

    @agent.tool
    async def query_by_amount_range(
        ctx: RunContext[AuditDeps],
        *,
        min_amount: float,
        max_amount: float,
    ) -> list[dict]:
        """按金额区间查询标准化流水记录（record_type="standard"）。

        金额存为字符串，工具在 Python 侧 parse 成 float 做区间过滤。只读不改。

        Args:
            min_amount: 金额下限（含）。
            max_amount: 金额上限（含）。
        """
        db = ctx.deps.db
        task_id = ctx.deps.task_id
        stmt = (
            select(FlowRecordRow)
            .where(
                FlowRecordRow.task_id == task_id,
                FlowRecordRow.record_type == "standard",
            )
            .order_by(FlowRecordRow.id.asc())
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()
        out: list[dict] = []
        for r in rows:
            try:
                amt = float(r.amount) if r.amount else None
            except (TypeError, ValueError):
                amt = None
            if amt is None:
                continue
            if min_amount <= amt <= max_amount:
                out.append(_row_to_dict(r))
        return out


def _row_to_dict(row: FlowRecordRow) -> dict:
    """精简 flow_records 行为 dict 供 agent 工具返回（只读快照）。"""
    return {
        "id": row.id,
        "channel": row.channel,
        "transaction_time": row.transaction_time,
        "counterparty_name": row.counterparty_name,
        "counterparty_account": row.counterparty_account,
        "amount": row.amount,
        "raw_amount": row.raw_amount,
        "summary": row.summary,
        "transaction_type": row.transaction_type,
    }


# ---------------------------------------------------------------------------
# run_analysis — 占位返回（不调真实 LLM，结构对了即可）
# ---------------------------------------------------------------------------


async def run_analysis(deps: AuditDeps) -> AnalysisResult:
    """运行 AI 分析，返 AnalysisResult。

    占位实现：直接返占位 findings 结构，不调真实 agent.run（避免占位 prompt
    产生垃圾输出）。结构对了即可，TODO 用户后续接真实审查逻辑（调
    ``get_analysis_agent().run(user_prompt, deps=deps)`` 并据 result.output 落库）。
    """
    # TODO(用户): 接入真实审查逻辑，例如：
    #   agent = get_analysis_agent()
    #   result = await agent.run(user_prompt, deps=deps)
    #   return result.output
    return AnalysisResult(
        findings=[],
        summary="AI 分析骨架已就绪，真实推理待接入。",
    )


# ---------------------------------------------------------------------------
# chat — 多轮对话骨架（ModelMessagesTypeAdapter 序列化 + 占位回复）
# ---------------------------------------------------------------------------


_CHAT_PLACEHOLDER_REPLY = "分析骨架已就绪，真实推理待接入。"


async def chat(
    deps: AuditDeps,
    message_history_json: str | None,
    user_msg: str,
) -> tuple[str, str]:
    """多轮对话：反序列化 history → 占位回复 → 序列化新 history 存回。

    占位实现：不调真实 agent.run，直接返占位回复 + 用
    ``ModelMessagesTypeAdapter`` 序列化占位 message_history 存回（结构通了即可，
    不强制调真实 LLM）。TODO 用户后续接真实推理：

        agent = get_analysis_agent()
        history = ModelMessagesTypeAdapter.validate_json(message_history_json or "[]")
        result = await agent.run(user_msg, deps=deps, message_history=history)
        reply = result.output  # 或 str(result.output)
        new_history_json = to_json(result.all_messages()).decode()
        return reply, new_history_json

    Args:
        deps: per-request deps（db + task_id）。
        message_history_json: 上一轮序列化的 message_history（JSON 字符串），
            为空或 "[]" 表示首轮。
        user_msg: 本轮用户提问。

    Returns:
        (reply, new_history_json)：占位回复 + 序列化后的新 history（可存回
        Task.config.analysis_chat_history）。
    """
    # 反序列化旧 history（结构校验 + 保证 model-independent 格式往返）。
    history = ModelMessagesTypeAdapter.validate_json(message_history_json or "[]")

    # 占位回复（不调真实 LLM）。
    reply = _CHAT_PLACEHOLDER_REPLY

    # 序列化占位新 history 存回。占位实现只透传旧 history（不追加 LLM 消息），
    # 保证 ModelMessagesTypeAdapter 往返结构通了即可。
    new_history_json = to_json(history).decode()
    return reply, new_history_json
