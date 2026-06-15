"""Collaborator model."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Collaborator(Base):
    """Task collaborator."""

    __tablename__ = "collaborators"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("tasks.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # read/write/admin
    invited_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    task: Mapped["Task"] = relationship("Task", back_populates="collaborators")  # noqa: F821
    user: Mapped["User"] = relationship("User", back_populates="collaborations", foreign_keys=[user_id])  # noqa: F821
    inviter: Mapped["User"] = relationship("User", foreign_keys=[invited_by])  # noqa: F821
