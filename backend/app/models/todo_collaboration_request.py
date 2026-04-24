from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class TodoCollaborationRequest(TimestampMixin, Base):
    __tablename__ = "todo_collaboration_requests"

    todo_id: Mapped[str] = mapped_column(String(36), ForeignKey("todos.id"), nullable=False, index=True)
    source_user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    target_user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    request_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    request_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rejected_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
