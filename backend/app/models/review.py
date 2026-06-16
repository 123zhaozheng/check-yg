"""Review models."""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Review(Base):
    """Review task matching documents with customer list."""

    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("tasks.id"), nullable=False)
    customer_list_id: Mapped[int] = mapped_column(Integer, ForeignKey("customer_lists.id"), nullable=False)
    match_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    task: Mapped["Task"] = relationship("Task", back_populates="reviews")  # noqa: F821
    customer_list: Mapped["CustomerList"] = relationship("CustomerList", back_populates="reviews")  # noqa: F821
    matches: Mapped[list["ReviewMatch"]] = relationship("ReviewMatch", back_populates="review", cascade="all, delete-orphan")  # noqa: F821
    reports: Mapped[list["Report"]] = relationship("Report", back_populates="review")  # noqa: F821


class ReviewMatch(Base):
    """Individual match result in a review."""

    __tablename__ = "review_matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    review_id: Mapped[int] = mapped_column(Integer, ForeignKey("reviews.id"), nullable=False)
    record_id: Mapped[int] = mapped_column(Integer, nullable=False)
    customer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    match_type: Mapped[str] = mapped_column(String(20), nullable=False)  # exact/masked/fuzzy
    score: Mapped[float] = mapped_column(Float, nullable=False)
    counterparty_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    counterparty_account: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_file: Mapped[str | None] = mapped_column(String(255), nullable=True)
    transaction_time: Mapped[str | None] = mapped_column(String(100), nullable=True)
    amount: Mapped[str | None] = mapped_column(String(100), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    record_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Relationships
    review: Mapped["Review"] = relationship("Review", back_populates="matches")
