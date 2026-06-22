"""Report model."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Report(Base):
    """Generated report."""

    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("tasks.id"), nullable=False)
    review_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("reviews.id"), nullable=True)
    format: Mapped[str] = mapped_column(String(20), nullable=False)
    content_path: Mapped[str] = mapped_column(String(500), nullable=False)
    # S7 软态：draft（可编辑/重生成/批注）| final（整报告只读，写操作 409）。
    # 定稿不改章节内容、不删行，只改本软态（不删减精神）。
    status: Mapped[str] = mapped_column(
        String(20),
        default="draft",
        nullable=False,
        server_default="draft",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    task: Mapped["Task"] = relationship("Task", back_populates="reports")  # noqa: F821
    review: Mapped["Review | None"] = relationship("Review", back_populates="reports")  # noqa: F821
    # S7 章节化：6 章 ReportChapter，按 order_index 排序，删报告级联删章。
    chapters: Mapped[list["ReportChapter"]] = relationship(  # noqa: F821
        "ReportChapter",
        back_populates="report",
        cascade="all, delete-orphan",
        order_by="ReportChapter.order_index",
    )
    # S7 章节级批注：删报告级联删批注。
    annotations: Mapped[list["ReportAnnotation"]] = relationship(  # noqa: F821
        "ReportAnnotation",
        back_populates="report",
        cascade="all, delete-orphan",
        order_by="ReportAnnotation.created_at",
    )
