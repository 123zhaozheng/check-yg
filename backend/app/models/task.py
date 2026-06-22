"""Task model."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models._types import jsonb
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
    config: Mapped[dict | None] = mapped_column(jsonb(), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Audited employee + review period metadata (populated by the new-task dialog).
    employee_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    employee_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    department: Mapped[str | None] = mapped_column(String(255), nullable=True)
    audit_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    audit_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expected_channels: Mapped[list[str] | None] = mapped_column(jsonb(), nullable=True)

    # Soft-delete / archive flag. DELETE /tasks/{id} flips this instead of
    # removing the row (不删减 hard line — never lose audit data).
    archived: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        server_default=text("false"),
    )

    # Relationships
    owner: Mapped["User"] = relationship("User", back_populates="owned_tasks", foreign_keys=[owner_id])  # noqa: F821
    documents: Mapped[list["Document"]] = relationship("Document", back_populates="task")  # noqa: F821
    logs: Mapped[list["TaskLog"]] = relationship("TaskLog", back_populates="task")  # noqa: F821
    reviews: Mapped[list["Review"]] = relationship("Review", back_populates="task")  # noqa: F821
    reports: Mapped[list["Report"]] = relationship("Report", back_populates="task")  # noqa: F821
    collaborators: Mapped[list["Collaborator"]] = relationship("Collaborator", back_populates="task")  # noqa: F821
    exports: Mapped[list["ExportFile"]] = relationship("ExportFile", back_populates="task")  # noqa: F821
