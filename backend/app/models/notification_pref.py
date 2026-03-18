from sqlalchemy import Boolean, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class NotificationPref(TimestampMixin, Base):
    __tablename__ = "notification_prefs"
    __table_args__ = (UniqueConstraint("user_id", "message_type", name="uq_notification_prefs_user_message_type"),)
    message_type: Mapped[str] = mapped_column(String(30), nullable=False)
    in_app_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    wechat_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    channel_enabled_map: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class NotificationGlobalPref(TimestampMixin, Base):
    __tablename__ = "notification_global_prefs"
    dnd_start: Mapped[str | None] = mapped_column(String(5), nullable=True)
    dnd_end: Mapped[str | None] = mapped_column(String(5), nullable=True)
    merge_strategy: Mapped[str] = mapped_column(String(20), default="none")
    merge_window_minutes: Mapped[int] = mapped_column(Integer, default=5)
    deadline_advance_minutes: Mapped[int] = mapped_column(Integer, default=60)
