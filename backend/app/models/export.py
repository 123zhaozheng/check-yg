"""Export file model."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ExportFile(Base):
    """Generated export artifact."""

    __tablename__ = "exports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("tasks.id"), nullable=False)
    review_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("reviews.id"), nullable=True)
    format: Mapped[str] = mapped_column(String(20), nullable=False)
    # S8 导出范围：report / raw / standard / findings（旧 excel/bundle 行 null 兼容）.
    scope: Mapped[str | None] = mapped_column(String(50), nullable=True)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    task: Mapped["Task"] = relationship("Task", back_populates="exports")  # noqa: F821
    review: Mapped["Review | None"] = relationship("Review")  # noqa: F821
