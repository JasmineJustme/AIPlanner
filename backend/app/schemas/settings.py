from pydantic import BaseModel
from typing import Optional, Any


class SystemSettingsUpdate(BaseModel):
    settings: dict[str, Any] = {}


class NotificationPrefUpdate(BaseModel):
    message_type: str
    in_app_enabled: Optional[bool] = None
    email_enabled: Optional[bool] = None
    wechat_enabled: Optional[bool] = None
    channel_enabled_map: Optional[dict[str, bool]] = None


class NotificationGlobalPrefUpdate(BaseModel):
    dnd_start: Optional[str] = None
    dnd_end: Optional[str] = None
    merge_strategy: Optional[str] = None
    merge_window_minutes: Optional[int] = None
    deadline_advance_minutes: Optional[int] = None
