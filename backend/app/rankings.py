"""排行榜：累计积分、接单人评分、委托人评分、完成数。

评分榜沿用与个人资料一致的贝叶斯平滑（C=10, m=4.0），并要求至少 5 条评价；
用户可开启「不参与排行榜」，开启后所有榜单都不再返回该用户。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .database import get_db
from .dependencies import get_current_user, get_optional_user
from .models import Task, TaskMember, TaskMemberResponse, TaskStatus, User
from .ratings import RATING_PRIOR_COUNT, RATING_PRIOR_MEAN, TaskRating
from .schemas import RankingEntryOut, RankingsOut, RankOptOutRequest

RANKING_BOARDS = {
    "points": "累计积分榜",
    "taker_rating": "接单人评分榜",
    "publisher_rating": "委托人评分榜",
    "completed": "完成数榜",
}
RATING_MIN_COUNT = 5
RANKING_LIMIT = 100


router = APIRouter(prefix="/api/rankings", tags=["rankings"])


def _eval_rating(db: Session, role: str) -> list[tuple[int, float, int]]:
    rows = db.execute(
        select(
            TaskRating.ratee_id,
            func.count(),
            func.sum(TaskRating.stars_half),
        )
        .where(TaskRating.rater_role == role, TaskRating.revoked_at.is_(None))
        .group_by(TaskRating.ratee_id)
        .having(func.count() >= RATING_MIN_COUNT)
    ).all()
    scored = []
    for user_id, count, half_total in rows:
        total = (half_total or 0) / 2
        bayes = (RATING_PRIOR_COUNT * RATING_PRIOR_MEAN + total) / (RATING_PRIOR_COUNT + count)
        scored.append((user_id, round(bayes, 2), count))
    scored.sort(key=lambda item: (-item[1], -item[2], item[0]))
    return scored


def _eval_completed(db: Session) -> list[tuple[int, float, int]]:
    published = dict(
        db.execute(
            select(Task.publisher_id, func.count())
            .where(Task.status == TaskStatus.COMPLETED)
            .group_by(Task.publisher_id)
        ).all()
    )
    taken = dict(
        db.execute(
            select(TaskMember.user_id, func.count(func.distinct(Task.id)))
            .join(Task, Task.id == TaskMember.task_id)
            .where(TaskMember.response_status == TaskMemberResponse.ACCEPTED, Task.status == TaskStatus.COMPLETED)
            .group_by(TaskMember.user_id)
        ).all()
    )
    totals = {user_id: published.get(user_id, 0) + taken.get(user_id, 0) for user_id in set(published) | set(taken)}
    scored = [(user_id, float(total), total) for user_id, total in totals.items() if total > 0]
    scored.sort(key=lambda item: (-item[1], item[0]))
    return scored


def _eval_points(db: Session) -> list[tuple[int, float, int]]:
    rows = db.execute(
        select(User.id, User.lifetime_points)
        .where(User.is_active.is_(True), User.lifetime_points > 0)
        .order_by(User.lifetime_points.desc(), User.id.asc())
        .limit(RANKING_LIMIT)
    ).all()
    return [(user_id, float(points), points) for user_id, points in rows]


@router.get("", response_model=RankingsOut)
def rankings(
    board: str = Query(default="points", pattern="^(points|taker_rating|publisher_rating|completed)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    viewer: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    if board == "points":
        scored = _eval_points(db)
    elif board == "completed":
        scored = _eval_completed(db)
    else:
        role = "publisher" if board == "taker_rating" else "taker"
        scored = _eval_rating(db, role)

    opted_out = set(db.scalars(select(User.id).where(User.rank_opt_out.is_(True))).all())
    scored = [item for item in scored if item[0] not in opted_out]
    total = len(scored)
    start = (page - 1) * page_size
    page_items = scored[start:start + page_size]
    users = {
        user.id: user
        for user in db.scalars(select(User).where(User.id.in_([item[0] for item in page_items]))).all()
    } if page_items else {}

    from .main import present_user_public

    items = []
    for index, (user_id, value, count) in enumerate(page_items, start=start + 1):
        user = users.get(user_id)
        if user is None:
            continue
        items.append(
            RankingEntryOut(
                rank=index,
                user=present_user_public(user, viewer),
                value=round(value, 2),
                count=count,
                is_me=bool(viewer is not None and viewer.id == user_id),
            )
        )
    return RankingsOut(
        board=board,
        title=RANKING_BOARDS[board],
        page=page,
        page_size=page_size,
        total=total,
        min_count=RATING_MIN_COUNT if board.endswith("_rating") else 0,
        items=items,
    )


@router.patch("/opt-out", response_model=dict)
def toggle_opt_out(
    payload: RankOptOutRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user.rank_opt_out = payload.opt_out
    db.commit()
    return {"rank_opt_out": payload.opt_out}
