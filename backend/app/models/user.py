"""User model."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    """User account."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role_id: Mapped[int] = mapped_column(Integer, ForeignKey("roles.id"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    role: Mapped["Role"] = relationship("Role", back_populates="users")  # noqa: F821
    owned_tasks: Mapped[list["Task"]] = relationship("Task", back_populates="owner", foreign_keys="Task.owner_id")  # noqa: F821
    owned_customer_lists: Mapped[list["CustomerList"]] = relationship("CustomerList", back_populates="owner")  # noqa: F821
    collaborations: Mapped[list["Collaborator"]] = relationship("Collaborator", back_populates="user", foreign_keys="Collaborator.user_id")  # noqa: F821
