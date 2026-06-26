# -*- coding: utf-8 -*-
"""AI 分析追问会话模型（06-26-ai-agent）.

``AuditConversation`` — 一个任务的多轮追问会话。``message_history`` (jsonb) 存
pydantic-ai 的 model-independent 消息历史（``ModelMessagesTypeAdapter`` 序列化
往返），跨轮继承。``task.config.active_conversation_id`` 存当前激活会话。

多会话（PRD §六/§九 Q9）：独立此表，不撑 ``task.config``。删会话只删对话历史，
不影响已沉淀维度（沉淀是 ``create_dimension`` 产物，落 ``audit_dimensions``，
跟会话独立）。
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models._types import jsonb
from app.models.base import Base, TimestampMixin


class AuditConversation(Base, TimestampMixin):
    """One multi-turn audit-QA conversation for a task."""

    __tablename__ = "audit_conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    # 会话标题（首问题前 10 字；前端悬浮球显示 ``#N · 前10字``）。
    title: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    # pydantic-ai model-independent 消息历史（ModelMessagesTypeAdapter 序列化）。
    message_history: Mapped[list | None] = mapped_column(jsonb(), nullable=True)
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
    task: Mapped["Task"] = relationship("Task")  # noqa: F821
