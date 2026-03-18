from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Any


class ScheduleTaskResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    plan_id: str | None = None
    agent_id: str | None = None
    wagent_id: str | None = None
    status: str
    priority: str | None = None
    scheduled_at: datetime | None = None
    original_scheduled_at: datetime | None = None
    current_scheduled_at: datetime | None = None
    delay_count: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None
    input_params: dict[str, Any] = {}
    output_result: dict[str, Any] | None = None
    error_message: str | None = None
    retry_count: int = 0
    dependencies: list[str] = []
