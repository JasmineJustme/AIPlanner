from datetime import datetime

from pydantic import BaseModel, Field


class ResponsibilityCreate(BaseModel):
    parent_id: str | None = None
    title: str
    description: str
    sort_order: int = 0


class ResponsibilityUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    sort_order: int | None = None


class ResponsibilityResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    parent_id: str | None = None
    title: str
    description: str
    sort_order: int = 0
    created_at: datetime
    updated_at: datetime


class ResponsibilityTreeNode(ResponsibilityResponse):
    children: list["ResponsibilityTreeNode"] = Field(default_factory=list)


ResponsibilityTreeNode.model_rebuild()
