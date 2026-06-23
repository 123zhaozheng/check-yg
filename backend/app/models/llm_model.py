# -*- coding: utf-8 -*-
"""LLM 模型卡片（06-23-llm-model-card）.

一张卡片 = 一个可复用的 LLM 连接 + 模型元信息（显示名 / 实际 model id /
端点 / api_key / 上下文长度 / 最大输出 / 工具调用 / 推理模式 / 流式 / 默认
max_tokens / 默认 thinking / 默认 temperature）。按阶段（classification /
portrait / normalization / ai_analysis / ai_qa / report_generation）指派卡片，
由 ``LLMModelAssignment`` 承载（见 ``llm_model_assignment.py``）。

api_key 明文存储（DB 列）；API 返回脱敏（``********XXXX``，见 router）。日志
不打 api_key。

不设 ``is_active`` 全局布尔——改用 assignments 按阶段选卡片（决策1）。
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


# default_thinking 枚举值（off/low/medium/high）。reasoning 模型默认 low，
# 非 reasoning 模型为 off。透传给 pydantic-ai ``ModelSettings(thinking=...)``，
# off/None/非 reasoning 时不传该字段（避免给非 reasoning 模型发
# reasoning_effort 报错——见 research §1.3）。
THINKING_OFF = "off"
THINKING_LEVELS = (THINKING_OFF, "low", "medium", "high")


class LLMModel(Base, TimestampMixin):
    """One reusable LLM model card (connection + metadata)."""

    __tablename__ = "llm_models"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 显示名，如「kimi-2.7」「step-3.7-flash」（前端展示用）。
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    # 实际 model id，发给 OpenAI 兼容端点的 ``model`` 字段。
    model_name: Mapped[str] = mapped_column(String(200), nullable=False)
    # OpenAI 兼容端点 base_url（agent_factory 会确保 /v1 结尾）。
    provider_base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    # 明文 api_key（DB 列）；API/日志脱敏。
    api_key: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    # 模型卡片数值（pydantic-ai 1.107.0 无内置模型库，需自维护——research §2/§5）。
    context_length: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_output: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    supports_tool_call: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    supports_tool_choice_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    is_reasoning: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    supports_streaming: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # off/low/medium/high。reasoning 模型默认 low，非 reasoning 默认 off。
    default_thinking: Mapped[str] = mapped_column(
        String(20), nullable=False, default=THINKING_OFF
    )
    # 单次响应最大 token（reasoning 模型含 reasoning token——research §3）。
    default_max_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=4000)
    # 默认采样温度，可空——空则回退 runtime ``llm.temperature`` 设置项。
    default_temperature: Mapped[float | None] = mapped_column(Float, nullable=True)

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
