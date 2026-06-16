"""Task model."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Task(Base, TimestampMixin):
    """Extraction task."""

    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        default="draft",
        nullable=False,
    )  # noqa: E501  # draft/running/paused/completed/failed/cancelled
    config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    owner: Mapped["User"] = relationship("User", back_populates="owned_tasks", foreign_keys=[owner_id])  # noqa: F821
    documents: Mapped[list["Document"]] = relationship("Document", back_populates="task")  # noqa: F821
    logs: Mapped[list["TaskLog"]] = relationship("TaskLog", back_populates="task")  # noqa: F821
    reviews: Mapped[list["Review"]] = relationship("Review", back_populates="task")  # noqa: F821
    reports: Mapped[list["Report"]] = relationship("Report", back_populates="task")  # noqa: F821
    collaborators: Mapped[list["Collaborator"]] = relationship("Collaborator", back_populates="task")  # noqa: F821
    exports: Mapped[list["ExportFile"]] = relationship("ExportFile", back_populates="task")  # noqa: F821
