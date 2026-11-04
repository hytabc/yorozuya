"""积分账户与流水。

积分分两个口袋：

- ``lifetime_points``：终身累计，只增不减，用于等级、排行榜与成就；
- ``wallet_points``：可用余额，只能用于发布悬赏（托管时扣除），不对外公开。

唯一的积分散发入口是 :func:`award_points`，它同时写流水，便于审计与对账。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func, select, update
from sqlalchemy.orm import Mapped, Session, mapped_column

from .database import Base, get_db
from .dependencies import get_current_user
from .models import Task, TaskMember, TaskMemberResponse, TaskStatus, User
from .schemas import PointLedgerOut, PointLedgerPage, PointsRules, PointsSummary

# 每日上限只统计系统发放的积分；悬赏、成就、邀请、每日任务不计入。
SYSTEM_POINT_KINDS = ("task_reward", "rating_settle")
LOCAL_TZ = ZoneInfo("Asia/Shanghai")

# 系统基础积分：档位 × 分类系数，四舍五入取整，最低 1 分。
SCALE_POINTS = {"small": 5, "medium": 15, "large": 40}
SCALE_LABELS = {"small": "小", "medium": "中", "large": "大"}
CATEGORY_FACTORS = {
    "萌新上路": 0.8,
    "心理倾听": 1.2,
    "技术疑难": 1.3,
    "VRC寻图": 1.0,
    "搭子召集": 0.9,
    "其他委托": 1.0,
}
BOUNTY_MIN = 0
BOUNTY_MAX = 200
# 完成时先发基础积分的 60%，评价后按星级结算尾款。
ADVANCE_RATIO = 0.6
# 防刷：同一对用户重复合作的系统积分衰减（第 1/2/3 次，第 4 次起为 0）。
PAIR_DECAY = {1: 1.0, 2: 0.5, 3: 0.25}
# 防刷：每日可获得的系统积分上限（悬赏、成就、邀请不受限）。
DAILY_SYSTEM_CAP = 60
# 防刷：注册 7 天内的新账号获得的系统积分减半。
NEW_ACCOUNT_DAYS = 7
NEW_ACCOUNT_FACTOR = 0.5


def _round_half_up(value: float) -> int:
    """四舍五入（Python 内置 round 是银行家舍入，2.5 会变 2，积分场景不适合）。"""
    return int(value + 0.5) if value >= 0 else -int(-value + 0.5)


def task_base_points(category: str, scale: str) -> int:
    return max(1, _round_half_up(SCALE_POINTS.get(scale, SCALE_POINTS["small"]) * CATEGORY_FACTORS.get(category, 1.0)))


def day_start_utc(now: datetime | None = None) -> datetime:
    """以 Asia/Shanghai 的 0 点作为「今天」的边界，返回 UTC naive 时间。"""
    current = (now or datetime.utcnow()).replace(tzinfo=timezone.utc).astimezone(LOCAL_TZ)
    return current.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc).replace(tzinfo=None)


def system_points_today(db: Session, user_id: int) -> int:
    return db.scalar(
        select(func.coalesce(func.sum(PointLedger.lifetime_delta), 0)).where(
            PointLedger.user_id == user_id,
            PointLedger.kind.in_(SYSTEM_POINT_KINDS),
            PointLedger.created_at >= day_start_utc(),
        )
    ) or 0


def remaining_system_points(db: Session, user_id: int) -> int:
    return max(0, DAILY_SYSTEM_CAP - system_points_today(db, user_id))


def pair_completed_count(db: Session, publisher_id: int, taker_id: int, exclude_task_id: int) -> int:
    return db.scalar(
        select(func.count(func.distinct(Task.id)))
        .select_from(Task)
        .join(TaskMember, TaskMember.task_id == Task.id)
        .where(
            Task.publisher_id == publisher_id,
            TaskMember.user_id == taker_id,
            Task.status == TaskStatus.COMPLETED,
            Task.id != exclude_task_id,
        )
    ) or 0


def effective_system_points(db: Session, task: Task, member: TaskMember) -> int:
    """按同对衰减与新号折扣折算本次可得的系统基础积分。"""
    collaboration = pair_completed_count(db, task.publisher_id, member.user_id, task.id) + 1
    factor = PAIR_DECAY.get(collaboration, 0.0)
    created_at = member.user.created_at if member.user is not None else None
    if created_at is not None and created_at > datetime.utcnow() - timedelta(days=NEW_ACCOUNT_DAYS):
        factor *= NEW_ACCOUNT_FACTOR
    return max(0, _round_half_up(task.base_points * factor))


def escrow_bounty(db: Session, task: Task) -> bool:
    """发布时把悬赏积分从钱包托管（同事务，失败则整笔委托回滚）。"""
    if task.bounty_points <= 0:
        return False
    return award_points(
        db,
        task.publisher_id,
        kind="bounty_escrow",
        wallet=-task.bounty_points,
        note=f"托管悬赏《{task.title}》",
        source_type="task",
        source_id=task.id,
    )


def refund_bounty(db: Session, task: Task) -> bool:
    """取消/过期时把托管中的悬赏全额退回发布者（幂等）。"""
    if task.bounty_points <= 0:
        return False
    return award_points(
        db,
        task.publisher_id,
        kind="bounty_refund",
        wallet=task.bounty_points,
        note=f"退回悬赏《{task.title}》",
        source_type="task",
        source_id=task.id,
    )


def award_task_completion(db: Session, task: Task) -> None:
    """委托完成时发放基础积分预付款与悬赏（幂等，可在同一事务里调用）。"""
    takers = [member for member in task.members if member.response_status == TaskMemberResponse.ACCEPTED]
    if not takers:
        refund_bounty(db, task)
        return
    for member in takers:
        earned = effective_system_points(db, task, member)
        member.base_points_earned = earned
        advance = min(_round_half_up(earned * ADVANCE_RATIO), remaining_system_points(db, member.user_id))
        if advance <= 0:
            continue
        award_points(
            db,
            member.user_id,
            kind="task_reward",
            lifetime=advance,
            wallet=advance,
            note=f"完成《{task.title}》",
            source_type="task",
            source_id=task.id,
        )
    if task.bounty_points <= 0:
        return
    share, remainder = divmod(task.bounty_points, len(takers))
    for member in takers:
        if share:
            award_points(
                db,
                member.user_id,
                kind="bounty_reward",
                lifetime=share,
                wallet=share,
                note=f"《{task.title}》悬赏",
                source_type="task",
                source_id=task.id,
            )
    if remainder:
        award_points(
            db,
            task.publisher_id,
            kind="bounty_remainder",
            wallet=remainder,
            note=f"《{task.title}》悬赏余数退回",
            source_type="task",
            source_id=task.id,
        )

POINT_KIND_LABELS = {
    "task_reward": "委托奖励",
    "task_bounty": "悬赏积分",
    "bounty_escrow": "托管悬赏",
    "bounty_refund": "退回悬赏",
    "bounty_reward": "悬赏收入",
    "bounty_remainder": "悬赏余数退回",
    "rating_settle": "评价结算",
    "rating_adjust": "评价调整",
    "rating_revoke": "申诉调整",
    "achievement": "成就奖励",
    "invite": "邀请奖励",
    "invited": "受邀奖励",
    "daily": "每日任务",
    "backfill": "历史补偿",
}


class PointLedger(Base):
    __tablename__ = "point_ledger"
    __table_args__ = (
        # 同一来源（例如同一份委托的同一类奖励）只入账一次，重复调用直接跳过。
        UniqueConstraint("user_id", "kind", "source_type", "source_id", name="uq_point_ledger_source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    # 终身累计变化（永远 >= 0）与可用余额变化（可为负）。
    lifetime_delta: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    wallet_delta: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    note: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # 幂等来源：例如 source_type="task", source_id=<任务 ID>。
    source_type: Mapped[str | None] = mapped_column(String(24), nullable=True)
    source_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


def award_points(
    db: Session,
    user_id: int,
    *,
    kind: str,
    lifetime: int = 0,
    wallet: int = 0,
    note: str | None = None,
    source_type: str | None = None,
    source_id: int | None = None,
    idempotent: bool = True,
) -> bool:
    """给用户发积分并写流水；返回是否真的入账。

    调用方负责提交事务（通常在业务动作的同一事务里调用，保证状态与积分一致）。
    """
    lifetime = max(0, lifetime)
    if lifetime == 0 and wallet == 0:
        return False
    if idempotent and source_type is not None and source_id is not None:
        exists = db.scalar(
            select(PointLedger.id).where(
                PointLedger.user_id == user_id,
                PointLedger.kind == kind,
                PointLedger.source_type == source_type,
                PointLedger.source_id == source_id,
            )
        )
        if exists is not None:
            return False

    user = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if user is None:
        return False
    # 可用余额不允许为负：扣分时按实际能扣多少记账。
    actual_wallet = wallet
    if actual_wallet < 0:
        actual_wallet = -min(user.wallet_points, -actual_wallet)
    if lifetime == 0 and actual_wallet == 0:
        return False

    db.execute(
        update(User)
        .where(User.id == user_id)
        .values(
            lifetime_points=User.lifetime_points + lifetime,
            wallet_points=User.wallet_points + actual_wallet,
        )
    )
    db.add(
        PointLedger(
            user_id=user_id,
            kind=kind,
            lifetime_delta=lifetime,
            wallet_delta=actual_wallet,
            note=note,
            source_type=source_type,
            source_id=source_id,
        )
    )
    return True


router = APIRouter(prefix="/api/points", tags=["points"])


@router.get("/rules", response_model=PointsRules)
def points_rules():
    return PointsRules(
        scale_points=SCALE_POINTS,
        scale_labels=SCALE_LABELS,
        category_factors=CATEGORY_FACTORS,
        bounty_min=BOUNTY_MIN,
        bounty_max=BOUNTY_MAX,
        advance_ratio=ADVANCE_RATIO,
        pair_decay=PAIR_DECAY,
        daily_system_cap=DAILY_SYSTEM_CAP,
        new_account_days=NEW_ACCOUNT_DAYS,
        new_account_factor=NEW_ACCOUNT_FACTOR,
    )


@router.get("/me", response_model=PointsSummary)
def my_points(user: User = Depends(get_current_user)):
    return PointsSummary(lifetime_points=user.lifetime_points, wallet_points=user.wallet_points)


@router.get("/ledger", response_model=PointLedgerPage)
def my_ledger(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    total = db.scalar(
        select(func.count()).select_from(PointLedger).where(PointLedger.user_id == user.id)
    ) or 0
    rows = db.scalars(
        select(PointLedger)
        .where(PointLedger.user_id == user.id)
        .order_by(PointLedger.created_at.desc(), PointLedger.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    items = [
        PointLedgerOut(
            id=row.id,
            kind=row.kind,
            kind_label=POINT_KIND_LABELS.get(row.kind, "积分变动"),
            lifetime_delta=row.lifetime_delta,
            wallet_delta=row.wallet_delta,
            note=row.note,
            created_at=row.created_at,
        )
        for row in rows
    ]
    return PointLedgerPage(total=total, page=page, page_size=page_size, items=items)
