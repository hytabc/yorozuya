from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator

from .models import (
    ApplicationStatus,
    AnnouncementKind,
    FeedbackStatus,
    FriendRequestStatus,
    ReportStatus,
    SugarPairStatus,
    TaskMemberResponse,
    TaskStatus,
    UserRole,
)


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
        "responded_at",
        "starts_at",
        "ends_at",
        check_fields=False,
    )
    def serialize_datetime(self, value: datetime | None):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class RequestModel(BaseModel):
    # extra="forbid"：拒绝多余字段，杜绝通过请求体夹带 role / is_admin 之类的越权字段
    # （即便处理器只读取白名单字段，也在入口处显式报错而不是静默忽略）。
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class RegisterRequest(RequestModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(min_length=8, max_length=72)
    nickname: str = Field(min_length=1, max_length=32)
    # 人机验证：builtin 用 captcha_id + captcha_code；turnstile 用 captcha_code 传 token。
    captcha_id: str = Field(default="", max_length=128)
    captcha_code: str = Field(default="", max_length=4096)


class LoginRequest(RequestModel):
    # 限制长度，避免超长输入拖垮 PBKDF2 校验（CPU 消耗型拒绝服务）。
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)
    # 勾选“自动登录”后签发 7 天有效令牌，否则维持 24 小时会话。
    remember: bool = False
    captcha_id: str = Field(default="", max_length=128)
    captcha_code: str = Field(default="", max_length=4096)


class UserPhotoOut(ApiModel):
    id: int
    image_url: str
    is_visible: bool = True


class UserPublic(ApiModel):
    id: int
    nickname: str
    bio: str | None = None
    photos: list[UserPhotoOut] = []
    # avatar_url 仅在查看者有权看到时由后端填充；未过审头像仅本人和管理员组可见
    avatar_url: str | None = None
    avatar_visible: bool = False
    is_beta_tester: bool = False


class UserProfileOut(ApiModel):
    """用户资料；QQ 按名录公开偏好及协作关系控制可见性。"""
    id: int
    nickname: str
    bio: str | None = None
    qq: str | None = None
    qq_public: bool = False
    is_admin: bool = False
    role: UserRole = UserRole.USER
    is_beta_tester: bool = False
    created_at: datetime
    photos: list[UserPhotoOut] = []
    avatar_url: str | None = None
    avatar_visible: bool = False


class UserSelf(UserPublic):
    username: str
    qq: str | None = None
    qq_public: bool = False
    is_admin: bool
    is_active: bool
    role: UserRole = UserRole.USER
    max_concurrent_tasks: int
    is_beta_tester: bool = False
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
    # 是否签发了“自动登录”（7 天）令牌，前端据此决定本地缓存的有效期窗口。
    remember: bool = False


class CaptchaChallenge(ApiModel):
    """前端拉取的人机验证配置。

    - provider="off"：当前未启用验证码，前端不渲染任何控件。
    - provider="turnstile"：前端按 site_key 渲染 Cloudflare Turnstile。
    - provider="builtin"：前端显示 image（data URL）并要求填写 captcha_code。
    """

    provider: str
    captcha_id: str = ""
    image: str | None = None
    expires_in: int = 0
    site_key: str | None = None


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
    # 非空时为指定委托，只允许名单内的管理员/志愿者响应。
    designated_user_ids: list[int] = Field(default_factory=list, max_length=999)
    # 匿名发布：大厅仅展示标题和内容，接取后联系方式仅双方可见。
    is_anonymous: bool = False
    expires_in_days: Literal[1, 2, 3, 5, 10]


class AcceptRequest(RequestModel):
    password: str | None = Field(default=None, max_length=72)


class PasswordUpdate(RequestModel):
    password: str = Field(min_length=4, max_length=32)


class UserPasswordUpdate(RequestModel):
    """用户自助修改登录密码：必须校验当前密码，防止令牌被盗后直接改密夺号。"""
    current_password: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=8, max_length=72)


class AdminPasswordReset(RequestModel):
    """超级管理员重置他人密码：不需要对方当前密码。"""
    password: str = Field(min_length=8, max_length=72)


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
    is_anonymous: bool = False
    reported: bool = False
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
    is_beta_tester: bool = False
    max_concurrent_tasks: int
    active_task_count: int = 0
    created_at: datetime
    photos: list[UserPhotoOut] = []


class AdminUserRoleUpdate(RequestModel):
    role: Literal["user", "volunteer", "staff", "mascot", "disciplinarian"]


class AdminUserBetaUpdate(RequestModel):
    is_beta_tester: bool


class AdminPhotoUpdate(RequestModel):
    is_visible: bool


class StaffDirectoryOut(BaseModel):
    staff: list[UserProfileOut]
    disciplinarians: list[UserProfileOut]
    mascots: list[UserProfileOut]
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


class ReportCreate(RequestModel):
    reason: str = Field(min_length=2, max_length=200)


class TaskReportOut(ApiModel):
    id: int
    task_id: int
    task_title: str = ''
    task_status: TaskStatus = TaskStatus.PUBLISHED
    reporter: UserPublic
    reason: str
    status: ReportStatus = ReportStatus.PENDING
    created_at: datetime
    handled_at: datetime | None = None


class ReportResolveRequest(RequestModel):
    action: Literal['close', 'hide', 'restore']
    admin_note: str | None = Field(default=None, max_length=200)


class ReportLimitOut(BaseModel):
    daily_limit: int


class VolunteerApplicationCreate(RequestModel):
    reason: str = Field(min_length=10, max_length=500)


class VolunteerApplicationReview(RequestModel):
    """管理员审核志愿者申请：approve 通过（升为志愿者）/ reject 拒绝。"""
    action: Literal["approve", "reject"]
    note: str | None = Field(default=None, max_length=500)


class VolunteerApplicationOut(ApiModel):
    id: int
    reason: str
    status: ApplicationStatus
    review_note: str | None = None
    created_at: datetime
    handled_at: datetime | None = None
    user: UserPublic


class VolunteerApplicationAdminOut(VolunteerApplicationOut):
    handled_by: UserPublic | None = None


class BetaApplicationCreate(RequestModel):
    reason: str = Field(min_length=10, max_length=500)


class BetaApplicationReview(RequestModel):
    action: Literal["approve", "reject"]
    note: str | None = Field(default=None, max_length=500)


class BetaApplicationOut(ApiModel):
    id: int
    reason: str
    status: ApplicationStatus
    review_note: str | None = None
    created_at: datetime
    handled_at: datetime | None = None
    user: UserPublic


class BetaApplicationAdminOut(BetaApplicationOut):
    handled_by: UserPublic | None = None


class ReportLimitUpdate(RequestModel):
    daily_limit: int = Field(ge=1, le=100)


class AdminStats(BaseModel):
    users: int
    tasks: int
    published: int
    processing: int
    completed: int
    hidden: int


class TaskStats(BaseModel):
    """大厅顶部统计：仅返回数量，不含任何委托内容。"""
    published: int
    processing: int
    completed: int


class AnnouncementWrite(RequestModel):
    kind: AnnouncementKind
    title: str = Field(min_length=2, max_length=80)
    content: str = Field(min_length=2, max_length=5000)
    is_published: bool = False
    is_pinned: bool = False
    starts_at: datetime | None = None
    ends_at: datetime | None = None

    @model_validator(mode="after")
    def validate_schedule(self):
        def comparable(value: datetime) -> datetime:
            if value.tzinfo is None:
                return value
            return value.astimezone(timezone.utc).replace(tzinfo=None)

        if self.starts_at and self.ends_at and comparable(self.ends_at) <= comparable(self.starts_at):
            raise ValueError("结束时间必须晚于开始时间")
        return self


class AnnouncementOut(ApiModel):
    id: int
    kind: AnnouncementKind
    title: str
    content: str
    is_published: bool
    is_pinned: bool
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    author_name: str
    created_at: datetime
    updated_at: datetime


class PageViewCreate(RequestModel):
    page_key: Literal["hall", "staff", "board", "maps", "friends", "sugar", "announcements", "versions", "mine", "profile", "login", "frost"]
    session_id: str = Field(min_length=16, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")


class PageMetric(BaseModel):
    page_key: str
    label: str
    views: int
    visitors: int


class DailyMetric(BaseModel):
    date: str
    views: int
    visitors: int


class AnalyticsOut(BaseModel):
    days: int
    total_views: int
    total_visitors: int
    today_views: int
    today_visitors: int
    pages: list[PageMetric]
    daily: list[DailyMetric]


class SugarPhotoOut(BaseModel):
    id: int
    image_url: str
    # is_visible=False 的照片仅主人和管理员组会收到；admin_note 为屏蔽理由
    is_visible: bool = True
    admin_note: str | None = None


class SugarPhotoAdminOut(ApiModel):
    id: int
    image_url: str
    is_visible: bool
    admin_note: str | None = None
    created_at: datetime
    user: UserPublic


class SugarPhotoModerateUpdate(RequestModel):
    """砂糖社照片审核：屏蔽时必须提供理由，恢复时可清空。"""
    is_visible: bool
    admin_note: str | None = Field(default=None, max_length=200)


class FriendPhotoOut(ApiModel):
    id: int
    image_url: str
    is_visible: bool = False
    admin_note: str | None = None


class FriendPhotoAdminOut(ApiModel):
    id: int
    image_url: str
    is_visible: bool
    admin_note: str | None = None
    moderated: bool = False
    created_at: datetime
    user: UserPublic


class FriendPhotoModerateUpdate(RequestModel):
    is_visible: bool
    admin_note: str | None = Field(default=None, max_length=200)


class VrMapCreate(RequestModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=10, max_length=2000)
    category: str = Field(min_length=1, max_length=16)


class VrMapLikeState(BaseModel):
    like_count: int
    liked: bool


class VrMapPhotoOut(BaseModel):
    id: int
    image_url: str
    # is_visible=False 的照片仅上传者和管理员组会收到；moderated_at 为空表示审核中
    is_visible: bool = False
    moderated: bool = False
    uploaded_by_me: bool = False


class VrMapOut(ApiModel):
    id: int
    name: str
    description: str
    category: str
    like_count: int = 0
    liked_by_me: bool = False
    reported_by_me: bool = False
    has_pending_report: bool = False
    is_visible: bool = True
    admin_note: str | None = None
    uploader: UserPublic
    photos: list[VrMapPhotoOut] = []
    created_at: datetime


class VrMapReportCreate(RequestModel):
    reason: str = Field(min_length=2, max_length=200)


class VrMapReportOut(ApiModel):
    id: int
    map_id: int
    map_name: str = ''
    reporter: UserPublic
    reason: str
    status: ReportStatus = ReportStatus.PENDING
    created_at: datetime
    handled_at: datetime | None = None


class VrMapReportResolveRequest(RequestModel):
    action: Literal["close", "hide", "restore"]
    admin_note: str | None = Field(default=None, max_length=200)


class VrMapPhotoAdminOut(ApiModel):
    id: int
    image_url: str
    is_visible: bool
    moderated: bool
    map_id: int
    map_name: str
    user: UserPublic
    created_at: datetime


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


class FriendRequestOut(ApiModel):
    id: int
    requester_id: int
    status: FriendRequestStatus
    created_at: datetime
    responded_at: datetime | None = None
    requester: UserPublic
    target: UserPublic


class FriendProfileCardOut(ApiModel):
    id: int
    user: UserPublic
    about: str
    photos: list[FriendPhotoOut] = []
    friend_count: int = 0
    created_at: datetime
    updated_at: datetime


class FriendProfileDetailOut(FriendProfileCardOut):
    qq: str | None = None
    relationship: FriendRequestOut | None = None


class FriendLeaderboardOut(ApiModel):
    user: UserPublic
    photo: FriendPhotoOut | None = None
    friend_count: int = 0


class BoardPostCreate(RequestModel):
    content: str = Field(min_length=1, max_length=500)


class BoardCommentCreate(RequestModel):
    content: str = Field(min_length=1, max_length=500)


class BoardCommentOut(ApiModel):
    id: int
    content: str
    created_at: datetime
    user: UserPublic
    can_delete: bool = False


class BoardMessageOut(ApiModel):
    id: int
    content: str
    created_at: datetime
    user: UserPublic
    comments: list[BoardCommentOut] = []
    can_delete: bool = False


class StoryCreate(RequestModel):
    title: str = Field(min_length=1, max_length=80)
    content: str = Field(min_length=10, max_length=5000)
    is_anonymous: bool = False


class StoryCommentCreate(RequestModel):
    content: str = Field(min_length=1, max_length=500)


class StoryPhotoOut(ApiModel):
    id: int
    image_url: str
    # is_visible=False 的照片仅作者本人和管理员组会收到；moderated 为 False 表示审核中
    is_visible: bool = False
    moderated: bool = False
    uploaded_by_me: bool = False


class StoryCommentOut(ApiModel):
    id: int
    content: str
    created_at: datetime
    user: UserPublic
    can_delete: bool = False


class StoryCardOut(ApiModel):
    id: int
    title: str
    excerpt: str = ''
    author: UserPublic
    is_anonymous: bool = False
    cover_url: str | None = None
    photo_count: int = 0
    comment_count: int = 0
    created_at: datetime
    can_delete: bool = False


class StoryDetailOut(ApiModel):
    id: int
    title: str
    content: str
    author: UserPublic
    is_anonymous: bool = False
    photos: list[StoryPhotoOut] = []
    comments: list[StoryCommentOut] = []
    created_at: datetime
    can_delete: bool = False


class StoryPhotoAdminOut(ApiModel):
    id: int
    image_url: str
    is_visible: bool
    moderated: bool
    story_id: int
    story_title: str
    user: UserPublic
    created_at: datetime
