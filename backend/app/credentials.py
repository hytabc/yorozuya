"""委托完成凭证与创作者作品集。

凭证在委托进入 ``completed`` 的**同一事务**内签发，内容在签发时快照，
后续修改委托标题/技能/资料都不会改变历史凭证。幂等键是 ``(task_id, taker_id)``。

编号 ``WS-{年份}-{id 补 6 位}`` 由数据库自增 ID 生成，不需要额外计数器表；
年份前缀只是给人看的，跨年也不会冲突。
"""
from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from .database import Base, get_db
from .dependencies import get_content_moderator, get_current_user, get_optional_user
from .models import Task, TaskMember, TaskMemberResponse, TaskStatus, User
from .ratelimit import enforce
from .schemas import RequestModel

VISIBILITY_PUBLIC = "public"
VISIBILITY_LINK = "link"
VISIBILITY_PRIVATE = "private"
VISIBILITIES = (VISIBILITY_PUBLIC, VISIBILITY_LINK, VISIBILITY_PRIVATE)

VERIFY_NOTE = "本凭证基于本站的委托完成记录生成，可在站内通过编号验证；不代表 VRChat 官方认证，也不代表平台对交易质量作出担保。"


class TaskCredential(Base):
    __tablename__ = "task_credentials"
    __table_args__ = (UniqueConstraint("task_id", "taker_id", name="uq_task_credential"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # 先插入取自增 ID，再回填编号；两个步骤在同一个事务里，对外不会看到空编号。
    serial: Mapped[str | None] = mapped_column(String(24), unique=True, nullable=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), nullable=False, index=True)
    taker_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    taker_name: Mapped[str] = mapped_column(String(32), nullable=False)
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    visibility: Mapped[str] = mapped_column(String(8), nullable=False, default=VISIBILITY_LINK)
    issued_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    admin_note: Mapped[str | None] = mapped_column(String(200), nullable=True)


class VisibilityUpdate(RequestModel):
    visibility: str = Field(pattern=r"^(public|link|private)$")


class AdminCredentialUpdate(RequestModel):
    revoked: bool
    admin_note: str | None = Field(default=None, max_length=200)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() + "Z" if value else None


def build_snapshot(db: Session, task: Task) -> dict:
    from .facets import TaskFacet

    facets = db.scalars(select(TaskFacet).where(TaskFacet.task_id == task.id)).all()

    def values(kind: str) -> list[str]:
        return [item.value for item in facets if item.facet_type == kind]

    return {
        "title": task.title,
        "category": task.category,
        "pay_type": task.pay_type,
        "reward": task.reward,
        "skills": values("skill"),
        "platforms": values("platform"),
        "worlds": values("world"),
        "publisher": "匿名委托" if task.is_anonymous else task.publisher.nickname,
        "publisher_id": None if task.is_anonymous else task.publisher_id,
        "completed_at": _iso(task.completed_at),
    }


def issue_for_task(db: Session, task: Task) -> list[TaskCredential]:
    """在完成委托的同一事务里为每位已接受成员签发凭证（幂等）。"""
    if task.status != TaskStatus.COMPLETED:
        return []
    existing = set(
        db.scalars(select(TaskCredential.taker_id).where(TaskCredential.task_id == task.id)).all()
    )
    snapshot = json.dumps(build_snapshot(db, task), ensure_ascii=False)
    issued: list[TaskCredential] = []
    for member in task.members:
        if member.response_status != TaskMemberResponse.ACCEPTED:
            continue
        if member.user_id in existing:
            continue
        credential = TaskCredential(
            task_id=task.id,
            taker_id=member.user_id,
            taker_name=member.user.nickname,
            snapshot_json=snapshot,
            visibility=VISIBILITY_LINK,
        )
        db.add(credential)
        issued.append(credential)
    if not issued:
        return []
    db.flush()
    for credential in issued:
        credential.serial = f"WS-{datetime.utcnow().year}-{credential.id:06d}"
    return issued


def load_snapshot(credential: TaskCredential) -> dict:
    try:
        return json.loads(credential.snapshot_json or "{}")
    except (TypeError, ValueError):
        return {}


def present(credential: TaskCredential) -> dict:
    snapshot = load_snapshot(credential)
    return {
        "serial": credential.serial,
        "task_id": credential.task_id,
        "title": snapshot.get("title", ""),
        "category": snapshot.get("category", ""),
        "skills": snapshot.get("skills", []),
        "platforms": snapshot.get("platforms", []),
        "worlds": snapshot.get("worlds", []),
        "publisher": snapshot.get("publisher", ""),
        "publisher_id": snapshot.get("publisher_id"),
        "taker": credential.taker_name,
        "taker_id": credential.taker_id,
        "completed_at": snapshot.get("completed_at"),
        "issued_at": _iso(credential.issued_at),
        "visibility": credential.visibility,
        "revoked": credential.revoked_at is not None,
        "revoked_at": _iso(credential.revoked_at),
        "verify_note": VERIFY_NOTE,
    }


def visible_to(credential: TaskCredential, viewer: User | None) -> bool:
    if credential.visibility == VISIBILITY_PRIVATE:
        return viewer is not None and (viewer.id == credential.taker_id or viewer.is_admin)
    # public / link 都可通过编号访问；区别只在于是否出现在作品集列表里。
    return True


def credential_by_serial(db: Session, serial: str) -> TaskCredential:
    credential = db.scalar(select(TaskCredential).where(TaskCredential.serial == serial))
    if credential is None:
        raise HTTPException(status_code=404, detail="凭证不存在")
    return credential


router = APIRouter(prefix="/api/credentials", tags=["credentials"])


@router.get("/mine")
def my_credentials(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(TaskCredential)
        .where(TaskCredential.taker_id == user.id)
        .order_by(TaskCredential.issued_at.desc())
    ).all()
    return [present(row) for row in rows]


@router.get("/{serial}")
def credential_detail(
    serial: str,
    viewer: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    credential = credential_by_serial(db, serial)
    if not visible_to(credential, viewer):
        # 私有凭证对未授权访问返回 404，避免通过编号探测存在性。
        raise HTTPException(status_code=404, detail="凭证不存在")
    return present(credential)


@router.patch("/{serial}/visibility")
def update_visibility(
    serial: str,
    payload: VisibilityUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    enforce("credential-visibility", str(user.id), 30, 600)
    credential = credential_by_serial(db, serial)
    if credential.taker_id != user.id:
        raise HTTPException(status_code=403, detail="只能修改自己的凭证可见性")
    credential.visibility = payload.visibility
    db.commit()
    return present(credential)


admin_router = APIRouter(prefix="/api/admin/credentials", tags=["credential moderation"])


@admin_router.patch("/{credential_id}")
def moderate_credential(
    credential_id: int,
    payload: AdminCredentialUpdate,
    moderator: User = Depends(get_content_moderator),
    db: Session = Depends(get_db),
):
    """撤销 / 恢复凭证：撤销后公开页显示「已失效」，记录不物理删除。"""
    credential = db.get(TaskCredential, credential_id)
    if credential is None:
        raise HTTPException(status_code=404, detail="凭证不存在")
    if payload.revoked:
        credential.revoked_at = datetime.utcnow()
        credential.revoked_by_id = moderator.id
        credential.admin_note = payload.admin_note
    else:
        credential.revoked_at = None
        credential.revoked_by_id = None
        credential.admin_note = None
    db.commit()
    return present(credential)


portfolio_router = APIRouter(prefix="/api/creators", tags=["creator portfolio"])


def portfolio_tag_counts(db: Session, user_id: int) -> list[dict]:
    """从完成记录反向生成标签：同一技能完成 ≥ 2 次才展示，用户不能自选。"""
    rows = db.scalars(
        select(TaskCredential).where(
            TaskCredential.taker_id == user_id,
            TaskCredential.revoked_at.is_(None),
            TaskCredential.visibility.in_([VISIBILITY_PUBLIC, VISIBILITY_LINK]),
        ).order_by(TaskCredential.issued_at.desc())
    ).all()
    counts: dict[str, dict] = {}
    for row in rows:
        snapshot = load_snapshot(row)
        for skill in snapshot.get("skills", [])[:6]:
            entry = counts.setdefault(
                skill,
                {"value": skill, "count": 0, "last_at": snapshot.get("completed_at")},
            )
            entry["count"] += 1
    return [entry for entry in counts.values() if entry["count"] >= 2]


@portfolio_router.get("/{user_id}")
def portfolio(
    user_id: int,
    viewer: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    from .main import present_user_profile

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=404, detail="用户不存在")
    credential_count = db.scalar(
        select(func.count()).select_from(TaskCredential).where(
            TaskCredential.taker_id == user_id,
            TaskCredential.revoked_at.is_(None),
            TaskCredential.visibility == VISIBILITY_PUBLIC,
        )
    ) or 0
    return {
        "user": present_user_profile(user, viewer),
        "credential_count": credential_count,
        "tags": portfolio_tag_counts(db, user_id),
    }


@portfolio_router.get("/{user_id}/credentials")
def portfolio_credentials(
    user_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """凭证墙：只列出「公开」且未撤销的凭证，沿用全站分页约定。"""
    query = select(TaskCredential).where(
        TaskCredential.taker_id == user_id,
        TaskCredential.revoked_at.is_(None),
        TaskCredential.visibility == VISIBILITY_PUBLIC,
    ).order_by(TaskCredential.issued_at.desc())
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()
    return {"total": total, "page": page, "page_size": page_size, "items": [present(row) for row in rows]}
