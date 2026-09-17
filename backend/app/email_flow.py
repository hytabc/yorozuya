"""邮箱令牌与流程编排：一次性令牌的发放与消费、邮件链接、发送冷却、fail-closed 投递。

令牌设计：
- **链接令牌**（验证邮箱/换绑/重置密码）用 32 字节随机值，库里存 ``sha256(secret)``，
  因此可以直接按索引 O(1) 查找，数据库泄露也无法反推出明文链接。
- 靠 ``UPDATE ... WHERE used_at IS NULL`` 的 rowcount 保证**一次性**：
  并发的两次提交只有一次能成功。
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta
from urllib.parse import quote

from fastapi import HTTPException, Request, status
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from .config import settings
from .mailer import (
    EmailDeliveryError,
    EmailNotConfigured,
    notification_message,
    send_email,
)
from .models import EmailToken, User

logger = logging.getLogger("yorozuya.email")

# ── 令牌用途 ──
VERIFY_EMAIL = "verify_email"
CHANGE_EMAIL = "change_email"
RESET_PASSWORD = "reset_password"
PURPOSES = (VERIFY_EMAIL, CHANGE_EMAIL, RESET_PASSWORD)

LINK_TOKEN_BYTES = 32

MAIL_UNAVAILABLE_DETAIL = "邮件服务暂时不可用，请稍后重试或联系管理员"
INVALID_TOKEN_DETAIL = "链接无效或已过期，请重新获取"
EMAIL_TAKEN_DETAIL = "该邮箱已被其他账号使用"

# 前端路由（邮件里的链接指向它们）
VERIFY_EMAIL_PATH = "/verify-email"
RESET_PASSWORD_PATH = "/reset-password"


def hash_link_token(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def _prune(db: Session, now: datetime) -> None:
    """顺手清理过期一天的令牌，避免表无限增长。"""
    db.execute(delete(EmailToken).where(EmailToken.expires_at < now - timedelta(days=1)))


# ---- 账号查找 ----


def find_account(db: Session, account: str) -> User | None:
    """按用户名或邮箱定位账号（邮箱统一小写存储，不区分大小写）。"""
    value = (account or "").strip()
    if not value:
        return None
    user = db.scalar(select(User).where(User.username == value))
    if user is not None:
        return user
    return db.scalar(select(User).where(User.email == value.lower()))


def email_taken(db: Session, address: str, *, exclude_user_id: int | None = None) -> bool:
    query = select(User.id).where(User.email == address.lower())
    if exclude_user_id is not None:
        query = query.where(User.id != exclude_user_id)
    return db.scalar(query.limit(1)) is not None


# ---- 发放 ----


def lock_credentials(db: Session, user: User) -> None:
    """以条件 UPDATE 串行化凭证操作，SQLite 上同样有效；拒绝过期会话快照。"""
    result = db.execute(
        update(User)
        .where(User.id == user.id, User.token_version == user.token_version, User.is_active.is_(True))
        .values(token_version=User.token_version)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        raise HTTPException(status_code=401, detail="登录状态已变更，请重新登录")


def revoke_credentials(db: Session, user: User) -> None:
    """调用方持有凭证锁；与密码/邮箱变更一起提交。"""
    user.token_version += 1
    user.pending_email = None
    db.execute(
        update(EmailToken)
        .where(EmailToken.user_id == user.id, EmailToken.used_at.is_(None))
        .values(used_at=datetime.utcnow())
    )


def _invalidate_previous(db: Session, user_id: int, purpose: str) -> None:
    """同账号同用途的旧令牌一律作废，避免同时存在多条可用链接。"""
    db.execute(
        update(EmailToken)
        .where(
            EmailToken.user_id == user_id,
            EmailToken.purpose == purpose,
            EmailToken.used_at.is_(None),
        )
        .values(used_at=datetime.utcnow())
    )


def issue_link_token(
    db: Session,
    user: User,
    purpose: str,
    *,
    ttl_minutes: int,
    new_email: str | None = None,
) -> str:
    """发放一次性链接令牌，返回明文（只出现在邮件正文里一次）。"""
    lock_credentials(db, user)
    now = datetime.utcnow()
    _prune(db, now)
    _invalidate_previous(db, user.id, purpose)
    secret = secrets.token_urlsafe(LINK_TOKEN_BYTES)
    db.add(
        EmailToken(
            user_id=user.id,
            purpose=purpose,
            token_hash=hash_link_token(secret),
            credential_version=user.token_version,
            salt="",
            new_email=new_email.lower() if new_email else None,
            expires_at=now + timedelta(minutes=ttl_minutes),
            created_at=now,
        )
    )
    db.flush()
    return secret


# ---- 消费 ----


def _mark_used(db: Session, row: EmailToken) -> EmailToken:
    """一次性语义：只有把 used_at 从 NULL 改成时间的那一次调用算成功。"""
    result = db.execute(
        update(EmailToken)
        .where(EmailToken.id == row.id, EmailToken.used_at.is_(None))
        .values(used_at=datetime.utcnow())
    )
    if result.rowcount != 1:
        raise HTTPException(status_code=422, detail=INVALID_TOKEN_DETAIL)
    return row


def consume_link_token(db: Session, purpose: str, secret: str) -> EmailToken:
    """校验并作废链接令牌（不提交，交由调用方与业务变更一起提交）。"""
    if not secret:
        raise HTTPException(status_code=422, detail=INVALID_TOKEN_DETAIL)
    row = db.scalar(
        select(EmailToken).where(
            EmailToken.purpose == purpose,
            EmailToken.token_hash == hash_link_token(secret),
        )
    )
    if row is None or row.used_at is not None or row.expires_at <= datetime.utcnow():
        raise HTTPException(status_code=422, detail=INVALID_TOKEN_DETAIL)
    user = db.get(User, row.user_id)
    if user is None or not user.is_active or row.credential_version != user.token_version:
        raise HTTPException(status_code=422, detail=INVALID_TOKEN_DETAIL)
    lock_credentials(db, user)
    return _mark_used(db, row)


def cooldown_remaining(db: Session, user_id: int, purpose: str) -> int:
    """同一账号同一用途的发信冷却剩余秒数；0 表示可以发送。

    间隔由 ``EMAIL_SEND_COOLDOWN_SECONDS`` 控制（0 表示不冷却，测试里常用）。
    """
    cooldown = settings.email_send_cooldown_seconds
    if cooldown <= 0:
        return 0
    last_created = db.scalar(
        select(EmailToken.created_at)
        .where(EmailToken.user_id == user_id, EmailToken.purpose == purpose)
        .order_by(EmailToken.created_at.desc())
        .limit(1)
    )
    if last_created is None:
        return 0
    elapsed = (datetime.utcnow() - last_created).total_seconds()
    return max(0, int(cooldown - elapsed))


# ---- 投递 ----


async def deliver(to: str, subject: str, text: str, html_body: str | None = None) -> None:
    """fail-closed 发信：未配置或投递失败一律转成 503，绝不让用户以为「已发信」。"""
    try:
        await send_email(to, subject, text, html_body)
    except (EmailNotConfigured, EmailDeliveryError) as error:
        logger.error("邮件服务不可用，已拒绝本次操作：%s", error)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=MAIL_UNAVAILABLE_DETAIL
        ) from error


def can_notify(user: User) -> bool:
    """事件通知条件：总开关 + 已通过验证的邮箱 + 用户自己没关掉通知。"""
    return bool(
        settings.notify_email_enabled and user.email_verified and user.notify_email and user.email
    )


def notification_target(user: User) -> str | None:
    """在请求内取出收件地址（此时 ORM 对象还带着会话）。

    事件通知会作为后台任务在响应之后执行，那时 ORM 实例已脱离会话，
    因此这里只传字符串，避免读取已 detach 的对象属性。
    """
    return user.email if can_notify(user) else None


async def notify_address(
    address: str | None,
    title: str,
    lines: list[str],
    link: str | None = None,
) -> None:
    """best-effort 事件通知：失败只记日志，绝不影响业务请求。

    链接由调用方在请求内算好（``base_url(request) + path``）再传进来，
    这样后台任务不必再去碰请求对象。
    """
    if not address:
        return
    subject, text, html_body = notification_message(title, lines, link)
    try:
        await send_email(address, subject, text, html_body, required=False)
    except (EmailNotConfigured, EmailDeliveryError):  # required=False 本不该抛，兜底
        logger.warning("事件通知发送失败：%s", title)


# ---- 链接 ----


def base_url(request: Request | None) -> str:
    """只使用配置来源；开发环境也必须显式配置本地 origin。"""
    if not settings.site_base_url:
        raise HTTPException(status_code=503, detail="网站邮件链接未配置，请联系管理员")
    return settings.site_base_url.rstrip("/")


def verify_link(token: str, request: Request | None = None) -> str:
    return f"{base_url(request)}{VERIFY_EMAIL_PATH}?token={quote(token)}"


def reset_link(token: str, request: Request | None = None) -> str:
    return f"{base_url(request)}{RESET_PASSWORD_PATH}?token={quote(token)}"
