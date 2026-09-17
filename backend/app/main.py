from __future__ import annotations

import base64
import logging
import re
import secrets
import sys
from contextlib import asynccontextmanager
from datetime import datetime, time, timedelta, timezone
from errno import EACCES, ENOSPC, EPERM, EROFS
from hashlib import sha256
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BeforeValidator, ValidationError
from sqlalchemy import delete, func, or_, select, text, update
from sqlalchemy.orm import Session, joinedload

from .config import PLACEHOLDER_ADMIN_PASSWORDS, settings
from .backup import skip_next_snapshot
from .captcha import captcha_required, create_image_captcha, verify_captcha
from .database import Base, SessionLocal, engine, get_db
from .email_flow import (
    CHANGE_EMAIL,
    EMAIL_TAKEN_DETAIL,
    INVALID_TOKEN_DETAIL,
    RESET_PASSWORD,
    VERIFY_EMAIL,
    base_url,
    cooldown_remaining,
    consume_link_token,
    deliver,
    email_taken,
    find_account,
    hash_link_token,
    issue_link_token,
    lock_credentials,
    revoke_credentials,
    notification_target,
    notify_address,
    reset_link,
    verify_link,
)
from .images import AVATAR_SIGNATURES, normalize_image
from .mailer import (
    change_email_message,
    email_changed_notice,
    mask_email,
    new_email_pending_notice,
    password_changed_notice,
    reset_password_message,
    send_email,
    verification_message,
)
from .media import commit_moderation, delete_media, media_url, place_media, storage_file, verify_media_signature, write_media
from .ratelimit import client_ip, enforce
from .dependencies import email_gate_required, get_admin, get_authenticated_user, get_beta_application_manager, get_content_moderator, get_current_user, get_operations_manager, get_optional_user, get_role_manager
from .models import (
    AnalyticsEvent,
    AppSetting,
    ApplicationStatus,
    Announcement,
    AnnouncementKind,
    BoardComment,
    BoardMessage,
    BetaApplication,
    EmailToken,
    Feedback,
    FeedbackStatus,
    FriendPhoto,
    FriendProfile,
    FriendRequest,
    FriendRequestStatus,
    PageView,
    ReportStatus,
    SugarPair,
    SugarPairStatus,
    SugarPhoto,
    SugarProfile,
    Story,
    StoryComment,
    StoryPhoto,
    Task,
    TaskMember,
    TaskMemberResponse,
    TaskReport,
    TaskStatus,
    User,
    UserPhoto,
    UserRole,
    VrMap,
    VrMapLike,
    VrMapPhoto,
    VrMapReport,
    VolunteerApplication,
)
from .schemas import (
    AcceptRequest,
    AccountRequest,
    ActionAckOut,
    EmailChangeRequest,
    EmailVerifyRequest,
    NotifyEmailUpdate,
    PasswordResetConfirm,
    RegisterPendingOut,
    AnalyticsEventCreate,
    AnalyticsOut,
    AnnouncementOut,
    AnnouncementWrite,
    AdminPasswordReset,
    AdminStats,
    AdminSummary,
    AdminTaskUpdate,
    AdminUserLimitUpdate,
    AdminUserBetaUpdate,
    AdminUserOut,
    AdminUserRoleUpdate,
    AdminUserTitleUpdate,
    AdminPhotoUpdate,
    CaptchaChallenge,
    FeedbackCreate,
    FeedbackOut,
    FeedbackUpdate,
    FriendLeaderboardOut,
    FriendPhotoAdminOut,
    FriendPhotoModerateUpdate,
    FriendPhotoOut,
    FriendProfileCardOut,
    FriendProfileDetailOut,
    FriendRequestOut,
    LoginRequest,
    PasswordUpdate,
    PageMetric,
    PageViewCreate,
    EventMetric,
    OperationsSummary,
    DailyMetric,
    ReportCreate,
    ReportLimitOut,
    ReportLimitUpdate,
    ReportResolveRequest,
    RegisterRequest,
    SiteConfigOut,
    TaskCreate,
    TaskMemberOut,
    TaskOut,
    TaskReportOut,
    TaskStats,
    StaffDirectoryOut,
    SugarPairOut,
    SugarPhotoAdminOut,
    SugarPhotoOut,
    SugarPhotoModerateUpdate,
    SugarProfileCardOut,
    SugarProfileDetailOut,
    TokenResponse,
    UserPasswordUpdate,
    UserPublic,
    UserProfileOut,
    UserPhotoOut,
    UserSelf,
    UserUpdate,
    BoardCommentCreate,
    BoardCommentOut,
    BoardMessageOut,
    BoardPostCreate,
    StoryCardOut,
    StoryCommentCreate,
    StoryCommentOut,
    StoryCreate,
    StoryDetailOut,
    StoryPhotoAdminOut,
    StoryPhotoOut,
    BetaApplicationAdminOut,
    BetaApplicationCreate,
    BetaApplicationOut,
    BetaApplicationReview,
    VolunteerApplicationAdminOut,
    VolunteerApplicationCreate,
    VolunteerApplicationOut,
    VolunteerApplicationReview,
    VrMapCreate,
    VrMapLikeState,
    VrMapOut,
    VrMapPhotoAdminOut,
    VrMapPhotoOut,
    VrMapReportCreate,
    VrMapReportOut,
    VrMapReportResolveRequest,
)
from .security import (
    create_access_token,
    equalize_password_check,
    hash_password,
    password_needs_rehash,
    verify_password,
)
from .sugar_frost import router as sugar_frost_router
from .virtual_life import router as virtual_life_router
from .virtual_life_packs import router as virtual_life_packs_router, seed_virtual_life_packs


TaskStatusFilter = Annotated[
    TaskStatus | None,
    BeforeValidator(lambda value: None if value == "" else value),
]

# 注册冲突统一提示：不区分「用户名已存在」与「邮箱已存在」，避免账号枚举。
ACCOUNT_TAKEN_DETAIL = "用户名或邮箱已被使用，请换一个试试"

# 生活素材（管理员导入并经净化的游戏资源）允许免数据库记录直接公开，
# 但文件名必须是服务端生成的 UUID 形态，杜绝任意文件借这条捷径对外提供。
LIFE_ASSET_PATTERN = re.compile(r"^life/[0-9a-f]{32}\.(?:png|jpg|jpeg)$")

_main_logger = logging.getLogger("yorozuya.main")


def _running_under_pytest() -> bool:
    """测试会触碰真实数据库，此时不要随机化/轮换管理员密码以免影响本地数据。"""
    return settings.testing


def _write_initial_admin_password(password: str) -> Path | None:
    """把首次生成/轮换的管理员密码写入数据目录下的 0600 文件。

    直接打印到日志会把明文密码交给任何能读日志的人（容器日志、日志采集、
    甚至把日志贴进 issue）；落盘的 0600 文件权限可控，且提示运维读后即删。
    """
    target = settings.sugar_upload_path.parent / "INITIAL_ADMIN_PASSWORD.txt"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            f"用户名：{settings.admin_username}\n密码：{password}\n"
            "读取后请立即删除本文件，并在 .env 中设置固定的 ADMIN_PASSWORD。\n",
            encoding="utf-8",
        )
        target.chmod(0o600)
    except OSError as error:
        _main_logger.error("无法写入初始管理员密码文件：%s", error)
        return None
    return target


def initialize_database() -> None:
    settings.validate_storage_isolation()
    settings.validate_directories_writable()
    Base.metadata.create_all(bind=engine)
    migrate_schema()
    logger = logging.getLogger("yorozuya")
    harden_default_password = not _running_under_pytest()
    with SessionLocal() as db:
        admin = db.scalar(select(User).where(User.username == settings.admin_username))
        if admin is None:
            password = settings.admin_password
            if settings.admin_password_is_default and harden_default_password:
                password = secrets.token_urlsafe(15)
                location = _write_initial_admin_password(password)
                logger.warning(
                    "ADMIN_PASSWORD 缺失或仍是公开占位值，已为超级管理员 %s 生成随机密码%s"
                    "（请读取后删除该文件，并在 .env 中设置固定的强密码）",
                    settings.admin_username,
                    f"，已写入 {location}（权限 0600）" if location else "，但写入失败，请手工重置",
                )
            db.add(
                User(
                    username=settings.admin_username,
                    password_hash=hash_password(password),
                    nickname=settings.admin_nickname,
                    is_admin=True,
                )
            )
            db.commit()
        elif harden_default_password and any(
            verify_password(candidate, admin.password_hash)
            for candidate in PLACEHOLDER_ADMIN_PASSWORDS
        ):
            # 已有管理员仍在使用公开的占位密码（含 .env.example 里的示例值）：强制轮换。
            rotated = secrets.token_urlsafe(15)
            admin.password_hash = hash_password(rotated)
            lock_credentials(db, admin)
            revoke_credentials(db, admin)
            db.commit()
            location = _write_initial_admin_password(rotated)
            logger.warning(
                "检测到超级管理员 %s 仍在使用公开的占位密码，已自动轮换%s"
                "（请读取后删除该文件，并在 .env 中设置固定的强密码）",
                settings.admin_username,
                f"，新密码已写入 {location}（权限 0600）" if location else "，但写入失败，请手工重置",
            )
        seed_virtual_life_packs(db)


def migrate_schema() -> None:
    """把旧版数据库升级到当前多接单人模型（SQLite 轻量迁移）。"""
    if not settings.database_url.startswith("sqlite"):
        return
    from sqlalchemy import inspect as sa_inspect

    inspector = sa_inspect(engine)
    with engine.begin() as connection:
        if inspector.has_table("users"):
            user_columns = {column["name"] for column in inspector.get_columns("users")}
            if "max_concurrent_tasks" not in user_columns:
                connection.execute(
                    text("ALTER TABLE users ADD COLUMN max_concurrent_tasks INTEGER NOT NULL DEFAULT 2")
                )
            if "role" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR(16) NOT NULL DEFAULT 'user'"))
            if "qq_public" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN qq_public BOOLEAN NOT NULL DEFAULT 0"))
            if "avatar_path" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN avatar_path VARCHAR(255)"))
            if "avatar_visible" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN avatar_visible BOOLEAN NOT NULL DEFAULT 0"))
            if "avatar_moderated_at" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN avatar_moderated_at DATETIME"))
            if "is_beta_tester" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN is_beta_tester BOOLEAN NOT NULL DEFAULT 0"))
            if "token_version" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN token_version INTEGER NOT NULL DEFAULT 0"))
            if "title" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN title VARCHAR(32)"))
            if "email" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN email VARCHAR(254)"))
            if "email_verified" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN email_verified BOOLEAN NOT NULL DEFAULT 0"))
            if "pending_email" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN pending_email VARCHAR(254)"))
            if "notify_email" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN notify_email BOOLEAN NOT NULL DEFAULT 1"))
            # SQLite 的 ALTER 不能加唯一约束，因此单独建唯一索引；
            # 唯一索引不限制 NULL，存量账号在被强制补充绑定前 email 为空，彼此不冲突。
            connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users (email)"))
            connection.execute(
                text("CREATE INDEX IF NOT EXISTS ix_users_email_verified ON users (email_verified)")
            )
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_users_is_beta_tester ON users (is_beta_tester)"))
        if inspector.has_table("email_tokens"):
            token_columns = {column["name"] for column in inspector.get_columns("email_tokens")}
            if "credential_version" not in token_columns:
                # 旧令牌未绑定凭证版本，升级时作废，需重新获取邮件。
                connection.execute(text("ALTER TABLE email_tokens ADD COLUMN credential_version INTEGER NOT NULL DEFAULT -1"))
                connection.execute(text("UPDATE email_tokens SET used_at = CURRENT_TIMESTAMP WHERE used_at IS NULL"))
                connection.execute(text("UPDATE users SET pending_email = NULL"))
        if not inspector.has_table("tasks"):
            return
        task_columns = {column["name"] for column in inspector.get_columns("tasks")}
        if "required_takers" not in task_columns:
            connection.execute(text("ALTER TABLE tasks ADD COLUMN required_takers INTEGER"))
        if "is_designated" not in task_columns:
            connection.execute(text("ALTER TABLE tasks ADD COLUMN is_designated BOOLEAN NOT NULL DEFAULT 0"))
        if "is_anonymous" not in task_columns:
            connection.execute(text("ALTER TABLE tasks ADD COLUMN is_anonymous BOOLEAN NOT NULL DEFAULT 0"))
        if "started_at" not in task_columns:
            connection.execute(text("ALTER TABLE tasks ADD COLUMN started_at DATETIME"))
        if "pay_type" not in task_columns:
            connection.execute(text("ALTER TABLE tasks ADD COLUMN pay_type VARCHAR(8)"))
            # 旧委托回填：填了报酬说明视为有偿，否则视为无偿
            connection.execute(
                text("UPDATE tasks SET pay_type = 'paid' WHERE pay_type IS NULL AND reward IS NOT NULL AND reward <> ''")
            )
            connection.execute(
                text("UPDATE tasks SET pay_type = 'free' WHERE pay_type IS NULL")
            )
        if "cancelled_at" not in task_columns:
            connection.execute(text("ALTER TABLE tasks ADD COLUMN cancelled_at DATETIME"))
        if "cancel_requested_by" not in task_columns:
            connection.execute(text("ALTER TABLE tasks ADD COLUMN cancel_requested_by INTEGER"))
        if "cancel_requested_at" not in task_columns:
            connection.execute(text("ALTER TABLE tasks ADD COLUMN cancel_requested_at DATETIME"))
        if "cancel_resume_status" not in task_columns:
            connection.execute(text("ALTER TABLE tasks ADD COLUMN cancel_resume_status VARCHAR(16)"))
        if "publisher_cancel_confirmed_at" not in task_columns:
            connection.execute(text("ALTER TABLE tasks ADD COLUMN publisher_cancel_confirmed_at DATETIME"))
        if "is_visible" not in task_columns:
            connection.execute(text("ALTER TABLE tasks ADD COLUMN is_visible BOOLEAN NOT NULL DEFAULT 1"))
        if "admin_note" not in task_columns:
            connection.execute(text("ALTER TABLE tasks ADD COLUMN admin_note VARCHAR(200)"))
        if inspector.has_table("task_members"):
            member_columns = {column["name"] for column in inspector.get_columns("task_members")}
            if "cancel_confirmed_at" not in member_columns:
                connection.execute(text("ALTER TABLE task_members ADD COLUMN cancel_confirmed_at DATETIME"))
            if "response_status" not in member_columns:
                connection.execute(
                    text("ALTER TABLE task_members ADD COLUMN response_status VARCHAR(16) NOT NULL DEFAULT 'accepted'")
                )
        # 旧版单接单人数据升级：
        # 1) submitted(已提交待验收) -> awaiting(待确认)，以提交时间作为接单人确认时间
        # 2) 有 assignee_id 的任务，把接单人搬进 task_members
        if "assignee_id" in task_columns:
            connection.execute(
                text(
                    "UPDATE tasks SET status='awaiting', assignee_confirmed_at = COALESCE(assignee_confirmed_at, submitted_at)"
                    " WHERE status='submitted' AND assignee_id IS NOT NULL"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO task_members (task_id, user_id, joined_at, confirmed_at) "
                    "SELECT t.id, t.assignee_id, COALESCE(t.accepted_at, t.created_at), t.assignee_confirmed_at "
                    "FROM tasks t "
                    "WHERE t.assignee_id IS NOT NULL "
                    "AND NOT EXISTS (SELECT 1 FROM task_members m WHERE m.task_id = t.id AND m.user_id = t.assignee_id)"
                )
            )
            if "accepted_at" in task_columns:
                connection.execute(
                    text(
                        "UPDATE tasks SET started_at = COALESCE(started_at, accepted_at) "
                        "WHERE assignee_id IS NOT NULL AND started_at IS NULL AND accepted_at IS NOT NULL"
                    )
                )
            connection.execute(
                text(
                    "UPDATE tasks SET required_takers = COALESCE(required_takers, 1) "
                    "WHERE assignee_id IS NOT NULL AND required_takers IS NULL"
                )
            )
        # 用户介绍页图片使用独立表；文件仍统一落在 uploads 挂载目录。
        if inspector.has_table("user_photos"):
            photo_columns = {column["name"] for column in inspector.get_columns("user_photos")}
            if "is_visible" not in photo_columns:
                connection.execute(text("ALTER TABLE user_photos ADD COLUMN is_visible BOOLEAN NOT NULL DEFAULT 1"))
            if "moderated_by_id" not in photo_columns:
                connection.execute(text("ALTER TABLE user_photos ADD COLUMN moderated_by_id INTEGER"))
            if "moderated_at" not in photo_columns:
                connection.execute(text("ALTER TABLE user_photos ADD COLUMN moderated_at DATETIME"))
        if inspector.has_table("sugar_photos"):
            sugar_photo_columns = {column["name"] for column in inspector.get_columns("sugar_photos")}
            if "is_visible" not in sugar_photo_columns:
                connection.execute(text("ALTER TABLE sugar_photos ADD COLUMN is_visible BOOLEAN NOT NULL DEFAULT 1"))
            if "admin_note" not in sugar_photo_columns:
                connection.execute(text("ALTER TABLE sugar_photos ADD COLUMN admin_note VARCHAR(200)"))
            if "moderated_by_id" not in sugar_photo_columns:
                connection.execute(text("ALTER TABLE sugar_photos ADD COLUMN moderated_by_id INTEGER"))
            if "moderated_at" not in sugar_photo_columns:
                connection.execute(text("ALTER TABLE sugar_photos ADD COLUMN moderated_at DATETIME"))
        if inspector.has_table("friend_profiles"):
            friend_columns = {column["name"] for column in inspector.get_columns("friend_profiles")}
            if "vrc_nickname" not in friend_columns:
                connection.execute(
                    text(
                        "ALTER TABLE friend_profiles ADD COLUMN vrc_nickname VARCHAR(64) NOT NULL DEFAULT ''"
                    )
                )
        # 旧版本为地图照片建立了 (map_id, user_id) 唯一索引，重建表以支持同一用户上传多张。
        if inspector.has_table("vr_map_photos"):
            unique_constraints = inspector.get_unique_constraints("vr_map_photos")
            if any(set(item.get("column_names") or []) == {"map_id", "user_id"} for item in unique_constraints):
                connection.execute(text("""
                    CREATE TABLE vr_map_photos_new (
                        id INTEGER NOT NULL PRIMARY KEY,
                        map_id INTEGER NOT NULL REFERENCES vr_maps (id),
                        user_id INTEGER NOT NULL REFERENCES users (id),
                        file_path VARCHAR(255) NOT NULL UNIQUE,
                        is_visible BOOLEAN NOT NULL DEFAULT 0,
                        moderated_by_id INTEGER REFERENCES users (id),
                        moderated_at DATETIME,
                        created_at DATETIME NOT NULL
                    )
                """))
                connection.execute(text("""
                    INSERT INTO vr_map_photos_new
                        (id, map_id, user_id, file_path, is_visible, moderated_by_id, moderated_at, created_at)
                    SELECT id, map_id, user_id, file_path, is_visible, moderated_by_id, moderated_at, created_at
                    FROM vr_map_photos
                """))
                connection.execute(text("DROP TABLE vr_map_photos"))
                connection.execute(text("ALTER TABLE vr_map_photos_new RENAME TO vr_map_photos"))
                connection.execute(text("CREATE INDEX ix_vr_map_photos_map_id ON vr_map_photos (map_id)"))
                connection.execute(text("CREATE INDEX ix_vr_map_photos_user_id ON vr_map_photos (user_id)"))
                connection.execute(text("CREATE INDEX ix_vr_map_photos_is_visible ON vr_map_photos (is_visible)"))


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    # 升级对账：把历史数据里仍留在公开区的待审/被屏蔽媒体搬进私有区，
    # 否则它们升级后依然能被 /uploads 直接下载，撤回等于没生效。
    # pytest 下跳过，避免动到开发者本机的真实上传目录（函数本身由测试直接覆盖）。
    if not _running_under_pytest():
        with SessionLocal() as db:
            sync_media_zones(db)
    yield


def sync_media_zones(db: Session) -> None:
    """让每个媒体文件都待在与其可见性匹配的区（幂等，可反复执行）。"""
    targets: list[tuple[str | None, bool]] = []
    targets += [(user.avatar_path, user.avatar_visible) for user in db.scalars(select(User))]
    targets += [(photo.file_path, photo.is_visible) for photo in db.scalars(select(UserPhoto))]
    targets += [(photo.file_path, photo.is_visible) for photo in db.scalars(select(SugarPhoto))]
    targets += [(photo.file_path, photo.is_visible) for photo in db.scalars(select(FriendPhoto))]
    targets += [(photo.file_path, photo.is_visible) for photo in db.scalars(select(StoryPhoto))]
    targets += [(photo.file_path, photo.is_visible) for photo in db.scalars(select(VrMapPhoto))]
    for key, public in targets:
        if key:
            place_media(key, public=public)


# 交互式文档与 OpenAPI 默认关闭（ENABLE_DOCS=false），避免把完整接口结构公之于众。
# 刻意不看 BEHIND_PROXY 单个标志：那个标志同时控制代理信任，误设一次就会连带暴露文档；
# 这里要求「显式打开」且「确实不在代理后面」两个条件同时成立。
_docs_enabled = settings.enable_docs and not settings.behind_proxy
app = FastAPI(
    title=settings.app_name,
    version="0.1-beta",
    lifespan=lifespan,
    docs_url="/docs" if _docs_enabled else None,
    redoc_url="/redoc" if _docs_enabled else None,
    openapi_url="/openapi.json" if _docs_enabled else None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """兜底安全响应头。

    生产入口由 nginx 下发同款响应头；这里覆盖直连后端（本地开发、Vite 代理）的场景，
    尤其保证 /uploads 下的用户文件不会被浏览器按内容嗅探成 HTML。
    """
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    return response


_MEDIA_PHOTO_MODELS = (UserPhoto, SugarPhoto, FriendPhoto, StoryPhoto, VrMapPhoto)


def media_key_is_public(key: str, db: Session) -> bool:
    """key 在数据库里当前是否属于「已过审、可公开访问」的媒体。"""
    if db.scalar(
        select(User.id).where(User.avatar_path == key, User.avatar_visible.is_(True)).limit(1)
    ):
        return True
    return any(
        db.scalar(select(model.id).where(model.file_path == key, model.is_visible.is_(True)).limit(1))
        for model in _MEDIA_PHOTO_MODELS
    )


def media_key_exists(key: str, db: Session) -> bool:
    """key 是否仍是数据库中的一条媒体记录（不区分可见性）。"""
    if db.scalar(select(User.id).where(User.avatar_path == key).limit(1)):
        return True
    return any(
        db.scalar(select(model.id).where(model.file_path == key).limit(1))
        for model in _MEDIA_PHOTO_MODELS
    )


@app.api_route("/uploads/{key:path}", methods=["GET", "HEAD"], include_in_schema=False)
def read_public_media(key: str, db: Session = Depends(get_db)):
    # 不能只凭磁盘所在区授权：搬移/提交之间崩溃或历史残留都可能留下公开副本。
    if any(part in ("", ".", "..") for part in key.split("/")):
        raise HTTPException(status_code=404, detail="文件不存在")
    path = storage_file(key, public=True)
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    # 生活素材是管理员导入并净化的游戏资源，不属于用户待审媒体；
    # 文件名限定为服务端 UUID 形态，避免任意文件借这条捷径公开。
    allowed = LIFE_ASSET_PATTERN.match(key) is not None or media_key_is_public(key, db)
    if not allowed:
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(path, headers={"Cache-Control": "no-store", "Content-Security-Policy": "default-src 'none'; sandbox"})


# 万事屋看板娘(站内 AI 助手)
from .mascot import router as mascot_router  # noqa: E402

app.include_router(mascot_router)
app.include_router(virtual_life_router)
app.include_router(virtual_life_packs_router)
app.include_router(sugar_frost_router)


def expire_due_tasks(db: Session) -> None:
    result = db.execute(
        update(Task)
        .where(
            Task.expires_at <= datetime.utcnow(),
            Task.status.in_([TaskStatus.PUBLISHED, TaskStatus.ACCEPTED, TaskStatus.AWAITING, TaskStatus.CANCELLING]),
        )
        .values(status=TaskStatus.EXPIRED, updated_at=datetime.utcnow())
    )
    if result.rowcount:
        db.commit()


PAGE_LABELS = {
    "hall": "委托大厅",
    "staff": "成员名录",
    "board": "留言板",
    "maps": "地图推荐",
    "friends": "交友厅",
    "stories": "故事会",
    "versions": "版本更新",
    "sugar": "砂糖社",
    "announcements": "公告中心",
    "mine": "我的委托",
    "profile": "个人设置",
    "login": "登录注册",
    "frost": "糖霜世界",
    "operations": "运营台",
    "admin": "监管台",
    "life": "虚拟人生",
    "life-admin": "人生内容管理",
    "verify-email": "邮箱验证",
    "forgot-password": "找回密码",
    "reset-password": "重置密码",
}

# 关键行为事件白名单：前端 track() 的 event_key 必须在这里，未知事件不入库（防脏数据）。
EVENT_LABELS = {
    "auth.login": "登录",
    "auth.register": "注册",
    "task.open_detail": "打开委托详情",
    "task.accept": "接取委托",
    "task.leave": "退出/拒绝委托",
    "task.start": "开始委托",
    "task.confirm": "确认完成委托",
    "task.cancel": "发起取消委托",
    "task.cancel_confirm": "同意取消委托",
    "task.password": "设置接取密码",
    "task.create": "发布委托",
    "task.report": "举报委托",
    "feedback.submit": "提交反馈",
    "board.post": "发表留言",
    "board.comment": "留言评论",
    "board.delete": "删除留言/评论",
    "map.create": "推荐地图",
    "map.open_detail": "查看地图详情",
    "map.like": "点赞地图",
    "map.report": "举报地图",
    "map.upload_photo": "上传地图实拍",
    "story.create": "发布故事",
    "story.open_detail": "阅读故事",
    "story.comment": "故事评论",
    "story.delete": "删除故事",
    "sugar.save_profile": "保存砂糖社档案",
    "sugar.open_profile": "查看砂糖社档案",
    "sugar.confirm": "确认结为砂糖",
    "sugar.end": "结束砂糖关系",
    "friend.save_profile": "保存交友资料",
    "friend.open_profile": "查看交友资料",
    "friend.apply": "发送好友申请",
    "friend.accept": "同意好友申请",
    "friend.reject": "拒绝好友申请",
    "profile.save": "更新个人资料",
    "profile.email_bind": "绑定/换绑邮箱",
    "staff.apply_volunteer": "申请志愿者",
    "announcement.confirm": "确认首页公告",
    "mascot.open": "打开看板娘",
    "mascot.send": "与看板娘对话",
    "lightbox.open": "放大查看图片",
    "frost.enter_level": "进入糖霜关卡",
    "frost.level_submit": "提交糖霜关卡解答",
    "life.start": "开始虚拟人生",
}


def utc_naive(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def present_announcement(item: Announcement) -> AnnouncementOut:
    return AnnouncementOut(
        id=item.id,
        kind=item.kind,
        title=item.title,
        content=item.content,
        is_published=item.is_published,
        is_pinned=item.is_pinned,
        starts_at=item.starts_at,
        ends_at=item.ends_at,
        author_name=item.author.nickname,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def task_query():
    return select(Task).options(
        joinedload(Task.publisher).joinedload(User.photos),
        joinedload(Task.members).joinedload(TaskMember.user).joinedload(User.photos),
        joinedload(Task.reports),
    )


def visible_user_photos(user: User, viewer: User | None = None) -> list[UserPhotoOut]:
    """资料主人和审核人员可看全部；其他访问者只能看已通过展示的图片。

    地址按 is_visible 决定分区：已通过的作品走公开区，待审/被屏蔽的只能拿到签名 URL。
    """
    can_manage = viewer is not None and (viewer.id == user.id or can_review_content(viewer))
    return [
        UserPhotoOut(
            id=photo.id,
            image_url=media_url(photo.file_path, public=photo.is_visible) or "",
            is_visible=photo.is_visible,
        )
        for photo in user.photos
        if can_manage or photo.is_visible
    ]


def visible_avatar(user: User, viewer: User | None = None) -> str | None:
    """头像 URL：审核通过后对所有人可见，未过审时仅本人和管理员组可见（拿签名 URL）。"""
    if not user.avatar_path:
        return None
    if user.avatar_visible or (viewer is not None and (viewer.id == user.id or can_review_content(viewer))):
        return media_url(user.avatar_path, public=user.avatar_visible)
    return None


def present_user_public(user: User, viewer: User | None = None) -> UserPublic:
    return UserPublic(
        id=user.id, nickname=user.nickname, title=user.title, bio=user.bio,
        photos=visible_user_photos(user, viewer),
        avatar_url=visible_avatar(user, viewer), avatar_visible=user.avatar_visible,
        is_beta_tester=user.is_beta_tester,
    )


ANONYMOUS_PUBLISHER = UserPublic(id=0, nickname="匿名委托人", bio=None, photos=[])


def present_user_self(user: User) -> UserSelf:
    """本人视角的完整资料（含账号字段）。

    不能直接 UserSelf.model_validate(user)：ORM 上已没有 avatar_url / image_url，
    那样会让本人的头像和介绍图片全部变成空，必须显式带上自己的可见性。
    """
    return UserSelf(
        id=user.id,
        nickname=user.nickname,
        title=user.title,
        bio=user.bio,
        photos=visible_user_photos(user, user),
        avatar_url=visible_avatar(user, user),
        avatar_visible=user.avatar_visible,
        is_beta_tester=user.is_beta_tester,
        username=user.username,
        qq=user.qq,
        qq_public=user.qq_public,
        email=user.email,
        email_verified=user.email_verified,
        pending_email=user.pending_email,
        notify_email=user.notify_email,
        email_gate_required=email_gate_required(user),
        is_admin=user.is_admin,
        is_active=user.is_active,
        role=user.role,
        max_concurrent_tasks=user.max_concurrent_tasks,
        created_at=user.created_at,
    )


def present_user_profile(user: User, viewer: User | None = None) -> UserProfileOut:
    return UserProfileOut(
        id=user.id, nickname=user.nickname, title=user.title, bio=user.bio, qq=user.qq, qq_public=user.qq_public,
        is_admin=user.is_admin,
        role=user.role, created_at=user.created_at, photos=visible_user_photos(user, viewer),
        avatar_url=visible_avatar(user, viewer), avatar_visible=user.avatar_visible, is_beta_tester=user.is_beta_tester,
    )


def present_moderation_profile(user: User, moderator: User) -> UserProfileOut:
    profile = present_user_profile(user, moderator)
    return profile.model_copy(update={"qq": None}) if moderator.role == UserRole.DISCIPLINARIAN else profile


def present_members(task: Task, viewer: User | None) -> list[TaskMemberOut]:
    """成员序列化；qq 只在协作相关方（委托人/成员/管理员）可见。

    匿名委托中，联系方式只对“发布人 ↔ 已接取成员”双方可见：发布人可看所有成员，
    成员只能看到自己的 QQ，成员之间互不可见。
    """
    out: list[TaskMemberOut] = []
    for member in task.members:
        item = TaskMemberOut(
            user=present_user_public(member.user, viewer), joined_at=member.joined_at,
            response_status=member.response_status, confirmed_at=member.confirmed_at,
            cancel_confirmed_at=member.cancel_confirmed_at,
        )
        if task.is_anonymous:
            can_see_this = viewer is not None and (
                viewer.is_admin or viewer.id == task.publisher_id or member.user_id == viewer.id
            )
        else:
            can_see_this = viewer is not None and (
                viewer.is_admin or viewer.id == task.publisher_id or any(m.user_id == viewer.id for m in task.members)
            )
        if can_see_this:
            item.qq = member.user.qq
        out.append(item)
    return out


def present_task(task: Task, viewer: User | None = None) -> TaskOut:
    data = TaskOut.model_validate(task)
    data.reported = any(report.status == ReportStatus.PENDING for report in task.reports)
    # 取消发起者属于内部协作信息，只对委托人/接单人/管理员组暴露。
    if not (is_task_participant(task, viewer) or is_task_manager(viewer)):
        data.cancel_requested_by = None
    can_see_hidden = viewer is not None and (
        viewer.is_admin or viewer.role == UserRole.STAFF or viewer.id == task.publisher_id
    )
    # 屏蔽原因只对监管人员和委托人返回，避免通过“我的委托”泄露给接单人。
    data.admin_note = task.admin_note if (not task.is_visible and can_see_hidden) else None
    data.publisher = present_user_public(task.publisher, viewer)
    data.members = present_members(task, viewer)
    if task.is_anonymous:
        # 匿名委托：接取前仅展示标题与内容，个人信息不公开；接取后联系方式仅双方可见。
        is_collaborator = viewer is not None and (
            viewer.id == task.publisher_id
            or any(
                m.user_id == viewer.id and m.response_status == TaskMemberResponse.ACCEPTED
                for m in task.members
            )
        )
        is_pending_designated = viewer is not None and any(
            m.user_id == viewer.id and m.response_status == TaskMemberResponse.PENDING for m in task.members
        )
        can_inspect = viewer is not None and (viewer.is_admin or viewer.role == UserRole.STAFF)
        if not (is_collaborator or is_pending_designated or can_inspect):
            data.publisher = ANONYMOUS_PUBLISHER
            data.publisher_id = 0
            data.members = []
            return data
        if is_pending_designated and not is_collaborator:
            # 匿名指定委托：被指定者仅看到自己的待响应状态，不暴露发布人与其他成员。
            data.publisher = ANONYMOUS_PUBLISHER
            data.publisher_id = 0
            data.members = [member for member in data.members if member.user.id == viewer.id]
            return data
        if task.publisher_id == viewer.id:
            # 委托人：成员 QQ 已由 present_members 填充
            return data
        if is_collaborator:
            # 已接取成员：可见委托人联系方式
            data.contact_qq = task.publisher.qq
            return data
        if viewer.is_admin:
            data.contact_qq = task.publisher.qq
        return data
    if viewer is None:
        return data
    if viewer.is_admin:
        # 管理员可看到发布人联系方式，便于处理纠纷
        data.contact_qq = task.publisher.qq
        return data
    if task.publisher_id == viewer.id:
        # 委托人：成员 QQ 已在成员列表可见
        return data
    if any(m.user_id == viewer.id and m.response_status == TaskMemberResponse.ACCEPTED for m in task.members):
        # 接单人：可见委托人联系方式（仅限已接受，指定委托里 pending/declined 不算接取）
        data.contact_qq = task.publisher.qq
        return data
    if task.status == TaskStatus.PUBLISHED and task.is_visible:
        # 待开始的委托：登录用户可看到委托人 QQ，用于联系洽谈
        data.contact_qq = task.publisher.qq
    return data


def get_task_or_404(db: Session, task_id: int) -> Task:
    task = db.scalar(task_query().where(Task.id == task_id))
    if task is None:
        raise HTTPException(status_code=404, detail="委托不存在")
    return task


def can_view_hidden_task(task: Task, viewer: User | None) -> bool:
    return viewer is not None and (
        viewer.is_admin or viewer.role == UserRole.STAFF or viewer.id == task.publisher_id
    )


def is_task_manager(viewer: User | None) -> bool:
    return viewer is not None and (viewer.is_admin or viewer.role == UserRole.STAFF)


def is_task_participant(task: Task, viewer: User | None) -> bool:
    return viewer is not None and (
        viewer.id == task.publisher_id or any(m.user_id == viewer.id for m in task.members)
    )


def get_setting_int(db: Session, key: str, default: int) -> int:
    setting = db.get(AppSetting, key)
    if setting is None:
        return default
    try:
        return int(setting.value)
    except (TypeError, ValueError):
        return default


def set_setting(db: Session, key: str, value: str) -> None:
    setting = db.get(AppSetting, key)
    if setting is None:
        db.add(AppSetting(key=key, value=value))
    else:
        setting.value = value


def present_report(report: TaskReport) -> TaskReportOut:
    return TaskReportOut(
        id=report.id,
        task_id=report.task_id,
        task_title=report.task.title if report.task else '',
        task_status=report.task.status if report.task else TaskStatus.PUBLISHED,
        reporter=present_user_public(report.reporter),
        reason=report.reason,
        status=report.status,
        created_at=report.created_at,
        handled_at=report.handled_at,
    )


def present_feedback(feedback: Feedback) -> FeedbackOut:
    """反馈里的提交者资料同样要走 presenter，否则会带出未过审头像与待审图片地址。"""
    data = FeedbackOut.model_validate(feedback)
    data.user = present_user_public(feedback.user) if feedback.user else None
    return data


def member_of(db: Session, task_id: int, user_id: int) -> TaskMember | None:
    return db.scalar(select(TaskMember).where(TaskMember.task_id == task_id, TaskMember.user_id == user_id))


def accepted_member_of(db: Session, task_id: int, user_id: int) -> TaskMember | None:
    return db.scalar(
        select(TaskMember).where(
            TaskMember.task_id == task_id,
            TaskMember.user_id == user_id,
            TaskMember.response_status == TaskMemberResponse.ACCEPTED,
        )
    )


def shares_task_with(db: Session, viewer_id: int, target_id: int) -> bool:
    """两人是否在同一委托中共事过（一个委托人发布、另一个成员接取，或同为成员）。

    匿名委托只算“发布人 ↔ 已接取成员”这一对关系：接单人之间不算共事，
    避免通过资料页互相看到联系方式。
    """
    if viewer_id == target_id:
        return True
    viewer_tasks = set(db.scalars(select(Task.id).where(Task.publisher_id == viewer_id)))
    viewer_tasks |= set(db.scalars(select(TaskMember.task_id).where(TaskMember.user_id == viewer_id)))
    target_tasks = set(db.scalars(select(Task.id).where(Task.publisher_id == target_id)))
    target_tasks |= set(db.scalars(select(TaskMember.task_id).where(TaskMember.user_id == target_id)))
    shared_ids = viewer_tasks & target_tasks
    for task_id in shared_ids:
        task = db.get(Task, task_id)
        if task is None:
            continue
        if not task.is_anonymous:
            return True
        # 匿名委托：必须是发布人与已接取成员之间的对应关系
        viewer_is_pub = task.publisher_id == viewer_id
        target_is_pub = task.publisher_id == target_id
        if viewer_is_pub != target_is_pub:
            member_id = target_id if viewer_is_pub else viewer_id
            member_row = db.scalar(
                select(TaskMember).where(
                    TaskMember.task_id == task_id,
                    TaskMember.user_id == member_id,
                    TaskMember.response_status == TaskMemberResponse.ACCEPTED,
                )
            )
            if member_row is not None:
                return True
    return False


def can_view_user_qq(db: Session, viewer: User | None, target: User) -> bool:
    """只有本人主动开启公开（qq_public）才对外可见；原有协作关系始终优先放行。

    不再对 staff 无条件放行：否则设置了「不公开」的工作人员 QQ 仍会被匿名抓取。
    """
    if target.qq_public:
        return True
    if viewer is None:
        return False
    if viewer.is_admin or viewer.id == target.id:
        return True
    if shares_task_with(db, viewer.id, target.id):
        return True
    recruiting = db.scalar(
        select(Task.id)
        .where(
            Task.publisher_id == target.id,
            Task.status == TaskStatus.PUBLISHED,
            Task.is_visible.is_(True),
            Task.is_anonymous.is_(False),
        )
        .limit(1)
    )
    return recruiting is not None


MAX_SUGAR_PHOTOS = 6
MAX_SUGAR_IMAGE_BYTES = 5 * 1024 * 1024

# 头像：仅 PNG/JPG，最大 2 MB，上传后需管理员审核
MAX_AVATAR_BYTES = 2 * 1024 * 1024

# VRChat 地图推荐：实拍照片仅 PNG/JPG，最大 10 MB，需管理员审核
MAX_VR_MAP_PHOTO_BYTES = 10 * 1024 * 1024
MAX_VR_MAP_UPLOAD_TOTAL_BYTES = 50 * 1024 * 1024
MAX_VR_MAP_PHOTOS = 5
MAP_CATEGORIES = ("游戏", "休闲", "恐怖", "风景", "解谜", "社交", "其他")

MAX_FRIEND_PHOTOS = 5

# 故事会配图：仅 PNG/JPG，单张最大 10 MB，每篇故事最多 3 张，需管理员审核
MAX_STORY_PHOTOS = 3
MAX_STORY_PHOTO_BYTES = 10 * 1024 * 1024
MAX_STORY_UPLOAD_TOTAL_BYTES = 30 * 1024 * 1024


def sugar_profile_query():
    return select(SugarProfile).options(joinedload(SugarProfile.user), joinedload(SugarProfile.photos))


def sugar_pair_query():
    return select(SugarPair).options(joinedload(SugarPair.first_user), joinedload(SugarPair.second_user))


def photo_url(photo: SugarPhoto) -> str:
    return media_url(photo.file_path, public=photo.is_visible) or ""


def present_sugar_photos(profile: SugarProfile, viewer: User | None) -> list[SugarPhotoOut]:
    """被屏蔽的照片仅主人和管理员组可见（附带屏蔽理由），对其他查看者隐藏。"""
    can_manage = viewer is not None and (viewer.id == profile.user_id or can_review_content(viewer))
    return [
        SugarPhotoOut(id=photo.id, image_url=photo_url(photo), is_visible=photo.is_visible, admin_note=photo.admin_note)
        for photo in profile.photos
        if photo.is_visible or can_manage
    ]


def present_sugar_profile(
    profile: SugarProfile,
    *,
    viewer: User | None = None,
    qq: str | None = None,
    relationship: SugarPair | None = None,
    detailed: bool = False,
) -> SugarProfileCardOut | SugarProfileDetailOut:
    data = {
        "id": profile.id,
        # 必须走 present_user_public：直接塞 ORM 的 profile.user 会带上未过审头像
        # 与待审/被屏蔽的介绍图片地址。
        "user": present_user_public(profile.user, viewer),
        "about": profile.about,
        "photos": present_sugar_photos(profile, viewer),
        "created_at": profile.created_at,
        "updated_at": profile.updated_at,
    }
    if detailed:
        return SugarProfileDetailOut(
            **data,
            qq=qq,
            relationship=present_sugar_pair(relationship, viewer) if relationship else None,
        )
    return SugarProfileCardOut(**data)


def sugar_pair_duration(pair: SugarPair) -> int:
    if pair.activated_at is None:
        return 0
    finish = pair.ended_at or datetime.utcnow()
    return max(0, int((finish - pair.activated_at).total_seconds()))


def present_sugar_pair(pair: SugarPair, viewer: User | None = None) -> SugarPairOut:
    """显式构造：SugarPairOut.model_validate(pair) 会把 first_user/second_user
    当作 ORM 对象直读，从而带出未过审头像与待审照片地址。"""
    return SugarPairOut(
        id=pair.id,
        first_user=present_user_public(pair.first_user, viewer),
        second_user=present_user_public(pair.second_user, viewer),
        initiated_by_id=pair.initiated_by_id,
        status=pair.status,
        initiated_at=pair.initiated_at,
        activated_at=pair.activated_at,
        ended_at=pair.ended_at,
        duration_seconds=sugar_pair_duration(pair),
    )


def get_sugar_profile_or_404(db: Session, user_id: int) -> SugarProfile:
    profile = db.scalars(sugar_profile_query().where(SugarProfile.user_id == user_id)).unique().one_or_none()
    if profile is None:
        raise HTTPException(status_code=404, detail="该用户尚未登记砂糖社档案")
    return profile


def pair_between(db: Session, first_user_id: int, second_user_id: int) -> SugarPair | None:
    return db.scalar(
        sugar_pair_query()
        .where(
            SugarPair.status.in_([SugarPairStatus.PENDING, SugarPairStatus.ACTIVE]),
            or_(
                (SugarPair.first_user_id == first_user_id) & (SugarPair.second_user_id == second_user_id),
                (SugarPair.first_user_id == second_user_id) & (SugarPair.second_user_id == first_user_id),
            ),
        )
        .order_by(SugarPair.initiated_at.desc())
    )


def ongoing_sugar_pair_for(db: Session, user_id: int, exclude_pair_id: int | None = None) -> SugarPair | None:
    filters = [
        SugarPair.status.in_([SugarPairStatus.PENDING, SugarPairStatus.ACTIVE]),
        or_(SugarPair.first_user_id == user_id, SugarPair.second_user_id == user_id),
    ]
    if exclude_pair_id is not None:
        filters.append(SugarPair.id != exclude_pair_id)
    return db.scalar(sugar_pair_query().where(*filters).order_by(SugarPair.initiated_at.desc()))


def active_sugar_pair_for(db: Session, user_id: int, exclude_pair_id: int | None = None) -> SugarPair | None:
    filters = [
        SugarPair.status == SugarPairStatus.ACTIVE,
        or_(SugarPair.first_user_id == user_id, SugarPair.second_user_id == user_id),
    ]
    if exclude_pair_id is not None:
        filters.append(SugarPair.id != exclude_pair_id)
    return db.scalar(sugar_pair_query().where(*filters).order_by(SugarPair.initiated_at.desc()))


async def read_sugar_images(photos: list[UploadFile]) -> list[tuple[str, bytes]]:
    """读取并净化上传的图片：魔数白名单 → 像素上限 → 剥元数据后重编码。"""
    images: list[tuple[str, bytes]] = []
    for photo in photos:
        content = await photo.read(MAX_SUGAR_IMAGE_BYTES + 1)
        if not content:
            raise HTTPException(status_code=422, detail="上传的照片不能为空")
        if len(content) > MAX_SUGAR_IMAGE_BYTES:
            raise HTTPException(status_code=422, detail="单张照片不能超过 5 MiB")
        images.append(normalize_image(content))
    return images


def image_storage_error_detail(error: OSError) -> str:
    if error.errno == ENOSPC:
        return "服务器存储空间不足，请稍后重试"
    if error.errno in (EACCES, EPERM, EROFS):
        return "服务器暂时无法写入图片，请稍后重试"
    return "图片保存失败，请稍后重试"


def store_sugar_images(profile: SugarProfile, images: list[tuple[str, bytes]]) -> list[SugarPhoto]:
    """砂糖社照片默认待审，落在私有区（先审后公开，需签名 URL 才能访问）。"""
    settings.ensure_storage_directory()
    keys: list[str] = []
    stored: list[Path] = []
    try:
        for extension, content in images:
            key = f"sugar/{uuid4().hex}{extension}"
            stored.append(write_media(key, content, public=False))
            keys.append(key)
    except OSError as error:
        for destination in stored:
            try:
                destination.unlink(missing_ok=True)
            except OSError:
                pass
        raise HTTPException(status_code=500, detail=image_storage_error_detail(error)) from error
    return [SugarPhoto(profile=profile, file_path=key) for key in keys]


def friend_profile_query():
    return select(FriendProfile).options(joinedload(FriendProfile.user), joinedload(FriendProfile.photos))


def friend_request_query():
    return select(FriendRequest).options(
        joinedload(FriendRequest.user_a),
        joinedload(FriendRequest.user_b),
        joinedload(FriendRequest.requester),
    )


def friend_photo_url(photo: FriendPhoto) -> str:
    return media_url(photo.file_path, public=photo.is_visible) or ""


def present_friend_photos(profile: FriendProfile, viewer: User | None) -> list[FriendPhotoOut]:
    can_manage = viewer is not None and (viewer.id == profile.user_id or can_review_content(viewer))
    return [
        FriendPhotoOut(id=photo.id, image_url=friend_photo_url(photo), is_visible=photo.is_visible, admin_note=photo.admin_note)
        for photo in profile.photos
        if photo.is_visible or can_manage
    ]


def friend_count(db: Session, user_id: int) -> int:
    return db.scalar(
        select(func.count())
        .select_from(FriendRequest)
        .where(
            FriendRequest.status == FriendRequestStatus.ACCEPTED,
            or_(FriendRequest.user_a_id == user_id, FriendRequest.user_b_id == user_id),
        )
    ) or 0


def friend_relation_between(db: Session, first_user_id: int, second_user_id: int) -> FriendRequest | None:
    user_a_id, user_b_id = sorted((first_user_id, second_user_id))
    return db.scalar(
        friend_request_query().where(
            FriendRequest.user_a_id == user_a_id,
            FriendRequest.user_b_id == user_b_id,
        )
    )


def present_friend_request(item: FriendRequest) -> FriendRequestOut:
    target = item.user_b if item.user_a_id == item.requester_id else item.user_a
    return FriendRequestOut(
        id=item.id,
        requester_id=item.requester_id,
        status=item.status,
        created_at=item.created_at,
        responded_at=item.responded_at,
        requester=present_user_public(item.requester),
        target=present_user_public(target),
    )


def present_friend_profile(
    profile: FriendProfile,
    *,
    db: Session,
    viewer: User | None = None,
    relationship: FriendRequest | None = None,
    detailed: bool = False,
) -> FriendProfileCardOut | FriendProfileDetailOut:
    data = {
        "id": profile.id,
        "user": present_user_public(profile.user),
        "vrc_nickname": profile.vrc_nickname,
        "about": profile.about,
        "photos": present_friend_photos(profile, viewer),
        "friend_count": friend_count(db, profile.user_id),
        "created_at": profile.created_at,
        "updated_at": profile.updated_at,
    }
    if detailed:
        can_see_qq = viewer is not None and (
            viewer.id == profile.user_id
            or (relationship is not None and relationship.status == FriendRequestStatus.ACCEPTED)
        )
        return FriendProfileDetailOut(
            **data,
            qq=profile.user.qq if can_see_qq else None,
            relationship=present_friend_request(relationship) if relationship else None,
        )
    return FriendProfileCardOut(**data)


def get_friend_profile_or_404(db: Session, user_id: int) -> FriendProfile:
    profile = db.scalars(friend_profile_query().where(FriendProfile.user_id == user_id)).unique().one_or_none()
    if profile is None:
        raise HTTPException(status_code=404, detail="该用户尚未登记交友厅资料")
    return profile


def store_friend_images(profile: FriendProfile, images: list[tuple[str, bytes]]) -> list[FriendPhoto]:
    """交友厅照片默认待审，落在私有区（需签名 URL 才能访问）。"""
    settings.ensure_storage_directory()
    keys: list[str] = []
    stored: list[Path] = []
    try:
        for extension, content in images:
            key = f"friends/{profile.user_id}/{uuid4().hex}{extension}"
            stored.append(write_media(key, content, public=False))
            keys.append(key)
    except OSError as error:
        for destination in stored:
            destination.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=image_storage_error_detail(error)) from error
    return [FriendPhoto(profile=profile, file_path=key) for key in keys]


@app.get("/api/friends/profiles", response_model=list[FriendProfileCardOut])
def list_friend_profiles(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    profiles = db.scalars(
        friend_profile_query()
        .join(FriendProfile.user)
        .where(User.is_active.is_(True), User.is_admin.is_(False))
        .order_by(FriendProfile.updated_at.desc())
        .limit(200)
    ).unique().all()
    return [present_friend_profile(profile, db=db, viewer=user) for profile in profiles]


@app.get("/api/friends/profiles/{user_id}", response_model=FriendProfileDetailOut)
def friend_profile_detail(
    user_id: int,
    viewer: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    target = db.get(User, user_id)
    if target is None or not target.is_active or target.is_admin:
        raise HTTPException(status_code=404, detail="用户不存在")
    profile = get_friend_profile_or_404(db, user_id)
    relationship = friend_relation_between(db, viewer.id, target.id) if viewer.id != target.id else None
    return present_friend_profile(profile, db=db, viewer=viewer, relationship=relationship, detailed=True)


@app.get("/api/friends/top", response_model=list[FriendLeaderboardOut])
def top_friend_users(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    profiles = db.scalars(
        friend_profile_query()
        .join(FriendProfile.user)
        .where(User.is_active.is_(True), User.is_admin.is_(False))
        .limit(200)
    ).unique().all()
    ranked = sorted(
        ((profile, friend_count(db, profile.user_id)) for profile in profiles),
        key=lambda item: (-item[1], item[0].updated_at, item[0].user_id),
    )[:3]
    output = []
    for profile, count in ranked:
        visible = [photo for photo in profile.photos if photo.is_visible]
        photo = visible[0] if visible else None
        output.append(
            FriendLeaderboardOut(
                user=present_user_public(profile.user),
                photo=FriendPhotoOut(id=photo.id, image_url=friend_photo_url(photo)) if photo else None,
                friend_count=count,
            )
        )
    return output


@app.post("/api/friends/profile", response_model=FriendProfileDetailOut)
async def save_friend_profile(
    response: Response,
    vrc_nickname: Annotated[str, Form(...)],
    about: Annotated[str, Form(...)],
    photos: list[UploadFile] = File(default=[]),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.is_admin:
        raise HTTPException(status_code=403, detail="管理员账号不能登记交友厅资料")
    enforce("upload", str(user.id), 30, 3600)
    vrc_nickname = vrc_nickname.strip()
    if not 1 <= len(vrc_nickname) <= 64:
        raise HTTPException(status_code=422, detail="VRChat 昵称需要 1 至 64 个字符")
    about = about.strip()
    if not 1 <= len(about) <= 1000:
        raise HTTPException(status_code=422, detail="交友厅介绍需要 1 至 1000 个字符")
    if len(photos) > MAX_FRIEND_PHOTOS:
        raise HTTPException(status_code=422, detail=f"最多上传 {MAX_FRIEND_PHOTOS} 张照片")
    images = await read_sugar_images(photos)
    profile = db.scalars(friend_profile_query().where(FriendProfile.user_id == user.id)).unique().one_or_none()
    is_new = profile is None
    if profile is None:
        if not images:
            raise HTTPException(status_code=422, detail="首次登记请至少上传一张照片")
        profile = FriendProfile(user_id=user.id, vrc_nickname=vrc_nickname, about=about)
        db.add(profile)
        db.flush()
    else:
        if len(profile.photos) + len(images) > MAX_FRIEND_PHOTOS:
            raise HTTPException(status_code=422, detail=f"每个档案最多保存 {MAX_FRIEND_PHOTOS} 张照片")
        profile.vrc_nickname = vrc_nickname
        profile.about = about
        profile.updated_at = datetime.utcnow()
    records = store_friend_images(profile, images)
    db.add_all(records)
    try:
        db.commit()
    except Exception:
        db.rollback()
        for record in records:
            delete_media(record.file_path)
        raise
    saved = get_friend_profile_or_404(db, user.id)
    response.status_code = status.HTTP_201_CREATED if is_new else status.HTTP_200_OK
    return present_friend_profile(saved, db=db, viewer=user, detailed=True)


@app.delete("/api/friends/photos/{photo_id}", response_model=FriendProfileDetailOut)
def delete_friend_photo(photo_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    photo = db.get(FriendPhoto, photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="照片不存在")
    profile = get_friend_profile_or_404(db, user.id)
    if photo.profile_id != profile.id:
        raise HTTPException(status_code=403, detail="只能删除自己的照片")
    if len(profile.photos) <= 1:
        raise HTTPException(status_code=409, detail="档案至少需要保留一张照片")
    file_path = photo.file_path
    db.delete(photo)
    delete_media(file_path)
    db.commit()
    return present_friend_profile(get_friend_profile_or_404(db, user.id), db=db, viewer=user, detailed=True)


@app.delete("/api/friends/profile", status_code=status.HTTP_204_NO_CONTENT)
def delete_friend_profile(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    profile = db.scalars(friend_profile_query().where(FriendProfile.user_id == user.id)).unique().one_or_none()
    if profile is None:
        raise HTTPException(status_code=404, detail="交友厅资料不存在")
    photo_paths = [photo.file_path for photo in profile.photos]
    db.delete(profile)
    for file_path in photo_paths:
        delete_media(file_path)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/friends/requests/mine", response_model=list[FriendRequestOut])
def my_friend_requests(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    requests = db.scalars(
        friend_request_query()
        .where(
            FriendRequest.status == FriendRequestStatus.PENDING,
            or_(FriendRequest.user_a_id == user.id, FriendRequest.user_b_id == user.id),
        )
        .order_by(FriendRequest.created_at.desc())
    ).all()
    return [present_friend_request(item) for item in requests]


@app.post("/api/friends/requests/{target_user_id}", response_model=FriendRequestOut, status_code=status.HTTP_201_CREATED)
def create_friend_request(target_user_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.is_admin:
        raise HTTPException(status_code=403, detail="管理员账号不能申请添加好友")
    if target_user_id == user.id:
        raise HTTPException(status_code=400, detail="不能申请添加自己为好友")
    target = db.get(User, target_user_id)
    if target is None or not target.is_active or target.is_admin:
        raise HTTPException(status_code=404, detail="用户不存在")
    get_friend_profile_or_404(db, user.id)
    get_friend_profile_or_404(db, target_user_id)
    existing = friend_relation_between(db, user.id, target_user_id)
    now = datetime.utcnow()
    if existing is not None:
        if existing.status == FriendRequestStatus.ACCEPTED:
            raise HTTPException(status_code=409, detail="你们已经是好友")
        if existing.status == FriendRequestStatus.PENDING:
            if existing.requester_id == user.id:
                raise HTTPException(status_code=409, detail="好友申请已发送，请等待对方处理")
            raise HTTPException(status_code=409, detail="对方已向你发送好友申请，请直接处理")
        existing.status = FriendRequestStatus.PENDING
        existing.requester_id = user.id
        existing.created_at = now
        existing.responded_at = None
    else:
        user_a_id, user_b_id = sorted((user.id, target_user_id))
        existing = FriendRequest(
            user_a_id=user_a_id,
            user_b_id=user_b_id,
            requester_id=user.id,
            status=FriendRequestStatus.PENDING,
            created_at=now,
        )
        db.add(existing)
    db.commit()
    saved = db.scalar(friend_request_query().where(FriendRequest.id == existing.id))
    return present_friend_request(saved)


def resolve_friend_request(request_id: int, user: User, db: Session, status_value: FriendRequestStatus) -> FriendRequest:
    item = db.scalar(friend_request_query().where(FriendRequest.id == request_id))
    if item is None:
        raise HTTPException(status_code=404, detail="好友申请不存在")
    if item.status != FriendRequestStatus.PENDING:
        raise HTTPException(status_code=409, detail="该好友申请已处理")
    if item.requester_id == user.id:
        raise HTTPException(status_code=403, detail="申请人不能处理自己的好友申请")
    if user.id not in (item.user_a_id, item.user_b_id):
        raise HTTPException(status_code=403, detail="无权处理该好友申请")
    item.status = status_value
    item.responded_at = datetime.utcnow()
    db.commit()
    return db.scalar(friend_request_query().where(FriendRequest.id == item.id))


@app.post("/api/friends/requests/{request_id}/accept", response_model=FriendRequestOut)
def accept_friend_request(request_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return present_friend_request(resolve_friend_request(request_id, user, db, FriendRequestStatus.ACCEPTED))


@app.post("/api/friends/requests/{request_id}/reject", response_model=FriendRequestOut)
def reject_friend_request(request_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return present_friend_request(resolve_friend_request(request_id, user, db, FriendRequestStatus.REJECTED))


@app.delete("/api/friends/requests/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_friend_request(request_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = db.get(FriendRequest, request_id)
    if item is None:
        raise HTTPException(status_code=404, detail="好友申请不存在")
    if item.requester_id != user.id:
        raise HTTPException(status_code=403, detail="只有申请人可以取消申请")
    if item.status != FriendRequestStatus.PENDING:
        raise HTTPException(status_code=409, detail="该好友申请已处理")
    db.delete(item)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


ACTIVE_TAKEN_STATUSES = (TaskStatus.PUBLISHED, TaskStatus.ACCEPTED, TaskStatus.AWAITING, TaskStatus.CANCELLING)


def active_task_count(db: Session, user_id: int) -> int:
    return db.scalar(
        select(func.count())
        .select_from(TaskMember)
        .join(Task, Task.id == TaskMember.task_id)
        .where(
            TaskMember.user_id == user_id,
            TaskMember.response_status == TaskMemberResponse.ACCEPTED,
            Task.status.in_(ACTIVE_TAKEN_STATUSES),
        )
    ) or 0


def start_if_ready(db: Session, task: Task) -> None:
    """达到所需人数时自动开始。required_takers 为 null 表示不限人数，只有委托人手动开始。"""
    if task.status != TaskStatus.PUBLISHED:
        return
    if task.required_takers is None or task.is_designated:
        return
    count = db.scalar(
        select(func.count()).select_from(TaskMember).where(
            TaskMember.task_id == task.id,
            TaskMember.response_status == TaskMemberResponse.ACCEPTED,
        )
    ) or 0
    if count >= task.required_takers:
        task.status = TaskStatus.ACCEPTED
        task.started_at = task.started_at or datetime.utcnow()
        task.updated_at = datetime.utcnow()


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/site-config", response_model=SiteConfigOut)
def site_config():
    """站点公开配置：目前只有页脚备案号。

    无需登录，也不读数据库；备案号等值来自 .env，前端运行时获取，
    因此不会被提交进仓库或打进前端构建产物。
    """
    return SiteConfigOut(
        icp=settings.site_icp.strip(),
        icp_url=settings.safe_site_icp_url,
    )


@app.get("/api/media/{key:path}", include_in_schema=False)
def read_gated_media(key: str, exp: int = 0, sig: str = "", db: Session = Depends(get_db)):
    """私有区媒体读取：必须携带未过期的签名，且记录当前仍处于非公开状态。

    待审/被屏蔽的文件不在 /uploads 静态目录里；``<img>`` 又带不了 Bearer 令牌，
    因此由接口响应签发短时签名 URL。除了验签与有效期，这里还回查数据库：
    记录已删除、或已经过审（此时应改用公开地址）时，旧签名立即失效。
    """
    if not verify_media_signature(key, exp, sig):
        raise HTTPException(status_code=404, detail="文件不存在")
    if not media_key_exists(key, db) or media_key_is_public(key, db):
        raise HTTPException(status_code=404, detail="文件不存在")
    path = storage_file(key, public=False)
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(
        path,
        headers={
            "Cache-Control": "no-store",
            # 即使有人直接打开这个地址，也让内容保持惰性，杜绝 polyglot 文件被当作页面执行。
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.get("/api/auth/captcha", response_model=CaptchaChallenge)
def get_captcha(request: Request):
    # 进入登录/注册页时拉取一次；按 IP 限流防止被刷。
    enforce("captcha-ip", client_ip(request), 60, 300)
    if not captcha_required():
        return CaptchaChallenge(provider="off")
    # 用「实际生效」的 provider：Site Key/Secret Key 缺一个就回落到站内图形验证码，
    # 避免前端拿到 builtin 图形验证码、服务端却按 turnstile 校验的死锁。
    if settings.captcha_effective_provider == "turnstile":
        return CaptchaChallenge(provider="turnstile", site_key=settings.turnstile_site_key)
    captcha_id, png = create_image_captcha()
    return CaptchaChallenge(
        provider="builtin",
        captcha_id=captcha_id,
        image="data:image/png;base64," + base64.b64encode(png).decode(),
        expires_in=settings.captcha_ttl_seconds,
    )


@app.post("/api/auth/register", response_model=RegisterPendingOut, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    """注册：创建待验证账号并发验证邮件。

    注册**不再直接下发登录令牌** —— 必须点邮件里的链接完成验证后才能登录。
    发信失败会返回 503 并回滚整个事务（fail-closed），不会留下「建好了却收不到信」的半成品账号。
    """
    enforce("register-ip", client_ip(request), 10, 3600)
    await verify_captcha(request, payload.captcha_id, payload.captcha_code)
    # 用户名按大小写不敏感判重（否则可注册 Admin 之类与真实管理员仅差大小写的账号），
    # 且用户名与邮箱共用同一句提示，不把「哪个已被注册」暴露成枚举预言机。
    username_taken = db.scalar(
        select(User.id).where(func.lower(User.username) == payload.username.lower()).limit(1)
    )
    email = payload.email.lower()
    if username_taken or email_taken(db, email):
        raise HTTPException(status_code=409, detail=ACCOUNT_TAKEN_DETAIL)
    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        nickname=payload.nickname,
        email=email,
        email_verified=False,
    )
    db.add(user)
    db.flush()
    await _send_verification_mail(db, user, request)
    db.commit()
    return RegisterPendingOut(email_masked=mask_email(email))


async def _send_verification_mail(db: Session, user: User, request: Request) -> None:
    """发放验证令牌并发信；失败会抛 503（调用方不提交事务）。"""
    ttl_hours = settings.email_verification_ttl_hours
    token = issue_link_token(db, user, VERIFY_EMAIL, ttl_minutes=ttl_hours * 60)
    subject, text, html_body = verification_message(verify_link(token, request), ttl_hours=ttl_hours)
    await deliver(user.email, subject, text, html_body)


@app.post("/api/auth/email/resend", response_model=ActionAckOut)
async def resend_verification(payload: AccountRequest, request: Request, db: Session = Depends(get_db)):
    """重发验证邮件。

    账号不存在或已完成验证时同样返回成功：不把「这个邮箱注册过没有」暴露给调用方。
    """
    enforce("email-send-ip", client_ip(request), 20, 3600)
    await verify_captcha(request, payload.captcha_id, payload.captcha_code)
    user = find_account(db, payload.account)
    if user is not None and user.email and not user.email_verified:
        enforce("email-send-user", str(user.id), 5, 3600)
        remaining = cooldown_remaining(db, user.id, VERIFY_EMAIL)
        if remaining == 0:
            await _send_verification_mail(db, user, request)
            db.commit()
    return ActionAckOut()


@app.post("/api/auth/email/confirm", response_model=ActionAckOut)
async def confirm_email_token(
    payload: EmailVerifyRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """统一确认入口：验证新注册账号的邮箱，或生效一次换绑。

    令牌本身就是凭证（只发到被确认的那个邮箱），因此不需要登录态 ——
    这样用户在其它浏览器/手机邮箱里点链接也能完成确认。
    """
    token = payload.token
    row = db.scalar(
        select(EmailToken).where(EmailToken.token_hash == hash_link_token(token))
    )
    if row is None or row.purpose not in (VERIFY_EMAIL, CHANGE_EMAIL):
        raise HTTPException(status_code=422, detail=INVALID_TOKEN_DETAIL)
    user = db.get(User, row.user_id)
    if user is None or not user.is_active or (row.purpose == VERIFY_EMAIL and not user.email):
        raise HTTPException(status_code=422, detail=INVALID_TOKEN_DETAIL)
    consume_link_token(db, row.purpose, token)
    old_verified_email: str | None = None
    if row.purpose == VERIFY_EMAIL:
        user.email_verified = True
    else:
        address = row.new_email
        if not address:
            raise HTTPException(status_code=422, detail=INVALID_TOKEN_DETAIL)
        if email_taken(db, address, exclude_user_id=user.id):
            raise HTTPException(status_code=409, detail=EMAIL_TAKEN_DETAIL)
        old_verified_email = user.email if user.email_verified else None
        user.email = address
        user.email_verified = True
        revoke_credentials(db, user)
    db.commit()
    # 换绑完成后通知老邮箱（best-effort：变更已经生效，不能因为通知失败而报错）
    if old_verified_email and old_verified_email != user.email:
        subject, text, html_body = email_changed_notice(old_verified_email, user.email)
        background.add_task(send_email, old_verified_email, subject, text, html_body, required=False)
    return ActionAckOut()


@app.post("/api/auth/login", response_model=TokenResponse)
async def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    # 按来源 IP 与账号双维度限流，抵御暴力破解与撞库。
    enforce("login-ip", client_ip(request), 30, 300)
    # 验证码校验放在昂贵的 PBKDF2 校验之前，避免被撞库消耗 CPU。
    await verify_captcha(request, payload.captcha_id, payload.captcha_code)
    # 登录名既可以是用户名，也可以是邮箱。
    user = find_account(db, payload.username)
    account_key = f"id:{user.id}" if user else "unknown:" + sha256(payload.username.strip().lower().encode()).hexdigest()
    enforce("login-user", account_key, 10, 300)
    if user is None:
        # 账号不存在时也做一次同成本的哈希校验，抹平「账号是否存在」的耗时旁路。
        equalize_password_check(payload.password)
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if password_needs_rehash(user.password_hash):
        # 迭代次数落后于当前标准时，借登录成功顺带升级哈希。
        user.password_hash = hash_password(payload.password)
        db.commit()
    if not user.is_active:
        raise HTTPException(status_code=403, detail="账号已停用")
    # 注册即带邮箱但还没点验证链接：必须先验证。
    # （存量账号没有邮箱，可以登录，但会被邮箱验证闸门限制到只剩「绑定邮箱」。）
    if user.email and not user.email_verified:
        raise HTTPException(status_code=403, detail="邮箱尚未验证，请先点击验证邮件里的链接")
    return issue_login_response(user, payload.remember)


def issue_login_response(user: User, remember: bool) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user.id, user.token_version, remember=remember),
        user=present_user_self(user),
        remember=remember,
    )


@app.post("/api/auth/password-reset/request", response_model=ActionAckOut)
async def request_password_reset(payload: AccountRequest, request: Request, db: Session = Depends(get_db)):
    """申请重置密码。

    无论账号是否存在、是否绑定了已验证邮箱，都返回同样的成功结果：
    否则这个接口就成了「某个邮箱/用户名是否注册过」的探测器。
    """
    enforce("password-reset-ip", client_ip(request), 10, 3600)
    await verify_captcha(request, payload.captcha_id, payload.captcha_code)
    user = find_account(db, payload.account)
    if user is not None and user.is_active and user.email and user.email_verified:
        enforce("email-send-user", str(user.id), 5, 3600)
        remaining = cooldown_remaining(db, user.id, RESET_PASSWORD)
        if remaining == 0:
            ttl_minutes = settings.password_reset_ttl_minutes
            token = issue_link_token(db, user, RESET_PASSWORD, ttl_minutes=ttl_minutes)
            subject, text, html_body = reset_password_message(reset_link(token, request), ttl_minutes=ttl_minutes)
            await deliver(user.email, subject, text, html_body)
            db.commit()
    return ActionAckOut()


@app.post("/api/auth/password-reset/confirm", response_model=ActionAckOut)
async def confirm_password_reset(payload: PasswordResetConfirm, db: Session = Depends(get_db)):
    """用邮件链接设置新密码：令牌一次性，改密后所有旧会话立即失效。"""
    row = consume_link_token(db, RESET_PASSWORD, payload.token)
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=422, detail=INVALID_TOKEN_DETAIL)
    user.password_hash = hash_password(payload.password)
    # 自增令牌版本：所有已签发的会话作废（与自助改密一致）。
    revoke_credentials(db, user)
    # 能点开重置链接就证明控制了该邮箱，顺带完成验证。
    if user.email:
        user.email_verified = True
    db.commit()
    if user.email:
        subject, text, html_body = password_changed_notice()
        await send_email(user.email, subject, text, html_body, required=False)
    return ActionAckOut()


@app.get("/api/auth/me", response_model=UserSelf)
def me(user: User = Depends(get_authenticated_user)):
    # 未验证也要能拿到自己的状态（前端据此弹强制绑定框），因此这里不走验证闸门。
    return present_user_self(user)


@app.post("/api/auth/logout", response_model=ActionAckOut)
def logout(user: User = Depends(get_authenticated_user), db: Session = Depends(get_db)):
    """退出登录：递增令牌版本，使该账号已签发的全部会话立即失效。

    Bearer 令牌无法在客户端「作废」，只有服务端递增 token_version 才能让被复制/
    泄露的令牌立刻失效；因此登出必须是服务端动作，而不是只清本地缓存。
    """
    lock_credentials(db, user)
    revoke_credentials(db, user)
    db.commit()
    return ActionAckOut()


@app.patch("/api/users/me", response_model=UserSelf)
def update_profile(payload: UserUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.nickname = payload.nickname.strip()
    user.qq = payload.qq
    # 志愿者与管理员都可以自行决定是否在名录公开 QQ（其余角色一律不公开）。
    user.qq_public = (
        payload.qq_public if user.role in (UserRole.VOLUNTEER, UserRole.STAFF) else False
    )
    user.bio = payload.bio.strip() if payload.bio else None
    db.commit()
    db.refresh(user)
    return present_user_self(user)


@app.patch("/api/users/me/password", response_model=UserSelf)
def update_my_password(
    payload: UserPasswordUpdate,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    # 限流当前密码的尝试次数，避免令牌泄露后被用来爆破当前密码改号。
    enforce("password-change", str(user.id), 10, 300)
    lock_credentials(db, user)
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=403, detail="当前密码不正确")
    user.password_hash = hash_password(payload.password)
    # 自增令牌版本：旧密码签发的所有会话立即失效，需用新密码重新登录。
    revoke_credentials(db, user)
    db.commit()
    db.refresh(user)
    return present_user_self(user)


@app.post("/api/users/me/email", response_model=ActionAckOut)
async def request_email_binding(
    payload: EmailChangeRequest,
    request: Request,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    """绑定或换绑邮箱：先向新地址发确认链接，确认前不生效。

    这是未验证用户唯一能做的「正事」之一，因此不走验证闸门。
    """
    enforce("email-change-password", str(user.id), 10, 300)
    lock_credentials(db, user)
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=403, detail="当前密码不正确")
    address = payload.email.lower()
    if user.email_verified and user.email == address:
        raise HTTPException(status_code=409, detail="该邮箱已是当前邮箱")
    if email_taken(db, address, exclude_user_id=user.id):
        raise HTTPException(status_code=409, detail=EMAIL_TAKEN_DETAIL)
    enforce("email-send-user", str(user.id), 5, 3600)
    remaining = cooldown_remaining(db, user.id, CHANGE_EMAIL)
    if remaining:
        raise HTTPException(status_code=429, detail=f"发送过于频繁，请 {remaining} 秒后再试")

    ttl_hours = settings.email_verification_ttl_hours
    # 换绑前的旧邮箱（只有已验证过才需要通知）
    old_verified_email = user.email if user.email_verified else None
    user.pending_email = address
    token = issue_link_token(
        db, user, CHANGE_EMAIL, ttl_minutes=ttl_hours * 60, new_email=address
    )
    subject, text, html_body = change_email_message(
        verify_link(token, request), address, ttl_hours=ttl_hours
    )
    # fail-closed：确认信发不出去就不改 pending_email（事务不提交）
    await deliver(address, subject, text, html_body)
    if old_verified_email:
        subject, text, html_body = new_email_pending_notice(address)
        await send_email(old_verified_email, subject, text, html_body, required=False)
    db.commit()
    return ActionAckOut()


@app.patch("/api/users/me/email-notify", response_model=UserSelf)
def update_email_notify(
    payload: NotifyEmailUpdate,
    user: User = Depends(get_authenticated_user),
    db: Session = Depends(get_db),
):
    """事件通知邮件开关（账号安全类邮件不受此开关影响）。"""
    user.notify_email = payload.notify_email
    db.commit()
    db.refresh(user)
    return present_user_self(user)


MAX_USER_PHOTOS = 3


def user_with_photos_query():
    return select(User).options(joinedload(User.photos))


async def save_user_photos(photos: list[UploadFile], user: User, db: Session) -> User:
    if len(photos) > MAX_USER_PHOTOS:
        raise HTTPException(status_code=422, detail=f"最多上传 {MAX_USER_PHOTOS} 张图片")
    images = await read_sugar_images(photos)
    existing = len(user.photos)
    if existing + len(images) > MAX_USER_PHOTOS:
        raise HTTPException(status_code=422, detail=f"每位用户最多保存 {MAX_USER_PHOTOS} 张图片")
    records = store_user_images(user, images)
    db.add_all(records)
    try:
        db.commit()
    except Exception:
        db.rollback()
        for record in records:
            delete_media(record.file_path)
        raise
    db.refresh(user)
    return user


def store_user_images(user: User, images: list[tuple[str, bytes]]) -> list[UserPhoto]:
    """用户介绍图片默认待审（先审后公开），落在私有区。"""
    settings.ensure_storage_directory()
    keys: list[str] = []
    stored: list[Path] = []
    try:
        for extension, content in images:
            key = f"users/{user.id}/{uuid4().hex}{extension}"
            stored.append(write_media(key, content, public=False))
            keys.append(key)
    except OSError as error:
        for destination in stored:
            destination.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=image_storage_error_detail(error)) from error
    return [UserPhoto(user=user, file_path=key) for key in keys]


@app.post("/api/users/me/photos", response_model=UserProfileOut, status_code=status.HTTP_201_CREATED)
async def upload_user_photos(
    photos: list[UploadFile] = File(default=[]),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not photos:
        raise HTTPException(status_code=422, detail="请选择要上传的图片")
    enforce("upload", str(user.id), 30, 3600)
    user = await save_user_photos(photos, user, db)
    return present_user_profile(user, user)


@app.delete("/api/users/me/photos/{photo_id}", response_model=UserProfileOut)
def delete_user_photo(photo_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    photo = db.get(UserPhoto, photo_id)
    if photo is None or photo.user_id != user.id:
        raise HTTPException(status_code=404, detail="图片不存在")
    path = photo.file_path
    db.delete(photo)
    delete_media(path)
    db.commit()
    db.refresh(user)
    return present_user_profile(user, user)


@app.post("/api/users/me/avatar", response_model=UserProfileOut, status_code=status.HTTP_201_CREATED)
async def upload_avatar(
    avatar: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """上传头像：仅支持 PNG/JPG、最大 2 MB；需管理员审核通过后才公开展示。

    未过审的头像存放在私有区，只有本人与审核人员能通过签名 URL 看到。
    """
    enforce("upload", str(user.id), 30, 3600)
    content = await avatar.read(MAX_AVATAR_BYTES + 1)
    if not content:
        raise HTTPException(status_code=422, detail="请选择要上传的头像图片")
    if len(content) > MAX_AVATAR_BYTES:
        raise HTTPException(status_code=422, detail="头像图片不能超过 2 MB")
    extension, content = normalize_image(
        content, allowed=AVATAR_SIGNATURES, format_hint="头像仅支持 PNG 或 JPG 格式"
    )
    settings.ensure_storage_directory()
    file_path = f"avatars/{user.id}/{uuid4().hex}{extension}"
    try:
        write_media(file_path, content, public=False)
    except OSError as error:
        raise HTTPException(status_code=500, detail=image_storage_error_detail(error)) from error
    clear_avatar_file(user)
    user.avatar_path = file_path
    user.avatar_visible = False
    user.avatar_moderated_at = None
    db.commit()
    db.refresh(user)
    return present_user_profile(user, user)


def clear_avatar_file(user: User) -> None:
    """移除旧头像文件并清空头像字段（重新上传换头像、删除头像时复用）。"""
    if not user.avatar_path:
        return
    delete_media(user.avatar_path)
    user.avatar_path = None
    user.avatar_visible = False
    user.avatar_moderated_at = None


@app.delete("/api/users/me/avatar", response_model=UserProfileOut)
def delete_avatar(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    clear_avatar_file(user)
    db.commit()
    db.refresh(user)
    return present_user_profile(user, user)


@app.patch("/api/admin/users/{user_id}/avatar", response_model=UserProfileOut)
def moderate_avatar(
    user_id: int,
    payload: AdminPhotoUpdate,
    manager: User = Depends(get_content_moderator),
    db: Session = Depends(get_db),
):
    """管理员组审核头像：通过后公开展示，驳回则仅本人可见。"""
    target = db.get(User, user_id)
    if target is None or not target.avatar_path:
        raise HTTPException(status_code=404, detail="头像不存在")
    target.avatar_visible = payload.is_visible
    target.avatar_moderated_at = datetime.utcnow()
    commit_moderation(db, target.avatar_path, public=payload.is_visible)
    db.refresh(target)
    return present_moderation_profile(target, manager)


@app.get("/api/users/{user_id}", response_model=UserProfileOut)
def user_profile(user_id: int, viewer: User | None = Depends(get_optional_user), db: Session = Depends(get_db)):
    """名录成员允许匿名查看，QQ 仍按公开偏好和协作关系脱敏。"""
    directory_roles = (
        UserRole.STAFF,
        UserRole.DISCIPLINARIAN,
        UserRole.MASCOT,
        UserRole.VOLUNTEER,
    )
    target = db.scalar(user_with_photos_query().where(User.id == user_id))
    # 匿名访客对「不存在」与「存在但需登录」返回同一状态码，避免被用来枚举账号 id。
    if viewer is None and (
        target is None or not target.is_active or target.role not in directory_roles
    ):
        raise HTTPException(status_code=401, detail="请先登录")
    if target is None or not target.is_active:
        raise HTTPException(status_code=404, detail="用户不存在")
    data = present_user_profile(target, viewer)
    if not can_view_user_qq(db, viewer, target):
        data.qq = None
    # 是否超管属于敏感的运营信息，只对本人与管理组成员展示。
    if not (
        viewer is not None
        and (viewer.is_admin or viewer.id == target.id or viewer.role == UserRole.STAFF)
    ):
        data.is_admin = False
    return data


@app.get("/api/users/{user_id}/public", response_model=UserProfileOut)
def user_public_profile(user_id: int, viewer: User | None = Depends(get_optional_user), db: Session = Depends(get_db)):
    """公开资料（无联系方式）：留言板等公开场景点击用户时使用，游客可访问。"""
    target = db.scalar(user_with_photos_query().where(User.id == user_id))
    if target is None or not target.is_active:
        raise HTTPException(status_code=404, detail="用户不存在")
    data = present_user_profile(target, viewer)
    data.qq = None
    return data


@app.get("/api/staff", response_model=StaffDirectoryOut)
def staff_directory(db: Session = Depends(get_db)):
    def users_with_role(role: UserRole) -> list[User]:
        return db.scalars(
            user_with_photos_query()
            .where(User.role == role, User.is_active.is_(True), User.is_admin.is_(False))
            .order_by(User.created_at.asc())
        ).unique().all()

    staff = users_with_role(UserRole.STAFF)
    disciplinarians = users_with_role(UserRole.DISCIPLINARIAN)
    mascots = users_with_role(UserRole.MASCOT)
    volunteers = users_with_role(UserRole.VOLUNTEER)

    def profile_without_qq(user: User) -> UserProfileOut:
        return present_user_profile(user).model_copy(update={"qq": None})

    def profile_with_optional_qq(user: User) -> UserProfileOut:
        return present_user_profile(user).model_copy(
            update={"qq": user.qq if user.qq_public else None}
        )

    return StaffDirectoryOut(
        staff=[profile_with_optional_qq(user) for user in staff],
        disciplinarians=[profile_without_qq(user) for user in disciplinarians],
        mascots=[profile_without_qq(user) for user in mascots],
        volunteers=[
            present_user_profile(user).model_copy(update={"qq": user.qq if user.qq_public else None})
            for user in volunteers
        ],
    )


@app.get("/api/sugar/profiles", response_model=list[SugarProfileCardOut])
def list_sugar_profiles(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """砂糖社卡片列表不含 QQ；查看详情时才按一对一上下文提供联系方式。"""
    profiles = db.scalars(
        sugar_profile_query()
        .join(SugarProfile.user)
        .where(User.is_active.is_(True), User.is_admin.is_(False))
        .order_by(SugarProfile.updated_at.desc())
        .limit(200)
    ).unique().all()
    return [present_sugar_profile(profile, viewer=user) for profile in profiles]


@app.get("/api/sugar/profiles/{user_id}", response_model=SugarProfileDetailOut)
def sugar_profile_detail(
    user_id: int,
    viewer: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    target = db.get(User, user_id)
    if target is None or not target.is_active or target.is_admin:
        raise HTTPException(status_code=404, detail="用户不存在")
    profile = get_sugar_profile_or_404(db, user_id)
    relationship = pair_between(db, viewer.id, target.id) if viewer.id != target.id else None
    # QQ 只在本人，或已与本人建立「进行中」砂糖关系的对方之间可见；
    # 否则任何登录用户都能遍历 user_id 抓取他人联系方式。
    can_see_qq = viewer.id == target.id or (
        relationship is not None and relationship.status == SugarPairStatus.ACTIVE
    )
    return present_sugar_profile(
        profile,
        viewer=viewer,
        qq=target.qq if can_see_qq else None,
        relationship=relationship,
        detailed=True,
    )


@app.post("/api/sugar/profile", response_model=SugarProfileDetailOut)
async def save_sugar_profile(
    response: Response,
    about: Annotated[str, Form(...)],
    photos: list[UploadFile] = File(default=[]),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """新建或更新砂糖社档案。每次追加上传最多 6 张，单张最多 5 MiB。"""
    if user.is_admin:
        raise HTTPException(status_code=403, detail="管理员账号不能登记砂糖社档案")
    enforce("upload", str(user.id), 30, 3600)
    about = about.strip()
    if not 1 <= len(about) <= 1000:
        raise HTTPException(status_code=422, detail="砂糖社介绍需要 1 至 1000 个字符")
    if len(photos) > MAX_SUGAR_PHOTOS:
        raise HTTPException(status_code=422, detail=f"最多上传 {MAX_SUGAR_PHOTOS} 张照片")
    images = await read_sugar_images(photos)
    profile = db.scalars(sugar_profile_query().where(SugarProfile.user_id == user.id)).unique().one_or_none()
    is_new = profile is None
    if profile is None:
        if not images:
            raise HTTPException(status_code=422, detail="首次登记请至少上传一张照片")
        profile = SugarProfile(user_id=user.id, about=about)
        db.add(profile)
        db.flush()
    else:
        if len(profile.photos) + len(images) > MAX_SUGAR_PHOTOS:
            raise HTTPException(status_code=422, detail=f"每个档案最多保存 {MAX_SUGAR_PHOTOS} 张照片")
        profile.about = about
        profile.updated_at = datetime.utcnow()
    records = store_sugar_images(profile, images)
    db.add_all(records)
    try:
        db.commit()
    except Exception:
        db.rollback()
        for record in records:
            delete_media(record.file_path)
        raise
    saved = get_sugar_profile_or_404(db, user.id)
    response.status_code = status.HTTP_201_CREATED if is_new else status.HTTP_200_OK
    return present_sugar_profile(saved, viewer=user, qq=user.qq, detailed=True)


@app.delete("/api/sugar/photos/{photo_id}", response_model=SugarProfileDetailOut)
def delete_sugar_photo(photo_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    photo = db.get(SugarPhoto, photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="照片不存在")
    profile = get_sugar_profile_or_404(db, user.id)
    if photo.profile_id != profile.id:
        raise HTTPException(status_code=403, detail="只能删除自己的照片")
    if len(profile.photos) <= 1:
        raise HTTPException(status_code=409, detail="档案至少需要保留一张照片")
    file_path = photo.file_path
    db.delete(photo)
    delete_media(file_path)
    db.commit()
    return present_sugar_profile(get_sugar_profile_or_404(db, user.id), viewer=user, qq=user.qq, detailed=True)


@app.delete("/api/sugar/profile", status_code=status.HTTP_204_NO_CONTENT)
def delete_sugar_profile(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """删除本人砂糖资料；待确认关系一并移除，进行中的关系标记为已结束。"""
    profile = db.scalars(sugar_profile_query().where(SugarProfile.user_id == user.id)).unique().one_or_none()
    if profile is None:
        raise HTTPException(status_code=404, detail="砂糖社资料不存在")
    photo_paths = [photo.file_path for photo in profile.photos]
    now = datetime.utcnow()
    pairs = db.scalars(
        sugar_pair_query().where(
            or_(SugarPair.first_user_id == user.id, SugarPair.second_user_id == user.id),
            SugarPair.status.in_([SugarPairStatus.PENDING, SugarPairStatus.ACTIVE]),
        )
    ).all()
    for pair in pairs:
        if pair.status == SugarPairStatus.ACTIVE:
            pair.status = SugarPairStatus.ENDED
            pair.ended_at = now
        else:
            db.delete(pair)
    db.delete(profile)
    for file_path in photo_paths:
        delete_media(file_path)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/sugar/pairs/mine", response_model=list[SugarPairOut])
def my_sugar_pairs(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    pairs = db.scalars(
        sugar_pair_query()
        .where(
            SugarPair.status.in_([SugarPairStatus.PENDING, SugarPairStatus.ACTIVE]),
            or_(SugarPair.first_user_id == user.id, SugarPair.second_user_id == user.id),
        )
        .order_by(SugarPair.initiated_at.desc())
    ).all()
    return [present_sugar_pair(pair) for pair in pairs]


@app.get("/api/sugar/pairs/top", response_model=list[SugarPairOut])
def top_sugar_pairs(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    pairs = db.scalars(
        sugar_pair_query()
        .where(SugarPair.status == SugarPairStatus.ACTIVE)
        .order_by(SugarPair.activated_at.asc())
        .limit(1000)
    ).all()
    return [present_sugar_pair(pair) for pair in sorted(pairs, key=sugar_pair_duration, reverse=True)[:3]]


@app.post("/api/sugar/pairs/{target_user_id}/confirm", response_model=SugarPairOut, status_code=status.HTTP_201_CREATED)
def confirm_sugar_pair(
    target_user_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """第一次点击建立待确认记录；被邀请的一方点击同一操作后正式开始计时。"""
    if target_user_id == user.id:
        raise HTTPException(status_code=400, detail="不能与自己登记为砂糖")
    target = db.get(User, target_user_id)
    if target is None or not target.is_active or target.is_admin:
        raise HTTPException(status_code=404, detail="用户不存在")
    get_sugar_profile_or_404(db, user.id)
    get_sugar_profile_or_404(db, target_user_id)
    existing = pair_between(db, user.id, target_user_id)
    now = datetime.utcnow()
    if existing is not None:
        if existing.status == SugarPairStatus.ACTIVE:
            raise HTTPException(status_code=409, detail="你们已经是砂糖")
        if existing.initiated_by_id == user.id:
            raise HTTPException(status_code=409, detail="已等待对方确认")
        # 已有待确认记录时，资料发布人（被邀请方）再次确认即可选择并激活该关系。
        # 其他人的待确认请求可以同时存在，待发布人逐一选择。
        if active_sugar_pair_for(db, user.id, existing.id) or active_sugar_pair_for(db, target_user_id, existing.id):
            raise HTTPException(status_code=409, detail="双方已有进行中的砂糖关系")
        existing.status = SugarPairStatus.ACTIVE
        existing.activated_at = now
        # 关系激活后，双方档案都被锁定；清理涉及任一方的其他待确认请求。
        locked_user_ids = [existing.first_user_id, existing.second_user_id]
        other_pending = db.scalars(
            select(SugarPair).where(
                SugarPair.id != existing.id,
                SugarPair.status == SugarPairStatus.PENDING,
                or_(
                    SugarPair.first_user_id.in_(locked_user_ids),
                    SugarPair.second_user_id.in_(locked_user_ids),
                ),
            )
        ).all()
        for pending in other_pending:
            db.delete(pending)
        db.commit()
        return present_sugar_pair(existing)
    # 允许同一资料发布人同时收到多条待确认请求，但任一方已有进行中的关系时不可再发起。
    if active_sugar_pair_for(db, user.id) or active_sugar_pair_for(db, target_user_id):
        raise HTTPException(status_code=409, detail="双方已有进行中的砂糖关系")
    pair = SugarPair(
        first_user_id=user.id,
        second_user_id=target_user_id,
        initiated_by_id=user.id,
        initiated_at=now,
    )
    db.add(pair)
    db.commit()
    db.refresh(pair)
    return present_sugar_pair(db.scalar(sugar_pair_query().where(SugarPair.id == pair.id)))


@app.post("/api/sugar/pairs/{pair_id}/end", response_model=SugarPairOut)
def end_sugar_pair(pair_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    pair = db.scalar(sugar_pair_query().where(SugarPair.id == pair_id))
    if pair is None:
        raise HTTPException(status_code=404, detail="砂糖关系不存在")
    if user.id not in (pair.first_user_id, pair.second_user_id):
        raise HTTPException(status_code=403, detail="只有砂糖双方可以结束关系")
    if pair.status != SugarPairStatus.ACTIVE:
        raise HTTPException(status_code=409, detail="当前关系不能结束")
    pair.status = SugarPairStatus.ENDED
    pair.ended_at = datetime.utcnow()
    db.commit()
    return present_sugar_pair(pair)


@app.post("/api/feedback", response_model=FeedbackOut, status_code=status.HTTP_201_CREATED)
def create_feedback(
    payload: FeedbackCreate,
    request: Request,
    viewer: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """提交反馈/建议。登录用户可留空联系方式；游客需填写联系方式便于管理员回复。"""
    enforce("feedback-ip", client_ip(request), 10, 3600)
    if viewer is None and not payload.contact:
        raise HTTPException(status_code=422, detail="请先登录，或填写联系方式以便管理员联系你")
    if viewer is None and payload.contact and len(payload.contact) < 2:
        raise HTTPException(status_code=422, detail="联系方式至少需要 2 个字符")
    feedback = Feedback(
        user_id=viewer.id if viewer else None,
        page=payload.page.strip() if payload.page else None,
        content=payload.content.strip(),
        contact=payload.contact.strip() if payload.contact else None,
    )
    db.add(feedback)
    db.commit()
    return present_feedback(feedback)


@app.get("/api/feedback/mine", response_model=list[FeedbackOut])
def my_feedback(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """当前用户提交过的反馈及其处理状态。"""
    feedback_list = db.scalars(
        select(Feedback).where(Feedback.user_id == user.id).order_by(Feedback.created_at.desc())
    ).all()
    return [present_feedback(item) for item in feedback_list]


@app.get("/api/admin/feedback", response_model=list[FeedbackOut])
def admin_feedback(_: User = Depends(get_role_manager), db: Session = Depends(get_db)):
    feedback_list = db.scalars(select(Feedback).order_by(Feedback.created_at.desc()).limit(500)).all()
    return [present_feedback(item) for item in feedback_list]


@app.patch("/api/admin/feedback/{feedback_id}", response_model=FeedbackOut)
def handle_feedback(
    feedback_id: int,
    payload: FeedbackUpdate,
    background: BackgroundTasks,
    _: User = Depends(get_role_manager),
    db: Session = Depends(get_db),
):
    """管理员组处理反馈：标记状态并填写处理回复。"""
    feedback = db.get(Feedback, feedback_id)
    if feedback is None:
        raise HTTPException(status_code=404, detail="反馈不存在")
    if payload.status is not None:
        feedback.status = payload.status
        feedback.handled_at = datetime.utcnow() if payload.status == FeedbackStatus.HANDLED else None
    if payload.reply is not None:
        feedback.reply = payload.reply.strip() or None
    feedback.handled_at = datetime.utcnow() if feedback.status == FeedbackStatus.HANDLED else feedback.handled_at
    db.commit()
    if feedback.user_id is not None and feedback.reply:
        queue_user_notification(
            feedback.user,
            background,
            "你的反馈已收到回复",
            ["你提交的反馈已由管理员回复，可登录站点查看处理结果。"],
        )
    return present_feedback(feedback)


def present_application(
    application: VolunteerApplication, viewer: User | None = None
) -> VolunteerApplicationAdminOut:
    return VolunteerApplicationAdminOut(
        id=application.id,
        reason=application.reason,
        status=application.status,
        review_note=application.review_note,
        created_at=application.created_at,
        handled_at=application.handled_at,
        user=present_user_public(application.user, viewer),
        handled_by=present_user_public(application.handled_by, viewer) if application.handled_by else None,
    )


@app.post("/api/volunteer-applications", response_model=VolunteerApplicationOut, status_code=status.HTTP_201_CREATED)
def create_volunteer_application(
    payload: VolunteerApplicationCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """普通用户申请成为志愿者，需提交理由，由管理员组审核。"""
    if user.is_admin or user.role != UserRole.USER:
        raise HTTPException(status_code=403, detail="只有普通用户可以申请成为志愿者")
    pending = db.scalar(
        select(VolunteerApplication).where(
            VolunteerApplication.user_id == user.id,
            VolunteerApplication.status == ApplicationStatus.PENDING,
        )
    )
    if pending is not None:
        raise HTTPException(status_code=409, detail="你已提交过申请，请等待管理员处理")
    application = VolunteerApplication(user_id=user.id, reason=payload.reason.strip())
    db.add(application)
    db.commit()
    db.refresh(application)
    return present_application(application, viewer=user)


@app.get("/api/volunteer-applications/mine", response_model=VolunteerApplicationOut | None)
def my_volunteer_application(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """当前用户最近一次志愿者申请及审核状态。"""
    application = db.scalars(
        select(VolunteerApplication)
        .where(VolunteerApplication.user_id == user.id)
        .order_by(VolunteerApplication.created_at.desc(), VolunteerApplication.id.desc())
        .limit(1)
    ).first()
    return present_application(application, viewer=user) if application else None


@app.get("/api/admin/volunteer-applications", response_model=list[VolunteerApplicationAdminOut])
def admin_volunteer_applications(
    manager: User = Depends(get_role_manager), db: Session = Depends(get_db)
):
    applications = db.scalars(
        select(VolunteerApplication)
        .options(joinedload(VolunteerApplication.user), joinedload(VolunteerApplication.handled_by))
        .order_by(VolunteerApplication.created_at.desc(), VolunteerApplication.id.desc())
        .limit(500)
    ).all()
    return [present_application(item, viewer=manager) for item in applications]


@app.post("/api/admin/volunteer-applications/{application_id}/review", response_model=VolunteerApplicationAdminOut)
def review_volunteer_application(
    application_id: int,
    payload: VolunteerApplicationReview,
    background: BackgroundTasks,
    manager: User = Depends(get_role_manager),
    db: Session = Depends(get_db),
):
    """管理员组审核志愿者申请：通过则申请人升为志愿者。"""
    application = db.get(VolunteerApplication, application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="申请不存在")
    if application.status != ApplicationStatus.PENDING:
        raise HTTPException(status_code=409, detail="该申请已处理过")
    if payload.action == "approve":
        applicant = db.get(User, application.user_id)
        if applicant is None:
            raise HTTPException(status_code=404, detail="申请用户不存在")
        if applicant.role != UserRole.VOLUNTEER:
            applicant.role = UserRole.VOLUNTEER
            applicant.qq_public = False
        application.status = ApplicationStatus.APPROVED
    else:
        application.status = ApplicationStatus.REJECTED
    application.review_note = payload.note.strip() if payload.note else None
    application.handled_by_id = manager.id
    application.handled_at = datetime.utcnow()
    db.commit()
    db.refresh(application)
    queue_user_notification(
        application.user,
        background,
        "志愿者申请审核结果",
        [
            f"你的志愿者申请已{'通过' if application.status == ApplicationStatus.APPROVED else '被驳回'}。",
            f"审核备注：{application.review_note}" if application.review_note else "管理员未填写备注。",
        ],
    )
    return present_application(application, viewer=manager)


def present_beta_application(
    application: BetaApplication, viewer: User | None = None
) -> BetaApplicationAdminOut:
    return BetaApplicationAdminOut(
        id=application.id,
        reason=application.reason,
        status=application.status,
        review_note=application.review_note,
        created_at=application.created_at,
        handled_at=application.handled_at,
        user=present_user_public(application.user, viewer),
        handled_by=present_user_public(application.handled_by, viewer) if application.handled_by else None,
    )


@app.post("/api/beta-applications", response_model=BetaApplicationOut, status_code=status.HTTP_201_CREATED)
def create_beta_application(
    payload: BetaApplicationCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """普通用户申请虚拟人生内测资格。"""
    if user.is_admin or user.role in (UserRole.STAFF, UserRole.MASCOT) or user.is_beta_tester:
        raise HTTPException(status_code=403, detail="当前账号无需申请内测资格")
    pending = db.scalar(
        select(BetaApplication).where(
            BetaApplication.user_id == user.id,
            BetaApplication.status == ApplicationStatus.PENDING,
        )
    )
    if pending is not None:
        raise HTTPException(status_code=409, detail="你已提交过内测申请，请等待审核")
    application = BetaApplication(user_id=user.id, reason=payload.reason.strip())
    db.add(application)
    db.commit()
    db.refresh(application)
    return present_beta_application(application, viewer=user)


@app.get("/api/beta-applications/mine", response_model=BetaApplicationOut | None)
def my_beta_application(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    application = db.scalars(
        select(BetaApplication)
        .where(BetaApplication.user_id == user.id)
        .order_by(BetaApplication.created_at.desc(), BetaApplication.id.desc())
        .limit(1)
    ).first()
    return present_beta_application(application, viewer=user) if application else None


@app.get("/api/admin/beta-applications", response_model=list[BetaApplicationAdminOut])
@app.get("/api/operations/beta-applications", response_model=list[BetaApplicationAdminOut])
def beta_applications(
    manager: User = Depends(get_beta_application_manager), db: Session = Depends(get_db)
):
    applications = db.scalars(
        select(BetaApplication)
        .options(joinedload(BetaApplication.user), joinedload(BetaApplication.handled_by))
        .order_by(BetaApplication.created_at.desc(), BetaApplication.id.desc())
        .limit(500)
    ).all()
    return [present_beta_application(item, viewer=manager) for item in applications]


@app.post("/api/admin/beta-applications/{application_id}/review", response_model=BetaApplicationAdminOut)
@app.post("/api/operations/beta-applications/{application_id}/review", response_model=BetaApplicationAdminOut)
def review_beta_application(
    application_id: int,
    payload: BetaApplicationReview,
    background: BackgroundTasks,
    manager: User = Depends(get_beta_application_manager),
    db: Session = Depends(get_db),
):
    application = db.get(BetaApplication, application_id)
    if application is None:
        raise HTTPException(status_code=404, detail="申请不存在")
    if application.status != ApplicationStatus.PENDING:
        raise HTTPException(status_code=409, detail="该申请已处理过")
    applicant = db.get(User, application.user_id)
    if applicant is None:
        raise HTTPException(status_code=404, detail="申请用户不存在")
    if payload.action == "approve":
        applicant.is_beta_tester = True
        application.status = ApplicationStatus.APPROVED
    else:
        application.status = ApplicationStatus.REJECTED
    application.review_note = payload.note.strip() if payload.note else None
    application.handled_by_id = manager.id
    application.handled_at = datetime.utcnow()
    db.commit()
    db.refresh(application)
    queue_user_notification(
        application.user,
        background,
        "内测申请审核结果",
        [
            f"你的内测申请已{'通过' if application.status == ApplicationStatus.APPROVED else '被驳回'}。",
            f"审核备注：{application.review_note}" if application.review_note else "管理员未填写备注。",
        ],
    )
    return present_beta_application(application, viewer=manager)


def can_moderate(user: User | None) -> bool:
    """留言板删除权限：管理员组（超管/管理员）。"""
    return user is not None and (user.is_admin or user.role == UserRole.STAFF)


def can_review_content(user: User | None) -> bool:
    return user is not None and (user.is_admin or user.role in (UserRole.STAFF, UserRole.DISCIPLINARIAN))


def present_board_comment(comment: BoardComment, viewer: User | None) -> BoardCommentOut:
    return BoardCommentOut(
        id=comment.id,
        content=comment.content,
        created_at=comment.created_at,
        user=present_user_public(comment.user, viewer),
        can_delete=can_moderate(viewer) or (viewer is not None and viewer.id == comment.user_id),
    )


def present_board_message(message: BoardMessage, viewer: User | None) -> BoardMessageOut:
    return BoardMessageOut(
        id=message.id,
        content=message.content,
        created_at=message.created_at,
        user=present_user_public(message.user, viewer),
        comments=[present_board_comment(comment, viewer) for comment in message.comments],
        can_delete=can_moderate(viewer) or (viewer is not None and viewer.id == message.user_id),
    )


@app.get("/api/board", response_model=list[BoardMessageOut])
def list_board_messages(
    viewer: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """留言板：最新 200 条留言及其评论，游客可浏览。"""
    messages = db.scalars(
        select(BoardMessage)
        .options(joinedload(BoardMessage.user), joinedload(BoardMessage.comments).joinedload(BoardComment.user))
        .order_by(BoardMessage.created_at.desc(), BoardMessage.id.desc())
        .limit(200)
    ).unique().all()
    return [present_board_message(message, viewer) for message in messages]


@app.post("/api/board", response_model=BoardMessageOut, status_code=status.HTTP_201_CREATED)
def create_board_message(
    payload: BoardPostCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    enforce("board-post", str(user.id), 20, 600)
    message = BoardMessage(user_id=user.id, content=payload.content.strip())
    db.add(message)
    db.commit()
    db.refresh(message)
    return present_board_message(message, viewer=user)


@app.post("/api/board/{message_id}/comments", response_model=BoardMessageOut, status_code=status.HTTP_201_CREATED)
def create_board_comment(
    message_id: int,
    payload: BoardCommentCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    message = db.get(BoardMessage, message_id)
    if message is None:
        raise HTTPException(status_code=404, detail="留言不存在或已被删除")
    enforce("board-post", str(user.id), 20, 600)
    message.comments.append(BoardComment(user_id=user.id, content=payload.content.strip()))
    db.commit()
    db.refresh(message)
    return present_board_message(message, viewer=user)


def delete_board_item_allowed(item_user_id: int, user: User) -> None:
    if user.id != item_user_id and not can_moderate(user):
        raise HTTPException(status_code=403, detail="只能删除自己的留言或评论")


@app.delete("/api/board/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_board_message(
    message_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    message = db.get(BoardMessage, message_id)
    if message is None:
        raise HTTPException(status_code=404, detail="留言不存在或已被删除")
    delete_board_item_allowed(message.user_id, user)
    db.delete(message)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.delete("/api/board/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_board_comment(
    comment_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    comment = db.get(BoardComment, comment_id)
    if comment is None:
        raise HTTPException(status_code=404, detail="评论不存在或已被删除")
    delete_board_item_allowed(comment.user_id, user)
    db.delete(comment)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---- 故事会 ----


ANONYMOUS_STORY_AUTHOR = UserPublic(id=0, nickname="匿名作者", bio=None, photos=[])


def story_author(story: Story, viewer: User | None) -> UserPublic:
    """匿名故事的作者对本人与管理员组可见，其他人只看到匿名哨兵。"""
    if story.is_anonymous and not (viewer is not None and (viewer.id == story.author_id or can_moderate(viewer))):
        return ANONYMOUS_STORY_AUTHOR
    return present_user_public(story.author, viewer)


def can_delete_story(story: Story, viewer: User | None) -> bool:
    return viewer is not None and (can_moderate(viewer) or viewer.id == story.author_id)


def present_story_photo(photo: StoryPhoto, viewer: User | None) -> StoryPhotoOut:
    return StoryPhotoOut(
        id=photo.id,
        image_url=media_url(photo.file_path, public=photo.is_visible) or "",
        is_visible=photo.is_visible,
        moderated=photo.moderated_at is not None,
        uploaded_by_me=viewer is not None and viewer.id == photo.user_id,
    )


def visible_story_photos(story: Story, viewer: User | None) -> list[StoryPhotoOut]:
    """待审/被驳回的配图仅作者本人和管理员组可见。"""
    return [
        present_story_photo(photo, viewer)
        for photo in story.photos
        if photo.is_visible or (viewer is not None and (viewer.id == photo.user_id or can_review_content(viewer)))
    ]


def present_story_comment(story: Story, comment: StoryComment, viewer: User | None) -> StoryCommentOut:
    can_delete = viewer is not None and (
        can_moderate(viewer) or viewer.id in (comment.user_id, story.author_id)
    )
    return StoryCommentOut(
        id=comment.id,
        content=comment.content,
        created_at=comment.created_at,
        user=present_user_public(comment.user, viewer),
        can_delete=can_delete,
    )


def present_story_card(story: Story, viewer: User | None, comment_count: int) -> StoryCardOut:
    visible = [photo for photo in story.photos if photo.is_visible]
    return StoryCardOut(
        id=story.id,
        title=story.title,
        excerpt=story.content[:120],
        author=story_author(story, viewer),
        is_anonymous=story.is_anonymous,
        cover_url=media_url(visible[0].file_path, public=True) if visible else None,
        photo_count=len(visible),
        comment_count=comment_count,
        created_at=story.created_at,
        can_delete=can_delete_story(story, viewer),
    )


def present_story_detail(story: Story, viewer: User | None) -> StoryDetailOut:
    return StoryDetailOut(
        id=story.id,
        title=story.title,
        content=story.content,
        author=story_author(story, viewer),
        is_anonymous=story.is_anonymous,
        photos=visible_story_photos(story, viewer),
        comments=[present_story_comment(story, comment, viewer) for comment in story.comments],
        created_at=story.created_at,
        can_delete=can_delete_story(story, viewer),
    )


def get_story_or_404(db: Session, story_id: int) -> Story:
    story = db.get(Story, story_id)
    if story is None:
        raise HTTPException(status_code=404, detail="故事不存在或已被删除")
    return story


def remove_story_file(file_path: str) -> None:
    """删除故事配图（自动覆盖公开区与私有区）。"""
    delete_media(file_path)


def _discard_written_media(keys) -> None:
    """尽力清理一批刚落盘、但因事务失败而失去引用的媒体文件（不掩盖原始异常）。"""
    for key in keys:
        try:
            delete_media(key)
        except HTTPException:
            _main_logger.warning("事务失败后清理媒体文件失败，需人工对账：%s", key)


async def save_story_photos(photos: list[UploadFile], story_id: int, user_id: int) -> list[StoryPhoto]:
    """先完整校验全部文件，再落盘；总量限制防止多文件绕过单图上限。

    配图默认待审，落在私有区，只有作者本人与审核人员能凭签名 URL 查看。
    """
    contents: list[tuple[bytes, str]] = []
    total_bytes = 0
    for photo in photos:
        content = await photo.read(MAX_STORY_PHOTO_BYTES + 1)
        if not content:
            raise HTTPException(status_code=422, detail="请选择要上传的照片")
        if len(content) > MAX_STORY_PHOTO_BYTES:
            raise HTTPException(status_code=422, detail="故事配图不能超过 10 MB")
        total_bytes += len(content)
        if total_bytes > MAX_STORY_UPLOAD_TOTAL_BYTES:
            raise HTTPException(status_code=422, detail="本次故事图片总大小不能超过 30 MB")
        contents.append(
            normalize_image(content, allowed=AVATAR_SIGNATURES, format_hint="故事配图仅支持 PNG 或 JPG 格式")
        )
    settings.ensure_storage_directory()
    keys: list[str] = []
    stored: list[Path] = []
    try:
        for extension, content in contents:
            file_path = f"stories/{story_id}/{uuid4().hex}{extension}"
            stored.append(write_media(file_path, content, public=False))
            keys.append(file_path)
    except OSError as error:
        for destination in stored:
            destination.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=image_storage_error_detail(error)) from error
    return [StoryPhoto(story_id=story_id, user_id=user_id, file_path=key) for key in keys]


@app.get("/api/stories", response_model=list[StoryCardOut])
def list_stories(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """故事会列表：最新 200 篇，附带评论数；仅登录用户可见。"""
    stories = db.scalars(
        select(Story)
        .options(joinedload(Story.author), joinedload(Story.photos))
        .order_by(Story.created_at.desc(), Story.id.desc())
        .limit(200)
    ).unique().all()
    ids = [story.id for story in stories]
    counts = dict(
        db.execute(
            select(StoryComment.story_id, func.count())
            .where(StoryComment.story_id.in_(ids))
            .group_by(StoryComment.story_id)
        ).all()
    ) if ids else {}
    return [present_story_card(story, user, counts.get(story.id, 0)) for story in stories]


@app.get("/api/stories/{story_id}", response_model=StoryDetailOut)
def story_detail(
    story_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    story = db.scalars(
        select(Story)
        .options(
            joinedload(Story.author),
            joinedload(Story.photos),
            joinedload(Story.comments).joinedload(StoryComment.user),
        )
        .where(Story.id == story_id)
    ).unique().one_or_none()
    if story is None:
        raise HTTPException(status_code=404, detail="故事不存在或已被删除")
    return present_story_detail(story, user)


@app.post("/api/stories", response_model=StoryDetailOut, status_code=status.HTTP_201_CREATED)
async def create_story(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """发布故事（可匿名），可选配图（最多 3 张，需审核）。支持 multipart 或 JSON。"""
    enforce("story-create", str(user.id), 5, 3600)
    try:
        if request.headers.get("content-type", "").startswith("multipart/form-data"):
            form = await request.form()
            payload = StoryCreate(
                title=str(form.get("title") or ""),
                content=str(form.get("content") or ""),
                is_anonymous=str(form.get("is_anonymous") or "false").lower() in ("true", "1", "yes", "on"),
            )
            photos = [item for item in form.getlist("photos") if getattr(item, "filename", None) is not None]
        else:
            payload = StoryCreate.model_validate(await request.json())
            photos = []
    except (ValidationError, ValueError):
        raise HTTPException(status_code=422, detail="故事信息格式不正确")
    if len(photos) > MAX_STORY_PHOTOS:
        raise HTTPException(status_code=422, detail="每篇故事最多上传 3 张图片")
    story = Story(
        title=payload.title.strip(),
        content=payload.content.strip(),
        author_id=user.id,
        is_anonymous=payload.is_anonymous,
    )
    db.add(story)
    db.flush()
    records = await save_story_photos(photos, story.id, user.id) if photos else []
    db.add_all(records)
    try:
        db.commit()
    except Exception:
        # 提交失败时清掉刚落盘的配图，避免留下无人引用的孤儿文件。
        db.rollback()
        _discard_written_media(record.file_path for record in records)
        raise
    db.refresh(story)
    return present_story_detail(story, user)


@app.delete("/api/stories/{story_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_story(
    story_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """作者本人或管理员组删除故事，级联删除评论与配图并清理磁盘文件。"""
    story = get_story_or_404(db, story_id)
    if story.author_id != user.id and not can_moderate(user):
        raise HTTPException(status_code=403, detail="只能删除自己发布的故事")
    photo_paths = [photo.file_path for photo in story.photos]
    db.delete(story)
    for file_path in photo_paths:
        remove_story_file(file_path)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/api/stories/{story_id}/comments", response_model=StoryDetailOut, status_code=status.HTTP_201_CREATED)
def create_story_comment(
    story_id: int,
    payload: StoryCommentCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    enforce("story-comment", str(user.id), 30, 600)
    story = get_story_or_404(db, story_id)
    story.comments.append(StoryComment(user_id=user.id, content=payload.content.strip()))
    db.commit()
    db.refresh(story)
    return present_story_detail(story, user)


@app.delete("/api/stories/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_story_comment(
    comment_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """评论作者、故事作者或管理员组可删除评论。"""
    comment = db.get(StoryComment, comment_id)
    if comment is None:
        raise HTTPException(status_code=404, detail="评论不存在或已被删除")
    story = db.get(Story, comment.story_id)
    if story is None:
        raise HTTPException(status_code=404, detail="评论不存在或已被删除")
    allowed = can_moderate(user) or user.id in (comment.user_id, story.author_id)
    if not allowed:
        raise HTTPException(status_code=403, detail="只能删除自己的评论")
    db.delete(comment)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/admin/story-photos", response_model=list[StoryPhotoAdminOut])
def admin_story_photos(
    manager: User = Depends(get_content_moderator), db: Session = Depends(get_db)
):
    photos = db.scalars(
        select(StoryPhoto)
        .options(
            joinedload(StoryPhoto.user).joinedload(User.photos),
            joinedload(StoryPhoto.story),
        )
        .order_by(StoryPhoto.created_at.desc(), StoryPhoto.id.desc())
        .limit(500)
    ).unique().all()
    return [
        StoryPhotoAdminOut(
            id=photo.id,
            image_url=media_url(photo.file_path, public=photo.is_visible) or "",
            is_visible=photo.is_visible,
            moderated=photo.moderated_at is not None,
            story_id=photo.story_id,
            story_title=photo.story.title,
            user=present_user_public(photo.user, manager),
            created_at=photo.created_at,
        )
        for photo in photos
    ]


@app.patch("/api/admin/story-photos/{photo_id}", response_model=StoryPhotoAdminOut)
def moderate_story_photo(
    photo_id: int,
    payload: AdminPhotoUpdate,
    manager: User = Depends(get_content_moderator),
    db: Session = Depends(get_db),
):
    """审核故事配图：通过后公开展示，驳回则仅作者本人可见。"""
    photo = db.get(StoryPhoto, photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="照片不存在")
    photo.is_visible = payload.is_visible
    photo.moderated_by_id = manager.id
    photo.moderated_at = datetime.utcnow()
    commit_moderation(db, photo.file_path, public=payload.is_visible)
    db.refresh(photo)
    return StoryPhotoAdminOut(
        id=photo.id,
        image_url=media_url(photo.file_path, public=photo.is_visible) or "",
        is_visible=photo.is_visible,
        moderated=photo.moderated_at is not None,
        story_id=photo.story_id,
        story_title=photo.story.title,
        user=present_user_public(photo.user, manager),
        created_at=photo.created_at,
    )


# ---- VRChat 地图推荐 ----


def vr_map_query():
    return select(VrMap).options(
        joinedload(VrMap.uploader).joinedload(User.photos),
        joinedload(VrMap.likes),
        joinedload(VrMap.reports),
        joinedload(VrMap.photos),
    )


def vr_map_pending_report_ids():
    return select(VrMapReport.map_id).where(VrMapReport.status == ReportStatus.PENDING)


def present_vr_map_photos(vr_map: VrMap, viewer: User | None) -> list[VrMapPhotoOut]:
    """待审/被驳回的照片仅上传者本人和管理员组可见。"""
    photos: list[VrMapPhotoOut] = []
    for photo in vr_map.photos:
        can_see = photo.is_visible or (viewer is not None and (viewer.id == photo.user_id or can_review_content(viewer)))
        if can_see:
            photos.append(
                VrMapPhotoOut(
                    id=photo.id,
                    image_url=media_url(photo.file_path, public=photo.is_visible) or "",
                    is_visible=photo.is_visible,
                    moderated=photo.moderated_at is not None,
                    uploaded_by_me=viewer is not None and viewer.id == photo.user_id,
                )
            )
    return photos


def present_vr_map(vr_map: VrMap, viewer: User | None) -> VrMapOut:
    return VrMapOut(
        id=vr_map.id,
        name=vr_map.name,
        description=vr_map.description,
        category=vr_map.category,
        like_count=vr_map.like_count,
        liked_by_me=viewer is not None and any(like.user_id == viewer.id for like in vr_map.likes),
        reported_by_me=viewer is not None and any(report.reporter_id == viewer.id for report in vr_map.reports),
        has_pending_report=any(report.status == ReportStatus.PENDING for report in vr_map.reports),
        is_visible=vr_map.is_visible,
        admin_note=vr_map.admin_note,
        uploader=present_user_public(vr_map.uploader, viewer),
        photos=present_vr_map_photos(vr_map, viewer),
        created_at=vr_map.created_at,
    )


def get_vr_map_or_404(db: Session, map_id: int) -> VrMap:
    vr_map = db.get(VrMap, map_id)
    if vr_map is None:
        raise HTTPException(status_code=404, detail="地图不存在或已被删除")
    return vr_map


def remove_vr_map_file(file_path: str) -> None:
    """删除地图实拍（自动覆盖公开区与私有区）。"""
    delete_media(file_path)


async def save_vr_map_photos(
    photos: list[UploadFile], map_id: int, user_id: int,
) -> list[VrMapPhoto]:
    """先完整校验全部文件，再落盘；总量限制防止多文件绕过单图上限。

    实拍照片默认待审，落在私有区，需审核通过后才会进入公开区。
    """
    contents: list[tuple[bytes, str]] = []
    total_bytes = 0
    for photo in photos:
        content = await photo.read(MAX_VR_MAP_PHOTO_BYTES + 1)
        if not content:
            raise HTTPException(status_code=422, detail="请选择要上传的照片")
        if len(content) > MAX_VR_MAP_PHOTO_BYTES:
            raise HTTPException(status_code=422, detail="地图照片不能超过 10 MB")
        total_bytes += len(content)
        if total_bytes > MAX_VR_MAP_UPLOAD_TOTAL_BYTES:
            raise HTTPException(status_code=422, detail="本次地图图片总大小不能超过 50 MB")
        contents.append(
            normalize_image(content, allowed=AVATAR_SIGNATURES, format_hint="地图照片仅支持 PNG 或 JPG 格式")
        )

    settings.ensure_storage_directory()
    keys: list[str] = []
    stored: list[Path] = []
    try:
        for extension, content in contents:
            file_path = f"vrmaps/{map_id}/{uuid4().hex}{extension}"
            stored.append(write_media(file_path, content, public=False))
            keys.append(file_path)
    except OSError as error:
        for destination in stored:
            destination.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=image_storage_error_detail(error)) from error

    return [VrMapPhoto(map_id=map_id, user_id=user_id, file_path=key) for key in keys]


@app.get("/api/vr-maps", response_model=list[VrMapOut])
def list_vr_maps(
    viewer: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """地图推荐列表：按点赞数排序；被举报待审/被屏蔽的地图对公众隐藏。"""
    query = vr_map_query()
    if viewer is None:
        query = query.where(VrMap.is_visible.is_(True), ~VrMap.id.in_(vr_map_pending_report_ids()))
    elif not can_review_content(viewer):
        publicly_ok = VrMap.is_visible.is_(True) & ~VrMap.id.in_(vr_map_pending_report_ids())
        query = query.where(or_(VrMap.uploader_id == viewer.id, publicly_ok))
    maps = db.scalars(
        query.order_by(VrMap.like_count.desc(), VrMap.created_at.desc(), VrMap.id.desc()).limit(200)
    ).unique().all()
    return [present_vr_map(vr_map, viewer) for vr_map in maps]


@app.post("/api/vr-maps", response_model=VrMapOut, status_code=status.HTTP_201_CREATED)
async def create_vr_map(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    enforce("upload", str(user.id), 30, 3600)
    try:
        if request.headers.get("content-type", "").startswith("multipart/form-data"):
            form = await request.form()
            payload = VrMapCreate(
                name=str(form.get("name") or ""),
                description=str(form.get("description") or ""),
                category=str(form.get("category") or ""),
            )
            photos = [item for item in form.getlist("photos") if getattr(item, "filename", None) is not None]
        else:
            payload = VrMapCreate.model_validate(await request.json())
            photos = []
    except (ValidationError, ValueError):
        raise HTTPException(status_code=422, detail="地图信息格式不正确")
    if payload.category not in MAP_CATEGORIES:
        raise HTTPException(status_code=422, detail="地图类型不正确")
    if len(photos) > 3:
        raise HTTPException(status_code=422, detail="创建推荐时最多上传 3 张图片")
    vr_map = VrMap(
        name=payload.name.strip(),
        description=payload.description.strip(),
        category=payload.category,
        uploader_id=user.id,
    )
    db.add(vr_map)
    db.flush()
    records = await save_vr_map_photos(photos, vr_map.id, user.id) if photos else []
    db.add_all(records)
    try:
        db.commit()
    except Exception:
        # 提交失败时清掉刚落盘的实拍，避免留下无人引用的孤儿文件。
        db.rollback()
        _discard_written_media(record.file_path for record in records)
        raise
    db.refresh(vr_map)
    return present_vr_map(vr_map, viewer=user)


@app.get("/api/vr-maps/{map_id}", response_model=VrMapOut)
def vr_map_detail(
    map_id: int,
    viewer: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    vr_map = get_vr_map_or_404(db, map_id)
    publicly_ok = vr_map.is_visible and not any(
        report.status == ReportStatus.PENDING for report in vr_map.reports
    )
    if not publicly_ok and not (viewer and (viewer.id == vr_map.uploader_id or can_review_content(viewer))):
        raise HTTPException(status_code=404, detail="地图不存在或已被删除")
    return present_vr_map(vr_map, viewer)


@app.delete("/api/vr-maps/{map_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_vr_map(
    map_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除本人发布的地图推荐，并清理该推荐下的全部图片。"""
    vr_map = get_vr_map_or_404(db, map_id)
    if vr_map.uploader_id != user.id:
        raise HTTPException(status_code=403, detail="只能删除自己发布的地图推荐")
    photo_paths = [photo.file_path for photo in vr_map.photos]
    db.delete(vr_map)
    for file_path in photo_paths:
        remove_vr_map_file(file_path)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/api/vr-maps/{map_id}/like", response_model=VrMapLikeState)
def toggle_vr_map_like(
    map_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """点赞/取消点赞：一人对同一张地图只能有一个有效点赞。"""
    vr_map = get_vr_map_or_404(db, map_id)
    like = db.scalar(select(VrMapLike).where(VrMapLike.map_id == map_id, VrMapLike.user_id == user.id))
    if like is not None:
        db.delete(like)
        vr_map.like_count = max(0, vr_map.like_count - 1)
        liked = False
    else:
        db.add(VrMapLike(map_id=map_id, user_id=user.id))
        vr_map.like_count += 1
        liked = True
    db.commit()
    return VrMapLikeState(like_count=vr_map.like_count, liked=liked)


@app.post("/api/vr-maps/{map_id}/report", response_model=VrMapOut, status_code=status.HTTP_201_CREATED)
def report_vr_map(
    map_id: int,
    payload: VrMapReportCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """举报地图：每人限一次；待处理举报会使地图退出公开列表。"""
    vr_map = get_vr_map_or_404(db, map_id)
    if vr_map.uploader_id == user.id:
        raise HTTPException(status_code=422, detail="不能举报自己推荐的地图")
    existing = db.scalar(
        select(VrMapReport).where(VrMapReport.map_id == map_id, VrMapReport.reporter_id == user.id)
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="你已举报过这张地图")
    db.add(VrMapReport(map_id=map_id, reporter_id=user.id, reason=payload.reason.strip()))
    db.commit()
    db.refresh(vr_map)
    return present_vr_map(vr_map, viewer=user)


@app.post("/api/vr-maps/{map_id}/photos", response_model=VrMapOut, status_code=status.HTTP_201_CREATED)
async def upload_vr_map_photo(
    map_id: int,
    photos: list[UploadFile] = File(default=[]),
    photo: UploadFile | None = File(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """上传地图实拍照片：单次最多 5 张，每位用户对每张地图最多 5 张；需审核后公开。"""
    enforce("upload", str(user.id), 30, 3600)
    vr_map = get_vr_map_or_404(db, map_id)
    if photo is not None:
        photos = [*photos, photo]
    if not photos:
        raise HTTPException(status_code=422, detail="请选择要上传的照片")
    if len(photos) > MAX_VR_MAP_PHOTOS:
        raise HTTPException(status_code=422, detail="单次最多上传 5 张图片")
    current_count = db.scalar(
        select(func.count()).select_from(VrMapPhoto).where(
            VrMapPhoto.map_id == map_id,
            VrMapPhoto.user_id == user.id,
        )
    ) or 0
    if current_count + len(photos) > MAX_VR_MAP_PHOTOS:
        raise HTTPException(status_code=422, detail="你在每张地图最多上传 5 张图片")
    records = await save_vr_map_photos(photos, map_id, user.id)
    db.add_all(records)
    try:
        db.commit()
    except Exception:
        # 提交失败时清掉刚落盘的实拍，避免留下无人引用的孤儿文件。
        db.rollback()
        _discard_written_media(record.file_path for record in records)
        raise
    db.refresh(vr_map)
    return present_vr_map(vr_map, viewer=user)


@app.patch("/api/vr-maps/{map_id}/photos/{photo_id}", response_model=VrMapOut)
async def replace_vr_map_photo(
    map_id: int,
    photo_id: int,
    photo: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """替换本人上传的地图图片；新图片必须重新通过审核。"""
    enforce("upload", str(user.id), 30, 3600)
    vr_map = get_vr_map_or_404(db, map_id)
    record = db.get(VrMapPhoto, photo_id)
    if record is None or record.map_id != map_id:
        raise HTTPException(status_code=404, detail="地图图片不存在或已被删除")
    if record.user_id != user.id:
        raise HTTPException(status_code=403, detail="只能更新自己上传的地图图片")

    replacement = (await save_vr_map_photos([photo], map_id, user.id))[0]
    old_file_path = record.file_path
    record.file_path = replacement.file_path
    record.is_visible = False
    record.moderated_by_id = None
    record.moderated_at = None
    try:
        remove_vr_map_file(old_file_path)
        db.commit()
    except Exception:
        db.rollback()
        remove_vr_map_file(replacement.file_path)
        raise
    db.refresh(vr_map)
    return present_vr_map(vr_map, viewer=user)


@app.delete("/api/vr-maps/{map_id}/photos/{photo_id}", response_model=VrMapOut)
def delete_vr_map_photo(
    map_id: int,
    photo_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除本人上传的地图图片。"""
    vr_map = get_vr_map_or_404(db, map_id)
    record = db.get(VrMapPhoto, photo_id)
    if record is None or record.map_id != map_id:
        raise HTTPException(status_code=404, detail="地图图片不存在或已被删除")
    if record.user_id != user.id:
        raise HTTPException(status_code=403, detail="只能删除自己上传的地图图片")
    file_path = record.file_path
    db.delete(record)
    remove_vr_map_file(file_path)
    db.commit()
    db.refresh(vr_map)
    return present_vr_map(vr_map, viewer=user)


@app.get("/api/admin/vr-map-reports", response_model=list[VrMapReportOut])
def admin_vr_map_reports(
    manager: User = Depends(get_content_moderator), db: Session = Depends(get_db)
):
    reports = db.scalars(
        select(VrMapReport)
        .options(joinedload(VrMapReport.map), joinedload(VrMapReport.reporter).joinedload(User.photos))
        .order_by(VrMapReport.created_at.desc(), VrMapReport.id.desc())
        .limit(500)
    ).unique().all()
    return [
        VrMapReportOut(
            id=report.id,
            map_id=report.map_id,
            map_name=report.map.name,
            reporter=present_user_public(report.reporter, manager),
            reason=report.reason,
            status=report.status,
            created_at=report.created_at,
            handled_at=report.handled_at,
        )
        for report in reports
    ]


@app.post("/api/admin/vr-map-reports/{report_id}/resolve", response_model=VrMapReportOut)
def resolve_vr_map_report(
    report_id: int,
    payload: VrMapReportResolveRequest,
    manager: User = Depends(get_content_moderator),
    db: Session = Depends(get_db),
):
    """处置地图举报：close 放开（举报不成立）/ hide 屏蔽 / restore 重新放开已屏蔽地图。"""
    report = db.get(VrMapReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="举报不存在")
    vr_map = db.get(VrMap, report.map_id)
    if payload.action == "close":
        report.status = ReportStatus.HANDLED
    elif payload.action == "hide":
        if not (payload.admin_note or "").strip():
            raise HTTPException(status_code=422, detail="屏蔽地图时必须填写理由")
        report.status = ReportStatus.HANDLED
        vr_map.is_visible = False
        vr_map.admin_note = payload.admin_note.strip()
    else:
        vr_map.is_visible = True
        vr_map.admin_note = None
        report.status = ReportStatus.HANDLED
    report.handled_by_id = manager.id
    report.handled_at = datetime.utcnow()
    db.commit()
    db.refresh(report)
    return VrMapReportOut(
        id=report.id,
        map_id=report.map_id,
        map_name=report.map.name,
        reporter=present_user_public(report.reporter, manager),
        reason=report.reason,
        status=report.status,
        created_at=report.created_at,
        handled_at=report.handled_at,
    )


@app.get("/api/admin/vr-map-photos", response_model=list[VrMapPhotoAdminOut])
def admin_vr_map_photos(
    manager: User = Depends(get_content_moderator), db: Session = Depends(get_db)
):
    photos = db.scalars(
        select(VrMapPhoto)
        .options(
            joinedload(VrMapPhoto.user).joinedload(User.photos),
            joinedload(VrMapPhoto.map),
        )
        .order_by(VrMapPhoto.created_at.desc(), VrMapPhoto.id.desc())
        .limit(500)
    ).unique().all()
    return [
        VrMapPhotoAdminOut(
            id=photo.id,
            image_url=media_url(photo.file_path, public=photo.is_visible) or "",
            is_visible=photo.is_visible,
            moderated=photo.moderated_at is not None,
            map_id=photo.map_id,
            map_name=photo.map.name,
            user=present_user_public(photo.user, manager),
            created_at=photo.created_at,
        )
        for photo in photos
    ]


@app.patch("/api/admin/vr-map-photos/{photo_id}", response_model=VrMapPhotoAdminOut)
def moderate_vr_map_photo(
    photo_id: int,
    payload: AdminPhotoUpdate,
    manager: User = Depends(get_content_moderator),
    db: Session = Depends(get_db),
):
    """审核地图照片：通过后公开展示，驳回则仅上传者本人可见。"""
    photo = db.get(VrMapPhoto, photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="照片不存在")
    photo.is_visible = payload.is_visible
    photo.moderated_by_id = manager.id
    photo.moderated_at = datetime.utcnow()
    commit_moderation(db, photo.file_path, public=payload.is_visible)
    db.refresh(photo)
    return VrMapPhotoAdminOut(
        id=photo.id,
        image_url=media_url(photo.file_path, public=photo.is_visible) or "",
        is_visible=photo.is_visible,
        moderated=photo.moderated_at is not None,
        map_id=photo.map_id,
        map_name=photo.map.name,
        user=present_user_public(photo.user, manager),
        created_at=photo.created_at,
    )


def queue_task_notification(
    task: Task,
    background: BackgroundTasks,
    title: str,
    lines: list[str],
    request: Request | None = None,
    *,
    include_publisher: bool = True,
    exclude: User | None = None,
) -> None:
    """把委托相关的事件通知排进后台任务。

    只有「已验证邮箱 + 没关通知开关」的账号会收到；``exclude`` 用来跳过动作发起人，
    避免用户收到自己刚做的事件的邮件。收件地址在请求内取好
    （ORM 对象随后会脱离会话），因此后台任务只拿到字符串。
    """
    # 事件通知是 best-effort；本地未配置来源时省略链接，不能让已提交操作报失败。
    link = f"{base_url(request)}/mine" if settings.site_base_url else None
    recipients: list[User] = [task.publisher] if include_publisher else []
    recipients.extend(
        member.user for member in task.members if member.response_status == TaskMemberResponse.ACCEPTED
    )
    seen: set[int] = set()
    for person in recipients:
        if person.id in seen or (exclude is not None and person.id == exclude.id):
            continue
        seen.add(person.id)
        address = notification_target(person)
        if address:
            background.add_task(notify_address, address, title, lines, link)


def queue_user_notification(
    user: User | None,
    background: BackgroundTasks,
    title: str,
    lines: list[str],
) -> None:
    """给单个账号排一条事件通知（如申请审核结果、反馈回复）。"""
    if user is None:
        return
    address = notification_target(user)
    if address:
        background.add_task(notify_address, address, title, lines)


@app.get("/api/tasks", response_model=list[TaskOut])
def list_tasks(
    search: str = Query(default="", max_length=80),
    category: str = Query(default=""),
    task_status: Annotated[TaskStatusFilter, Query(alias="status")] = None,
    pay_type: str = Query(default=""),
    viewer: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    expire_due_tasks(db)
    reported_ids = select(TaskReport.task_id).where(TaskReport.status == ReportStatus.PENDING)
    query = task_query().where(Task.is_visible.is_(True), ~Task.id.in_(reported_ids))
    if search:
        query = query.where(or_(Task.title.contains(search), Task.description.contains(search)))
    if category:
        query = query.where(Task.category == category)
    # 普通用户只能浏览招募中的委托；超级管理员/管理员可查看全部状态。
    if task_status and is_task_manager(viewer):
        query = query.where(Task.status == task_status)
    elif not is_task_manager(viewer):
        query = query.where(Task.status == TaskStatus.PUBLISHED)
    if pay_type in ("paid", "free"):
        query = query.where(Task.pay_type == pay_type)
    tasks = db.scalars(query.order_by(Task.created_at.desc()).limit(200)).unique().all()
    return [present_task(task, viewer) for task in tasks]


@app.get("/api/tasks/stats", response_model=TaskStats)
def task_stats(db: Session = Depends(get_db)):
    """大厅顶部统计：全站数量（正在招募/正在处理/顺利完成），不受筛选影响。

    仅返回数量不返回内容；被后台屏蔽的委托不计入。路由需注册在
    /api/tasks/{task_id} 之前，避免 "stats" 被当作委托 ID 解析。
    """
    expire_due_tasks(db)
    visible = Task.is_visible.is_(True)
    return TaskStats(
        published=db.scalar(
            select(func.count()).select_from(Task).where(visible, Task.status == TaskStatus.PUBLISHED)
        ) or 0,
        processing=db.scalar(
            select(func.count()).select_from(Task).where(visible, Task.status.in_([TaskStatus.ACCEPTED, TaskStatus.AWAITING]))
        ) or 0,
        completed=db.scalar(
            select(func.count()).select_from(Task).where(visible, Task.status == TaskStatus.COMPLETED)
        ) or 0,
    )


@app.get("/api/tasks/mine", response_model=list[TaskOut])
def my_tasks(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    expire_due_tasks(db)
    participation = or_(
        Task.publisher_id == user.id,
        Task.id.in_(select(TaskMember.task_id).where(TaskMember.user_id == user.id)),
    )
    visibility = or_(
        Task.is_visible.is_(True),
        Task.publisher_id == user.id,
        user.is_admin,
        user.role == UserRole.STAFF,
    )
    tasks = db.scalars(task_query().where(participation, visibility).order_by(Task.updated_at.desc())).unique().all()
    return [present_task(task, user) for task in tasks]


@app.get("/api/tasks/{task_id}", response_model=TaskOut)
def task_detail(task_id: int, viewer: User | None = Depends(get_optional_user), db: Session = Depends(get_db)):
    expire_due_tasks(db)
    task = get_task_or_404(db, task_id)
    if not task.is_visible and not can_view_hidden_task(task, viewer):
        raise HTTPException(status_code=404, detail="委托不存在")
    reported = db.scalar(
        select(TaskReport.id).where(
            TaskReport.task_id == task_id,
            TaskReport.status == ReportStatus.PENDING,
        ).limit(1)
    ) is not None
    # 被举报的委托仅管理员/超级管理员/委托双方可见；处理中或已完成的委托仅委托双方可见。
    if reported or task.status != TaskStatus.PUBLISHED:
        if not is_task_manager(viewer) and not is_task_participant(task, viewer):
            raise HTTPException(status_code=404, detail="委托不存在")
    return present_task(task, viewer)


@app.post("/api/tasks", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    enforce("task-create", str(user.id), 20, 600)
    if not user.qq:
        raise HTTPException(status_code=422, detail="发布委托需要先填写联系方式（QQ），请在个人设置中添加后再发布")
    now = datetime.utcnow()
    designated_user_ids = list(dict.fromkeys(payload.designated_user_ids))
    if user.id in designated_user_ids:
        raise HTTPException(status_code=422, detail="不能指定自己接取委托")
    designated_users: list[User] = []
    if designated_user_ids:
        designated_users = db.scalars(
            select(User).where(
                User.id.in_(designated_user_ids),
                User.is_active.is_(True),
                User.is_admin.is_(False),
                User.role.in_([UserRole.VOLUNTEER, UserRole.STAFF]),
            )
        ).all()
        if len(designated_users) != len(designated_user_ids):
            raise HTTPException(status_code=422, detail="只能指定当前可用的管理员或志愿者")
    task = Task(
        title=payload.title.strip(),
        description=payload.description.strip(),
        category=payload.category,
        pay_type=payload.pay_type,
        reward=payload.reward.strip() if payload.reward else None,
        expires_at=now + timedelta(days=payload.expires_in_days),
        publisher_id=user.id,
        is_anonymous=payload.is_anonymous,
        required_takers=len(designated_user_ids) if designated_user_ids else payload.required_takers,
        # 指定委托无须密码，响应权限由指定名单保证。
        accept_password_hash=None if designated_user_ids else (hash_password(payload.accept_password) if payload.accept_password else None),
        is_designated=bool(designated_user_ids),
    )
    db.add(task)
    db.flush()
    for designated_user in designated_users:
        db.add(
            TaskMember(
                task_id=task.id,
                user_id=designated_user.id,
                response_status=TaskMemberResponse.PENDING,
            )
        )
    db.commit()
    return present_task(get_task_or_404(db, task.id), user)


@app.post("/api/tasks/{task_id}/report", response_model=TaskReportOut, status_code=status.HTTP_201_CREATED)
def report_task(
    task_id: int,
    payload: ReportCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """举报委托：被举报的委托不进入大厅，仅由管理员/超级管理员处理。"""
    task = get_task_or_404(db, task_id)
    if task.publisher_id == user.id:
        raise HTTPException(status_code=422, detail="不能举报自己发布的委托")
    existing = db.scalar(
        select(TaskReport).where(
            TaskReport.task_id == task_id,
            TaskReport.reporter_id == user.id,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="你已经举报过该委托")
    daily_limit = get_setting_int(db, "report_daily_limit", 2)
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_count = db.scalar(
        select(func.count()).select_from(TaskReport).where(
            TaskReport.reporter_id == user.id,
            TaskReport.created_at >= today_start,
        )
    ) or 0
    if today_count >= daily_limit:
        raise HTTPException(status_code=429, detail=f"今日举报次数已达上限（{daily_limit} 次）")
    report = TaskReport(task_id=task_id, reporter_id=user.id, reason=payload.reason.strip())
    db.add(report)
    db.commit()
    return present_report(db.get(TaskReport, report.id))


@app.get("/api/admin/reports", response_model=list[TaskReportOut])
def admin_reports(_: User = Depends(get_content_moderator), db: Session = Depends(get_db)):
    reports = db.scalars(
        select(TaskReport)
        .options(joinedload(TaskReport.task), joinedload(TaskReport.reporter))
        .order_by(TaskReport.created_at.desc())
        .limit(500)
    ).unique().all()
    return [present_report(report) for report in reports]


@app.post("/api/admin/reports/{report_id}/resolve", response_model=TaskReportOut)
def resolve_report(
    report_id: int,
    payload: ReportResolveRequest,
    manager: User = Depends(get_content_moderator),
    db: Session = Depends(get_db),
):
    """处理被举报的委托：close 关闭举报 / hide 屏蔽委托 / restore 重新放开。"""
    report = db.get(TaskReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="举报不存在")
    task = report.task
    if payload.action == "hide":
        note = payload.admin_note.strip() if payload.admin_note else None
        if not note:
            raise HTTPException(status_code=422, detail="屏蔽委托时必须填写理由")
        task.is_visible = False
        task.admin_note = note
    elif payload.action == "restore":
        task.is_visible = True
        task.admin_note = None
    now = datetime.utcnow()
    pending = db.scalars(
        select(TaskReport).where(
            TaskReport.task_id == task.id,
            TaskReport.status == ReportStatus.PENDING,
        )
    ).all()
    for item in pending:
        item.status = ReportStatus.HANDLED
        item.handled_by_id = manager.id
        item.handled_at = now
    task.updated_at = now
    db.commit()
    db.refresh(report)
    return present_report(report)


@app.get("/api/admin/settings/report-limit", response_model=ReportLimitOut)
def get_report_limit(_: User = Depends(get_role_manager), db: Session = Depends(get_db)):
    return ReportLimitOut(daily_limit=get_setting_int(db, "report_daily_limit", 2))


@app.patch("/api/admin/settings/report-limit", response_model=ReportLimitOut)
def set_report_limit(
    payload: ReportLimitUpdate,
    _: User = Depends(get_role_manager),
    db: Session = Depends(get_db),
):
    set_setting(db, "report_daily_limit", str(payload.daily_limit))
    db.commit()
    return ReportLimitOut(daily_limit=payload.daily_limit)


@app.post("/api/tasks/{task_id}/accept", response_model=TaskOut)
def accept_task(
    task_id: int,
    payload: AcceptRequest,
    request: Request,
    background: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """加入委托（有密码时需凭正确密码，无密码时所有非管理员用户可加入）。"""
    expire_due_tasks(db)
    task = get_task_or_404(db, task_id)
    if not task.is_visible:
        raise HTTPException(status_code=403, detail="该委托已被管理员隐藏")
    if task.publisher_id == user.id:
        raise HTTPException(status_code=400, detail="不能接取自己发布的委托")
    if user.is_admin:
        raise HTTPException(status_code=403, detail="管理员不接取委托")
    if task.status != TaskStatus.PUBLISHED:
        raise HTTPException(status_code=409, detail="委托已开始或不可接取")
    existing_member = member_of(db, task_id, user.id)
    if task.is_designated:
        if existing_member is None:
            raise HTTPException(status_code=403, detail="该委托已指定其他管理员或志愿者")
        if existing_member.response_status != TaskMemberResponse.PENDING:
            raise HTTPException(status_code=409, detail="你已响应此指定委托")
        # 在支持行锁的数据库上串行化同一用户的接单操作，避免并发突破个人上限。
        db.scalar(select(User).where(User.id == user.id).with_for_update())
        if active_task_count(db, user.id) >= user.max_concurrent_tasks:
            raise HTTPException(
                status_code=409,
                detail=f"你同时接取的委托已达上限（{user.max_concurrent_tasks} 个）",
            )
        existing_member.response_status = TaskMemberResponse.ACCEPTED
        task.updated_at = datetime.utcnow()
        # 指定单人接受后立即开始；多人须等所有指定人员均响应后开始。
        if all(member.response_status != TaskMemberResponse.PENDING for member in task.members):
            if any(member.response_status == TaskMemberResponse.ACCEPTED for member in task.members):
                task.status = TaskStatus.ACCEPTED
                task.started_at = task.started_at or datetime.utcnow()
            else:
                task.status = TaskStatus.CANCELLED
                task.cancelled_at = datetime.utcnow()
        db.commit()
        settled = get_task_or_404(db, task_id)
        queue_task_notification(
            settled,
            background,
            "指定委托已响应",
            [f"《{settled.title}》的指定接单人已响应，当前状态：{settled.status.value}。"],
            request,
            include_publisher=True,
            exclude=user,
        )
        return present_task(settled, user)
    if existing_member is not None:
        raise HTTPException(status_code=409, detail="你已经接取过该委托")
    if task.required_takers is not None:
        joined = db.scalar(select(func.count()).select_from(TaskMember).where(TaskMember.task_id == task.id)) or 0
        if joined >= task.required_takers:
            raise HTTPException(status_code=409, detail="需要的人数已满，委托即将开始")
    if task.requires_password:
        # 限流尝试次数，防止暴力枚举 4 位起的接取密码。
        enforce("accept-password", str(user.id), 10, 300)
        if not payload.password or not verify_password(payload.password, task.accept_password_hash):
            raise HTTPException(status_code=403, detail="接取密码不正确，请联系委托人确认")
    # 在支持行锁的数据库上串行化同一用户的接单操作，避免并发突破个人上限。
    db.scalar(select(User).where(User.id == user.id).with_for_update())
    if active_task_count(db, user.id) >= user.max_concurrent_tasks:
        raise HTTPException(
            status_code=409,
            detail=f"你同时接取的委托已达上限（{user.max_concurrent_tasks} 个）",
        )
    db.add(TaskMember(task_id=task.id, user_id=user.id))
    db.commit()
    task = get_task_or_404(db, task_id)
    start_if_ready(db, task)
    db.commit()
    accepted = get_task_or_404(db, task_id)
    queue_task_notification(
        accepted,
        background,
        "有人接取了你的委托",
        [f"《{accepted.title}》已被接取，当前状态：{accepted.status.value}。"],
        request,
        include_publisher=True,
        exclude=user,
    )
    return present_task(accepted, user)


@app.post("/api/tasks/{task_id}/start", response_model=TaskOut)
def start_task(
    task_id: int,
    request: Request,
    background: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """委托人手动开始委托任务（即使人数不足也可以开始）。"""
    expire_due_tasks(db)
    task = get_task_or_404(db, task_id)
    if task.publisher_id != user.id:
        raise HTTPException(status_code=403, detail="只有委托人（发布人）可以开始委托")
    if task.status != TaskStatus.PUBLISHED:
        raise HTTPException(status_code=409, detail="委托已开始或不可开始")
    if task.is_designated:
        raise HTTPException(status_code=409, detail="指定委托须等待所有被指定人员响应")
    if not task.members:
        raise HTTPException(status_code=409, detail="至少需要一名接单人才能开始，请先等待接单人加入")
    task.status = TaskStatus.ACCEPTED
    task.started_at = datetime.utcnow()
    task.updated_at = datetime.utcnow()
    db.commit()
    started = get_task_or_404(db, task_id)
    queue_task_notification(
        started,
        background,
        "委托已开始",
        [f"《{started.title}》已开始，请按约定推进。"],
        request,
        include_publisher=False,
        exclude=user,
    )
    return present_task(started, user)


@app.post("/api/tasks/{task_id}/leave", response_model=TaskOut)
def leave_task(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """接单人在委托开始前退出接取。"""
    expire_due_tasks(db)
    task = get_task_or_404(db, task_id)
    membership = member_of(db, task_id, user.id)
    if membership is None:
        raise HTTPException(status_code=403, detail="你不是该委托的接单人")
    if task.status != TaskStatus.PUBLISHED:
        raise HTTPException(status_code=409, detail="委托已经开始，不能退出")
    if task.is_designated:
        if membership.response_status != TaskMemberResponse.PENDING:
            raise HTTPException(status_code=409, detail="已接受指定委托，不能拒绝")
        membership.response_status = TaskMemberResponse.DECLINED
        task.updated_at = datetime.utcnow()
        if all(member.response_status != TaskMemberResponse.PENDING for member in task.members):
            if any(member.response_status == TaskMemberResponse.ACCEPTED for member in task.members):
                task.status = TaskStatus.ACCEPTED
                task.started_at = datetime.utcnow()
            else:
                task.status = TaskStatus.CANCELLED
                task.cancelled_at = datetime.utcnow()
        db.commit()
        return present_task(get_task_or_404(db, task_id), user)
    db.delete(membership)
    db.commit()
    return present_task(get_task_or_404(db, task_id), user)


@app.post("/api/tasks/{task_id}/confirm", response_model=TaskOut)
def confirm_task(
    task_id: int,
    request: Request,
    background: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """完成确认：委托人（发布人）与每一位接单人都需要确认；全部确认后委托才算完成。"""
    expire_due_tasks(db)
    task = get_task_or_404(db, task_id)
    if task.status not in (TaskStatus.ACCEPTED, TaskStatus.AWAITING):
        raise HTTPException(status_code=409, detail="当前状态不能确认完成")
    now = datetime.utcnow()
    if task.publisher_id == user.id:
        if task.publisher_confirmed_at is not None:
            raise HTTPException(status_code=409, detail="你已确认完成")
        task.publisher_confirmed_at = now
    else:
        membership = accepted_member_of(db, task_id, user.id)
        if membership is None:
            raise HTTPException(status_code=403, detail="只有委托人和接单人可确认完成")
        if membership.confirmed_at is not None:
            raise HTTPException(status_code=409, detail="你已确认完成")
        membership.confirmed_at = now
    task = get_task_or_404(db, task_id)
    if task.all_confirmed:
        task.status = TaskStatus.COMPLETED
        task.completed_at = now
    elif any(member.confirmed_at is not None for member in task.members) or task.publisher_confirmed_at is not None:
        task.status = TaskStatus.AWAITING
    else:
        task.status = TaskStatus.ACCEPTED
    task.updated_at = now
    db.commit()
    confirmed = get_task_or_404(db, task_id)
    if confirmed.status == TaskStatus.COMPLETED:
        queue_task_notification(
            confirmed,
            background,
            "委托已完成",
            [f"《{confirmed.title}》已由委托人与全体接单人确认完成。"],
            request,
            exclude=user,
        )
    return present_task(confirmed, user)


@app.patch("/api/tasks/{task_id}/password", response_model=TaskOut)
def update_task_password(
    task_id: int,
    payload: PasswordUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """委托人重设接取密码：仅在委托尚未开始时可用。"""
    task = get_task_or_404(db, task_id)
    if task.publisher_id != user.id:
        raise HTTPException(status_code=403, detail="只有委托人可以重设接取密码")
    if task.status != TaskStatus.PUBLISHED:
        raise HTTPException(status_code=409, detail="委托开始后不能重设密码")
    task.accept_password_hash = hash_password(payload.password)
    task.updated_at = datetime.utcnow()
    db.commit()
    return present_task(get_task_or_404(db, task_id), user)


@app.post("/api/tasks/{task_id}/cancel", response_model=TaskOut)
def request_cancel_task(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """发起取消委托：委托人或任一接单人都可在未完成阶段发起，进入取消确认(cancelling)。

    委托仍无人接取（published 且无成员）时，委托人可直接取消；否则需委托人+全体接单人确认。
    """
    expire_due_tasks(db)
    task = get_task_or_404(db, task_id)
    if task.publisher_id != user.id and accepted_member_of(db, task_id, user.id) is None:
        raise HTTPException(status_code=403, detail="只有委托人或接单人能发起取消")
    if task.status == TaskStatus.CANCELLING:
        raise HTTPException(status_code=409, detail="已发起取消，等待双方确认")
    if task.status not in (TaskStatus.PUBLISHED, TaskStatus.ACCEPTED, TaskStatus.AWAITING):
        raise HTTPException(status_code=409, detail="当前状态不能取消委托")
    now = datetime.utcnow()
    # 尚未有人接取：委托人直接取消
    if task.publisher_id == user.id and not task.members:
        task.status = TaskStatus.CANCELLED
        task.cancelled_at = now
        task.updated_at = now
        db.commit()
        return present_task(get_task_or_404(db, task_id), user)
    # 进入取消确认：记录发起人与要恢复的状态，发起人视为已同意
    original_status = task.status
    task.status = TaskStatus.CANCELLING
    task.cancel_requested_by = user.id
    task.cancel_requested_at = now
    task.cancel_resume_status = original_status
    if task.publisher_id == user.id:
        task.publisher_cancel_confirmed_at = now
    else:
        membership = accepted_member_of(db, task_id, user.id)
        if membership is not None:
            membership.cancel_confirmed_at = now
    task.updated_at = now
    db.commit()
    return present_task(get_task_or_404(db, task_id), user)


@app.post("/api/tasks/{task_id}/confirm-cancel", response_model=TaskOut)
def confirm_cancel_task(
    task_id: int,
    request: Request,
    background: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """同意取消：委托人或接单人各自确认，全部同意后委托才取消。"""
    expire_due_tasks(db)
    task = get_task_or_404(db, task_id)
    if task.status != TaskStatus.CANCELLING:
        raise HTTPException(status_code=409, detail="当前没有待确认的取消请求")
    if task.publisher_id != user.id and accepted_member_of(db, task_id, user.id) is None:
        raise HTTPException(status_code=403, detail="只有委托人或接单人可确认取消")
    now = datetime.utcnow()
    if task.publisher_id == user.id:
        if task.publisher_cancel_confirmed_at is not None:
            raise HTTPException(status_code=409, detail="你已同意取消")
        task.publisher_cancel_confirmed_at = now
    else:
        membership = accepted_member_of(db, task_id, user.id)
        if membership is None or membership.cancel_confirmed_at is not None:
            raise HTTPException(status_code=409, detail="你已同意取消")
        membership.cancel_confirmed_at = now
    task = get_task_or_404(db, task_id)
    if task.all_agree_to_cancel:
        task.status = TaskStatus.CANCELLED
        task.cancelled_at = now
    task.updated_at = now
    db.commit()
    settled = get_task_or_404(db, task_id)
    if settled.status == TaskStatus.CANCELLED:
        queue_task_notification(
            settled,
            background,
            "委托已取消",
            [f"《{settled.title}》经委托人与全体接单人同意后已取消。"],
            request,
            exclude=user,
        )
    return present_task(settled, user)


@app.post("/api/tasks/{task_id}/cancel-continue", response_model=TaskOut)
def reject_cancel_task(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """不同意取消 / 撤回取消请求：委托继续，恢复到发起取消前的状态。"""
    expire_due_tasks(db)
    task = get_task_or_404(db, task_id)
    if task.status != TaskStatus.CANCELLING:
        raise HTTPException(status_code=409, detail="当前没有可撤回的取消请求")
    if task.publisher_id != user.id and accepted_member_of(db, task_id, user.id) is None:
        raise HTTPException(status_code=403, detail="只有委托人或接单人可操作取消请求")
    now = datetime.utcnow()
    resume = task.cancel_resume_status or TaskStatus.ACCEPTED
    task.status = resume
    task.cancel_requested_by = None
    task.cancel_requested_at = None
    task.cancel_resume_status = None
    task.publisher_cancel_confirmed_at = None
    for member in task.members:
        member.cancel_confirmed_at = None
    task.updated_at = now
    db.commit()
    return present_task(get_task_or_404(db, task_id), user)


@app.get("/api/announcements", response_model=list[AnnouncementOut])
def public_announcements(
    kind: AnnouncementKind | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """返回当前展示期内的公告，供游客和登录用户查看。"""
    now = datetime.utcnow()
    query = (
        select(Announcement)
        .where(
            Announcement.is_published.is_(True),
            or_(Announcement.starts_at.is_(None), Announcement.starts_at <= now),
            or_(Announcement.ends_at.is_(None), Announcement.ends_at > now),
        )
        .options(joinedload(Announcement.author))
        .order_by(Announcement.is_pinned.desc(), Announcement.created_at.desc())
    )
    if kind is not None:
        query = query.where(Announcement.kind == kind)
    return [present_announcement(item) for item in db.scalars(query).unique().all()]


@app.get("/api/operations/announcements", response_model=list[AnnouncementOut])
def operations_announcements(
    _: User = Depends(get_operations_manager),
    db: Session = Depends(get_db),
):
    query = (
        select(Announcement)
        .options(joinedload(Announcement.author))
        .order_by(Announcement.updated_at.desc())
    )
    return [present_announcement(item) for item in db.scalars(query).unique().all()]


@app.post("/api/operations/announcements", response_model=AnnouncementOut, status_code=status.HTTP_201_CREATED)
def create_announcement(
    payload: AnnouncementWrite,
    operator: User = Depends(get_operations_manager),
    db: Session = Depends(get_db),
):
    item = Announcement(
        kind=payload.kind,
        title=payload.title,
        content=payload.content,
        is_published=payload.is_published,
        is_pinned=payload.is_pinned,
        starts_at=utc_naive(payload.starts_at),
        ends_at=utc_naive(payload.ends_at),
        author_id=operator.id,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    item.author = operator
    return present_announcement(item)


@app.put("/api/operations/announcements/{announcement_id}", response_model=AnnouncementOut)
def update_announcement(
    announcement_id: int,
    payload: AnnouncementWrite,
    _: User = Depends(get_operations_manager),
    db: Session = Depends(get_db),
):
    item = db.scalar(
        select(Announcement)
        .where(Announcement.id == announcement_id)
        .options(joinedload(Announcement.author))
    )
    if item is None:
        raise HTTPException(status_code=404, detail="公告不存在")
    item.kind = payload.kind
    item.title = payload.title
    item.content = payload.content
    item.is_published = payload.is_published
    item.is_pinned = payload.is_pinned
    item.starts_at = utc_naive(payload.starts_at)
    item.ends_at = utc_naive(payload.ends_at)
    item.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(item)
    return present_announcement(item)


@app.delete("/api/operations/announcements/{announcement_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_announcement(
    announcement_id: int,
    _: User = Depends(get_operations_manager),
    db: Session = Depends(get_db),
):
    item = db.get(Announcement, announcement_id)
    if item is None:
        raise HTTPException(status_code=404, detail="公告不存在")
    db.delete(item)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def analytics_visitor_key(viewer: User | None, request: Request) -> str:
    """统计用的访客标识：登录用户按账号，游客按来源 IP 摘要。

    刻意不采用客户端传入的 session_id：否则伪造随机 session_id 就能无限抬高
    「独立访客」数字，污染运营看板。
    """
    if viewer is not None:
        return f"user:{viewer.id}"
    return f"anon:{sha256(client_ip(request).encode()).hexdigest()}"


@app.post("/api/analytics/page-view", status_code=status.HTTP_204_NO_CONTENT)
def track_page_view(
    payload: PageViewCreate,
    request: Request,
    viewer: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    # 游客也能写入，按 IP 限流，避免被用来放大 SQLite 写入量。
    enforce("page-view-ip", client_ip(request), 120, 60)
    visitor_key = analytics_visitor_key(viewer, request)
    now = datetime.utcnow()
    skip_next_snapshot(db)
    db.add(PageView(page_key=payload.page_key, visitor_key=visitor_key, user_id=viewer.id if viewer else None, viewed_at=now))
    db.execute(delete(PageView).where(PageView.viewed_at < now - timedelta(days=180)))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/api/analytics/event", status_code=status.HTTP_204_NO_CONTENT)
def track_event(
    payload: AnalyticsEventCreate,
    request: Request,
    viewer: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """记录关键行为事件；未知 event_key 直接忽略，避免脏数据污染统计。"""
    enforce("analytics-event-ip", client_ip(request), 240, 60)
    if payload.event_key not in EVENT_LABELS:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    visitor_key = analytics_visitor_key(viewer, request)
    now = datetime.utcnow()
    skip_next_snapshot(db)
    db.add(
        AnalyticsEvent(
            event_key=payload.event_key,
            page_key=payload.page_key,
            visitor_key=visitor_key,
            user_id=viewer.id if viewer else None,
            created_at=now,
        )
    )
    db.execute(delete(AnalyticsEvent).where(AnalyticsEvent.created_at < now - timedelta(days=180)))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/operations/analytics", response_model=AnalyticsOut)
def operations_analytics(
    days: int = Query(default=7, ge=1, le=90),
    _: User = Depends(get_role_manager),
    db: Session = Depends(get_db),
):
    """按北京时间统计页面浏览量、去重访客与关键行为事件，不暴露任何访客明细。"""
    utc_now = datetime.utcnow()
    local_today = (utc_now + timedelta(hours=8)).date()
    first_day = local_today - timedelta(days=days - 1)
    range_start = datetime.combine(first_day, time.min) - timedelta(hours=8)
    range_end = datetime.combine(local_today + timedelta(days=1), time.min) - timedelta(hours=8)
    events = db.scalars(
        select(PageView)
        .where(PageView.viewed_at >= range_start, PageView.viewed_at < range_end)
        .order_by(PageView.viewed_at.asc())
    ).all()

    page_buckets = {key: {"views": 0, "visitors": set()} for key in PAGE_LABELS}
    daily_buckets = {
        first_day + timedelta(days=offset): {"views": 0, "visitors": set()}
        for offset in range(days)
    }
    all_visitors: set[str] = set()
    for event in events:
        local_day = (event.viewed_at + timedelta(hours=8)).date()
        if event.page_key not in page_buckets or local_day not in daily_buckets:
            continue
        page_buckets[event.page_key]["views"] += 1
        page_buckets[event.page_key]["visitors"].add(event.visitor_key)
        daily_buckets[local_day]["views"] += 1
        daily_buckets[local_day]["visitors"].add(event.visitor_key)
        all_visitors.add(event.visitor_key)

    event_counts: dict[tuple[str | None, str], int] = {}
    for row in db.scalars(
        select(AnalyticsEvent).where(
            AnalyticsEvent.created_at >= range_start, AnalyticsEvent.created_at < range_end
        )
    ).all():
        key = (row.page_key, row.event_key)
        event_counts[key] = event_counts.get(key, 0) + 1
    event_metrics = [
        EventMetric(
            event_key=event_key,
            label=EVENT_LABELS.get(event_key, event_key),
            page_key=page_key,
            page_label=PAGE_LABELS.get(page_key) if page_key else None,
            count=count,
        )
        for (page_key, event_key), count in event_counts.items()
    ]
    event_metrics.sort(key=lambda item: (-item.count, item.label))

    pages = [
        PageMetric(
            page_key=key,
            label=PAGE_LABELS[key],
            views=bucket["views"],
            visitors=len(bucket["visitors"]),
        )
        for key, bucket in page_buckets.items()
    ]
    pages.sort(key=lambda item: (-item.visitors, -item.views, item.label))
    daily = [
        DailyMetric(date=day.isoformat(), views=bucket["views"], visitors=len(bucket["visitors"]))
        for day, bucket in daily_buckets.items()
    ]
    today_bucket = daily_buckets[local_today]
    return AnalyticsOut(
        days=days,
        total_views=len(events),
        total_visitors=len(all_visitors),
        today_views=today_bucket["views"],
        today_visitors=len(today_bucket["visitors"]),
        pages=pages,
        daily=daily,
        events=event_metrics,
    )


@app.get("/api/operations/summary", response_model=OperationsSummary)
def operations_summary(_: User = Depends(get_beta_application_manager), db: Session = Depends(get_db)):
    """运营台轻量汇总：给「内测申请」标签提供待处理角标（看板娘也可以读）。"""
    return OperationsSummary(
        pending_beta_applications=(
            db.scalar(
                select(func.count())
                .select_from(BetaApplication)
                .where(BetaApplication.status == ApplicationStatus.PENDING)
            )
            or 0
        ),
    )


@app.get("/api/admin/stats", response_model=AdminStats)
def admin_stats(_: User = Depends(get_admin), db: Session = Depends(get_db)):
    expire_due_tasks(db)
    return AdminStats(
        users=db.scalar(select(func.count()).select_from(User)) or 0,
        tasks=db.scalar(select(func.count()).select_from(Task)) or 0,
        published=db.scalar(select(func.count()).select_from(Task).where(Task.status == TaskStatus.PUBLISHED)) or 0,
        processing=db.scalar(select(func.count()).select_from(Task).where(Task.status.in_([TaskStatus.ACCEPTED, TaskStatus.AWAITING]))) or 0,
        completed=db.scalar(select(func.count()).select_from(Task).where(Task.status == TaskStatus.COMPLETED)) or 0,
        hidden=db.scalar(select(func.count()).select_from(Task).where(Task.is_visible.is_(False))) or 0,
    )


@app.get("/api/admin/summary", response_model=AdminSummary)
def admin_summary(user: User = Depends(get_content_moderator), db: Session = Depends(get_db)):
    """监管台轻量汇总：统计卡数字与各标签页待处理角标，全部为 COUNT 查询。

    列表接口已改为按标签页懒加载，这里只负责角标与统计卡，避免首屏并发拉取全部列表。
    只有超级管理员能看到用户/委托总量（与统计卡展示范围一致）。
    """
    expire_due_tasks(db)
    is_admin = user.is_admin
    return AdminSummary(
        users=(db.scalar(select(func.count()).select_from(User)) or 0) if is_admin else 0,
        tasks=(db.scalar(select(func.count()).select_from(Task)) or 0) if is_admin else 0,
        processing=(
            db.scalar(select(func.count()).select_from(Task).where(Task.status.in_([TaskStatus.ACCEPTED, TaskStatus.AWAITING]))) or 0
        ) if is_admin else 0,
        completed=(
            db.scalar(select(func.count()).select_from(Task).where(Task.status == TaskStatus.COMPLETED)) or 0
        ) if is_admin else 0,
        hidden=(
            db.scalar(select(func.count()).select_from(Task).where(Task.is_visible.is_(False))) or 0
        ) if is_admin else 0,
        pending_reports=(
            db.scalar(
                select(func.count())
                .select_from(TaskReport)
                .where(TaskReport.status == ReportStatus.PENDING)
            )
            or 0
        ),
        pending_feedbacks=(
            db.scalar(
                select(func.count())
                .select_from(Feedback)
                .where(Feedback.status == FeedbackStatus.PENDING)
            )
            or 0
        ),
        pending_applications=(
            db.scalar(
                select(func.count())
                .select_from(VolunteerApplication)
                .where(VolunteerApplication.status == ApplicationStatus.PENDING)
            )
            or 0
        ),
        pending_beta_applications=(
            db.scalar(
                select(func.count())
                .select_from(BetaApplication)
                .where(BetaApplication.status == ApplicationStatus.PENDING)
            )
            or 0
        ),
        pending_vr_map_reports=(
            db.scalar(
                select(func.count())
                .select_from(VrMapReport)
                .where(VrMapReport.status == ReportStatus.PENDING)
            )
            or 0
        ),
        pending_vr_map_photos=(
            db.scalar(
                select(func.count())
                .select_from(VrMapPhoto)
                .where(VrMapPhoto.moderated_at.is_(None))
            )
            or 0
        ),
        pending_story_photos=(
            db.scalar(
                select(func.count())
                .select_from(StoryPhoto)
                .where(StoryPhoto.moderated_at.is_(None))
            )
            or 0
        ),
    )


@app.get("/api/admin/tasks", response_model=list[TaskOut])
def admin_tasks(_: User = Depends(get_role_manager), db: Session = Depends(get_db)):
    expire_due_tasks(db)
    tasks = db.scalars(task_query().order_by(Task.updated_at.desc()).limit(500)).unique().all()
    return [present_task(task, _) for task in tasks]


def present_admin_user(db: Session, user: User, viewer: User) -> AdminUserOut:
    """监管台用户条目。

    照片必须由 visible_user_photos 生成：直接 model_validate(user) 读 ORM 的 photos
    拿不到地址（ORM 上没有 image_url），而可见性判断也需要按查看者身份区分。
    邮箱属于个人隐私，仅超级管理员可见：管理员组负责日常运营，不需要全站邮箱库。
    """
    can_see_email = viewer.is_admin
    return AdminUserOut(
        id=user.id,
        username=user.username,
        nickname=user.nickname,
        title=user.title,
        email=user.email if can_see_email else None,
        email_verified=user.email_verified if can_see_email else False,
        is_admin=user.is_admin,
        is_active=user.is_active,
        role=user.role,
        is_beta_tester=user.is_beta_tester,
        max_concurrent_tasks=user.max_concurrent_tasks,
        active_task_count=active_task_count(db, user.id),
        created_at=user.created_at,
        photos=visible_user_photos(user, viewer),
    )


@app.get("/api/admin/users", response_model=list[AdminUserOut])
def admin_users(manager: User = Depends(get_role_manager), db: Session = Depends(get_db)):
    expire_due_tasks(db)
    query = select(User).order_by(User.created_at.desc())
    if not manager.is_admin:
        query = query.where(User.is_admin.is_(False))
    users = db.scalars(query.options(joinedload(User.photos))).unique().all()
    return [present_admin_user(db, user, manager) for user in users]


@app.get("/api/admin/photos", response_model=list[UserProfileOut])
def admin_photos(_: User = Depends(get_content_moderator), db: Session = Depends(get_db)):
    users = db.scalars(user_with_photos_query().order_by(User.created_at.desc())).unique().all()
    return [present_moderation_profile(user, _) for user in users if user.photos or user.avatar_path]


@app.patch("/api/admin/photos/{photo_id}", response_model=UserProfileOut)
def moderate_user_photo(
    photo_id: int,
    payload: AdminPhotoUpdate,
    manager: User = Depends(get_content_moderator),
    db: Session = Depends(get_db),
):
    photo = db.get(UserPhoto, photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="图片不存在")
    photo.is_visible = payload.is_visible
    photo.moderated_by_id = manager.id
    photo.moderated_at = datetime.utcnow()
    commit_moderation(db, photo.file_path, public=payload.is_visible)
    user = db.scalar(user_with_photos_query().where(User.id == photo.user_id))
    return present_moderation_profile(user, manager)


def present_sugar_photo_admin(photo: SugarPhoto) -> SugarPhotoAdminOut:
    return SugarPhotoAdminOut(
        id=photo.id,
        image_url=photo_url(photo),
        is_visible=photo.is_visible,
        admin_note=photo.admin_note,
        created_at=photo.created_at,
        user=present_user_public(photo.profile.user),
    )


@app.get("/api/admin/sugar/photos", response_model=list[SugarPhotoAdminOut])
def admin_sugar_photos(_: User = Depends(get_content_moderator), db: Session = Depends(get_db)):
    photos = db.scalars(
        select(SugarPhoto)
        .options(joinedload(SugarPhoto.profile).joinedload(SugarProfile.user))
        .order_by(SugarPhoto.created_at.desc())
        .limit(500)
    ).unique().all()
    return [present_sugar_photo_admin(photo) for photo in photos]


@app.patch("/api/admin/sugar/photos/{photo_id}", response_model=SugarPhotoAdminOut)
def moderate_sugar_photo(
    photo_id: int,
    payload: SugarPhotoModerateUpdate,
    manager: User = Depends(get_content_moderator),
    db: Session = Depends(get_db),
):
    """管理员组屏蔽/恢复砂糖社照片：屏蔽必须填写理由，恢复时清空理由。"""
    photo = db.get(SugarPhoto, photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="照片不存在")
    if not payload.is_visible and not (payload.admin_note or "").strip():
        raise HTTPException(status_code=422, detail="屏蔽照片时必须填写理由")
    photo.is_visible = payload.is_visible
    photo.admin_note = payload.admin_note.strip() if payload.admin_note and payload.admin_note.strip() else None
    photo.moderated_by_id = manager.id
    photo.moderated_at = datetime.utcnow()
    commit_moderation(db, photo.file_path, public=payload.is_visible)
    db.refresh(photo)
    return present_sugar_photo_admin(photo)


def present_friend_photo_admin(photo: FriendPhoto) -> FriendPhotoAdminOut:
    return FriendPhotoAdminOut(
        id=photo.id,
        image_url=friend_photo_url(photo),
        is_visible=photo.is_visible,
        admin_note=photo.admin_note,
        moderated=photo.moderated_at is not None,
        created_at=photo.created_at,
        user=present_user_public(photo.profile.user),
    )


@app.get("/api/admin/friends/photos", response_model=list[FriendPhotoAdminOut])
def admin_friend_photos(_: User = Depends(get_content_moderator), db: Session = Depends(get_db)):
    photos = db.scalars(
        select(FriendPhoto)
        .options(joinedload(FriendPhoto.profile).joinedload(FriendProfile.user))
        .order_by(FriendPhoto.created_at.desc())
        .limit(500)
    ).unique().all()
    return [present_friend_photo_admin(photo) for photo in photos]


@app.patch("/api/admin/friends/photos/{photo_id}", response_model=FriendPhotoAdminOut)
def moderate_friend_photo(
    photo_id: int,
    payload: FriendPhotoModerateUpdate,
    manager: User = Depends(get_content_moderator),
    db: Session = Depends(get_db),
):
    photo = db.get(FriendPhoto, photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="照片不存在")
    if not payload.is_visible and not (payload.admin_note or "").strip():
        raise HTTPException(status_code=422, detail="屏蔽照片时必须填写理由")
    photo.is_visible = payload.is_visible
    photo.admin_note = payload.admin_note.strip() if payload.admin_note and payload.admin_note.strip() else None
    photo.moderated_by_id = manager.id
    photo.moderated_at = datetime.utcnow()
    commit_moderation(db, photo.file_path, public=payload.is_visible)
    db.refresh(photo)
    photo = db.scalar(
        select(FriendPhoto)
        .options(joinedload(FriendPhoto.profile).joinedload(FriendProfile.user))
        .where(FriendPhoto.id == photo.id)
    )
    return present_friend_photo_admin(photo)


@app.patch("/api/admin/users/{user_id}/task-limit", response_model=AdminUserOut)
def update_user_task_limit(
    user_id: int,
    payload: AdminUserLimitUpdate,
    manager: User = Depends(get_admin),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    user.max_concurrent_tasks = payload.max_concurrent_tasks
    db.commit()
    db.refresh(user)
    return present_admin_user(db, user, manager)


@app.patch("/api/admin/users/{user_id}/password", response_model=AdminUserOut)
def reset_user_password(
    user_id: int,
    payload: AdminPasswordReset,
    manager: User = Depends(get_admin),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    lock_credentials(db, user)
    user.password_hash = hash_password(payload.password)
    # 重置密码后立即吊销该用户已签发的全部登录令牌。
    revoke_credentials(db, user)
    db.commit()
    db.refresh(user)
    return present_admin_user(db, user, manager)


@app.patch("/api/admin/users/{user_id}/role", response_model=AdminUserOut)
def update_user_role(
    user_id: int,
    payload: AdminUserRoleUpdate,
    manager: User = Depends(get_role_manager),
    db: Session = Depends(get_db),
):
    """超级管理员可设置全部角色；管理员只能管理普通用户和志愿者。"""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.is_admin:
        raise HTTPException(status_code=409, detail="管理员账号的权限等级不可修改")
    protected_roles = (UserRole.STAFF, UserRole.MASCOT, UserRole.DISCIPLINARIAN)
    if not manager.is_admin and (payload.role in protected_roles or user.role in protected_roles):
        raise HTTPException(status_code=403, detail="只有超级管理员可以管理管理员、看板娘和风纪委员权限")
    # 离开可公开 QQ 的角色（志愿者 / 管理员）时，收回公开标记。
    publishable_roles = (UserRole.VOLUNTEER, UserRole.STAFF)
    if payload.role not in publishable_roles and user.role in publishable_roles:
        user.qq_public = False
    user.role = payload.role
    db.commit()
    db.refresh(user)
    return present_admin_user(db, user, manager)


@app.patch("/api/admin/users/{user_id}/title", response_model=AdminUserOut)
def update_user_title(
    user_id: int,
    payload: AdminUserTitleUpdate,
    manager: User = Depends(get_role_manager),
    db: Session = Depends(get_db),
):
    """设置用户自定义称号；管理员只能设置普通用户与志愿者的称号。"""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    protected_roles = (UserRole.STAFF, UserRole.MASCOT, UserRole.DISCIPLINARIAN)
    if not manager.is_admin and (user.is_admin or user.role in protected_roles):
        raise HTTPException(status_code=403, detail="只有超级管理员可以设置管理员、看板娘和风纪委员的称号")
    user.title = payload.title
    db.commit()
    db.refresh(user)
    return present_admin_user(db, user, manager)


@app.patch("/api/admin/users/{user_id}/beta-tester", response_model=AdminUserOut)
def update_user_beta_tester(
    user_id: int,
    payload: AdminUserBetaUpdate,
    manager: User = Depends(get_admin),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    user.is_beta_tester = payload.is_beta_tester
    db.commit()
    db.refresh(user)
    return present_admin_user(db, user, manager)


@app.patch("/api/admin/tasks/{task_id}", response_model=TaskOut)
def moderate_task(
    task_id: int,
    payload: AdminTaskUpdate,
    background: BackgroundTasks,
    admin: User = Depends(get_role_manager),
    db: Session = Depends(get_db),
):
    task = get_task_or_404(db, task_id)
    note = payload.admin_note.strip() if payload.admin_note else None
    if not payload.is_visible and not note:
        raise HTTPException(status_code=422, detail="屏蔽委托时必须填写理由")
    task.is_visible = payload.is_visible
    task.admin_note = note if not payload.is_visible else None
    db.commit()
    moderated = get_task_or_404(db, task_id)
    if not moderated.is_visible:
        queue_task_notification(
            moderated,
            background,
            "你的委托已被管理员隐藏",
            [f"《{moderated.title}》已被管理员隐藏，大厅中不再展示。", f"理由：{note}"],
            include_publisher=True,
        )
    return present_task(moderated, admin)
