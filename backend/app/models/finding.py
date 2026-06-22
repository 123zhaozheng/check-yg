"""Finding model — AI analysis 异常发现 (S6).

One row per anomaly the AI analysis agent surfaces for a task. 全标量字段
（无 jsonb，决策1）：type / severity / description / counterparty / amount /
confidence / status / comment。severity 三态 high|medium|low，前端按灰阶+形状
双编码（单色原则）。status 三态 pending|accepted|ignored，记录人工复核结论。

关联 ``tasks.id``（owner-only 复用 _load_owned_task）。多轮对话历史不在此表，
存 ``Task.config.analysis_chat_history``（决策3，单任务单对话线程，轻量）。
"""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Finding(Base, TimestampMixin):
    """One AI-surfaced anomaly for a task (S6 analysis skeleton)."""

    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("tasks.id"), nullable=False)
    # 异常类型（大额/高频/对手异常等，free-form 标签）。
    type: Mapped[str] = mapped_column(String(100), nullable=False)
    # high | medium | low — 前端灰阶+形状双编码（单色，禁红黄绿）。
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # Optional context fields — null when the finding isn't tied to a specific
    # counterparty or amount (e.g. 高频交易 is count-based).
    counterparty: Mapped[str | None] = mapped_column(String(255), nullable=True)
    amount: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # 0.0–1.0 — rendered as a grayscale horizontal bar on the frontend.
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # pending | accepted | ignored — 人工复核结论，默认 pending。
    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        nullable=False,
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    task: Mapped["Task"] = relationship("Task")  # noqa: F821
