from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List

from app.schemas.agent import ParamDefinition


class NotificationChannelUpdate(BaseModel):
    name: Optional[str] = None
    agent_id: Optional[str] = None
    dify_endpoint: Optional[str] = None
    dify_api_key: Optional[str] = None
    input_params: Optional[List[ParamDefinition]] = None
    input_mapping: Optional[dict] = None
    is_enabled: Optional[bool] = None
    message_field: Optional[str] = None


class NotificationChannelResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    channel_type: str
    name: str
    agent_id: str | None = None
    dify_endpoint: str
    dify_api_key: str
    input_params: List[ParamDefinition] = []
    input_mapping: dict = {}
    is_enabled: bool = True
    created_at: datetime
    updated_at: datetime
    message_field: str | None = None
