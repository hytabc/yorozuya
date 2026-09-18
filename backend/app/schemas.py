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


# 邮箱格式：不引入 email-validator 依赖，用够用的正则 + 长度上限；
# 真正的可达性由「必须点验证链接」来证明，因此这里只做基本形状校验。
EMAIL_PATTERN = r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$"


class RegisterRequest(RequestModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(min_length=8, max_length=72)
    nickname: str = Field(min_length=1, max_length=32)
    # 邮箱为注册必填项；注册后必须点验证邮件里的链接才能登录。
    email: str = Field(min_length=6, max_length=254, pattern=EMAIL_PATTERN)
    # 人机验证：builtin 用 captcha_id + captcha_code；turnstile 用 captcha_code 传 token。
    captcha_id: str = Field(default="", max_length=128)
    captcha_code: str = Field(default="", max_length=4096)


class LoginRequest(RequestModel):
    # 兼容用户名与邮箱两种登录名，因此上限放宽到邮箱的最大长度。
    # 同时限制长度，避免超长输入拖垮 PBKDF2 校验（CPU 消耗型拒绝服务）。
    username: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=128)
    # 勾选“自动登录”后签发 7 天有效令牌，否则维持 24 小时会话。
    remember: bool = False
    captcha_id: str = Field(default="", max_length=128)
    captcha_code: str = Field(default="", max_length=4096)


class ActionAckOut(BaseModel):
    """通用「已受理」响应：刻意不透露内部细节（例如账号是否存在）。"""

    ok: bool = True


class RegisterPendingOut(BaseModel):
    """注册成功但尚未验证：注册不再直接下发登录令牌。"""

    email_masked: str
    verification_sent: bool = True


class AccountRequest(RequestModel):
    """按用户名或邮箱定位账号（重发验证信 / 申请重置密码）。"""

    account: str = Field(min_length=1, max_length=254)
    captcha_id: str = Field(default="", max_length=128)
    captcha_code: str = Field(default="", max_length=4096)


class EmailVerifyRequest(RequestModel):
    token: str = Field(min_length=8, max_length=256)


class PasswordResetConfirm(RequestModel):
    token: str = Field(min_length=8, max_length=256)
    password: str = Field(min_length=8, max_length=72)


class EmailChangeRequest(RequestModel):
    email: str = Field(min_length=6, max_length=254, pattern=EMAIL_PATTERN)
    current_password: str = Field(min_length=1, max_length=128)


class NotifyEmailUpdate(RequestModel):
    notify_email: bool


class UserPhotoOut(ApiModel):
    id: int
    # 默认空串：万一有人把 ORM 的 UserPhoto 直接塞进来（from_attributes），
    # 得到的只是空地址而不是可访问的真实 URL —— 泄露是 fail-closed 的。
    # 真实地址一律由 visible_user_photos 按 is_visible 生成。
    image_url: str = ""
    is_visible: bool = True


class UserPublic(ApiModel):
    id: int
    nickname: str
    title: str | None = None
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
    title: str | None = None
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
    # 邮箱与验证状态：前端据此决定是否弹出「强制绑定验证」弹窗。
    email: str | None = None
    email_verified: bool = False
    # 换绑待确认的新地址（有值时前端提示「待确认」）。
    pending_email: str | None = None
    notify_email: bool = True
    # 服务端算好的「需要先完成邮箱验证」标记：前端据此弹强制绑定框，
    # 避免把 require_email_verification 这类策略在前端重写一遍。
    email_gate_required: bool = False
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
    - provider="click"：前端显示 image（data URL）与 prompt，按顺序点选 target_count 个图形，
      点击坐标以 captcha_code 回传。**响应绝不包含目标坐标，答案只存服务端。**
    """

    provider: str
    captcha_id: str = ""
    image: str | None = None
    expires_in: int = 0
    site_key: str | None = None
    # click 专用：题面文字与需要点击的目标数量。
    prompt: str | None = None
    target_count: int = 0


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
    title: str | None = None
    # 邮箱与验证状态：监管台据此找出「还没补充绑定邮箱」的存量账号并提供协助。
    email: str | None = None
    email_verified: bool = False
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


class AdminUserTitleUpdate(RequestModel):
    """管理员为用户设置自定义称号；空串表示清空。"""

    title: str | None = Field(default=None, max_length=16)

    @field_validator("title", mode="before")
    @classmethod
    def empty_to_none(cls, value):
        return value or None


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


class AdminSummary(BaseModel):
    """监管台轻量汇总：统计卡数字 + 各标签页待处理角标。

    列表数据改为按标签页懒加载后，角标单独由该接口提供，避免首屏并发拉取全部列表。
    """
    users: int = 0
    tasks: int = 0
    processing: int = 0
    completed: int = 0
    hidden: int = 0
    pending_reports: int = 0
    pending_feedbacks: int = 0
    pending_applications: int = 0
    pending_beta_applications: int = 0
    pending_vr_map_reports: int = 0
    pending_vr_map_photos: int = 0
    pending_story_photos: int = 0


class TaskStats(BaseModel):
    """大厅顶部统计：仅返回数量，不含任何委托内容。"""
    published: int
    processing: int
    completed: int


class SiteConfigOut(BaseModel):
    """站点公开配置：目前只有页脚备案号。

    备案号属于私有信息，值放在服务端 .env，前端运行时通过接口获取，
    避免被提交进公开仓库或打进前端构建产物。留空时前端不展示该行。
    """
    icp: str = ""
    icp_url: str = "https://beian.miit.gov.cn/"


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


# 全站埋点覆盖的页面 key：前端 router 的 meta.analyticsKey 必须与这里保持一致。
PageKeyLiteral = Literal[
    "hall", "staff", "board", "maps", "friends", "stories", "sugar",
    "announcements", "versions", "mine", "profile", "login", "frost",
    "operations", "admin", "life", "life-admin",
    "verify-email", "forgot-password", "reset-password",
]


class PageViewCreate(RequestModel):
    page_key: PageKeyLiteral
    session_id: str = Field(min_length=16, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")


class AnalyticsEventCreate(RequestModel):
    """关键行为事件埋点：event_key 由后端白名单校验，未知事件直接忽略。"""

    event_key: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9_.]+$")
    page_key: PageKeyLiteral | None = None
    session_id: str = Field(min_length=16, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")


class PageMetric(BaseModel):
    page_key: str
    label: str
    views: int
    visitors: int


class EventMetric(BaseModel):
    event_key: str
    label: str
    page_key: str | None = None
    page_label: str | None = None
    count: int


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
    # 关键行为事件计数（按事件 + 页面聚合），用于分析点击/使用偏好。
    events: list[EventMetric] = []


class OperationsSummary(BaseModel):
    """运营台轻量汇总：目前只提供「内测申请」待处理角标（看板娘也需要）。"""

    pending_beta_applications: int = 0


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
    vrc_nickname: str = ""
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
