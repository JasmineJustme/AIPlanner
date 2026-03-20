from pydantic import BaseModel, field_serializer, field_validator
from datetime import datetime
from app.utils.timezone import utc_to_beijing_datetime


class AuditLogResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    action: str
    resource_type: str
    resource_id: str | None = None
    resource_name: str | None = None
    details: dict | None = None
    ip_address: str | None = None
    user_id: str
    created_at: datetime

    @field_validator("created_at", mode="before")
    @classmethod
    def _convert_utc_to_beijing(cls, value):
        return utc_to_beijing_datetime(value)

    @field_serializer("created_at")
    def _serialize_created_at(self, value: datetime):
        return value.isoformat()

