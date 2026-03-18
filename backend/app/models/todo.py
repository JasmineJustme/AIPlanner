from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Todo(TimestampMixin, Base):
    __tablename__ = "todos"
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    priority: Mapped[str] = mapped_column(String(10), default="medium")
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    execution_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="system")
    source_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    due_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    tags: Mapped[dict | None] = mapped_column(JSON, default=list)
    responsibility_ids: Mapped[list[str] | None] = mapped_column(JSON, default=list)
    responsibility_titles: Mapped[list[str] | None] = mapped_column(JSON, default=list)
    project: Mapped[str | None] = mapped_column(String(200), nullable=True)
    review_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    duplicate_of: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("todos.id"), nullable=True
    )
    orchestration_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    recurrence_cron: Mapped[str | None] = mapped_column(String(100), nullable=True)
    recurrence_count: Mapped[int] = mapped_column(Integer, default=0)
