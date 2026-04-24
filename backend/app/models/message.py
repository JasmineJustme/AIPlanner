from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Message(TimestampMixin, Base):
    __tablename__ = "messages"
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="unread")
    related_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    related_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    related_request_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    recipient_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    sender_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    action_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    external_pushed: Mapped[bool] = mapped_column(Boolean, default=False)
