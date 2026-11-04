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
    # 可选邀请码：注册时填写，注册后 7 天内也可补填一次。
    invite_code: str | None = Field(default=None, max_length=12)


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


class ThemePreferenceUpdate(RequestModel):
    """外观偏好。两个字段都可选：只传要改的那个，避免前端为了改明暗把风格也一并覆盖。"""

    theme_mode: Literal["auto", "system", "day", "night"] | None = None
    theme_style: Literal["classic", "pixel"] | None = None


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
    # 终身累计积分（公开）；钱包余额只在 UserSelf 里返回。
    lifetime_points: int = 0
    # 信誉等级：由 lifetime_points 推导，只升不降。
    level: int = 1
    photos: list[UserPhotoOut] = []
    # avatar_url 仅在查看者有权看到时由后端填充；未过审头像仅本人和管理员组可见
    avatar_url: str | None = None
    avatar_visible: bool = False
    is_beta_tester: bool = False


class ShareCreate(RequestModel):
    channel: Literal["dialog", "copy", "qrcode", "native"] = "dialog"


class InviteBindRequest(RequestModel):
    code: str = Field(min_length=4, max_length=12)


class DailyTaskOut(BaseModel):
    key: str
    label: str
    detail: str = ""
    reward: int = 0
    target: int = 1
    progress: int = 0
    claimed: bool = False
    can_claim: bool = False


class RankingEntryOut(BaseModel):
    rank: int
    user: UserPublic
    # 积分榜/完成数榜为整数，评分榜为贝叶斯分。
    value: float = 0
    count: int = 0
    is_me: bool = False


class RankingsOut(BaseModel):
    board: str
    title: str
    page: int
    page_size: int
    total: int
    min_count: int = 0
    items: list[RankingEntryOut] = []


class RankOptOutRequest(RequestModel):
    opt_out: bool


class UserLevelOut(BaseModel):
    level: int = 1
    lifetime_points: int = 0
    next_threshold: int | None = None
    taker_limit: int = 2
    bounty_cap: int = 20
    can_post_bounty: bool = False
    multi_taker: bool = True
    daily_publish_limit: int = 5
    publisher_rating_active: bool = False
    publisher_bayes: float = 0


class AchievementOut(ApiModel):
    key: str
    category: str
    name: str
    description: str
    reward: int = 0
    target: int = 1
    progress: int = 0
    unlocked: bool = False
    unlocked_at: datetime | None = None


class AchievementWallOut(BaseModel):
    unlocked: int = 0
    total: int = 0
    items: list[AchievementOut] = []


class DailyOut(BaseModel):
    day: str
    items: list[DailyTaskOut] = []
    claimed_count: int = 0


class DailyClaimOut(BaseModel):
    key: str
    reward: int = 0
    day: str
    lifetime_points: int = 0
    wallet_points: int = 0
    daily: DailyOut


class InviteInfoOut(BaseModel):
    code: str
    invited_total: int = 0
    valid_this_month: int = 0
    monthly_limit: int = 5
    inviter_bonus: int = 20
    invitee_bonus: int = 10
    invited_by: bool = False
    can_bind: bool = False


class ShareOut(BaseModel):
    path: str
    title: str
    channel: str
    shared_tasks_today: int = 0


class RatingStatsOut(BaseModel):
    count: int = 0
    average: float = 0
    # 贝叶斯平滑分：(C × m + Σstars) / (C + count)，避免「只做一单 5 星」霸榜。
    bayes: float = 0
    good: int = 0
    neutral: int = 0
    bad: int = 0


class UserRatingSummary(BaseModel):
    taker: RatingStatsOut = Field(default_factory=RatingStatsOut)
    publisher: RatingStatsOut = Field(default_factory=RatingStatsOut)


class UserRecordsOut(BaseModel):
    user_id: int
    lifetime_points: int = 0
    level: int = 1
    next_threshold: int | None = None
    joined_days: int = 0
    completed_taken: int = 0
    completed_published: int = 0
    published_total: int = 0
    first_completed_at: datetime | None = None
    last_completed_at: datetime | None = None
    taker_rating: RatingStatsOut = Field(default_factory=RatingStatsOut)
    publisher_rating: RatingStatsOut = Field(default_factory=RatingStatsOut)
    achievements_unlocked: int = 0
    top_categories: list[dict] = []


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
    lifetime_points: int = 0
    level: int = 1
    photos: list[UserPhotoOut] = []
    avatar_url: str | None = None
    avatar_visible: bool = False
    # 评分聚合：只在单用户资料接口里填充，列表接口保持为空以免 N+1。
    ratings: UserRatingSummary | None = None


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
    # 外观偏好：跟着账号走，登录后前端以服务端值为准。
    theme_mode: Literal["auto", "system", "day", "night"] = "auto"
    theme_style: Literal["classic", "pixel"] | None = None
    # 新手引导：已看过的引导版本号（0 = 从未看过）；前端据此决定是否展示一次。
    onboarding_version: int = 0
    # 服务端算好的「需要先完成邮箱验证」标记：前端据此弹强制绑定框，
    # 避免把 require_email_verification 这类策略在前端重写一遍。
    email_gate_required: bool = False
    is_admin: bool
    is_active: bool
    role: UserRole = UserRole.USER
    max_concurrent_tasks: int
    lifetime_points: int = 0
    # 钱包余额只对本人返回；公开资料里没有这个字段。
    wallet_points: int = 0
    # 邀请码：前端分享时附带 ?ref=，便于把分享和邀请绑定。
    invite_code: str | None = None
    rank_opt_out: bool = False
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
    - provider="vaptcha"：前端按 vaptcha_vid 初始化 VAPTCHA V4 SDK，调用 validate() 后把
      token/knock/dfu/ip 以 JSON 放进 captcha_code 提交。**下发的只有公开 VID，VKEY 绝不下发。**
    """

    provider: str
    captcha_id: str = ""
    image: str | None = None
    expires_in: int = 0
    site_key: str | None = None
    # click 专用：题面文字与需要点击的目标数量。
    prompt: str | None = None
    target_count: int = 0
    # vaptcha 专用：公开的 VID（前端初始化 SDK 用）。
    vaptcha_vid: str | None = None


FacetTypeLiteral = Literal["skill", "platform", "world", "atmosphere"]


class TaskFacetIn(RequestModel):
    """创建/修改委托时提交的模块化标签；白名单与数量上限由 facets.py 校验。"""

    facet_type: FacetTypeLiteral
    value: str = Field(min_length=1, max_length=64)


class TaskFacetUpdate(RequestModel):
    facets: list[TaskFacetIn] = Field(default_factory=list, max_length=16)


class TaskFacetOut(BaseModel):
    facet_type: str
    value: str


class TaskCreate(RequestModel):
    title: str = Field(min_length=2, max_length=80)
    description: str = Field(min_length=10, max_length=3000)
    category: str = Field(min_length=1, max_length=24)
    # 规模档位决定系统基础积分：small=5 / medium=15 / large=40，再按分类系数微调。
    scale: Literal["small", "medium", "large"] = "small"
    # 额外悬赏积分：从发布者钱包托管，完成时发给接单人。
    bounty_points: int = Field(default=0, ge=0, le=200)
    # 需要几人接取；null / 缺省表示人数不限（只能由委托人手动开始）
    required_takers: int | None = Field(default=None, ge=1, le=999)
    # 非空时为指定委托，只允许名单内的管理员/志愿者响应。
    designated_user_ids: list[int] = Field(default_factory=list, max_length=999)
    # 匿名发布：大厅仅展示标题和内容，接取后联系方式仅双方可见。
    is_anonymous: bool = False
    expires_in_days: Literal[1, 2, 3, 5, 10]
    # 模块化标签：技能 / 平台 / 参考 World / 氛围，均可选。
    facets: list[TaskFacetIn] = Field(default_factory=list, max_length=16)


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
    scale: str = "small"
    base_points: int = 0
    bounty_points: int = 0
    is_official: bool = False
    official_key: str | None = None
    status: TaskStatus
    is_visible: bool
    admin_note: str | None = None
    publisher: UserPublic
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
    # 模块化标签由各端点批量预取后填充；旧委托没有标签时为空数组。
    facets: list[TaskFacetOut] = []


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
    pending_house_textures: int = 0


class RatingCreate(RequestModel):
    """提交评价：stars_half 以半星为单位（0~10），0 星必须给原因。"""

    ratee_id: int
    stars_half: int = Field(ge=0, le=10)
    comment: str | None = Field(default=None, max_length=200)
    reason_code: str | None = Field(default=None, max_length=24)


class RatingUpdate(RequestModel):
    stars_half: int = Field(ge=0, le=10)
    comment: str | None = Field(default=None, max_length=200)
    reason_code: str | None = Field(default=None, max_length=24)


class RatingOut(ApiModel):
    id: int
    rater_id: int
    ratee_id: int
    rater_role: str
    stars: float
    comment: str | None = None
    reason_code: str | None = None
    reason_label: str | None = None
    automatic: bool = False
    created_at: datetime
    revealed: bool = False
    editable_until: datetime | None = None
    can_edit: bool = False
    # 申诉撤销后为 True：前端据此隐藏内容并停止展示申诉入口。
    revoked: bool = False


class RatingSlotOut(BaseModel):
    counterpart: UserPublic
    my_rating: RatingOut | None = None
    their_rating: RatingOut | None = None
    can_rate: bool = False
    can_edit: bool = False


class TaskRatingsOut(ApiModel):
    deadline: datetime | None = None
    role: str | None = None
    can_rate: bool = False
    slots: list[RatingSlotOut] = []
    # 非参与者看到的已解盲评价。
    public: list[RatingOut] = []


class RatingAppealCreate(RequestModel):
    reason: str = Field(min_length=20, max_length=500)


class RatingAppealResolve(RequestModel):
    action: Literal["reject", "revoke", "change"]
    # action=change 时必填，其余情况忽略。
    stars_half: int | None = Field(default=None, ge=0, le=10)
    note: str | None = Field(default=None, max_length=300)


class RatingAppealOut(ApiModel):
    id: int
    rating_id: int
    reason: str
    status: str
    admin_note: str | None = None
    created_at: datetime
    handled_at: datetime | None = None
    user: UserPublic
    # 被申诉评价的摘要（管理员列表与本人查询都需要）。
    stars: float = 0
    comment: str | None = None
    rater_role: str = ""
    task_id: int = 0
    task_title: str = ""


class RatingPublicOut(ApiModel):
    id: int
    stars: float
    comment: str | None = None
    reason_code: str | None = None
    reason_label: str | None = None
    role: str
    task_id: int
    task_title: str = ""
    task_category: str = ""
    rater: UserPublic
    created_at: datetime
    automatic: bool = False


class RatingPublicPage(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[RatingPublicOut] = []


class PointsSummary(BaseModel):
    """积分概览：终身累计公开，钱包余额仅本人可见。"""

    lifetime_points: int = 0
    wallet_points: int = 0


class PointLedgerOut(BaseModel):
    id: int
    kind: str
    kind_label: str
    lifetime_delta: int = 0
    wallet_delta: int = 0
    note: str | None = None
    created_at: datetime


class PointLedgerPage(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[PointLedgerOut] = []


class PointsRules(BaseModel):
    """积分规则（前端发布页据此实时预览，避免把系数在两端各写一份）。"""

    scale_points: dict[str, int]
    scale_labels: dict[str, str]
    category_factors: dict[str, float]
    bounty_min: int
    bounty_max: int
    advance_ratio: float
    pair_decay: dict[int, float]
    daily_system_cap: int
    new_account_days: int
    new_account_factor: float


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
    # 大厅「星图」入口是否可用；列表始终可用，星图只是补充视图。
    hall_space_view: bool = True


class AtmosphereAckRequest(RequestModel):
    """礼仪确认：携带前端当前看到的版本号，版本不一致时后端拒绝。"""

    version: int = Field(ge=1, le=1000)


class AtmosphereStatusOut(BaseModel):
    version: int
    accepted: bool = False
    accepted_version: int = 0


class OnboardingAckRequest(RequestModel):
    """新手引导完成/跳过：携带前端当前展示的引导版本号。"""

    version: int = Field(ge=1, le=1000)


class OnboardingStatusOut(BaseModel):
    onboarding_version: int = 0


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
    "hall", "staff", "board", "talk", "maps", "friends", "stories", "sugar",
    "announcements", "versions", "mine", "profile", "login", "frost",
    "operations", "admin", "life", "life-admin", "house", "terms",
    "creator", "credential", "daily", "rankings",
    "verify-email", "forgot-password", "reset-password",
]


class PageViewCreate(RequestModel):
    page_key: PageKeyLiteral
    session_id: str = Field(min_length=16, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")


class PageDwellCreate(RequestModel):
    """页面曝光时长：离页结算一次，seconds 为本次可见停留秒数。"""

    page_key: PageKeyLiteral
    # 单次上限 2 小时：前端已截断，这里再兜底防止有人直接 POST 天文数字污染均值。
    seconds: int = Field(ge=1, le=7200)
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
    # 游客（未登录）与登录用户拆分：views 按次数、visitors 按去重访客。
    guest_views: int = 0
    user_views: int = 0
    guest_visitors: int = 0
    user_visitors: int = 0
    # 曝光时长：dwell_sessions 为结算次数，avg_seconds 为单次平均可见秒数。
    dwell_sessions: int = 0
    total_seconds: int = 0
    avg_seconds: float = 0


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
    guest_views: int = 0
    user_views: int = 0
    guest_visitors: int = 0
    user_visitors: int = 0


class DeviceMetric(BaseModel):
    """设备维度聚合：PC 端 / 手机端 / 平板 / 其他。"""

    device: str
    label: str
    views: int
    visitors: int
    dwell_sessions: int = 0
    total_seconds: int = 0
    avg_seconds: float = 0


class AnalyticsOut(BaseModel):
    days: int
    total_views: int
    total_visitors: int
    today_views: int
    today_visitors: int
    # 周期总量按游客 / 登录用户拆分。
    guest_views: int = 0
    user_views: int = 0
    guest_visitors: int = 0
    user_visitors: int = 0
    # 周期总曝光时长与单次平均停留。
    total_seconds: int = 0
    avg_seconds: float = 0
    pages: list[PageMetric]
    daily: list[DailyMetric]
    devices: list[DeviceMetric] = []
    # 关键行为事件计数（按事件 + 页面聚合），用于分析点击/使用偏好。
    events: list[EventMetric] = []


class OperationsSummary(BaseModel):
    """运营台轻量汇总：目前只提供「内测申请」待处理角标（看板娘也需要）。"""

    pending_beta_applications: int = 0


class SugarPhotoOut(BaseModel):
    id: int
    image_url: str
    # is_visible=False 的照片仅主人和管理员组会收到；moderated 为空表示待审核，admin_note 为屏蔽理由
    is_visible: bool = True
    moderated: bool = False
    admin_note: str | None = None


class SugarPhotoAdminOut(ApiModel):
    id: int
    image_url: str
    is_visible: bool
    moderated: bool = False
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


# ---- 交流大厅·疑难解答区 ----
# 子版块 key 与 main.py 的 TALK_BOARDS 保持一致。
TalkBoardLiteral = Literal["newbie", "tech", "vrc", "resource", "chat", "other"]


class TalkThreadCreate(RequestModel):
    board: TalkBoardLiteral
    title: str = Field(min_length=2, max_length=80)
    content: str = Field(min_length=5, max_length=5000)
    is_anonymous: bool = False


class TalkReplyCreate(RequestModel):
    content: str = Field(min_length=1, max_length=2000)
    is_anonymous: bool = False


class TalkAcceptRequest(RequestModel):
    """采纳最佳回答；reply_id 为 null 表示取消采纳。"""

    reply_id: int | None = None


class TalkReplyOut(BaseModel):
    id: int
    floor: int
    content: str
    created_at: datetime
    user: UserPublic
    is_anonymous: bool = False
    accepted: bool = False
    can_delete: bool = False


class TalkThreadCardOut(BaseModel):
    id: int
    board: str
    board_label: str
    title: str
    excerpt: str = ""
    user: UserPublic
    is_anonymous: bool = False
    reply_count: int = 0
    solved: bool = False
    last_reply_at: datetime
    created_at: datetime
    can_delete: bool = False


class TalkThreadDetailOut(TalkThreadCardOut):
    content: str
    accepted_reply_id: int | None = None
    can_accept: bool = False


class TalkThreadListOut(BaseModel):
    """列表分页：全站首个分页约定，字段名统一为 total/page/page_size/items。"""

    total: int
    page: int
    page_size: int
    items: list[TalkThreadCardOut] = []


class TalkThreadDetailPageOut(BaseModel):
    thread: TalkThreadDetailOut
    reply_total: int
    reply_page: int
    reply_page_size: int
    replies: list[TalkReplyOut] = []


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
