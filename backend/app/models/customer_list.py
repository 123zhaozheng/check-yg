"""Customer list models."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class CustomerList(Base):
    """Customer list for matching."""

    __tablename__ = "customer_lists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    owner: Mapped["User"] = relationship("User", back_populates="owned_customer_lists")  # noqa: F821
    items: Mapped[list["CustomerListItem"]] = relationship("CustomerListItem", back_populates="list", cascade="all, delete-orphan")  # noqa: F821
    reviews: Mapped[list["Review"]] = relationship("Review", back_populates="customer_list")  # noqa: F821


class CustomerListItem(Base):
    """Customer list item."""

    __tablename__ = "customer_list_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    list_id: Mapped[int] = mapped_column(Integer, ForeignKey("customer_lists.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    list: Mapped["CustomerList"] = relationship("CustomerList", back_populates="items")
