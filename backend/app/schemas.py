from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from .models import TaskStatus


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    @field_serializer("created_at", "updated_at", "expires_at", "accepted_at", "submitted_at", "completed_at", check_fields=False)
    def serialize_datetime(self, value: datetime | None):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class RequestModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)


class RegisterRequest(RequestModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(min_length=8, max_length=72)
    nickname: str = Field(min_length=1, max_length=32)


class LoginRequest(RequestModel):
    username: str
    password: str


class UserPublic(ApiModel):
    id: int
    nickname: str
    bio: str | None = None


class UserSelf(UserPublic):
    username: str
    qq: str | None = None
    is_admin: bool
    is_active: bool
    created_at: datetime


class UserUpdate(RequestModel):
    nickname: str = Field(min_length=1, max_length=32)
    qq: str | None = Field(default=None, max_length=20, pattern=r"^[0-9]{5,20}$")
    bio: str | None = Field(default=None, max_length=300)

    @field_validator("qq", "bio", mode="before")
    @classmethod
    def empty_to_none(cls, value):
        return value or None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserSelf


class TaskCreate(RequestModel):
    title: str = Field(min_length=2, max_length=80)
    description: str = Field(min_length=10, max_length=3000)
    category: str = Field(min_length=1, max_length=24)
    reward: str | None = Field(default=None, max_length=60)
    expires_at: datetime

    @field_validator("expires_at")
    @classmethod
    def normalize_expiry(cls, value: datetime):
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value


class TaskOut(ApiModel):
    id: int
    title: str
    description: str
    category: str
    reward: str | None
    status: TaskStatus
    is_visible: bool
    admin_note: str | None = None
    publisher: UserPublic
    assignee: UserPublic | None = None
    publisher_id: int
    assignee_id: int | None
    contact_qq: str | None = None
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    accepted_at: datetime | None
    submitted_at: datetime | None
    completed_at: datetime | None


class AdminTaskUpdate(RequestModel):
    is_visible: bool
    admin_note: str | None = Field(default=None, max_length=200)


class AdminStats(BaseModel):
    users: int
    tasks: int
    published: int
    processing: int
    completed: int
    hidden: int
