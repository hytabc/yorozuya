"""每日任务中心：固定 5 项，按 Asia/Shanghai 自然日刷新。

进度全部由现有业务表实时计算（不额外记流水），领取后才写
``user_daily_claims`` 并发放积分，因此重复领取会被唯一约束挡住。
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from .database import Base, get_db
from .dependencies import get_current_user
from .models import Task, TaskMember, TaskMemberResponse, TaskStatus, User
from .points import award_points, day_start_utc
from .ratings import TaskRating
from .schemas import DailyOut, DailyTaskOut, DailyClaimOut
from .shares import TaskShare

DAILY_TASKS = (
    {"key": "publish", "label": "发布 1 份委托", "detail": "描述不少于 30 字", "reward": 2, "target": 1},
    {"key": "complete", "label": "完成 1 次委托", "detail": "完成确认后计入", "reward": 4, "target": 1},
    {"key": "rate", "label": "评价 1 次协作", "detail": "半星也算", "reward": 1, "target": 1},
    {"key": "share", "label": "分享 1 份委托", "detail": "同一份委托每天只计一次", "reward": 1, "target": 1},
    {"key": "all_clear", "label": "完成全部每日任务", "detail": "额外奖励", "reward": 2, "target": 4},
)
DAILY_KEYS = {item["key"] for item in DAILY_TASKS}
MAIN_TASKS = ("publish", "complete", "rate", "share")

class UserDailyClaim(Base):
    __tablename__ = "user_daily_claims"
    __table_args__ = (UniqueConstraint("user_id", "day", "task_key", name="uq_daily_claim"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    # 自然日字符串（Asia/Shanghai），例如 2026-11-04。
    day: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    task_key: Mapped[str] = mapped_column(String(16), nullable=False)
    reward: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


def current_day(now: datetime | None = None) -> str:
    """按 Asia/Shanghai 计算自然日字符串。"""
    from .points import LOCAL_TZ

    local = (now or datetime.utcnow()).replace(tzinfo=timezone.utc).astimezone(LOCAL_TZ)
    return local.strftime("%Y-%m-%d")


def _claimed_keys(db: Session, user_id: int, day: str) -> dict[str, UserDailyClaim]:
    rows = db.scalars(
        select(UserDailyClaim).where(UserDailyClaim.user_id == user_id, UserDailyClaim.day == day)
    ).all()
    return {row.task_key: row for row in rows}


def _progress(db: Session, user_id: int, start: datetime) -> dict[str, int]:
    published = db.scalar(
        select(func.count()).select_from(Task).where(
            Task.publisher_id == user_id,
            Task.created_at >= start,
            func.length(Task.description) >= 30,
        )
    ) or 0
    completed = db.scalar(
        select(func.count(func.distinct(Task.id)))
        .select_from(Task)
        .join(TaskMember, TaskMember.task_id == Task.id)
        .where(
            TaskMember.user_id == user_id,
            TaskMember.response_status == TaskMemberResponse.ACCEPTED,
            Task.status == TaskStatus.COMPLETED,
            Task.completed_at >= start,
        )
    ) or 0
    completed_published = db.scalar(
        select(func.count()).select_from(Task).where(
            Task.publisher_id == user_id,
            Task.status == TaskStatus.COMPLETED,
            Task.completed_at >= start,
        )
    ) or 0
    rated = db.scalar(
        select(func.count()).select_from(TaskRating).where(
            TaskRating.rater_id == user_id,
            TaskRating.created_at >= start,
        )
    ) or 0
    shared = db.scalar(
        select(func.count(func.distinct(TaskShare.task_id))).where(
            TaskShare.user_id == user_id,
            TaskShare.created_at >= start,
        )
    ) or 0
    return {
        "publish": published,
        "complete": completed + completed_published,
        "rate": rated,
        "share": shared,
    }


def daily_snapshot(db: Session, user: User) -> DailyOut:
    day = current_day()
    start = day_start_utc()
    progress = _progress(db, user.id, start)
    claims = _claimed_keys(db, user.id, day)
    main_claimed = sum(1 for key in MAIN_TASKS if key in claims)
    progress["all_clear"] = main_claimed
    items: list[DailyTaskOut] = []
    for task in DAILY_TASKS:
        claimed = task["key"] in claims
        reached = progress[task["key"]] >= task["target"]
        items.append(
            DailyTaskOut(
                key=task["key"],
                label=task["label"],
                detail=task["detail"],
                reward=task["reward"],
                target=task["target"],
                progress=min(progress[task["key"]], task["target"]),
                claimed=claimed,
                can_claim=reached and not claimed,
            )
        )
    return DailyOut(day=day, items=items, claimed_count=len(claims))


router = APIRouter(prefix="/api/daily", tags=["daily"])


@router.get("", response_model=DailyOut)
def my_daily(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return daily_snapshot(db, user)


@router.post("/{task_key}/claim", response_model=DailyClaimOut)
def claim_daily(
    task_key: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if task_key not in DAILY_KEYS:
        raise HTTPException(status_code=404, detail="每日任务不存在")
    day = current_day()
    start = day_start_utc()
    progress = _progress(db, user.id, start)
    claims = _claimed_keys(db, user.id, day)
    progress["all_clear"] = sum(1 for key in MAIN_TASKS if key in claims)
    task = next(item for item in DAILY_TASKS if item["key"] == task_key)
    if task_key in claims:
        raise HTTPException(status_code=409, detail="今日已领取过该任务")
    if progress[task_key] < task["target"]:
        raise HTTPException(status_code=409, detail="任务尚未完成")
    claim = UserDailyClaim(user_id=user.id, day=day, task_key=task_key, reward=task["reward"])
    db.add(claim)
    db.flush()
    award_points(
        db,
        user.id,
        kind="daily",
        lifetime=task["reward"],
        wallet=task["reward"],
        note=f"每日任务：{task['label']}",
        source_type="daily_claim",
        source_id=claim.id,
        idempotent=True,
    )
    db.commit()
    db.refresh(user)
    return DailyClaimOut(
        key=task_key,
        reward=task["reward"],
        day=day,
        lifetime_points=user.lifetime_points,
        wallet_points=user.wallet_points,
        daily=daily_snapshot(db, user),
    )
