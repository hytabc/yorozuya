"""人生记录：把分散在委托、评价、积分、成就里的数据汇总成一份可公开的履历。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .achievements import UserAchievement
from .database import get_db
from .dependencies import get_optional_user
from .levels import level_for, next_threshold
from .models import Task, TaskMember, TaskMemberResponse, TaskStatus, User
from .ratings import user_rating_summary
from .schemas import UserRecordsOut

router = APIRouter(prefix="/api", tags=["records"])


@router.get("/users/{user_id}/records", response_model=UserRecordsOut)
def user_records(user_id: int, viewer: User | None = Depends(get_optional_user), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="用户不存在")

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
    published = db.scalar(
        select(func.count()).select_from(Task).where(
            Task.publisher_id == user_id,
            Task.status == TaskStatus.COMPLETED,
            Task.is_official.is_(False),
        )
    ) or 0
    published_total = db.scalar(
        select(func.count()).select_from(Task).where(
            Task.publisher_id == user_id,
            Task.is_official.is_(False),
        )
    ) or 0
    first_at = db.scalar(
        select(func.min(Task.completed_at))
        .select_from(Task)
        .join(TaskMember, TaskMember.task_id == Task.id)
        .where(
            TaskMember.user_id == user_id,
            TaskMember.response_status == TaskMemberResponse.ACCEPTED,
            Task.status == TaskStatus.COMPLETED,
            Task.is_official.is_(False),
        )
    )
    last_at = db.scalar(
        select(func.max(Task.completed_at))
        .select_from(Task)
        .join(TaskMember, TaskMember.task_id == Task.id)
        .where(
            TaskMember.user_id == user_id,
            TaskMember.response_status == TaskMemberResponse.ACCEPTED,
            Task.status == TaskStatus.COMPLETED,
            Task.is_official.is_(False),
        )
    )
    categories = db.execute(
        select(Task.category, func.count())
        .select_from(Task)
        .join(TaskMember, TaskMember.task_id == Task.id)
        .where(
            TaskMember.user_id == user_id,
            TaskMember.response_status == TaskMemberResponse.ACCEPTED,
            Task.status == TaskStatus.COMPLETED,
            Task.is_official.is_(False),
        )
        .group_by(Task.category)
        .order_by(func.count().desc())
        .limit(5)
    ).all()
    achievements = db.scalar(
        select(func.count()).select_from(UserAchievement).where(UserAchievement.user_id == user_id)
    ) or 0
    summary = user_rating_summary(db, user_id)
    from datetime import datetime

    return UserRecordsOut(
        user_id=user.id,
        lifetime_points=user.lifetime_points,
        level=level_for(user.lifetime_points),
        next_threshold=next_threshold(user.lifetime_points),
        joined_days=max(0, (datetime.utcnow() - user.created_at).days) if user.created_at else 0,
        completed_taken=taken,
        completed_published=published,
        published_total=published_total,
        first_completed_at=first_at,
        last_completed_at=last_at,
        taker_rating=summary.taker,
        publisher_rating=summary.publisher,
        achievements_unlocked=achievements,
        top_categories=[{"category": category, "count": count} for category, count in categories],
    )
