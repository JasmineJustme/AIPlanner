from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class DataSource(TimestampMixin, Base):
    __tablename__ = "datasources"
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    agent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    dify_endpoint: Mapped[str | None] = mapped_column(String(500), nullable=True)
    dify_api_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    input_params: Mapped[dict] = mapped_column(JSON, default=list)
    output_params: Mapped[dict] = mapped_column(JSON, default=list)
    is_enabled: Mapped[bool] = mapped_column(default=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_sync_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    last_sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sync_data_cache: Mapped[dict | None] = mapped_column(JSON, nullable=True)
