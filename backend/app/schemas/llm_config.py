from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class LLMConfigUpdate(BaseModel):
    provider: Optional[str] = None
    model_name: Optional[str] = None
    api_endpoint: Optional[str] = None
    api_key: Optional[str] = None
    temperature: Optional[float] = None
    temperature_enabled: Optional[bool] = None
    top_p: Optional[float] = None
    top_p_enabled: Optional[bool] = None
    max_tokens: Optional[int] = None
    timeout: Optional[int] = None
    prompt_template: Optional[str] = None
    cost_alert_threshold: Optional[float] = None


class LLMConfigResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    provider: str | None = None
    model_name: str | None = None
    api_endpoint: str | None = None
    api_key: str | None = None
    temperature: float = 0.7
    temperature_enabled: bool = True
    top_p: float = 1.0
    top_p_enabled: bool = True
    max_tokens: int = 4096
    timeout: int = 180
    prompt_template: str = ""
    cost_alert_threshold: float | None = None
    purpose: str
    prompt_version: int = 1
    total_tokens_used: int = 0
    total_cost: float = 0.0
    created_at: datetime
    updated_at: datetime
