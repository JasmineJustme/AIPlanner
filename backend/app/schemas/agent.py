from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class ParamDefinition(BaseModel):
    name: str
    type: str
    required: bool = False
    # True means this param should be filled by user in config/confirm forms.
    user_fill_enabled: bool = False
    default: str | None = None
    value: str | None = None
    description: str | None = None


class AgentCreate(BaseModel):
    name: str
    description: str | None = None
    capability_tags: list[str] = []
    dify_endpoint: str
    dify_api_key: str
    input_params: list[ParamDefinition] = []
    output_params: list[ParamDefinition] = []
    timeout_seconds: int = 300
    auto_execute: bool = False
    confirm_before_exec: bool = True


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    capability_tags: Optional[list[str]] = None
    dify_endpoint: Optional[str] = None
    dify_api_key: Optional[str] = None
    input_params: Optional[list[ParamDefinition]] = None
    output_params: Optional[list[ParamDefinition]] = None
    timeout_seconds: Optional[int] = None
    auto_execute: Optional[bool] = None
    confirm_before_exec: Optional[bool] = None


class AgentResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    name: str
    description: str | None = None
    capability_tags: list[str] = []
    dify_endpoint: str
    dify_api_key: str
    input_params: list[ParamDefinition] = []
    output_params: list[ParamDefinition] = []
    timeout_seconds: int = 300
    auto_execute: bool = False
    confirm_before_exec: bool = True
    is_enabled: bool = True
    call_count: int = 0
    success_count: int = 0
    created_at: datetime
    updated_at: datetime
    user_id: str | None = None


class AgentListResponse(BaseModel):
    items: list[AgentResponse] = []
