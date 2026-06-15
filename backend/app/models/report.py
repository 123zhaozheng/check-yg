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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    task: Mapped["Task"] = relationship("Task", back_populates="reports")  # noqa: F821
    review: Mapped["Review | None"] = relationship("Review", back_populates="reports")  # noqa: F821
