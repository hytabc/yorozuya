"""委托评价：0~5 星（半星步进，共 11 档）、双向互评、双盲与积分结算。

规则摘要：

- 只有已完成的委托可以评价，窗口为完成后 7 天；
- 委托人评接单人、接单人评委托人，双方各自独立；
- 双方都提交后立即互相可见，否则 7 天后解盲；
- 逾期未评自动记 3 星（无文字）；
- 提交后 24 小时内可修改一次；
- 0 星必须选择原因；≤2 星必须写至少 15 字说明；
- 委托人给接单人的星级决定该单系统积分的最终结算（基础积分 × 星级 / 5）。
"""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func, select
from sqlalchemy.orm import Mapped, Session, joinedload, mapped_column, relationship

from .database import Base, get_db
from .dependencies import get_current_user, get_optional_user
from .models import Task, TaskMember, TaskMemberResponse, TaskStatus, User
from .points import PointLedger, _round_half_up, award_points, remaining_system_points
from .schemas import (
    RatingCreate,
    RatingOut,
    RatingPublicOut,
    RatingPublicPage,
    RatingSlotOut,
    RatingStatsOut,
    RatingUpdate,
    TaskRatingsOut,
    UserRatingSummary,
)

RATING_WINDOW_DAYS = 7
RATING_EDIT_HOURS = 24
RATING_APPEAL_DAYS = 14
RATING_REASONS = {
    "not_delivered": "未交付",
    "breach": "严重失约",
    "delay": "恶意拖延",
    "harassment": "言语骚扰",
}
MIN_NEGATIVE_COMMENT = 15
MAX_COMMENT = 200
AUTO_STARS_HALF = 6
# 贝叶斯先验：相当于先给每个人 10 条 4.0 星评价，避免「只做一单 5 星」直接霸榜。
RATING_PRIOR_COUNT = 10
RATING_PRIOR_MEAN = 4.0


class TaskRating(Base):
    __tablename__ = "task_ratings"
    __table_args__ = (UniqueConstraint("task_id", "rater_id", "ratee_id", name="uq_task_rating_pair"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), nullable=False, index=True)
    rater_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    ratee_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    # publisher=委托人评接单人；taker=接单人评委托人。
    rater_role: Mapped[str] = mapped_column(String(12), nullable=False)
    # 星级以半星为单位存整数：0=0 星，10=5 星。
    stars_half: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason_code: Mapped[str | None] = mapped_column(String(24), nullable=True)
    # 逾期系统自动补评（3 星、无文字）。
    automatic: Mapped[bool] = mapped_column(Integer, default=0, nullable=False)
    # 差评申诉：确认撤销后不再计入聚合分。
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    admin_note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    task: Mapped[Task] = relationship()
    rater: Mapped[User] = relationship(foreign_keys=[rater_id])
    ratee: Mapped[User] = relationship(foreign_keys=[ratee_id])

    @property
    def stars(self) -> float:
        return self.stars_half / 2


def rating_deadline(task: Task) -> datetime | None:
    if task.completed_at is None:
        return None
    return task.completed_at + timedelta(days=RATING_WINDOW_DAYS)


def _now() -> datetime:
    return datetime.utcnow()


def _accepted_members(task: Task) -> list[TaskMember]:
    return [member for member in task.members if member.response_status == TaskMemberResponse.ACCEPTED]


def _validate_payload(stars_half: int, comment: str | None, reason_code: str | None) -> tuple[str | None, str | None]:
    comment = (comment or "").strip() or None
    reason_code = (reason_code or "").strip() or None
    if stars_half == 0 and reason_code not in RATING_REASONS:
        raise HTTPException(status_code=422, detail="0 星评价必须选择原因")
    if reason_code is not None and reason_code not in RATING_REASONS:
        raise HTTPException(status_code=422, detail="评价原因不正确")
    if stars_half <= 4 and (comment is None or len(comment) < MIN_NEGATIVE_COMMENT):
        raise HTTPException(status_code=422, detail=f"2 星及以下必须填写至少 {MIN_NEGATIVE_COMMENT} 字说明")
    if comment is not None and len(comment) > MAX_COMMENT:
        raise HTTPException(status_code=422, detail=f"评价内容不能超过 {MAX_COMMENT} 字")
    if stars_half > 4:
        reason_code = None
    return comment, reason_code


def apply_rating_settlement(db: Session, task: Task, taker_id: int, stars_half: int) -> None:
    """按委托人给接单人的星级结算系统积分尾款。

    ``already`` 是这单已经发出去的基础积分；差额为正时受每日上限约束，
    为负时只从钱包扣、终身累计不回退，且余额不足只扣到 0。
    """
    member = db.scalar(
        select(TaskMember).where(
            TaskMember.task_id == task.id,
            TaskMember.user_id == taker_id,
        )
    )
    if member is None:
        return
    base = member.base_points_earned or 0
    if base <= 0:
        return
    target = _round_half_up(base * (stars_half / 10))
    already = db.scalar(
        select(func.coalesce(func.sum(PointLedger.lifetime_delta), 0)).where(
            PointLedger.user_id == taker_id,
            PointLedger.kind == "task_reward",
            PointLedger.source_type == "task",
            PointLedger.source_id == task.id,
        )
    ) or 0
    delta = target - already
    if delta > 0:
        delta = min(delta, remaining_system_points(db, taker_id))
    if delta == 0:
        return
    first_settle = db.scalar(
        select(PointLedger.id).where(
            PointLedger.user_id == taker_id,
            PointLedger.kind == "rating_settle",
            PointLedger.source_type == "task",
            PointLedger.source_id == task.id,
        )
    ) is None
    award_points(
        db,
        taker_id,
        # 首次结算带来源便于对账；修改评价产生的差额不挂来源（同一来源允许多次调整）。
        kind="rating_settle" if first_settle else "rating_adjust",
        lifetime=max(0, delta),
        wallet=delta,
        note=f"《{task.title}》评价结算",
        source_type="task" if first_settle else None,
        source_id=task.id if first_settle else None,
        idempotent=first_settle,
    )


def upsert_rating(
    db: Session,
    task: Task,
    rater: User,
    ratee: User,
    rater_role: str,
    stars_half: int,
    comment: str | None,
    reason_code: str | None,
    *,
    automatic: bool = False,
) -> TaskRating:
    rating = db.scalar(
        select(TaskRating).where(
            TaskRating.task_id == task.id,
            TaskRating.rater_id == rater.id,
            TaskRating.ratee_id == ratee.id,
        )
    )
    if rating is None:
        rating = TaskRating(
            task_id=task.id,
            rater_id=rater.id,
            ratee_id=ratee.id,
            rater_role=rater_role,
            stars_half=stars_half,
            comment=comment,
            reason_code=reason_code,
            automatic=automatic,
        )
        db.add(rating)
        db.flush()
    else:
        rating.stars_half = stars_half
        rating.comment = comment
        rating.reason_code = reason_code
        rating.updated_at = _now()
    if rater_role == "publisher" and not automatic:
        apply_rating_settlement(db, task, ratee.id, stars_half)
    return rating


def settle_due_ratings(db: Session) -> None:
    """惰性补评：完成超过 7 天仍缺评价的组合自动记 3 星。"""
    cutoff = _now() - timedelta(days=RATING_WINDOW_DAYS)
    tasks = db.scalars(
        select(Task)
        .where(Task.status == TaskStatus.COMPLETED, Task.completed_at.isnot(None), Task.completed_at <= cutoff)
        .order_by(Task.id)
        .limit(100)
    ).unique().all()
    changed = False
    for task in tasks:
        for member in _accepted_members(task):
            if member.user_id == task.publisher_id:
                continue
            exists = db.scalar(
                select(TaskRating.id).where(
                    TaskRating.task_id == task.id,
                    TaskRating.rater_id == task.publisher_id,
                    TaskRating.ratee_id == member.user_id,
                )
            )
            if exists is None:
                upsert_rating(db, task, task.publisher, member.user, "publisher", AUTO_STARS_HALF, None, None, automatic=True)
                changed = True
            exists = db.scalar(
                select(TaskRating.id).where(
                    TaskRating.task_id == task.id,
                    TaskRating.rater_id == member.user_id,
                    TaskRating.ratee_id == task.publisher_id,
                )
            )
            if exists is None:
                upsert_rating(db, task, member.user, task.publisher, "taker", AUTO_STARS_HALF, None, None, automatic=True)
                changed = True
    if changed:
        db.commit()


def _counterpart_id(db: Session, rating: TaskRating) -> int | None:
    return db.scalar(
        select(TaskRating.id).where(
            TaskRating.task_id == rating.task_id,
            TaskRating.rater_id == rating.ratee_id,
            TaskRating.ratee_id == rating.rater_id,
        )
    )


def _is_revealed(db: Session, task: Task, rating: TaskRating) -> bool:
    deadline = rating_deadline(task)
    if deadline is not None and _now() >= deadline:
        return True
    return _counterpart_id(db, rating) is not None


def present_rating(rating: TaskRating, revealed: bool, viewer: User | None) -> RatingOut:
    editable = (
        not rating.automatic
        and rating.revoked_at is None
        and _now() < rating.created_at + timedelta(hours=RATING_EDIT_HOURS)
        and viewer is not None
        and viewer.id == rating.rater_id
    )
    return RatingOut(
        id=rating.id,
        rater_id=rating.rater_id,
        ratee_id=rating.ratee_id,
        rater_role=rating.rater_role,
        stars=rating.stars,
        comment=rating.comment,
        reason_code=rating.reason_code,
        reason_label=RATING_REASONS.get(rating.reason_code or "") or None,
        automatic=bool(rating.automatic),
        created_at=rating.created_at,
        revealed=revealed,
        editable_until=rating.created_at + timedelta(hours=RATING_EDIT_HOURS),
        can_edit=editable,
    )


def _role_of(task: Task, user: User) -> str | None:
    if task.publisher_id == user.id:
        return "publisher"
    if any(m.user_id == user.id and m.response_status == TaskMemberResponse.ACCEPTED for m in task.members):
        return "taker"
    return None


def _require_completed_task(db: Session, task_id: int) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="委托不存在")
    if task.status != TaskStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="委托完成后才能评价")
    return task


router = APIRouter(prefix="/api", tags=["ratings"])


def _stats(rows: list[TaskRating]) -> RatingStatsOut:
    count = len(rows)
    total = sum(row.stars for row in rows)
    average = total / count if count else 0
    bayes = (RATING_PRIOR_COUNT * RATING_PRIOR_MEAN + total) / (RATING_PRIOR_COUNT + count)
    return RatingStatsOut(
        count=count,
        average=round(average, 2),
        bayes=round(bayes, 2),
        good=sum(1 for row in rows if row.stars >= 4),
        neutral=sum(1 for row in rows if row.stars == 3),
        bad=sum(1 for row in rows if row.stars <= 2),
    )


def user_rating_summary(db: Session, user_id: int) -> UserRatingSummary:
    rows = db.scalars(
        select(TaskRating).where(TaskRating.ratee_id == user_id, TaskRating.revoked_at.is_(None))
    ).all()
    return UserRatingSummary(
        # 接单人评分来自委托人（rater_role=publisher），委托人评分反之。
        taker=_stats([row for row in rows if row.rater_role == "publisher"]),
        publisher=_stats([row for row in rows if row.rater_role == "taker"]),
    )


@router.get("/users/{user_id}/rating-summary", response_model=UserRatingSummary)
def rating_summary(user_id: int, db: Session = Depends(get_db)):
    settle_due_ratings(db)
    return user_rating_summary(db, user_id)


@router.get("/tasks/{task_id}/ratings", response_model=TaskRatingsOut)
def task_ratings(
    task_id: int,
    viewer: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    settle_due_ratings(db)
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="委托不存在")
    if task.status != TaskStatus.COMPLETED:
        return TaskRatingsOut(deadline=None, role=None, can_rate=False, slots=[])

    deadline = rating_deadline(task)
    can_rate = deadline is not None and _now() < deadline
    role = _role_of(task, viewer) if viewer is not None else None
    if role is None:
        rows = db.scalars(
            select(TaskRating)
            .where(TaskRating.task_id == task.id, TaskRating.revoked_at.is_(None))
            .order_by(TaskRating.created_at)
        ).all()
        public = [present_rating(row, True, viewer) for row in rows if _is_revealed(db, task, row)]
        return TaskRatingsOut(deadline=deadline, role=None, can_rate=False, public=public)

    from .main import present_user_public

    slots: list[RatingSlotOut] = []
    counterparts = [m.user for m in _accepted_members(task)] if role == "publisher" else [task.publisher]
    for counterpart in counterparts:
        mine = db.scalar(
            select(TaskRating).where(
                TaskRating.task_id == task.id,
                TaskRating.rater_id == viewer.id,
                TaskRating.ratee_id == counterpart.id,
            )
        )
        theirs = db.scalar(
            select(TaskRating).where(
                TaskRating.task_id == task.id,
                TaskRating.rater_id == counterpart.id,
                TaskRating.ratee_id == viewer.id,
            )
        )
        revealed = theirs is not None and _is_revealed(db, task, theirs)
        slots.append(
            RatingSlotOut(
                counterpart=present_user_public(counterpart, viewer),
                my_rating=present_rating(mine, True, viewer) if mine else None,
                their_rating=present_rating(theirs, revealed, viewer) if theirs and revealed else None,
                can_rate=can_rate and mine is None,
                can_edit=bool(
                    mine
                    and not mine.automatic
                    and _now() < mine.created_at + timedelta(hours=RATING_EDIT_HOURS)
                ),
            )
        )
    return TaskRatingsOut(deadline=deadline, role=role, can_rate=can_rate, slots=slots)


@router.post("/tasks/{task_id}/ratings", response_model=RatingOut, status_code=status.HTTP_201_CREATED)
def create_rating(
    task_id: int,
    payload: RatingCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    settle_due_ratings(db)
    task = _require_completed_task(db, task_id)
    role = _role_of(task, user)
    if role is None:
        raise HTTPException(status_code=403, detail="只有该委托的委托人或接单人才能评价")
    deadline = rating_deadline(task)
    if deadline is None or _now() >= deadline:
        raise HTTPException(status_code=409, detail="评价窗口已结束")
    if payload.ratee_id == user.id:
        raise HTTPException(status_code=422, detail="不能评价自己")
    if role == "publisher":
        if not any(
            m.user_id == payload.ratee_id and m.response_status == TaskMemberResponse.ACCEPTED for m in task.members
        ):
            raise HTTPException(status_code=422, detail="对方不是该委托的接单人")
        ratee = db.get(User, payload.ratee_id)
    else:
        if payload.ratee_id != task.publisher_id:
            raise HTTPException(status_code=422, detail="只能评价该委托的委托人")
        ratee = task.publisher
    if ratee is None:
        raise HTTPException(status_code=404, detail="评价对象不存在")
    exists = db.scalar(
        select(TaskRating.id).where(
            TaskRating.task_id == task.id,
            TaskRating.rater_id == user.id,
            TaskRating.ratee_id == ratee.id,
        )
    )
    if exists is not None:
        raise HTTPException(status_code=409, detail="你已经评价过对方，如需修改请在 24 小时内编辑")
    comment, reason_code = _validate_payload(payload.stars_half, payload.comment, payload.reason_code)
    rating = upsert_rating(db, task, user, ratee, role, payload.stars_half, comment, reason_code)
    db.commit()
    db.refresh(rating)
    return present_rating(rating, True, user)


@router.patch("/tasks/{task_id}/ratings/{ratee_id}", response_model=RatingOut)
def update_rating(
    task_id: int,
    ratee_id: int,
    payload: RatingUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task = _require_completed_task(db, task_id)
    rating = db.scalar(
        select(TaskRating).where(
            TaskRating.task_id == task.id,
            TaskRating.rater_id == user.id,
            TaskRating.ratee_id == ratee_id,
        )
    )
    if rating is None:
        raise HTTPException(status_code=404, detail="你还没有评价对方")
    if rating.automatic:
        raise HTTPException(status_code=409, detail="系统自动评价不能修改")
    if _now() >= rating.created_at + timedelta(hours=RATING_EDIT_HOURS):
        raise HTTPException(status_code=409, detail="评价提交后 24 小时内才能修改")
    comment, reason_code = _validate_payload(payload.stars_half, payload.comment, payload.reason_code)
    rating.stars_half = payload.stars_half
    rating.comment = comment
    rating.reason_code = reason_code
    rating.updated_at = _now()
    if rating.rater_role == "publisher":
        apply_rating_settlement(db, task, ratee_id, payload.stars_half)
    db.commit()
    db.refresh(rating)
    return present_rating(rating, True, user)


@router.get("/users/{user_id}/ratings", response_model=RatingPublicPage)
def user_ratings(
    user_id: int,
    role: str = Query(default="taker", pattern="^(taker|publisher)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
    viewer: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """公开评价列表：只返回已解盲、未撤销的评价。"""
    settle_due_ratings(db)
    rows = db.scalars(
        select(TaskRating)
        .options(joinedload(TaskRating.rater), joinedload(TaskRating.task))
        .where(
            TaskRating.ratee_id == user_id,
            TaskRating.rater_role == role,
            TaskRating.revoked_at.is_(None),
        )
        .order_by(TaskRating.created_at.desc())
    ).unique().all()
    visible = []
    for row in rows:
        task = row.task
        deadline = rating_deadline(task) if task is not None else None
        if deadline is not None and _now() < deadline and _counterpart_id(db, row) is None:
            continue
        visible.append(row)
    total = len(visible)
    start = (page - 1) * page_size
    from .main import present_user_public

    items = [
        RatingPublicOut(
            id=row.id,
            stars=row.stars,
            comment=row.comment,
            reason_code=row.reason_code,
            reason_label=RATING_REASONS.get(row.reason_code or "") or None,
            role=row.rater_role,
            task_id=row.task_id,
            task_title=row.task.title if row.task else "",
            task_category=row.task.category if row.task else "",
            rater=present_user_public(row.rater, viewer),
            created_at=row.created_at,
            automatic=bool(row.automatic),
        )
        for row in visible[start:start + page_size]
    ]
    return RatingPublicPage(total=total, page=page, page_size=page_size, items=items)
