from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from .models import FeedbackStatus, SugarPairStatus, TaskMemberResponse, TaskStatus, UserRole


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    @field_serializer(
        "created_at",
        "updated_at",
        "expires_at",
        "joined_at",
        "confirmed_at",
        "started_at",
        "completed_at",
        "publisher_confirmed_at",
        "handled_at",
        "cancelled_at",
        "cancel_requested_at",
        "publisher_cancel_confirmed_at",
        "initiated_at",
        "activated_at",
        "ended_at",
        check_fields=False,
    )
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


class UserPhotoOut(ApiModel):
    id: int
    image_url: str
    is_visible: bool = True


class UserPublic(ApiModel):
    id: int
    nickname: str
    bio: str | None = None
    photos: list[UserPhotoOut] = []


class UserProfileOut(ApiModel):
    """用户资料；QQ 按名录公开偏好及协作关系控制可见性。"""
    id: int
    nickname: str
    bio: str | None = None
    qq: str | None = None
    qq_public: bool = False
    is_admin: bool = False
    role: UserRole = UserRole.USER
    created_at: datetime
    photos: list[UserPhotoOut] = []


class UserSelf(UserPublic):
    username: str
    qq: str | None = None
    qq_public: bool = False
    is_admin: bool
    is_active: bool
    role: UserRole = UserRole.USER
    max_concurrent_tasks: int
    created_at: datetime


class UserUpdate(RequestModel):
    nickname: str = Field(min_length=1, max_length=32)
    qq: str | None = Field(default=None, max_length=20, pattern=r"^[0-9]{5,20}$")
    qq_public: bool = False
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
    # paid=有偿 free=无偿
    pay_type: Literal["paid", "free"] = "paid"
    reward: str | None = Field(default=None, max_length=60)
    # null 表示公开接取；设置密码时仍要求 4-32 位。
    accept_password: str | None = Field(default=None, min_length=4, max_length=32)
    # 需要几人接取；null / 缺省表示人数不限（只能由委托人手动开始）
    required_takers: int | None = Field(default=None, ge=1, le=999)
    # 非空时为指定委托，只允许名单内的店员/志愿者响应。
    designated_user_ids: list[int] = Field(default_factory=list, max_length=999)
    expires_in_days: Literal[1, 2, 3, 5, 10]


class AcceptRequest(RequestModel):
    password: str | None = Field(default=None, max_length=72)


class PasswordUpdate(RequestModel):
    password: str = Field(min_length=4, max_length=32)


class TaskMemberOut(ApiModel):
    user: UserPublic
    joined_at: datetime
    response_status: TaskMemberResponse = TaskMemberResponse.ACCEPTED
    confirmed_at: datetime | None = None
    cancel_confirmed_at: datetime | None = None
    # 联系方式只在协作双方可见时由后端填充
    qq: str | None = None


class TaskOut(ApiModel):
    id: int
    title: str
    description: str
    category: str
    reward: str | None
    pay_type: str = "paid"
    status: TaskStatus
    is_visible: bool
    admin_note: str | None = None
    publisher: UserPublic
    requires_password: bool
    required_takers: int | None = None
    is_designated: bool = False
    members: list[TaskMemberOut] = []
    publisher_id: int
    publisher_confirmed_at: datetime | None = None
    publisher_cancel_confirmed_at: datetime | None = None
    cancel_requested_by: int | None = None
    cancel_requested_at: datetime | None = None
    contact_qq: str | None = None
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    cancelled_at: datetime | None = None


class AdminTaskUpdate(RequestModel):
    is_visible: bool
    admin_note: str | None = Field(default=None, max_length=200)


class AdminUserOut(ApiModel):
    id: int
    username: str
    nickname: str
    is_admin: bool
    is_active: bool
    role: UserRole = UserRole.USER
    max_concurrent_tasks: int
    active_task_count: int = 0
    created_at: datetime
    photos: list[UserPhotoOut] = []


class AdminUserRoleUpdate(RequestModel):
    role: Literal["user", "volunteer", "staff"]


class AdminPhotoUpdate(RequestModel):
    is_visible: bool


class StaffDirectoryOut(BaseModel):
    group_chat_id: str
    staff: list[UserProfileOut]
    volunteers: list[UserProfileOut]


class AdminUserLimitUpdate(RequestModel):
    max_concurrent_tasks: int = Field(ge=0, le=999)


class FeedbackCreate(RequestModel):
    content: str = Field(min_length=5, max_length=2000)
    page: str | None = Field(default=None, max_length=120)
    # 游客填写联系方式便于管理员回复；登录用户可留空
    contact: str | None = Field(default=None, max_length=80)


class FeedbackUpdate(RequestModel):
    """管理员处理反馈：status 为 pending/handled，reply 为处理回复（可空）。"""
    status: FeedbackStatus | None = None
    reply: str | None = Field(default=None, max_length=1000)


class FeedbackOut(ApiModel):
    id: int
    page: str | None = None
    content: str
    contact: str | None = None
    status: FeedbackStatus
    reply: str | None = None
    created_at: datetime
    handled_at: datetime | None = None
    user: UserPublic | None = None


class AdminStats(BaseModel):
    users: int
    tasks: int
    published: int
    processing: int
    completed: int
    hidden: int


class SugarPhotoOut(BaseModel):
    id: int
    image_url: str


class SugarProfileCardOut(ApiModel):
    id: int
    user: UserPublic
    about: str
    photos: list[SugarPhotoOut] = []
    created_at: datetime
    updated_at: datetime


class SugarPairOut(ApiModel):
    id: int
    first_user: UserPublic
    second_user: UserPublic
    initiated_by_id: int
    status: SugarPairStatus
    initiated_at: datetime
    activated_at: datetime | None = None
    ended_at: datetime | None = None
    duration_seconds: int = 0


class SugarProfileDetailOut(SugarProfileCardOut):
    qq: str | None = None
    relationship: SugarPairOut | None = None
