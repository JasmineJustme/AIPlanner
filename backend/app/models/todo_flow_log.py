from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class TodoFlowLog(TimestampMixin, Base):
    __tablename__ = "todo_flow_logs"

    todo_id: Mapped[str] = mapped_column(String(36), ForeignKey("todos.id"), nullable=False, index=True)
    action_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    from_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    to_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    status_before: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status_after: Mapped[str | None] = mapped_column(String(20), nullable=True)
    flow_state_before: Mapped[str | None] = mapped_column(String(20), nullable=True)
    flow_state_after: Mapped[str | None] = mapped_column(String(20), nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
