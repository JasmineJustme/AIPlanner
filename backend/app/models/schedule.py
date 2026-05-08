from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class SchedulePlan(TimestampMixin, Base):
    __tablename__ = "schedule_plans"
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    recurrence_cron: Mapped[str | None] = mapped_column(String(100), nullable=True)
    recurrence_count: Mapped[int] = mapped_column(Integer, default=0)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ScheduleTask(TimestampMixin, Base):
    __tablename__ = "schedule_tasks"
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    plan_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("schedule_plans.id"), nullable=False
    )
    parent_task_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("schedule_tasks.id"), nullable=True
    )
    is_parent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    orchestration_id: Mapped[str] = mapped_column(String(36), nullable=False)
    agent_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    wagent_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    wagent_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    priority: Mapped[str] = mapped_column(String(10), default="medium")
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    original_scheduled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    current_scheduled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    delay_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    input_params: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    output_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    dependencies: Mapped[dict] = mapped_column(JSON, default=list)
    confirm_deadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    confirm_action: Mapped[str | None] = mapped_column(String(20), nullable=True)
    execution_log: Mapped[str | None] = mapped_column(Text, nullable=True)
    recurrence_cron: Mapped[str | None] = mapped_column(String(100), nullable=True)
    recurrence_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    recurrence_done: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
