from datetime import datetime

from pydantic import BaseModel


class TodoFlowLogResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    todo_id: str
    action_type: str
    from_user_id: str | None = None
    to_user_id: str | None = None
    status_before: str | None = None
    status_after: str | None = None
    flow_state_before: str | None = None
    flow_state_after: str | None = None
    remark: str | None = None
    created_at: datetime


class TodoCollaborationRequestResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    todo_id: str
    source_user_id: str
    target_user_id: str
    request_status: str
    request_message: str | None = None
    accepted_at: datetime | None = None
    rejected_at: datetime | None = None
    rejected_reason: str | None = None
    created_at: datetime
    updated_at: datetime
