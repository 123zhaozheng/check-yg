"""Finding model — AI analysis 异常发现 (S6).

One row per anomaly the AI analysis agent surfaces for a task. 基础标量字段：
type / severity / description / counterparty / amount / confidence / status /
comment。severity 三态 high|medium|low，前端按灰阶+形状双编码（单色原则）。
status 三态 pending|accepted|ignored，记录人工复核结论。

06-26-ai-agent additive 列：``dimension_id``（产出该 finding 的维度）/``detail_text``
（自然语言分析正文）/``evidence_record_ids``（命中 flow_record id 列表，jsonb）/
``source``（``rule``=维度跑出 | None=历史占位）。这些列不动现有字段，向后兼容。

06-28-balance-column-check additive 列：``document_id``（balance_check finding 关联
到产出它的文档，用于按文档范围重算；维度 finding 为 NULL，不受影响）。

关联 ``tasks.id``（owner-only 复用 _load_owned_task）。多轮追问对话历史在
``AuditConversation`` 表（06-26-ai-agent，独立于 task.config）。
"""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models._types import jsonb
from app.models.base import Base, TimestampMixin


class Finding(Base, TimestampMixin):
    """One AI-surfaced anomaly for a task (S6 analysis skeleton)."""

    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("tasks.id"), nullable=False)
    # 06-28-balance-column-check additive 列：balance_check finding 关联到产出它的
    # 文档（重跑/append 按文档范围删旧重算，不误删其它文档的校验结果）。维度 finding
    # （source='rule'）不设该列 → NULL，不受影响。ondelete=CASCADE：文档删除时其
    # 余额校验 finding 脱离文档无意义，跟随删除（与 audit_conversation.task_id 风格一致）。
    document_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=True,
    )
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

    # 06-26-ai-agent additive 列（不动上面现有字段）：
    # 产出该 finding 的维度（维度 agent 跑出 → source='rule'）；历史占位 finding
    # 为 None。删维度时若已被 finding 引用 → router 返 409（FK ondelete=RESTRICT）。
    dimension_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("audit_dimensions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    # 自然语言分析正文（右侧详情区展示，引用真实笔数与样本）。维度 agent 产出。
    detail_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 命中的 flow_record id 列表（关联记录下钻用）。
    evidence_record_ids: Mapped[list | None] = mapped_column(jsonb(), nullable=True)
    # finding 来源：``rule``（维度跑出）| ``balance_check``（余额校验不符行）|
    # 兼容历史占位（None）。balance_check 是确定性算术产物（非 LLM 维度），AI 分析页
    # 默认不显示、由 clean 页校验区单独取（GET ?source=balance_check）。
    source: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Relationships
    task: Mapped["Task"] = relationship("Task")  # noqa: F821
    dimension: Mapped["AuditDimension | None"] = relationship(  # noqa: F821
        "AuditDimension",
        back_populates="findings",
    )
