from pydantic import BaseModel
from datetime import datetime
from typing import Optional

from app.schemas.agent import ParamDefinition


class DataSourceCreate(BaseModel):
    type: str
    name: str
    agent_id: Optional[str] = None
    dify_endpoint: Optional[str] = None
    dify_api_key: Optional[str] = None
    input_params: Optional[list[ParamDefinition]] = []
    output_params: Optional[list[ParamDefinition]] = []


class DataSourceUpdate(BaseModel):
    name: Optional[str] = None
    agent_id: Optional[str] = None
    dify_endpoint: Optional[str] = None
    dify_api_key: Optional[str] = None
    input_params: Optional[list[ParamDefinition]] = None
    output_params: Optional[list[ParamDefinition]] = None
    is_enabled: Optional[bool] = None


class DataSourceResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    name: str | None = None
    type: str
    agent_id: str | None = None
    dify_endpoint: str | None = None
    dify_api_key: str | None = None
    input_params: list[ParamDefinition] = []
    output_params: list[ParamDefinition] = []
    is_enabled: bool = True
    last_sync_at: datetime | None = None
    last_sync_status: str | None = None
    last_sync_error: str | None = None
    created_at: datetime
    updated_at: datetime
