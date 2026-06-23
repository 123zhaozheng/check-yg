# -*- coding: utf-8 -*-
"""关键词库模型（06-23-tab）.

两张全局资产表 + 一张任务级命中表：

* ``KeywordCard`` — 关键词卡片（卡片名 + 卡片级风险等级 高/中/低 + 备注）。全局共享，
  平行于审查任务 / 设置。词级无风险等级。
* ``KeywordTerm`` — 卡片下的关键词。``(card_id, term)`` 唯一。删卡 ondelete CASCADE
  连带删词。
* ``KeywordHit`` — 任务关键词审查的命中行。引用 ``flow_records`` / ``keyword_cards`` /
  ``keyword_terms``。删卡时若该卡已有命中 → router 返 409（对齐删已指派模型卡）。
  ``flow_record_id`` 用 ondelete=CASCADE：仅在 flow_record 行硬删时（非 append 重跑抽取）
  顺带清命中；捞回（restore）只翻 status 不删行，命中保留至下次重跑审查重算（重跑才同步）。
"""

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


# 卡片级风险等级（词级无风险等级）。
RISK_HIGH = "高"
RISK_MEDIUM = "中"
RISK_LOW = "低"
RISK_LEVELS = (RISK_HIGH, RISK_MEDIUM, RISK_LOW)

# 命中匹配类型（对齐 matcher.MatchType.value）。
MATCH_EXACT = "精确匹配"
MATCH_DESENSITIZED = "脱敏匹配"
MATCH_FUZZY = "模糊匹配"

# 命中字段（只扫 standard 记录的这两列）。
FIELD_COUNTERPARTY = "counterparty_name"
FIELD_SUMMARY = "summary"

# 命中人工处理状态。
HIT_PENDING = "pending"
HIT_CONFIRMED = "confirmed"
HIT_IGNORED = "ignored"
HIT_STATUSES = (HIT_PENDING, HIT_CONFIRMED, HIT_IGNORED)


class KeywordCard(Base, TimestampMixin):
    """One keyword card (name + card-level risk + note)."""

    __tablename__ = "keyword_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 卡片名（全局唯一由 service 层 upsert 保证；DB 不加唯一约束以便导入合并同名）。
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # 卡片级风险等级：高/中/低。词级无风险等级。
    risk_level: Mapped[str] = mapped_column(String(10), nullable=False, default=RISK_MEDIUM)
    # 备注，可空。
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    terms: Mapped[list["KeywordTerm"]] = relationship(
        "KeywordTerm",
        back_populates="card",
        cascade="all, delete-orphan",
    )
    hits: Mapped[list["KeywordHit"]] = relationship("KeywordHit", back_populates="card")


class KeywordTerm(Base):
    """One keyword under a card. (card_id, term) unique."""

    __tablename__ = "keyword_terms"
    __table_args__ = (
        UniqueConstraint("card_id", "term", name="uq_keyword_terms_card_id_term"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    card_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("keyword_cards.id", ondelete="CASCADE"),
        nullable=False,
    )
    term: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    card: Mapped["KeywordCard"] = relationship("KeywordCard", back_populates="terms")
    hits: Mapped[list["KeywordHit"]] = relationship("KeywordHit", back_populates="term")


class KeywordHit(Base, TimestampMixin):
    """One keyword-review hit for a task (a flow_record × keyword match)."""

    __tablename__ = "keyword_hits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tasks.id"),
        nullable=False,
    )
    # CASCADE 只在 flow_record 行被硬删时触发（非 append 重跑抽取会删旧 standard 行），
    # 顺带清掉指向已不存在行的命中。捞回（restore）只翻 status、不删行、不改 record_type，
    # 故命中保留——下次重跑审查才按当前 standard 重算（重跑才同步，prd §B 决策）。
    flow_record_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("flow_records.id", ondelete="CASCADE"),
        nullable=False,
    )
    keyword_card_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("keyword_cards.id", ondelete="RESTRICT"),
        nullable=False,
    )
    keyword_term_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("keyword_terms.id", ondelete="CASCADE"),
        nullable=False,
    )
    # 精确匹配/脱敏匹配/模糊匹配。
    match_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # 0-100。
    confidence: Mapped[int] = mapped_column(Integer, nullable=False)
    # 高/中/低，来自卡片。
    risk_level: Mapped[str] = mapped_column(String(10), nullable=False)
    # counterparty_name / summary。
    matched_field: Mapped[str] = mapped_column(String(50), nullable=False)
    # 命中片段文本。
    matched_snippet: Mapped[str] = mapped_column(Text, nullable=False)
    # pending/confirmed/ignored，默认 pending。
    status: Mapped[str] = mapped_column(
        String(20),
        default=HIT_PENDING,
        nullable=False,
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    card: Mapped["KeywordCard"] = relationship("KeywordCard", back_populates="hits")
    term: Mapped["KeywordTerm"] = relationship("KeywordTerm", back_populates="hits")
