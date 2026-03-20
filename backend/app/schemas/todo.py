from pydantic import BaseModel, Field, field_serializer, field_validator
from datetime import datetime
from typing import Optional
from app.utils.timezone import utc_to_beijing_datetime


class TodoCreate(BaseModel):
    title: str
    description: str | None = None
    priority: str = "medium"
    source: str = "manual"
    execution_mode: str = "system"
    due_date: datetime | None = None
    completed_at: datetime | None = None
    tags: list[str] = Field(default_factory=list)
    responsibility_ids: list[str] = Field(default_factory=list)
    responsibility_titles: list[str] = Field(default_factory=list)
    project: str | None = None
    is_recurring: bool = False
    recurrence_cron: str | None = None
    recurrence_count: int = 0


class TodoUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    source: Optional[str] = None
    execution_mode: Optional[str] = None
    due_date: Optional[datetime] = None
    tags: Optional[list[str]] = None
    responsibility_ids: Optional[list[str]] = None
    responsibility_titles: Optional[list[str]] = None
    project: Optional[str] = None
    is_recurring: Optional[bool] = None
    recurrence_cron: Optional[str] = None
    recurrence_count: Optional[int] = None


class TodoResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    title: str
    description: str | None = None
    priority: str = "medium"
    source: str = "manual"
    execution_mode: str = "system"
    due_date: datetime | None = None
    tags: list[str] = Field(default_factory=list)
    responsibility_ids: list[str] = Field(default_factory=list)
    responsibility_titles: list[str] = Field(default_factory=list)
    project: str | None = None
    status: str
    source_ref: str | None = None
    review_status: str | None = None
    review_reason: str | None = None
    duplicate_of: str | None = None
    orchestration_id: str | None = None
    is_recurring: bool = False
    recurrence_cron: str | None = None
    recurrence_count: int = 0
    created_at: datetime
    updated_at: datetime

    @field_validator("due_date", "created_at", "updated_at", mode="before")
    @classmethod
    def _convert_utc_to_beijing(cls, value):
        return utc_to_beijing_datetime(value)

    @field_serializer("due_date", "created_at", "updated_at")
    def _serialize_datetime(self, value: datetime | None):
        return value.isoformat() if value else None


class TodoReviewConfirm(BaseModel):
    title: Optional[str] = None
    priority: Optional[str] = None
    due_date: Optional[datetime] = None
