# -*- coding: utf-8 -*-
"""LLM 模型卡片服务（06-23-llm-model-card）.

职责：
* ``get_stage_model(db, stage)``：查 ``llm_model_assignments`` 该 stage 指派的
  卡片；未指派或卡片被删返 None（调用方回退 runtime ``llm.*`` 设置项 + 模块
  硬编码兜底常量）。
* ``seed_default_llm_models(db)``：seed 几张常见模型卡片（research §5）。
  assignments 留空（grill 决策：用户在设置页手动给每阶段选卡片）。

解析优先级（见 prd ②）：阶段卡片 > runtime ``llm.*`` 设置项 > 模块硬编码
兜底常量。本服务只负责第一层（查卡片），后两层在调用方（extractor / 三模块）
里做，避免 extractor 内直接访问 DB。

api_key 不进日志（logging-guidelines.md）。
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import LLMModel, LLMModelAssignment
from app.models.llm_model_assignment import STAGES
from app.models.llm_model import THINKING_OFF

logger = logging.getLogger(__name__)


async def get_stage_model(db: AsyncSession, stage: str) -> Optional[LLMModel]:
    """查该 stage 指派的卡片；未指派或卡片被删返 None。

    Args:
        db: 异步 DB session。
        stage: 阶段枚举（classification/portrait/normalization/ai_analysis/
            ai_qa/report_generation）。

    Returns:
        指派的 ``LLMModel`` 或 None（回退兜底）。
    """
    result = await db.execute(
        select(LLMModelAssignment).where(LLMModelAssignment.stage == stage)
    )
    assignment = result.scalar_one_or_none()
    if assignment is None or assignment.llm_model_id is None:
        return None
    model_result = await db.execute(
        select(LLMModel).where(LLMModel.id == assignment.llm_model_id)
    )
    return model_result.scalar_one_or_none()


async def load_stage_models(
    db: AsyncSession, stages: tuple[str, ...] = STAGES
) -> dict[str, Optional[LLMModel]]:
    """批量查多阶段的指派卡片（runner 启动时一次查完，避免 extractor 内查 DB）。

    Args:
        db: 异步 DB session。
        stages: 要查的阶段元组，默认全部 6 个。

    Returns:
        ``{stage: LLMModel | None}`` 映射。
    """
    result = await db.execute(select(LLMModelAssignment))
    assignments = {a.stage: a.llm_model_id for a in result.scalars().all()}
    wanted_ids = [mid for mid in assignments.values() if mid is not None]
    models_by_id: dict[int, LLMModel] = {}
    if wanted_ids:
        models_result = await db.execute(select(LLMModel).where(LLMModel.id.in_(wanted_ids)))
        for m in models_result.scalars().all():
            models_by_id[m.id] = m
    return {stage: models_by_id.get(assignments[stage]) if stage in assignments else None for stage in stages}


async def seed_default_llm_models(db: AsyncSession) -> list[LLMModel]:
    """Seed 几张常见模型卡片（research §5），已存在的 display_name 跳过。

    assignments 留空（grill 决策：用户在设置页手动给每阶段选卡片）。
    api_key 留空——用户在设置页填。kimi 32K 最大输出未独立核实，按已知写。
    幂等：以 (display_name) 去重，已存在的不重复插入。

    Args:
        db: 异步 DB session。

    Returns:
        本次插入的卡片列表（已存在的不含）。
    """
    # (display_name, model_name, provider_base_url, context_length, max_output,
    #  supports_tool_call, supports_tool_choice_required, is_reasoning,
    #  supports_streaming, default_thinking, default_max_tokens)
    defaults = [
        ("step-3.7-flash", "step-3.7-flash", "https://api.stepfun.com/v1",
         262144, 8192, True, True, True, True, "low", 6000),
        ("deepseek-chat", "deepseek-chat", "https://api.deepseek.com/v1",
         1000000, 384000, True, True, False, True, THINKING_OFF, 4000),
        ("qwen-plus", "qwen-plus", "https://dashscope.aliyuncs.com/compatible-mode/v1",
         1000000, 8192, True, False, False, True, THINKING_OFF, 4000),
        ("kimi-k2.6", "kimi-k2.6", "https://api.moonshot.ai/v1",
         262144, 32768, True, True, True, True, "low", 6000),
    ]

    existing_result = await db.execute(select(LLMModel.display_name))
    existing = {name for name in existing_result.scalars().all()}

    inserted: list[LLMModel] = []
    for (display_name, model_name, base_url, ctx, max_out,
         tool_call, tool_required, reasoning, streaming, thinking, max_tokens) in defaults:
        if display_name in existing:
            continue
        model = LLMModel(
            display_name=display_name,
            model_name=model_name,
            provider_base_url=base_url,
            api_key="",
            context_length=ctx,
            max_output=max_out,
            supports_tool_call=tool_call,
            supports_tool_choice_required=tool_required,
            is_reasoning=reasoning,
            supports_streaming=streaming,
            default_thinking=thinking,
            default_max_tokens=max_tokens,
            default_temperature=None,
        )
        db.add(model)
        inserted.append(model)

    if inserted:
        await db.commit()
        for m in inserted:
            await db.refresh(m)
        logger.info("seed 默认模型卡片 %d 张", len(inserted))
    return inserted
