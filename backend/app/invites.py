"""邀请码：注册绑定、首单奖励与月度上限。

规则：

- 每个账号一个 8 位永久邀请码（去掉易混字符）；
- 注册时可填邀请码，注册后 7 天内可补填一次，终身只能绑定一个邀请人；
- 奖励不在注册时发放，而是在被邀请人**首次完成委托**后触发；
- 邀请人每月最多 5 个有效邀请计分，超出只记录；被邀请人封号/刷分不回收（无自动判定）。
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .database import get_db
from .dependencies import get_current_user
from .models import Task, TaskMember, TaskMemberResponse, TaskStatus, User
from .points import LOCAL_TZ, award_points
from .schemas import InviteBindRequest, InviteInfoOut


def month_start_utc() -> datetime:
    """当前自然月的起点（按 Asia/Shanghai 切月），返回 UTC naive。"""
    local = datetime.utcnow().replace(tzinfo=timezone.utc).astimezone(LOCAL_TZ)
    start = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return start.astimezone(timezone.utc).replace(tzinfo=None)

INVITE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
INVITE_CODE_LENGTH = 8
INVITE_BIND_DAYS = 7
INVITER_BONUS = 20
INVITEE_BONUS = 10
MONTHLY_VALID_LIMIT = 5


def generate_invite_code(db: Session) -> str:
    for _ in range(20):
        code = "".join(secrets.choice(INVITE_ALPHABET) for _ in range(INVITE_CODE_LENGTH))
        if db.scalar(select(User.id).where(User.invite_code == code)) is None:
            return code
    raise RuntimeError("无法生成唯一邀请码，请检查用户量或随机源")


def ensure_invite_code(db: Session, user: User) -> str:
    if not user.invite_code:
        user.invite_code = generate_invite_code(db)
    return user.invite_code


def resolve_code(db: Session, code: str) -> User | None:
    cleaned = (code or "").strip().upper()
    if not cleaned:
        return None
    return db.scalar(select(User).where(User.invite_code == cleaned))


def bind_inviter(db: Session, user: User, code: str) -> User:
    cleaned = (code or "").strip().upper()
    if not cleaned:
        raise HTTPException(status_code=422, detail="邀请码不能为空")
    if user.invited_by_id is not None:
        raise HTTPException(status_code=409, detail="你已经绑定过邀请人，不能重复绑定")
    if datetime.utcnow() > user.created_at + timedelta(days=INVITE_BIND_DAYS):
        raise HTTPException(status_code=409, detail=f"注册后 {INVITE_BIND_DAYS} 天内才能填写邀请码")
    inviter = resolve_code(db, cleaned)
    if inviter is None:
        raise HTTPException(status_code=404, detail="邀请码不存在")
    if inviter.id == user.id:
        raise HTTPException(status_code=422, detail="不能填写自己的邀请码")
    user.invited_by_id = inviter.id
    return inviter


def _completed_participation_count(db: Session, user_id: int) -> int:
    published = db.scalar(
        select(func.count()).select_from(Task).where(
            Task.publisher_id == user_id,
            Task.status == TaskStatus.COMPLETED,
            Task.is_official.is_(False),
        )
    ) or 0
    taken = db.scalar(
        select(func.count(func.distinct(Task.id)))
        .select_from(Task)
        .join(TaskMember, TaskMember.task_id == Task.id)
        .where(
            TaskMember.user_id == user_id,
            TaskMember.response_status == TaskMemberResponse.ACCEPTED,
            Task.status == TaskStatus.COMPLETED,
            Task.is_official.is_(False),
        )
    ) or 0
    return published + taken


def _valid_invites_this_month(db: Session, inviter_id: int) -> int:
    from .points import PointLedger

    return db.scalar(
        select(func.count()).select_from(PointLedger).where(
            PointLedger.user_id == inviter_id,
            PointLedger.kind == "invite",
            PointLedger.source_type == "user",
            PointLedger.created_at >= month_start_utc(),
        )
    ) or 0


def maybe_reward_invite(db: Session, user: User) -> bool:
    """被邀请人完成的首个委托触发邀请奖励；返回是否真的发放。"""
    if user.invited_by_id is None:
        return False
    if _completed_participation_count(db, user.id) != 1:
        return False
    inviter = db.get(User, user.invited_by_id)
    if inviter is None:
        return False
    if _valid_invites_this_month(db, inviter.id) >= MONTHLY_VALID_LIMIT:
        return False
    awarded = award_points(
        db,
        inviter.id,
        kind="invite",
        lifetime=INVITER_BONUS,
        wallet=INVITER_BONUS,
        note=f"邀请 {user.nickname} 完成首个委托",
        source_type="user",
        source_id=user.id,
        idempotent=True,
    )
    if not awarded:
        return False
    award_points(
        db,
        user.id,
        kind="invited",
        lifetime=INVITEE_BONUS,
        wallet=INVITEE_BONUS,
        note="受邀完成首个委托",
        source_type="user",
        source_id=user.id,
        idempotent=True,
    )
    return True


router = APIRouter(prefix="/api/invite", tags=["invite"])


@router.get("/me", response_model=InviteInfoOut)
def my_invite(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    code = ensure_invite_code(db, user)
    db.commit()
    invited = db.scalar(select(func.count()).select_from(User).where(User.invited_by_id == user.id)) or 0
    return InviteInfoOut(
        code=code,
        invited_total=invited,
        valid_this_month=_valid_invites_this_month(db, user.id),
        monthly_limit=MONTHLY_VALID_LIMIT,
        inviter_bonus=INVITER_BONUS,
        invitee_bonus=INVITEE_BONUS,
        invited_by=user.invited_by_id is not None,
        can_bind=user.invited_by_id is None
        and datetime.utcnow() <= user.created_at + timedelta(days=INVITE_BIND_DAYS),
    )


@router.post("/bind", response_model=InviteInfoOut)
def bind(payload: InviteBindRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    bind_inviter(db, user, payload.code)
    db.commit()
    return my_invite(user=user, db=db)
