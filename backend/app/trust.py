"""VRChat 身份：简介验证码校验 + 真实资料快照。

流程：
1. 用户提交 ``usr_...`` 或主页链接；
2. 服务端用**站点机器人账号**（``VRCHAT_BOT_AUTH_COOKIE``）读取该用户公开资料；
3. 生成 10 分钟一次性验证码，用户写入 VRChat 简介；
4. 服务端再次读取最新简介并匹配验证码，通过后记录 Trust Rank / 账号年龄 / 平台；
5. 用户逐项决定是否披露；所有裁剪发生在接口层。

约束：
- 不保存任何用户的 VRChat 密码、Cookie 或令牌；
- 机器人凭据只放服务端 .env，不写数据库、不写日志；
- 官方未提供 OAuth，因此这是「资料控制权验证」，不是 VRChat 官方登录；
- 不伪造 Trust Rank / 账号年龄 / 共同好友。
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
import secrets
import struct
import threading
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import Field
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from .config import settings
from .database import Base, get_db
from .dependencies import get_admin, get_current_user, get_optional_user, get_role_manager
from .models import AppSetting, Task, TaskMemberResponse, User
from .ratelimit import client_ip, enforce
from .schemas import RequestModel

# 与 frontend/src/trust.js 的 TRUST_DISCLOSURE 保持一致。
DISCLOSURE_KEYS = (
    "identity",
    "trust_rank",
    "account_age",
    "platform",
    "common_friends",
    "common_groups",
    "worlds",
)
DEFAULT_DISCLOSURE = {key: False for key in DISCLOSURE_KEYS}

STATUS_UNVERIFIED = "unverified"
STATUS_PENDING = "pending"
STATUS_VERIFIED = "verified"
STATUS_UNLINKED = "unlinked"

# 用户 ID 形如 usr_c1644b5b-3ca4-45b4-97c6-a2a0de70d469，也接受短形式。
VRCHAT_USER_ID = re.compile(r"usr_[0-9a-fA-F-]{4,}")
VRCHAT_HOSTS = {"vrchat.com", "www.vrchat.com"}
CHALLENGE_LABEL = "万事屋 VRChat 验证"
CHALLENGE_PREFIX = "vrcverify"
MAX_CHALLENGE_FAILURES = 5
CHALLENGE_COOLDOWN_SECONDS = 300

TRUST_RANK_LABELS = {
    "visitor": "游客",
    "new_user": "新用户",
    "user": "用户",
    "known_user": "熟识用户",
    "trusted_user": "可信用户",
    "unknown": "未识别",
}

_DASH_VARIANTS = "‐‑‒–—―−﹘﹣－"
_DASH_TRANSLATION = str.maketrans({char: "-" for char in _DASH_VARIANTS})

_BOT_LOCK = threading.Lock()
_BOT_LAST_CALL = 0.0
_BOT_STATE: dict[str, object] = {"last_error": None, "last_success_at": None}


class VRChatIdentity(Base):
    __tablename__ = "vrchat_identities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)
    vrchat_user_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    profile_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    disclosure_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=STATUS_UNVERIFIED)
    link_method: Mapped[str] = mapped_column(String(16), nullable=False, default="manual")
    linked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    last_error: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # 真实验证与快照
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    trust_rank: Mapped[str | None] = mapped_column(String(24), nullable=True)
    account_created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    platform: Mapped[str | None] = mapped_column(String(32), nullable=True)
    snapshot_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # 一次性验证码：只保存 10 分钟，验证成功后保留用于后续刷新复核。
    challenge_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    challenge_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    challenge_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    challenge_locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class VRChatBan(Base):
    """管理员黑名单：只存 VRChat ID 与操作人，不存社交数据。"""

    __tablename__ = "vrchat_bans"

    vrchat_user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    banned_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class LinkRequest(RequestModel):
    profile: str = Field(min_length=4, max_length=255)
    # 兼容旧客户端；新流程不再要求手填显示名，以 VRChat 资料为准。
    display_name: str | None = Field(default=None, max_length=64)


class DisclosureUpdate(RequestModel):
    identity: bool | None = None
    trust_rank: bool | None = None
    account_age: bool | None = None
    platform: bool | None = None
    common_friends: bool | None = None
    common_groups: bool | None = None
    worlds: bool | None = None


class AdminConfigUpdate(RequestModel):
    enabled: bool | None = None
    allow_new_links: bool | None = None


class AdminBanRequest(RequestModel):
    note: str | None = Field(default=None, max_length=200)


class VRChatError(Exception):
    def __init__(self, status_code: int, detail: str, retry_after: int | None = None):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.retry_after = retry_after


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() + "Z" if value else None


def _match_text(text: str) -> str:
    """匹配用归一化：NFKC、去零宽/格式字符、去全部空白、转小写。

    VRChat 在保存简介时可能插入零宽空格、换行或全角字符；用户也可能在
    简介里保留旧验证码。这里只关心“当前码是否作为子串出现”。
    """
    normalized = unicodedata.normalize("NFKC", text or "")
    normalized = normalized.translate(_DASH_TRANSLATION)
    normalized = "".join(
        char for char in normalized if unicodedata.category(char) != "Cf"
    )
    return re.sub(r"\s+", "", normalized).lower()


def bio_contains_token(bio: str, token: str) -> bool:
    needle = _match_text(token)
    return bool(needle) and needle in _match_text(bio)


def challenge_text(token: str) -> str:
    return f"【{CHALLENGE_LABEL} - {token}】"


def normalize_trust_rank(tags) -> str:
    if not isinstance(tags, list):
        return "unknown"
    tag_set = {str(tag) for tag in tags}
    if "system_trust_legend" in tag_set or "system_trust_veteran" in tag_set:
        return "trusted_user"
    if "system_trust_trusted" in tag_set:
        return "known_user"
    if "system_trust_known" in tag_set:
        return "user"
    if "system_trust_basic" in tag_set:
        return "new_user"
    if "system_trust_visitor" in tag_set:
        return "visitor"
    if tag_set:
        return "visitor"
    return "unknown"


def parse_account_created_at(value) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def account_age_days(created_at: datetime | None) -> int | None:
    if created_at is None:
        return None
    return max(0, (datetime.utcnow() - created_at).days)


def account_age_label(created_at: datetime | None) -> str | None:
    days = account_age_days(created_at)
    if days is None:
        return None
    months = days // 30
    years, remainder = divmod(months, 12)
    if years:
        return f"{years} 年 {remainder} 个月" if remainder else f"{years} 年"
    if months:
        return f"{months} 个月"
    return f"{days} 天"


def parse_profile(raw: str) -> tuple[str, str]:
    """从主页链接/ID 里取出 VRChat 用户 ID，并归一化出可安全渲染的 https 地址。"""
    text = (raw or "").strip()
    if text.startswith("http://"):
        raise HTTPException(status_code=422, detail="只接受 https 的 VRChat 主页链接")
    if text.startswith("https://"):
        parsed = urlparse(text)
        if (parsed.hostname or "").lower() not in VRCHAT_HOSTS:
            raise HTTPException(status_code=422, detail="请填写 vrchat.com 的个人主页链接")
    match = VRCHAT_USER_ID.search(text)
    if match is None:
        raise HTTPException(status_code=422, detail="链接中找不到 VRChat 用户 ID（形如 usr_）")
    vrchat_user_id = match.group(0)
    if text.startswith("https://"):
        return vrchat_user_id, text
    return vrchat_user_id, f"https://vrchat.com/home/user/{vrchat_user_id}"


def load_disclosure(identity: VRChatIdentity) -> dict[str, bool]:
    try:
        stored = json.loads(identity.disclosure_json or "{}")
    except (TypeError, ValueError):
        stored = {}
    return {key: bool(stored.get(key, False)) for key in DISCLOSURE_KEYS}


def dump_disclosure(values: dict[str, bool]) -> str:
    return json.dumps({key: bool(values.get(key, False)) for key in DISCLOSURE_KEYS})


def identity_of(db: Session, user_id: int) -> VRChatIdentity | None:
    return db.scalar(select(VRChatIdentity).where(VRChatIdentity.user_id == user_id))


def _flag(db: Session, key: str, default: bool = True) -> bool:
    row = db.get(AppSetting, key)
    if row is None:
        return default
    return row.value == "1"


def _set_flag(db: Session, key: str, value: bool) -> None:
    row = db.get(AppSetting, key)
    if row is None:
        db.add(AppSetting(key=key, value="1" if value else "0"))
    else:
        row.value = "1" if value else "0"


def integration_state(db: Session) -> dict:
    return {
        "enabled": _flag(db, "vrchat_enabled", True),
        "allow_new_links": _flag(db, "vrchat_allow_new_links", True),
    }


def bot_auth_mode() -> str | None:
    """cookie 优先；否则使用机器人账号密码 + TOTP。"""
    if (settings.vrchat_bot_auth_cookie or "").strip():
        return "cookie"
    if (settings.vrchat_bot_username or "").strip() and (settings.vrchat_bot_password or "").strip():
        return "password"
    return None


def bot_configured() -> bool:
    return bot_auth_mode() is not None


def _cookie_header() -> str:
    raw = (settings.vrchat_bot_auth_cookie or "").strip()
    if raw.lower().startswith("cookie:"):
        raw = raw.split(":", 1)[1].strip()
    if "=" in raw:
        return raw
    return f"auth={raw}"


_BOT_SESSION: dict[str, object] = {"client": None, "mode": None}


def _reset_bot_session() -> None:
    client = _BOT_SESSION.get("client")
    if client is not None:
        try:
            client.close()
        except Exception:
            pass
    _BOT_SESSION["client"] = None
    _BOT_SESSION["mode"] = None


def _new_http_client() -> httpx.Client:
    return httpx.Client(
        timeout=settings.vrchat_http_timeout_seconds,
        headers={"Accept": "application/json", "User-Agent": settings.vrchat_user_agent},
        follow_redirects=True,
    )


def _totp_code(secret: str) -> str:
    """标准 TOTP（SHA1 / 6 位 / 30 秒），避免为一个功能新增依赖。"""
    normalized = re.sub(r"\s+", "", secret or "").upper()
    if not normalized:
        raise VRChatError(503, "VRChat 机器人需要 2FA，但未配置 VRCHAT_BOT_TOTP_SECRET")
    padded = normalized + "=" * ((8 - len(normalized) % 8) % 8)
    try:
        key = base64.b32decode(padded)
    except (ValueError, binascii.Error) as error:
        raise VRChatError(503, "VRChat 机器人 TOTP 密钥格式不正确") from error
    counter = int(time.time()) // 30
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{code:06d}"


def _login_bot(client: httpx.Client) -> None:
    """用机器人账号密码登录；支持 TOTP 2FA。密码/TOTP 只读 .env，不落库、不打日志。"""
    username = (settings.vrchat_bot_username or "").strip()
    password = settings.vrchat_bot_password or ""
    if not username or not password:
        raise VRChatError(503, "VRChat 机器人账号未配置")
    base = (settings.vrchat_api_base or "").rstrip("/")
    try:
        response = client.get(f"{base}/auth/user", auth=(username, password))
    except httpx.HTTPError as error:
        _BOT_STATE["last_error"] = "连接 VRChat 失败"
        raise VRChatError(503, "VRChat 暂时不可用，请稍后再试") from error
    if response.status_code in (401, 403):
        _BOT_STATE["last_error"] = "机器人账号或密码不正确"
        raise VRChatError(503, "VRChat 机器人账号或密码不正确")
    if response.status_code >= 400:
        _BOT_STATE["last_error"] = f"机器人登录失败（{response.status_code}）"
        raise VRChatError(503, "VRChat 机器人登录失败")

    try:
        body = response.json()
    except ValueError:
        body = {}
    if isinstance(body, dict) and body.get("requiresTwoFactorAuth"):
        methods = body.get("requiresTwoFactorAuth") or []
        if "totp" not in methods:
            _BOT_STATE["last_error"] = "机器人需要不支持的二次验证方式"
            raise VRChatError(503, "VRChat 机器人需要不支持的二次验证方式")
        if not (settings.vrchat_bot_totp_secret or "").strip():
            _BOT_STATE["last_error"] = "机器人需要 2FA，但未配置 TOTP"
            raise VRChatError(503, "VRChat 机器人需要 2FA，请配置 VRCHAT_BOT_TOTP_SECRET")
        try:
            verify = client.post(
                f"{base}/auth/twofactorauth/totp/verify",
                json={"code": _totp_code(settings.vrchat_bot_totp_secret)},
            )
        except httpx.HTTPError as error:
            _BOT_STATE["last_error"] = "连接 VRChat 失败"
            raise VRChatError(503, "VRChat 暂时不可用，请稍后再试") from error
        if verify.status_code >= 400:
            _BOT_STATE["last_error"] = "机器人 2FA 验证失败"
            raise VRChatError(503, "VRChat 机器人 2FA 验证失败")
        again = client.get(f"{base}/auth/user")
        if again.status_code >= 400:
            _BOT_STATE["last_error"] = "机器人登录失败"
            raise VRChatError(503, "VRChat 机器人登录失败")
    _BOT_STATE["last_error"] = None


def _ensure_bot_client() -> httpx.Client:
    mode = bot_auth_mode()
    if mode is None:
        raise VRChatError(503, "VRChat 机器人尚未配置，请联系管理员")
    existing = _BOT_SESSION.get("client")
    if existing is not None and _BOT_SESSION.get("mode") == mode:
        return existing
    _reset_bot_session()
    client = _new_http_client()
    try:
        if mode == "cookie":
            client.headers["Cookie"] = _cookie_header()
        else:
            _login_bot(client)
    except Exception as error:
        _BOT_STATE["last_error"] = getattr(error, "detail", "机器人登录失败")
        try:
            client.close()
        except Exception:
            pass
        raise
    _BOT_SESSION["client"] = client
    _BOT_SESSION["mode"] = mode
    return client


def _bot_get(path: str) -> httpx.Response:
    base = (settings.vrchat_api_base or "").rstrip("/")
    client = _ensure_bot_client()
    try:
        response = client.get(f"{base}{path}")
    except httpx.HTTPError as error:
        _BOT_STATE["last_error"] = "连接 VRChat 失败"
        raise VRChatError(503, "VRChat 暂时不可用，请稍后再试") from error
    if response.status_code in (401, 403):
        # 会话可能过期：清掉后重新登录/重设 cookie，只重试一次。
        _reset_bot_session()
        client = _ensure_bot_client()
        try:
            response = client.get(f"{base}{path}")
        except httpx.HTTPError as error:
            _BOT_STATE["last_error"] = "连接 VRChat 失败"
            raise VRChatError(503, "VRChat 暂时不可用，请稍后再试") from error
        if response.status_code in (401, 403):
            _BOT_STATE["last_error"] = "机器人会话失效"
            raise VRChatError(503, "VRChat 机器人会话已失效，请联系管理员")
    return response


def fetch_profile(vrchat_user_id: str) -> dict:
    """用站点机器人账号读取 VRChat 公开资料；失败时 fail-closed。"""
    if not bot_configured():
        raise VRChatError(503, "VRChat 机器人尚未配置，请联系管理员")
    # 机器人请求串行 + 最小间隔，降低触发 429 的概率。
    global _BOT_LAST_CALL
    with _BOT_LOCK:
        wait = 2.0 - (time.monotonic() - _BOT_LAST_CALL)
        if wait > 0:
            time.sleep(wait)
        _BOT_LAST_CALL = time.monotonic()

    response = _bot_get(f"/users/{vrchat_user_id}")
    if response.status_code == 404:
        raise VRChatError(404, "找不到该 VRChat 用户")
    if response.status_code == 429:
        retry = response.headers.get("Retry-After")
        _BOT_STATE["last_error"] = "VRChat 限流"
        raise VRChatError(429, "VRChat 请求过于频繁，请稍后再试", int(retry) if retry and retry.isdigit() else None)
    if response.status_code >= 400:
        _BOT_STATE["last_error"] = f"VRChat 返回 {response.status_code}"
        raise VRChatError(503, "VRChat 暂时不可用，请稍后再试")

    try:
        profile = response.json()
    except ValueError as error:
        _BOT_STATE["last_error"] = "VRChat 返回无法解析的数据"
        raise VRChatError(503, "VRChat 返回了无法解析的数据") from error
    if not isinstance(profile, dict) or not profile.get("id"):
        _BOT_STATE["last_error"] = "VRChat 返回的资料不完整"
        raise VRChatError(503, "VRChat 返回的资料不完整")
    _BOT_STATE["last_error"] = None
    _BOT_STATE["last_success_at"] = datetime.utcnow()
    return profile


def _fetch_or_http(vrchat_user_id: str) -> dict:
    try:
        return fetch_profile(vrchat_user_id)
    except VRChatError as error:
        headers = {"Retry-After": str(error.retry_after)} if error.retry_after else None
        raise HTTPException(status_code=error.status_code, detail=error.detail, headers=headers) from error


def apply_profile(identity: VRChatIdentity, profile: dict) -> None:
    now = datetime.utcnow()
    display_name = str(profile.get("displayName") or "").strip()
    if display_name:
        identity.display_name = display_name[:64]
    identity.profile_url = f"https://vrchat.com/home/user/{identity.vrchat_user_id}"
    identity.trust_rank = normalize_trust_rank(profile.get("tags"))
    identity.account_created_at = parse_account_created_at(profile.get("date_joined"))
    identity.platform = (profile.get("last_platform") or profile.get("platform") or None)
    identity.last_synced_at = now
    identity.snapshot_expires_at = now + timedelta(days=settings.vrchat_snapshot_ttl_days)
    identity.last_error = None


def snapshot_is_stale(identity: VRChatIdentity) -> bool:
    return bool(identity.snapshot_expires_at and identity.snapshot_expires_at <= datetime.utcnow())


def _present_verified_fields(identity: VRChatIdentity) -> dict:
    return {
        "trust_rank": identity.trust_rank,
        "trust_rank_label": TRUST_RANK_LABELS.get(identity.trust_rank or "", TRUST_RANK_LABELS["unknown"]),
        "account_created_at": _iso(identity.account_created_at),
        "account_age_days": account_age_days(identity.account_created_at),
        "account_age_label": account_age_label(identity.account_created_at),
        "platform": identity.platform,
    }


def present_self(identity: VRChatIdentity | None) -> dict:
    if identity is None:
        return {
            "bound": False,
            "status": None,
            "disclosure": dict(DEFAULT_DISCLOSURE),
            "verified": False,
            "bot_configured": bot_configured(),
        }
    verified = identity.status == STATUS_VERIFIED and identity.verified_at is not None
    result = {
        "bound": identity.status in (STATUS_UNVERIFIED, STATUS_PENDING, STATUS_VERIFIED),
        "status": identity.status,
        "display_name": identity.display_name,
        "profile_url": identity.profile_url,
        "verified": verified,
        "source": "vrchat-bio" if verified else "manual",
        "linked_at": _iso(identity.linked_at),
        "verified_at": _iso(identity.verified_at),
        "last_verified_at": _iso(identity.last_verified_at),
        "last_synced_at": _iso(identity.last_synced_at),
        "stale": snapshot_is_stale(identity),
        "disclosure": load_disclosure(identity),
        "last_error": identity.last_error,
        "bot_configured": bot_configured(),
        "challenge_locked_until": _iso(identity.challenge_locked_until),
        **_present_verified_fields(identity),
    }
    if identity.status == STATUS_PENDING and identity.challenge_token:
        result["challenge"] = {
            "code": identity.challenge_token,
            "text": challenge_text(identity.challenge_token),
            "expires_at": _iso(identity.challenge_expires_at),
            "failures": identity.challenge_failures,
        }
    return result


def present_public(db: Session, user_id: int, viewer: User | None) -> dict:
    """对他人展示的信任摘要：只返回用户主动披露的部分。"""
    identity = identity_of(db, user_id)
    if identity is None or identity.status not in (STATUS_UNVERIFIED, STATUS_VERIFIED):
        return {"user_id": user_id, "bound": False, "verified": False}
    return _present_public_identity(identity, viewer)


def present_public_many(db: Session, user_ids, viewer: User | None) -> dict[int, dict]:
    """批量版信任摘要，供委托列表/好友列表避免逐条查询。"""
    ids = list({int(user_id) for user_id in user_ids})
    if not ids:
        return {}
    identities = db.scalars(
        select(VRChatIdentity).where(VRChatIdentity.user_id.in_(ids))
    ).all()
    return {
        identity.user_id: _present_public_identity(identity, viewer)
        for identity in identities
        if identity.status in (STATUS_UNVERIFIED, STATUS_VERIFIED)
    }


def _present_public_identity(identity: VRChatIdentity, viewer: User | None) -> dict:
    user_id = identity.user_id
    disclosure = load_disclosure(identity)
    owner = viewer is not None and viewer.id == user_id
    verified = identity.status == STATUS_VERIFIED
    result = {
        "user_id": user_id,
        "bound": True,
        "verified": verified,
        "source": "vrchat-bio" if verified else "manual",
        "linked_at": _iso(identity.linked_at),
        "verified_at": _iso(identity.verified_at),
        "last_verified_at": _iso(identity.last_verified_at),
        "last_synced_at": _iso(identity.last_synced_at),
        "stale": snapshot_is_stale(identity),
        "disclosed": any(disclosure.values()),
    }
    if owner or disclosure["identity"]:
        result["display_name"] = identity.display_name
        result["profile_url"] = identity.profile_url
    if owner or disclosure["trust_rank"]:
        result["trust_rank"] = identity.trust_rank
        result["trust_rank_label"] = TRUST_RANK_LABELS.get(
            identity.trust_rank or "", TRUST_RANK_LABELS["unknown"]
        )
    if owner or disclosure["account_age"]:
        result["account_created_at"] = _iso(identity.account_created_at)
        result["account_age_days"] = account_age_days(identity.account_created_at)
        result["account_age_label"] = account_age_label(identity.account_created_at)
    if owner or disclosure["platform"]:
        result["platform"] = identity.platform
    return result


def _taken_by_other(db: Session, vrchat_user_id: str, user_id: int) -> bool:
    return db.scalar(
        select(VRChatIdentity.id).where(
            VRChatIdentity.vrchat_user_id == vrchat_user_id,
            VRChatIdentity.user_id != user_id,
        )
    ) is not None


def _identity_for_update(db: Session, user: User) -> VRChatIdentity:
    identity = identity_of(db, user.id)
    if identity is None:
        identity = VRChatIdentity(
            user_id=user.id,
            disclosure_json=dump_disclosure(DEFAULT_DISCLOSURE),
        )
        db.add(identity)
    return identity


def _clear_binding(identity: VRChatIdentity) -> None:
    identity.status = STATUS_UNLINKED
    identity.vrchat_user_id = None
    identity.display_name = None
    identity.profile_url = None
    identity.link_method = "manual"
    identity.disclosure_json = dump_disclosure(DEFAULT_DISCLOSURE)
    identity.verified_at = None
    identity.last_verified_at = None
    identity.last_synced_at = None
    identity.trust_rank = None
    identity.account_created_at = None
    identity.platform = None
    identity.snapshot_expires_at = None
    identity.challenge_token = None
    identity.challenge_expires_at = None
    identity.challenge_failures = 0
    identity.challenge_locked_until = None
    identity.last_error = None
    identity.updated_at = datetime.utcnow()


def _issue_challenge(identity: VRChatIdentity, vrchat_user_id: str, profile: dict) -> None:
    now = datetime.utcnow()
    identity.vrchat_user_id = vrchat_user_id
    identity.profile_url = f"https://vrchat.com/home/user/{vrchat_user_id}"
    identity.status = STATUS_PENDING
    identity.link_method = "bio"
    identity.linked_at = now
    identity.challenge_token = f"{CHALLENGE_PREFIX}{secrets.token_hex(16)}"
    identity.challenge_expires_at = now + timedelta(seconds=settings.vrchat_challenge_ttl_seconds)
    identity.challenge_failures = 0
    identity.challenge_locked_until = None
    identity.verified_at = None
    identity.last_error = None
    apply_profile(identity, profile)


router = APIRouter(prefix="/api/vrchat", tags=["vrchat identity"])


@router.get("/status")
def my_status(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    enforce("vrchat-trust-read", str(user.id), 120, 600)
    return {**present_self(identity_of(db, user.id)), **integration_state(db)}


@router.post("/link/start")
@router.post("/link", include_in_schema=False)
def link_start(
    payload: LinkRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """开始验证：读取公开资料并签发 10 分钟一次性简介验证码。"""
    enforce("vrchat-link", str(user.id), 5, 3600)
    state = integration_state(db)
    if not state["enabled"]:
        raise HTTPException(status_code=503, detail="VRChat 身份功能当前已关闭")
    if not state["allow_new_links"]:
        raise HTTPException(status_code=503, detail="当前暂停接受新的 VRChat 绑定")
    vrchat_user_id, _ = parse_profile(payload.profile)
    if db.get(VRChatBan, vrchat_user_id) is not None:
        raise HTTPException(status_code=403, detail="该 VRChat 身份已被管理员禁止绑定")
    if _taken_by_other(db, vrchat_user_id, user.id):
        raise HTTPException(status_code=409, detail="该 VRChat 主页已被其他账号绑定")
    profile = _fetch_or_http(vrchat_user_id)
    canonical_id = str(profile.get("id") or vrchat_user_id)
    if _taken_by_other(db, canonical_id, user.id):
        raise HTTPException(status_code=409, detail="该 VRChat 主页已被其他账号绑定")
    identity = _identity_for_update(db, user)
    _issue_challenge(identity, canonical_id, profile)
    db.commit()
    db.refresh(identity)
    return {**present_self(identity), **integration_state(db)}


@router.post("/link/check")
def link_check(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """读取最新简介并核对验证码；连续失败 5 次冷却 5 分钟。"""
    enforce("vrchat-link", str(user.id), 10, 3600)
    identity = identity_of(db, user.id)
    if identity is None or identity.status != STATUS_PENDING or not identity.vrchat_user_id:
        raise HTTPException(status_code=409, detail="当前没有待验证的 VRChat 绑定")
    now = datetime.utcnow()
    if identity.challenge_locked_until and identity.challenge_locked_until > now:
        raise HTTPException(status_code=429, detail="验证失败次数过多，请稍后再试")
    if not identity.challenge_token or not identity.challenge_expires_at or identity.challenge_expires_at <= now:
        raise HTTPException(status_code=409, detail="验证码已过期，请重新获取")

    profile = _fetch_or_http(identity.vrchat_user_id)
    bio = str(profile.get("bio") or "")
    if not bio_contains_token(bio, identity.challenge_token or ""):
        identity.challenge_failures = (identity.challenge_failures or 0) + 1
        identity.last_error = "简介中未找到验证码"
        if identity.challenge_failures >= MAX_CHALLENGE_FAILURES:
            identity.challenge_locked_until = now + timedelta(seconds=CHALLENGE_COOLDOWN_SECONDS)
            identity.challenge_failures = 0
        db.commit()
        detail = (
            "VRChat 返回的简介为空，未找到验证码；请确认个人资料可见性，或稍等缓存刷新后再试"
            if not bio.strip()
            else "简介中未找到验证码；请确认码完整写在 Bio 中、未被截断，并稍等 10-60 秒后再试"
        )
        raise HTTPException(status_code=409, detail=detail)

    apply_profile(identity, profile)
    identity.status = STATUS_VERIFIED
    identity.verified_at = now
    identity.last_verified_at = now
    identity.challenge_expires_at = None
    identity.challenge_failures = 0
    identity.challenge_locked_until = None
    identity.last_error = None
    db.commit()
    db.refresh(identity)
    return {**present_self(identity), **integration_state(db)}


@router.post("/refresh")
def refresh(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """重新拉取快照并复核简介；码被删掉时降级为未验证，但保留曾验证时间。"""
    enforce("vrchat-link", str(user.id), 10, 3600)
    identity = identity_of(db, user.id)
    if identity is None or not identity.vrchat_user_id or identity.status not in (
        STATUS_VERIFIED,
        STATUS_UNVERIFIED,
        STATUS_PENDING,
    ):
        raise HTTPException(status_code=404, detail="当前账号没有可刷新的 VRChat 身份")
    profile = _fetch_or_http(identity.vrchat_user_id)
    apply_profile(identity, profile)
    if identity.challenge_token:
        bio = str(profile.get("bio") or "")
        if bio_contains_token(bio, identity.challenge_token):
            identity.status = STATUS_VERIFIED
            identity.verified_at = datetime.utcnow()
            identity.last_verified_at = identity.verified_at
            identity.last_error = None
        elif identity.status == STATUS_VERIFIED:
            identity.status = STATUS_UNVERIFIED
            identity.verified_at = None
            identity.last_error = "简介中未找到验证码，请重新写入后再刷新"
    db.commit()
    db.refresh(identity)
    return {**present_self(identity), **integration_state(db), "refreshed": True}


@router.post("/unlink")
def unlink(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    enforce("vrchat-link", str(user.id), 5, 3600)
    identity = identity_of(db, user.id)
    if identity is None or identity.status == STATUS_UNLINKED:
        raise HTTPException(status_code=404, detail="当前账号没有绑定 VRChat 身份")
    # 行本身保留，用于已签发凭证标注「身份来源已解绑」。
    _clear_binding(identity)
    db.commit()
    return present_self(identity)


@router.delete("/data")
def delete_data(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    enforce("vrchat-link", str(user.id), 5, 3600)
    identity = identity_of(db, user.id)
    if identity is None:
        raise HTTPException(status_code=404, detail="当前账号没有 VRChat 数据")
    db.delete(identity)
    db.commit()
    return {"ok": True}


@router.patch("/disclosure")
def update_disclosure(
    payload: DisclosureUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    enforce("vrchat-trust-read", str(user.id), 120, 600)
    identity = identity_of(db, user.id)
    if identity is None or identity.status not in (STATUS_UNVERIFIED, STATUS_VERIFIED):
        raise HTTPException(status_code=409, detail="请先绑定并验证 VRChat 身份")
    values = load_disclosure(identity)
    for key in DISCLOSURE_KEYS:
        value = getattr(payload, key)
        if value is not None:
            values[key] = value
    identity.disclosure_json = dump_disclosure(values)
    identity.updated_at = datetime.utcnow()
    db.commit()
    return present_self(identity)


admin_router = APIRouter(prefix="/api/admin/vrchat", tags=["vrchat admin"])


@admin_router.get("/status")
def admin_status(_: User = Depends(get_role_manager), db: Session = Depends(get_db)):
    """只返回数量、开关与机器人健康，不返回任何用户的社交数据。"""
    counts = dict(
        db.execute(
            select(VRChatIdentity.status, func.count()).group_by(VRChatIdentity.status)
        ).all()
    )
    banned = db.scalar(select(func.count()).select_from(VRChatBan)) or 0
    return {
        **integration_state(db),
        "verified": counts.get(STATUS_VERIFIED, 0),
        "unverified": counts.get(STATUS_UNVERIFIED, 0),
        "pending": counts.get(STATUS_PENDING, 0),
        "unlinked": counts.get(STATUS_UNLINKED, 0),
        "banned": banned,
        "bot_configured": bot_configured(),
        "bot_auth_mode": bot_auth_mode(),
        "bot_last_error": _BOT_STATE["last_error"],
        "bot_last_success_at": _iso(_BOT_STATE["last_success_at"]),
    }


@admin_router.patch("/config")
def admin_config(
    payload: AdminConfigUpdate,
    _: User = Depends(get_admin),
    db: Session = Depends(get_db),
):
    if payload.enabled is not None:
        _set_flag(db, "vrchat_enabled", payload.enabled)
    if payload.allow_new_links is not None:
        _set_flag(db, "vrchat_allow_new_links", payload.allow_new_links)
    db.commit()
    return integration_state(db)


def _admin_binding(db: Session, identity: VRChatIdentity) -> dict:
    user = db.get(User, identity.user_id)
    return {
        "user_id": identity.user_id,
        "nickname": user.nickname if user else None,
        "status": identity.status,
        "verified": identity.status == STATUS_VERIFIED,
        "display_name": identity.display_name,
        "profile_url": identity.profile_url,
        "verified_at": _iso(identity.verified_at),
        "last_synced_at": _iso(identity.last_synced_at),
    }


@admin_router.get("/accounts")
def admin_accounts(
    vrchat_user_id: str = Query(min_length=4, max_length=64),
    _: User = Depends(get_role_manager),
    db: Session = Depends(get_db),
):
    identities = db.scalars(
        select(VRChatIdentity).where(VRChatIdentity.vrchat_user_id == vrchat_user_id)
    ).all()
    ban = db.get(VRChatBan, vrchat_user_id)
    return {
        "vrchat_user_id": vrchat_user_id,
        "bindings": [_admin_binding(db, identity) for identity in identities],
        "banned": ban is not None,
    }


@admin_router.post("/accounts/{vrchat_user_id}/unbind")
def admin_unbind(
    vrchat_user_id: str,
    _: User = Depends(get_role_manager),
    db: Session = Depends(get_db),
):
    identities = db.scalars(
        select(VRChatIdentity).where(VRChatIdentity.vrchat_user_id == vrchat_user_id)
    ).all()
    for identity in identities:
        _clear_binding(identity)
    db.commit()
    return {"unbound": len(identities)}


@admin_router.post("/accounts/{vrchat_user_id}/ban")
def admin_ban(
    vrchat_user_id: str,
    payload: AdminBanRequest | None = None,
    manager: User = Depends(get_role_manager),
    db: Session = Depends(get_db),
):
    identities = db.scalars(
        select(VRChatIdentity).where(VRChatIdentity.vrchat_user_id == vrchat_user_id)
    ).all()
    for identity in identities:
        _clear_binding(identity)
    ban = db.get(VRChatBan, vrchat_user_id)
    note = (payload.note or "").strip() if payload and payload.note else None
    if ban is None:
        db.add(VRChatBan(vrchat_user_id=vrchat_user_id, banned_by_id=manager.id, note=note))
    else:
        ban.banned_by_id = manager.id
        ban.note = note
    db.commit()
    return {"banned": True, "unbound": len(identities)}


@admin_router.delete("/accounts/{vrchat_user_id}/ban")
def admin_unban(
    vrchat_user_id: str,
    _: User = Depends(get_role_manager),
    db: Session = Depends(get_db),
):
    ban = db.get(VRChatBan, vrchat_user_id)
    if ban is not None:
        db.delete(ban)
        db.commit()
    return {"banned": False}


@admin_router.get("/bans")
def admin_bans(_: User = Depends(get_role_manager), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(VRChatBan).order_by(VRChatBan.created_at.desc()).limit(200)
    ).all()
    return [
        {
            "vrchat_user_id": row.vrchat_user_id,
            "banned_by_id": row.banned_by_id,
            "note": row.note,
            "created_at": _iso(row.created_at),
        }
        for row in rows
    ]


# 读取他人信任摘要：路径挂在 /api/users、/api/tasks 下，因此单独用一个不带前缀的 router。
trust_router = APIRouter(prefix="/api", tags=["vrchat trust"])


@trust_router.get("/users/{user_id}/trust")
def user_trust(
    user_id: int,
    request: Request,
    viewer: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    enforce(
        "vrchat-trust-read",
        str(viewer.id) if viewer is not None else client_ip(request),
        120,
        600,
    )
    if db.get(User, user_id) is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return present_public(db, user_id, viewer)


def _is_participant(task: Task, viewer: User | None) -> bool:
    if viewer is None:
        return False
    return viewer.is_admin or viewer.id == task.publisher_id or any(
        member.user_id == viewer.id for member in task.members
    )


@trust_router.get("/tasks/{task_id}/trust")
def task_trust(
    task_id: int,
    request: Request,
    viewer: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """委托双方的信任摘要；匿名委托在**接口层**直接裁剪发布者侧信息。"""
    enforce(
        "vrchat-trust-read",
        str(viewer.id) if viewer is not None else client_ip(request),
        120,
        600,
    )
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="委托不存在")
    if task.is_anonymous and not _is_participant(task, viewer):
        return {"anonymous": True, "publisher": None, "members": []}
    members = [
        present_public(db, member.user_id, viewer)
        for member in task.members
        if member.response_status == TaskMemberResponse.ACCEPTED
    ]
    return {
        "anonymous": bool(task.is_anonymous),
        "publisher": present_public(db, task.publisher_id, viewer),
        "members": members,
    }
