# -*- coding: utf-8 -*-
"""AI 审查维度模型（06-26-ai-agent）.

``AuditDimension`` — 审查维度（维度 = 结构化提示词，不是工具、不是代码规则）。
全局共享，平行于审查任务 / 关键词卡片。每个维度含 ``purpose`` / ``steps``
(jsonb 调用序列) / ``judgment`` / ``severity`` 五字段；服务端用
``app.services.audit.dimension_prompt.build_dimension_prompt`` 拼成完整 ``prompt``
缓存于 ``prompt`` 列。

* ``source=system`` —— 预冻 5 条系统维度（Alembic seed，``enabled=true``）。
* ``source=agent`` —— 追问 agent 调 ``create_dimension`` 沉淀的草稿
  （``enabled=false``，需人在维度管理页启用才进 analyze）。

删维度（UI/后端，非 agent）：``source=system`` 仅 admin 可删；``source=agent``
``created_by``（owner）或 admin 可删。已被 ``Finding`` 引用 → router 返 409
（对齐删已指派模型卡 / 删已命中关键词卡的 409 模式）。
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models._types import jsonb
from app.models.base import Base, TimestampMixin


# 维度来源：system（预冻）/ agent（追问 agent 沉淀草稿）。
SOURCE_SYSTEM = "system"
SOURCE_AGENT = "agent"
DIMENSION_SOURCES = (SOURCE_SYSTEM, SOURCE_AGENT)

# 维度默认 severity（与 Finding.severity 同语义：high | medium | low）。
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"
DIMENSION_SEVERITIES = (SEVERITY_HIGH, SEVERITY_MEDIUM, SEVERITY_LOW)


class AuditDimension(Base, TimestampMixin):
    """One audit dimension (a structured prompt, not a tool/code rule).

    跑分析时该维度的 ``prompt`` 注入维度 agent 的 instructions；新维度
    沉淀 = 加一行提示词（``create_dimension`` 填字段 → 服务端拼模板 → 落库），
    零代码。
    """

    __tablename__ = "audit_dimensions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 维度名（≤20 字，PRD §六）。
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    # system（预冻）/ agent（追问 agent 沉淀草稿）。
    source: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=SOURCE_SYSTEM,
    )
    # 要查什么异常（1-2 句）。
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    # 按序列出要调哪些工具、传什么参数：``[{tool, params}]``。tool 限只读
    # 工具白名单（5 个）+ query_findings，``create_dimension`` 校验。
    steps: Mapped[list | None] = mapped_column(jsonb(), nullable=True)
    # 命中 / severity 判定标准。
    judgment: Mapped[str] = mapped_column(Text, nullable=False)
    # 默认 severity：high | medium | low。
    severity: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=SEVERITY_MEDIUM,
    )
    # 服务端拼好的成品 prompt（build_dimension_prompt 输出）。
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    # 是否启用（system seed=true；agent 沉淀默认 false，需人审启用才进 analyze）。
    # server_default 由 Alembic 迁移跨方言设置（pg true / sqlite 1）；ORM 插入
    # 走 ``default=True``，不依赖 server_default。
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    # source=agent 时的沉淀人（owner 校验用）；system seed 为 None。
    created_by: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
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
    findings: Mapped[list["Finding"]] = relationship(  # noqa: F821
        "Finding",
        back_populates="dimension",
    )
