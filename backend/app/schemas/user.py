from datetime import datetime

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str = Field(min_length=1)
    password: str = Field(min_length=1)
    login_type: str = Field(default="user", pattern="^(user|admin)$")


class AdminLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    is_admin: bool = True


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime


class OrgUnitCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    unit_type: str = Field(pattern="^(department|section)$")
    parent_id: str | None = None
    is_active: bool = True


class OrgUnitResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    name: str
    unit_type: str
    parent_id: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=128)
    email: str = Field(min_length=1, max_length=255)
    full_name: str | None = Field(default=None, max_length=200)
    role: str = Field(default="member")
    org_unit_id: str | None = None
    manager_id: str | None = None
    is_active: bool = True
    is_superuser: bool = False




class UserUpdate(BaseModel):
    password: str | None = Field(default=None, min_length=8, max_length=128)
    email: str | None = Field(default=None, min_length=1, max_length=255)
    full_name: str | None = Field(default=None, max_length=200)
    role: str | None = None
    org_unit_id: str | None = None
    manager_id: str | None = None
    is_active: bool | None = None


class UserResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    username: str
    email: str
    full_name: str | None = None
    role: str
    org_unit_id: str | None = None
    manager_id: str | None = None
    is_active: bool
    is_superuser: bool
    last_login_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class MeResponse(BaseModel):
    id: str
    username: str
    email: str
    role: str
    org_unit_id: str | None = None
    manager_id: str | None = None
    is_superuser: bool
    is_active: bool
