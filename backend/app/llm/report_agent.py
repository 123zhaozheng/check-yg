# -*- coding: utf-8 -*-
"""报告章节生成 agent —— pydantic-ai（06-28-report-fusion-word-cover Phase 2）.

每个章节一个 ``agent.run``，**上下文喂数据**（MVP 不挂工具，更简）：调用方
``build_all_chapters`` 先 ``_aggregate(task)`` 聚合真实审查数据，按章切片成
JSON 上下文，传给 ``run_chapter(deps, title, context_json)``。agent 围绕真实
数据写分析正文（markdown），**严禁编造数字/对手方/日期**（系统提示词硬底线 +
格式约束子集，渲染器只认子集）。

落地严格遵循 ``docs/research/pydantic-ai-conventions.md`` (v1.107.0)：
* ``ReportDeps`` dataclass：``db: AsyncSession`` + ``task_id: int``（MVP 上下文
  喂数据，不挂工具，故无 user_id）。
* ``get_report_agent(chapter_title, *, model)`` → ``get_agent`` 单例（缓存 key
  含 instructions → 每章各自单例）；``output_type=str``（章节 markdown 正文）。
* 复用 ``_resolve_agent_params``（从 analysis.py import，不重写） +
  ``get_report_generation_model``（接通 report_generation 阶段卡片 → env 兜底）。
* ``run_chapter`` → ``agent.run(context_json, deps=deps)`` → ``result.output``。
  LLM 失败抛异常由调用方 try/except 回退模板（兜底 spec）。

格式约束子集（硬约束，渲染器只认这些）：
  * 正文从 ``##``/``###`` 起（章标题系统已加，不要自己写 ``#`` 一级）。
  * 段落空行分隔；要点用 ``- `` 列表；强调用 ``**加粗**``；
    表格用标准 markdown 表格（``| a | b |`` + ``|---|---|``）。
  * **禁用**：HTML、代码块、``# `` 一级标题、嵌套列表、图片。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from pydantic_ai import Agent
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.llm.agent_factory import get_agent
from app.llm.analysis import _resolve_agent_params
from app.models.llm_model import LLMModel

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Deps — per-request 数据走 deps=（conventions.md：deps_type 传类型，deps= 传实例）
# ---------------------------------------------------------------------------


@dataclass
class ReportDeps:
    """per-request deps for the report chapter agents.

    MVP 上下文喂数据（不挂工具），故只需 ``db`` + ``task_id``。
    """

    db: AsyncSession
    task_id: int


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# 报告章节 max_tokens（足够 8 章 markdown 正文，含表格）。
_MAX_TOKENS_CHAPTER = 3000


# 共用系统提示词（每章注入）—— 数据接地硬底线 + 格式约束子集（prd §一.2）。
_COMMON_INSTRUCTIONS = """你是银行/支付流水审查报告撰写专家。根据提供的**真实审查数据**撰写专业、丰满、格式规范的报告章节（markdown）。

## 数据接地（硬底线）
- **只能使用下方提供的真实数据**，严禁编造任何数字、对手方名称、日期、金额。
- 提供的数据里没有的信息，一律写「未发现」或「无相关数据」，不要凑数。
- 引用金额、笔数、对手方时，必须来自提供的 JSON 上下文。

## 格式约束子集（严格遵守，渲染器只认这些）
- 正文从 `##`（节）/ `###`（小节）起。**不要**写 `#` 一级标题（章标题系统已加）。
- 段落用空行分隔。
- 要点用 `- ` 列表。
- 强调用 `**加粗**`。
- 表格用标准 markdown 表格：`| 列A | 列B |` 换行 `| --- | --- |` 再跟数据行。
- **禁止**：HTML 标签、代码块（```）、一级标题 `# `、嵌套列表、图片。

## 语言
专业、客观、简练。中文。"""


# 章节专项 instructions（每章说明该章要写什么）。
# key = 章节标题（与 CHAPTER_TITLES 对齐）。
_CHAPTER_INSTRUCTIONS: dict[str, str] = {
    "概述": (
        "本章写任务背景与审查范围总述。基于提供的任务元信息（标题、被审查人、"
        "审查期间）和流水统计（标准化记录数），概述本次审查的对象、范围与目的。"
        "2-3 段即可。"
    ),
    "被审查对象": (
        "本章写被审查员工的基本信息（姓名、工号、部门，来自任务元信息）与审查期间。"
        "客观陈述，不做评价。"
    ),
    "数据范围": (
        "本章解读本次审查的数据范围。基于提供的流水统计（标准化记录数、文档数、"
        "渠道分布、清洗提交时间），说明数据覆盖的渠道、时间跨度、记录规模。"
        "可用列表呈现渠道分布。"
    ),
    "完整性校验（余额）": (
        "本章解读余额校验结论。基于提供的余额校验发现（balance_check findings），"
        "逐条说明不符项（文档、金额差异）。若无不符项，写「余额校验通过」。"
        "不要编造校验数字。"
    ),
    "关键词审查": (
        "本章分析关键词审查命中情况。基于提供的关键词命中明细（confirmed），"
        "汇总命中总数、按风险等级与匹配类型分组，并列出关键命中明细。"
        "若无命中，写「未发现已确认命中」。可用 markdown 表格呈现明细。"
    ),
    "异常发现汇总": (
        "本章汇总 AI 分析的异常发现。基于提供的已采纳发现（accepted findings），"
        "按风险等级（高/中/低）分组汇总总数，客观陈述发现类型。"
        "若无已采纳发现，写「未发现已采纳的异常发现」。"
    ),
    "风险评估": (
        "本章基于已采纳发现做风险研判。若无高风险发现，整体风险等级为较低/中等；"
        "若有高风险发现，逐条研判（类型、金额、对手方，均来自提供数据）。"
        "可用列表呈现高风险发现。不要编造风险结论。"
    ),
    "结论建议": (
        "本章给结论与建议。基于风险评估结论，给出客观的复核建议。"
        "若存在高风险发现，建议重点复核；否则建议常规复核。简练，2-3 条建议。"
    ),
}


def _build_chapter_instructions(chapter_title: str) -> str:
    """拼装章节 instructions = 共用系统提示词 + 本章专项。

    若 ``chapter_title`` 不在专项 dict 里（理论上不会），用通用兜底。
    """
    specific = _CHAPTER_INSTRUCTIONS.get(
        chapter_title,
        "基于提供的真实数据撰写本章正文。只可用提供的数据，不编造。",
    )
    return f"{_COMMON_INSTRUCTIONS}\n\n## 本章节要求\n{specific}"


# ---------------------------------------------------------------------------
# 阶段模型卡片接线（STAGE_REPORT_GENERATION）—— 接通！（prd 验收项）
# ---------------------------------------------------------------------------


async def get_report_generation_model(db: AsyncSession) -> Optional[LLMModel]:
    """report_generation 阶段指派的卡片（报告章节 agent 用）。

    Returns:
        指派的 ``LLMModel`` 或 None（未指派 → 回退 env settings）。
    """
    from app.services.llm_model_service import get_stage_model
    from app.models.llm_model_assignment import STAGE_REPORT_GENERATION

    return await get_stage_model(db, STAGE_REPORT_GENERATION)


# ---------------------------------------------------------------------------
# 报告 agent —— get_report_agent（模块级单例，每章各自缓存）
# ---------------------------------------------------------------------------


def get_report_agent(
    chapter_title: str, *, model: Optional[LLMModel] = None
) -> Agent:
    """建/取报告章节 agent（模块级单例，缓存 key 含 instructions → 每章各自单例）。

    ``output_type=str``（章节 markdown 正文）。``instructions`` = 共用系统提示词 +
    本章专项（prd §一.2）。``deps_type=ReportDeps``（conventions.md：传类型）。
    复用 ``_resolve_agent_params``（report_generation 阶段卡片 → env 兜底）。
    """
    instructions = _build_chapter_instructions(chapter_title)
    params = _resolve_agent_params(model, fallback_max_tokens=_MAX_TOKENS_CHAPTER)
    agent = get_agent(
        str,
        instructions,
        base_url=params["base_url"],
        api_key=params["api_key"],
        model=params["model"],
        timeout=params["timeout"],
        max_tokens=params["max_tokens"],
        thinking=params["thinking"],
        temperature=params["temperature"],
        deps_type=ReportDeps,
    )
    return agent


async def run_chapter(
    deps: ReportDeps,
    chapter_title: str,
    context_json: str,
    *,
    model: Optional[LLMModel] = None,
) -> str:
    """跑单个章节：本章 instructions 注入 agent → agent.run(context_json) → markdown 正文。

    Args:
        deps: per-request deps（db + task_id）。
        chapter_title: 章节标题（用于选 instructions）。
        context_json: 本章所需聚合数据的 JSON 字符串（真实审查数据，agent 围绕它写）。
        model: report_generation 阶段指派的卡片（None → 回退 env settings）。

    Returns:
        章节正文 markdown 字符串。

    Raises:
        Exception: LLM 不可用 / agent 失败时抛出，由调用方 try/except 回退模板。
    """
    agent = get_report_agent(chapter_title, model=model)
    user_prompt = (
        f"请根据下方真实审查数据，撰写「{chapter_title}」章节的正文（markdown）。"
        f"严格只用提供的数据，遵守格式约束子集。\n\n"
        f"## 审查数据（JSON）\n{context_json}"
    )
    result = await agent.run(user_prompt, deps=deps)
    return str(result.output)
