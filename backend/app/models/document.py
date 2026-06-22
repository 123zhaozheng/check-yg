"""Document model."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models._types import jsonb
from app.models.base import Base


class Document(Base):
    """Document to be processed."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("tasks.id"), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_path: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        nullable=False,
    )  # noqa: E501  # pending/processing/completed/failed/deleted
    # Channel label (e.g. 银行流水/支付渠道/证券交易/票据凭证/其他). Nullable so
    # legacy rows and fallback-created documents still work. Set at upload time.
    channel: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # File size in bytes, captured at upload so the documents list can show it
    # without a filesystem stat. Nullable for legacy / fallback-created rows.
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extracted_tables: Mapped[dict | None] = mapped_column(jsonb(), nullable=True)
    flow_tables: Mapped[dict | None] = mapped_column(jsonb(), nullable=True)
    error_log: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    task: Mapped["Task"] = relationship("Task", back_populates="documents")  # noqa: F821
