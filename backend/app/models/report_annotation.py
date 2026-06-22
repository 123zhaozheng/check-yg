"""ReportAnnotation model — S7 章节级复核批注.

本轮批注挂在章节上（``chapter_id`` nullable，决策3 章节级批注）。灰阶呈现
（前端左细灰竖线 + 浅灰底块，禁彩色高亮）。``resolved`` 软态切解决状态，
定稿后新建/切换均 409。
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ReportAnnotation(Base):
    """One review annotation on a report chapter (S7)."""

    __tablename__ = "report_annotations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("reports.id"), nullable=False
    )
    # nullable — 章节级批注本轮挂章节；预留 null 以便后续章节外全局批注。
    chapter_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("report_chapters.id"), nullable=True
    )
    author: Mapped[str] = mapped_column(String(100), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    resolved: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default=func.false()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    report: Mapped["Report"] = relationship("Report", back_populates="annotations")  # noqa: F821
    chapter: Mapped["ReportChapter | None"] = relationship(  # noqa: F821
        "ReportChapter", back_populates="annotations"
    )
