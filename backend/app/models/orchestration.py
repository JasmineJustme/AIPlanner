from datetime import datetime

from sqlalchemy import DateTime, JSON, String, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.utils.timezone import utc_now_naive


class Orchestration(Base):
    """Persists orchestration state that was previously held in a JSON file."""

    __tablename__ = "orchestrations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="analyzing", index=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    todos_snapshot: Mapped[list | None] = mapped_column(JSON, nullable=True)
    suggested_agent: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    suggested_wagent: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    plan: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    llm_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_recommended_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    llm_recommended_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    llm_recommended_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    llm_recommended_input_params: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive, onupdate=utc_now_naive, nullable=False)

    def to_dict(self) -> dict:
        return {
            "orch_id": self.id,
            "summary": self.summary,
            "status": self.status,
            "submitted_at": self.submitted_at.isoformat() if self.submitted_at else None,
            "todos": self.todos_snapshot or [],
            "suggested_agent": self.suggested_agent,
            "suggested_wagent": self.suggested_wagent,
            "plan": self.plan,
            "llm_reason": self.llm_reason,
            "error": self.error,
            "llm_recommended_id": self.llm_recommended_id,
            "llm_recommended_name": self.llm_recommended_name,
            "llm_recommended_type": self.llm_recommended_type,
            "llm_recommended_input_params": self.llm_recommended_input_params,
        }
