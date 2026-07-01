# -*- coding: utf-8 -*-
"""AI 关键词生成 agent —— pydantic-ai（07-01-ai-50）.

用于「关键词库」页「新建关键词卡片」dialog 的 AI 生成按钮。
输入：卡片 name + risk_level + note；输出：约 50 个语义相关的关键词列表。

落地严格遵循 ``docs/research/pydantic-ai-conventions.md`` (v1.107.0)：
* 复用 ``_resolve_agent_params``（从 analysis.py import，不重写） +
  ``get_keyword_generation_model``（接通 keyword_generation 阶段卡片 → env 兜底）。
* ``get_keyword_agent`` → ``get_agent`` 单例（缓存 key 含 instructions）。
* ``generate_terms`` → ``agent.run`` → ``result.output.terms``。
* 失败时返回空列表（由调用方决定是否报错/提示）。

生成结果**只填前端表单态，不自动落库**；用户仍需点「保存」才建卡。
去重保序由调用方（router 或 service）复用 ``_dedup_terms`` 逻辑。
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.agent_factory import get_agent
from app.llm.analysis import _resolve_agent_params
from app.llm.types import KeywordTerms
from app.models.llm_model import LLMModel

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 系统提示词（领域：银行/支付流水审查命中用关键词）
# ---------------------------------------------------------------------------

# 数量约束：默认生成约 50 个。
_TARGET_COUNT = 50

# 风险等级词风引导。
_RISK_GUIDANCE = {
    "高": (
        "高风险卡片：重点生成敏感/违规/洗钱/欺诈/逃避监管类主体词。"
        "可包含：敏感人物、违规机构、灰色/黑色产业链主体、洗钱通道、"
        "规避监管的化名/别称、地下钱庄/支付通道等。"
    ),
    "中": (
        "中风险卡片：生成常规异常/可疑交易对手类词。"
        "可包含：频繁交易对手、金额异常主体、时间规律异常主体、"
        "非正常业务往来的公司/个人等。"
    ),
    "低": (
        "低风险卡片：生成需关注但风险较低的业务相关词。"
        "可包含：特定行业/商户、常规业务伙伴、需核实的交易对手等。"
    ),
}

_COMMON_INSTRUCTIONS = f"""你是银行/支付流水审查关键词专家。
根据给定的「卡片名称 + 风险等级 + 备注」，生成约 {_TARGET_COUNT} 个语义相关的关键词，
用于命中审查对象的 counterparty_name（交易对手名称）或 summary（摘要/备注）字段。

## 任务
- 基于卡片名称（核心语义）+ 备注（补充说明）+ 风险等级（词风引导），
  发散同义词、变体、相关主体、化名/别称、行业/商户词。
- 关键词应**直接可用于文本匹配**（精确/脱敏/模糊），避免过于宽泛的通用词。
- 每词长度一般 2-20 字；避免纯数字、纯符号、超长描述句。
- 输出数量目标：约 {_TARGET_COUNT} 个（可略多或略少，质量优先）。

## 风险等级词风（不同等级生成不同侧重）
{_RISK_GUIDANCE["高"]}
{_RISK_GUIDANCE["中"]}
{_RISK_GUIDANCE["低"]}

## 去重与格式
- 严格去重（同一语义的不同写法只保留一个最常用形式）。
- 直接输出关键词列表，不要解释、不要编号、不要加引号、不要 markdown。
- 每行一个词（或用 JSON 数组返回，字段见下方）。

## 返回 JSON 格式（严格遵守）
{{
  "terms": ["词1", "词2", "..."]
}}
"""

# 阶段 fallback max_tokens（关键词列表生成，较短）。
_MAX_TOKENS_KEYWORD_GEN = 2000


# ---------------------------------------------------------------------------
# 阶段模型卡片接线（STAGE_KEYWORD_GENERATION）
# ---------------------------------------------------------------------------


async def get_keyword_generation_model(db: AsyncSession) -> Optional[LLMModel]:
    """keyword_generation 阶段指派的卡片（AI 关键词生成用）。

    Returns:
        指派的 ``LLMModel`` 或 None（未指派 → 回退 env settings）。
    """
    from app.services.llm_model_service import get_stage_model
    from app.models.llm_model_assignment import STAGE_KEYWORD_GENERATION

    return await get_stage_model(db, STAGE_KEYWORD_GENERATION)


# ---------------------------------------------------------------------------
# 关键词生成 agent —— 模块级单例
# ---------------------------------------------------------------------------


def get_keyword_agent(*, model: Optional[LLMModel] = None):
    """建/取关键词生成 agent（模块级单例，缓存 key 含 instructions）。

    ``output_type=KeywordTerms``。``instructions`` 为领域提示词 + 数量/词风约束。
    复用 ``_resolve_agent_params``（keyword_generation 阶段卡片 → env 兜底）。
    """
    params = _resolve_agent_params(model, fallback_max_tokens=_MAX_TOKENS_KEYWORD_GEN)
    agent = get_agent(
        KeywordTerms,
        _COMMON_INSTRUCTIONS,
        base_url=params["base_url"],
        api_key=params["api_key"],
        model=params["model"],
        timeout=params["timeout"],
        max_tokens=params["max_tokens"],
        thinking=params["thinking"],
        temperature=params["temperature"],
        supports_tool_choice_required=params["supports_tool_choice_required"],
    )
    return agent


# ---------------------------------------------------------------------------
# 对外接口：generate_terms
# ---------------------------------------------------------------------------


async def generate_terms(
    name: str,
    risk_level: str,
    note: Optional[str] = None,
    *,
    model: Optional[LLMModel] = None,
) -> list[str]:
    """调用 AI 生成约 50 个语义相关的关键词。

    Args:
        name: 卡片名称（必填，非空）。
        risk_level: 风险等级（高/中/低）。
        note: 备注（可空）。
        model: keyword_generation 阶段指派的卡片（None → 回退 env settings）。

    Returns:
        关键词列表（已去重保序）。失败或返回过少时返回空列表。

    失败处理：
    - LLM 不可用 / 超时 / 解析失败 → 记录日志，返回 []（调用方决定是否提示）。
    - 返回词数过少（<3）→ 也视为失败，返回 []。
    """
    clean_name = (name or "").strip()
    if not clean_name:
        logger.warning("关键词生成：name 为空，跳过调用")
        return []

    # 构造 user prompt（把 name/risk/note 喂给 agent）。
    note_text = (note or "").strip()
    risk_text = (risk_level or "").strip() or "中"
    user_prompt = (
        f"卡片名称：{clean_name}\n"
        f"风险等级：{risk_text}\n"
        f"备注：{note_text if note_text else '（无）'}\n\n"
        f"请生成约 {_TARGET_COUNT} 个语义相关的关键词（用于银行/支付流水审查的对手方/摘要命中）。"
    )

    try:
        agent = get_keyword_agent(model=model)
        result = await agent.run(user_prompt)
        terms: list[str] = list(result.output.terms or [])
    except Exception as exc:
        logger.warning(
            "关键词生成失败（返回空列表）: name=%s, 异常类型=%s, 异常=%s",
            clean_name,
            type(exc).__name__,
            exc,
        )
        return []

    # 基本质量门：返回过少视为失败。
    if len(terms) < 3:
        logger.warning(
            "关键词生成返回过少（<%d 个），视为失败返回空列表: name=%s, count=%d",
            3,
            clean_name,
            len(terms),
        )
        return []

    return terms
