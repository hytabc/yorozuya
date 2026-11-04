"""VRChat 身份（软绑定：未验证、不调用外部 API）。

本站**没有**接入 VRChat 官方认证：用户提交的是自己的显示名与个人主页链接，
服务端只做格式校验与「同一主页不可被两个账号占用」的唯一性约束，
并以 ``verified=false`` 明确标注「未验证 · 手动填写」。

设计约束：
- 不保存任何 VRChat 密码、会话 Cookie 或令牌；
- 不伪造 Trust Rank / 账号年龄 / 共同好友（这些字段保留但恒为空）；
- 所有展示字段都按用户逐项披露开关裁剪，且裁剪发生在**接口层**；
- 匿名委托的信任信息在接口层直接裁剪，不依赖前端隐藏。
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from .database import Base, get_db
from .dependencies import get_admin, get_current_user, get_role_manager
from .models import AppSetting, Task, TaskMember, TaskMemberResponse, User
from .ratelimit import enforce
from .schemas import RequestModel

# 与 frontend/src/trust.js 的 TRUST_DISCLOSURE 保持一致。
DISCLOSURE_KEYS = (
    "identity",
    "trust_rank",
    "account_age",
    "common_friends",
    "common_groups",
    "worlds",
)
DEFAULT_DISCLOSURE = {key: False for key in DISCLOSURE_KEYS}

STATUS_UNVERIFIED = "unverified"
STATUS_UNLINKED = "unlinked"

# VRChat 用户 ID 形如 usr_c1644b5b-3ca4-45b4-97c6-a2a0de70d469，
# 同时也接受 usr_ 开头的短形式（测试与老链接）。
VRCHAT_USER_ID = re.compile(r"usr_[0-9a-fA-F-]{4,}")
VRCHAT_HOSTS = {"vrchat.com", "www.vrchat.com"}


class VRChatIdentity(Base):
    __tablename__ = "vrchat_identities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)
    # 未验证的软绑定：同一个 VRChat 主页不能被两个本站账号同时占用。
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
    # 留作将来接入真实同步时记录最近一次失败原因；软绑定下恒为空。
    last_error: Mapped[str | None] = mapped_column(String(200), nullable=True)


class LinkRequest(RequestModel):
    display_name: str = Field(min_length=1, max_length=64)
    # VRChat 个人主页链接（或直接粘贴 usr_ 开头的用户 ID）。
    profile: str = Field(min_length=4, max_length=255)


class DisclosureUpdate(RequestModel):
    identity: bool | None = None
    trust_rank: bool | None = None
    account_age: bool | None = None
    common_friends: bool | None = None
    common_groups: bool | None = None
    worlds: bool | None = None


class AdminConfigUpdate(RequestModel):
    enabled: bool | None = None
    allow_new_links: bool | None = None


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
        row = AppSetting(key=key, value="1" if value else "0")
        db.add(row)
    else:
        row.value = "1" if value else "0"


def integration_state(db: Session) -> dict:
    return {
        "enabled": _flag(db, "vrchat_enabled", True),
        "allow_new_links": _flag(db, "vrchat_allow_new_links", True),
    }


def present_self(identity: VRChatIdentity | None) -> dict:
    if identity is None:
        return {"bound": False, "status": None, "disclosure": dict(DEFAULT_DISCLOSURE)}
    return {
        "bound": identity.status == STATUS_UNVERIFIED,
        "status": identity.status,
        "display_name": identity.display_name,
        "profile_url": identity.profile_url,
        "verified": False,
        "source": "manual",
        "linked_at": identity.linked_at.isoformat() + "Z",
        "disclosure": load_disclosure(identity),
        # 软绑定没有真实同步时间；保留字段让前端能区分「未绑定」与「未同步」。
        "last_synced_at": None,
    }


def present_public(db: Session, user_id: int, viewer: User) -> dict:
    """对他人展示的信任摘要：只返回用户主动披露的部分。"""
    identity = identity_of(db, user_id)
    if identity is None or identity.status != STATUS_UNVERIFIED:
        return {"user_id": user_id, "bound": False, "verified": False}
    disclosure = load_disclosure(identity)
    result = {
        "user_id": user_id,
        "bound": True,
        "verified": False,
        "source": "manual",
        "linked_at": identity.linked_at.isoformat() + "Z",
        "disclosed": any(disclosure.values()),
    }
    # 显示名与主页链接同属 identity 一项；未开启时接口层直接不返回。
    if viewer.id == user_id or disclosure["identity"]:
        result["display_name"] = identity.display_name
        result["profile_url"] = identity.profile_url
    return result


router = APIRouter(prefix="/api/vrchat", tags=["vrchat identity"])


@router.get("/status")
def my_status(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    enforce("vrchat-trust-read", str(user.id), 120, 600)
    state = integration_state(db)
    return {**present_self(identity_of(db, user.id)), **state}


@router.post("/link")
def link_identity(
    payload: LinkRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """软绑定：只校验格式与唯一性，不做任何外部请求，也永远不保存密码。"""
    enforce("vrchat-link", str(user.id), 5, 3600)
    state = integration_state(db)
    if not state["enabled"]:
        raise HTTPException(status_code=503, detail="VRChat 身份功能当前已关闭")
    if not state["allow_new_links"]:
        raise HTTPException(status_code=503, detail="当前暂停接受新的 VRChat 绑定")
    vrchat_user_id, profile_url = parse_profile(payload.profile)
    taken = db.scalar(
        select(VRChatIdentity).where(
            VRChatIdentity.vrchat_user_id == vrchat_user_id,
            VRChatIdentity.user_id != user.id,
        )
    )
    if taken is not None:
        raise HTTPException(status_code=409, detail="该 VRChat 主页已被其他账号绑定")
    identity = identity_of(db, user.id)
    if identity is None:
        identity = VRChatIdentity(
            user_id=user.id,
            disclosure_json=dump_disclosure(DEFAULT_DISCLOSURE),
        )
        db.add(identity)
    # 重新绑定时保留用户已设置的披露开关，避免解绑/重绑把隐私设置重置成默认。
    identity.vrchat_user_id = vrchat_user_id
    identity.display_name = payload.display_name.strip()
    identity.profile_url = profile_url
    identity.status = STATUS_UNVERIFIED
    identity.link_method = "manual"
    identity.linked_at = datetime.utcnow()
    identity.last_error = None
    db.commit()
    return {**present_self(identity_of(db, user.id)), **integration_state(db)}


@router.post("/refresh")
def refresh(_: User = Depends(get_current_user)):
    """软绑定没有外部数据源：明确返回「未接入」，而不是假装刷新成功。"""
    raise HTTPException(status_code=400, detail="尚未接入 VRChat 数据同步，当前为手动填写的未验证身份")


@router.post("/unlink")
def unlink(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    enforce("vrchat-link", str(user.id), 5, 3600)
    identity = identity_of(db, user.id)
    if identity is None or identity.status == STATUS_UNLINKED:
        raise HTTPException(status_code=404, detail="当前账号没有绑定 VRChat 身份")
    # 解绑即清理展示数据与披露设置；行本身保留，用于已签发凭证标注「身份来源已解绑」。
    identity.status = STATUS_UNLINKED
    identity.display_name = None
    identity.profile_url = None
    identity.vrchat_user_id = None
    identity.disclosure_json = dump_disclosure(DEFAULT_DISCLOSURE)
    identity.updated_at = datetime.utcnow()
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
    if identity is None or identity.status != STATUS_UNVERIFIED:
        raise HTTPException(status_code=409, detail="请先绑定 VRChat 身份")
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
    """只返回数量与开关，不返回任何用户的社交数据。"""
    bound = db.scalar(
        select(func.count()).select_from(VRChatIdentity).where(VRChatIdentity.status == STATUS_UNVERIFIED)
    ) or 0
    unlinked = db.scalar(
        select(func.count()).select_from(VRChatIdentity).where(VRChatIdentity.status == STATUS_UNLINKED)
    ) or 0
    return {**integration_state(db), "bound": bound, "unlinked": unlinked}


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


# 读取他人信任摘要：路径挂在 /api/users、/api/tasks 下，因此单独用一个不带前缀的 router。
trust_router = APIRouter(prefix="/api", tags=["vrchat trust"])


@trust_router.get("/users/{user_id}/trust")
def user_trust(
    user_id: int,
    viewer: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    enforce("vrchat-trust-read", str(viewer.id), 120, 600)
    if db.get(User, user_id) is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return present_public(db, user_id, viewer)


def _is_participant(task: Task, viewer: User) -> bool:
    return viewer.is_admin or viewer.id == task.publisher_id or any(
        member.user_id == viewer.id for member in task.members
    )


@trust_router.get("/tasks/{task_id}/trust")
def task_trust(
    task_id: int,
    viewer: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """委托双方的信任摘要；匿名委托在**接口层**直接裁剪发布者侧信息。"""
    enforce("vrchat-trust-read", str(viewer.id), 120, 600)
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
