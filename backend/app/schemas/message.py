from pydantic import BaseModel, field_serializer, field_validator
from datetime import datetime
from app.utils.timezone import utc_to_beijing_datetime


class MessageResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    type: str
    title: str
    content: str
    status: str
    related_type: str | None = None
    related_id: str | None = None
    action_url: str | None = None
    external_pushed: bool = False
    created_at: datetime

    @field_validator("created_at", mode="before")
    @classmethod
    def _convert_utc_to_beijing(cls, value):
        return utc_to_beijing_datetime(value)

    @field_serializer("created_at")
    def _serialize_created_at(self, value: datetime):
        return value.isoformat()

