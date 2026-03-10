from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class TodoCreate(BaseModel):
    title: str
    description: str | None = None
    priority: str = "medium"
    source: str = "manual"
    execution_mode: str = "system"
    due_date: datetime | None = None
    tags: list[str] = Field(default_factory=list)
    project: str | None = None


class TodoUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    source: Optional[str] = None
    execution_mode: Optional[str] = None
    due_date: Optional[datetime] = None
    tags: Optional[list[str]] = None
    project: Optional[str] = None


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
    project: str | None = None
    status: str
    source_ref: str | None = None
    review_status: str | None = None
    review_reason: str | None = None
    duplicate_of: str | None = None
    orchestration_id: str | None = None
    created_at: datetime
    updated_at: datetime


class TodoReviewConfirm(BaseModel):
    title: Optional[str] = None
    priority: Optional[str] = None
    due_date: Optional[datetime] = None
