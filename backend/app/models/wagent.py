from sqlalchemy import ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class WAgent(TimestampMixin, Base):
    __tablename__ = "wagents"
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    capability_tags: Mapped[dict | None] = mapped_column(JSON, default=list)
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    input_params: Mapped[dict] = mapped_column(JSON, nullable=False)
    output_params: Mapped[dict] = mapped_column(JSON, nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=600)
    auto_execute: Mapped[bool] = mapped_column(default=False)
    confirm_before_exec: Mapped[bool] = mapped_column(default=True)
    is_enabled: Mapped[bool] = mapped_column(default=True)
    source: Mapped[str] = mapped_column(String(20), default="manual")
    call_count: Mapped[int] = mapped_column(default=0)
    success_count: Mapped[int] = mapped_column(default=0)


class WAgentVersion(TimestampMixin, Base):
    __tablename__ = "wagent_versions"
    __table_args__ = (UniqueConstraint("wagent_id", "version", name="uq_wagent_version"),)
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    wagent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("wagents.id"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    steps: Mapped[dict] = mapped_column(JSON, nullable=False)
    input_params: Mapped[dict] = mapped_column(JSON, nullable=False)
    output_params: Mapped[dict] = mapped_column(JSON, nullable=False)
    change_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
