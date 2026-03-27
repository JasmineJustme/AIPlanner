from sqlalchemy import BigInteger, Float, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class LLMConfig(TimestampMixin, Base):
    __tablename__ = "llm_configs"
    purpose: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    api_endpoint: Mapped[str | None] = mapped_column(String(500), nullable=True)
    api_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    temperature: Mapped[float] = mapped_column(Float, default=0.7)
    top_p: Mapped[float] = mapped_column(Float, default=1.0)
    max_tokens: Mapped[int] = mapped_column(Integer, default=4096)
    timeout: Mapped[int] = mapped_column(Integer, default=180)
    prompt_template: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[int] = mapped_column(Integer, default=1)
    total_tokens_used: Mapped[int] = mapped_column(BigInteger, default=0)
    total_cost: Mapped[float] = mapped_column(Float, default=0.0)
    cost_alert_threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    user_preferences: Mapped[dict] = mapped_column(JSON, default=dict)
