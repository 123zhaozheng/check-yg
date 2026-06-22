"""FlowRecord model — the record-of-truth for normalized + unparsed + excluded rows.

S5 清洗不删减 hard line: every raw table row is persisted 1:1 here.

* ``record_type=standard``  — normalizer 输出且 is_valid=true 的流水行（下游可用）。
* ``record_type=unparsed``  — normalizer 标 is_valid=false 的噪音行（合计/小计/
  余额/页脚/页眉/空行），不丢，带 raw_payload 可捞回。
* ``record_type=excluded``  — classifier 判为非流水表（is_flow_table=false 或
  confidence < 阈值）的整表原始行，不丢，带 raw_payload 可捞回。

``raw_payload`` (JSONB) 保存原始全部单元格，是"清洗不删减"的物理兜底——任何
被规则过滤的行都能从这里还原原文。``status`` 走软删语义：``active`` 默认，
``restored`` 表示用户从排除项视图捞回过（记录仍在表，不删减）。
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models._types import jsonb
from app.models.base import Base


class FlowRecordRow(Base):
    """One persisted flow record (standard / unparsed / excluded)."""

    __tablename__ = "flow_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("tasks.id"), nullable=False)
    document_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("documents.id"), nullable=True
    )
    # Channel label copied from the owning Document so record queries can filter
    # by channel without a join. Nullable for legacy/fallback rows.
    channel: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # standard | unparsed | excluded — drives the cleaning page's tabs/filters.
    record_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # 1-based row index within the source table (mirrors FlowRecord.original_row).
    row_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_valid: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    # Standardized fields (empty for excluded rows where normalizer never ran).
    transaction_time: Mapped[str | None] = mapped_column(String(100), nullable=True)
    counterparty_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    counterparty_account: Mapped[str | None] = mapped_column(String(255), nullable=True)
    amount: Mapped[str | None] = mapped_column(String(100), nullable=True)
    raw_amount: Mapped[str | None] = mapped_column(String(100), nullable=True)
    summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    transaction_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Original cells preserved verbatim (清洗不删减 physical guarantee).
    raw_payload: Mapped[dict | None] = mapped_column(jsonb(), nullable=True)
    # active | restored — restored marks a row捞回过 but never deletes it.
    status: Mapped[str] = mapped_column(
        String(20),
        default="active",
        nullable=False,
    )
    # Why the row was excluded/unparsed (e.g. "classifier: not flow table",
    # "normalizer: noise row"). Free text for the export log.
    exclude_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    task: Mapped["Task"] = relationship("Task")  # noqa: F821
    document: Mapped["Document | None"] = relationship("Document")  # noqa: F821
