from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class DashboardStats(BaseModel):
    today_todo: int = 0
    pending_confirm: int = 0
    running: int = 0
    today_completed: int = 0
    failed: int = 0


class NextTask(BaseModel):
    id: str | None = None
    name: str | None = None
    scheduled_at: datetime | None = None
