from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, JSON, String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.utils.timezone import utc_now_naive


class SystemSetting(Base):
    __tablename__ = "system_settings"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    value: Mapped[dict] = mapped_column(JSON, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)
