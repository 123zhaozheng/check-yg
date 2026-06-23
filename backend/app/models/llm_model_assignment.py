# -*- coding: utf-8 -*-
"""LLM 阶段模型指派（06-23-llm-model-card）.

每个阶段（classification/portrait/normalization/ai_analysis/ai_qa/
report_generation）至多一行（stage 唯一）。``llm_model_id`` nullable——
nullable 表示该阶段未指派卡片，运行时回退 runtime ``llm.*`` 设置项 + 模块
硬编码兜底常量（决策5）。

阶段枚举见 :data:`STAGES`。前三个（classification/portrait/normalization）
已接真实 LLM；后三个（ai_analysis/ai_qa/report_generation）为预留映射位，
当前 analysis.py / report_chapter_builder 是占位，等后续接真实 LLM 时生效。
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


# 阶段枚举。前三个真实生效；后三个预留（占位，待接入真实 LLM）。
STAGE_CLASSIFICATION = "classification"
STAGE_PORTRAIT = "portrait"
STAGE_NORMALIZATION = "normalization"
STAGE_AI_ANALYSIS = "ai_analysis"
STAGE_AI_QA = "ai_qa"
STAGE_REPORT_GENERATION = "report_generation"

STAGES = (
    STAGE_CLASSIFICATION,
    STAGE_PORTRAIT,
    STAGE_NORMALIZATION,
    STAGE_AI_ANALYSIS,
    STAGE_AI_QA,
    STAGE_REPORT_GENERATION,
)

# 已接真实 LLM 的阶段（extractor 三模块）。
ACTIVE_STAGES = (STAGE_CLASSIFICATION, STAGE_PORTRAIT, STAGE_NORMALIZATION)
# 预留映射位阶段（占位，待后续任务接通真实 LLM）。
RESERVED_STAGES = (STAGE_AI_ANALYSIS, STAGE_AI_QA, STAGE_REPORT_GENERATION)


class LLMModelAssignment(Base, TimestampMixin):
    """Per-stage model assignment (stage → llm_model_id, nullable)."""

    __tablename__ = "llm_model_assignments"
    __table_args__ = (UniqueConstraint("stage", name="uq_llm_model_assignments_stage"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stage: Mapped[str] = mapped_column(String(50), nullable=False)
    # nullable = 该阶段未指派 → 运行时回退兜底（runtime settings + 模块常量）。
    llm_model_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("llm_models.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    llm_model: Mapped["LLMModel | None"] = relationship("LLMModel")  # noqa: F821
