"""成就系统：分级徽章，达成后一次性发放终身积分（不进入钱包，避免刷币）。

成就进度全部由现有业务表实时计算，``user_achievements`` 只记录已解锁的 key，
因此在任何入口打开成就页都会自动补发此前已达成的成就。
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from .database import Base, get_db
from .dependencies import get_current_user, get_optional_user
from .house import HouseRoom
from .models import Story, TalkReply, TalkThread, Task, TaskMember, TaskMemberResponse, TaskStatus, User
from .points import PointLedger, award_points
from .ratings import TaskRating
from .schemas import AchievementOut, AchievementWallOut
from .shares import TaskShare

ACHIEVEMENTS = (
    # 旅程
    {"key": "first_done", "category": "旅程", "name": "初次启程", "desc": "完成第 1 次委托", "metric": "completed_taken", "target": 1, "reward": 10},
    {"key": "taker_10", "category": "旅程", "name": "老练", "desc": "累计完成 10 次委托", "metric": "completed_taken", "target": 10, "reward": 20},
    {"key": "taker_50", "category": "旅程", "name": "万事屋栋梁", "desc": "累计完成 50 次委托", "metric": "completed_taken", "target": 50, "reward": 50},
    {"key": "taker_100", "category": "旅程", "name": "传说", "desc": "累计完成 100 次委托", "metric": "completed_taken", "target": 100, "reward": 100},
    {"key": "publisher_1", "category": "旅程", "name": "第一次发布", "desc": "发布第 1 份委托", "metric": "published_total", "target": 1, "reward": 5},
    {"key": "publisher_10", "category": "旅程", "name": "熟客委托人", "desc": "累计发布 10 份委托", "metric": "published_total", "target": 10, "reward": 20},
    {"key": "veteran_30", "category": "旅程", "name": "老住户", "desc": "注册满 30 天", "metric": "account_days", "target": 30, "reward": 20},
    {"key": "veteran_365", "category": "旅程", "name": "周年纪念", "desc": "注册满 365 天", "metric": "account_days", "target": 365, "reward": 50},
    # 口碑
    {"key": "first_good", "category": "口碑", "name": "初次好评", "desc": "收到第 1 个 4 星及以上评价", "metric": "good_received", "target": 1, "reward": 10},
    {"key": "good_10", "category": "口碑", "name": "口碑不错", "desc": "收到 10 个好评", "metric": "good_received", "target": 10, "reward": 25},
    {"key": "good_50", "category": "口碑", "name": "有口皆碑", "desc": "收到 50 个好评", "metric": "good_received", "target": 50, "reward": 60},
    {"key": "perfect_10", "category": "口碑", "name": "十全十美", "desc": "收到 10 个满分评价", "metric": "perfect_received", "target": 10, "reward": 40},
    {"key": "rater_1", "category": "口碑", "name": "伯乐", "desc": "给出第 1 次评价", "metric": "rated_given", "target": 1, "reward": 5},
    {"key": "rater_20", "category": "口碑", "name": "阅人无数", "desc": "累计给出 20 次评价", "metric": "rated_given", "target": 20, "reward": 30},
    {"key": "clean_20", "category": "口碑", "name": "零差评", "desc": "累计 20 条评价且没有任何差评", "metric": "clean_good", "target": 20, "reward": 40},
    # 社交
    {"key": "vrchat_linked", "category": "社交", "name": "双向认同", "desc": "绑定 VRChat 身份", "metric": "vrchat_linked", "target": 1, "reward": 10},
    {"key": "invite_1", "category": "社交", "name": "引路人", "desc": "邀请 1 位好友完成首个委托", "metric": "invite_valid", "target": 1, "reward": 15},
    {"key": "invite_5", "category": "社交", "name": "伯乐之友", "desc": "累计邀请 5 位有效好友", "metric": "invite_valid", "target": 5, "reward": 40},
    {"key": "story_1", "category": "社交", "name": "第一篇故事", "desc": "在故事会发布一篇故事", "metric": "stories", "target": 1, "reward": 10},
    {"key": "talk_accepted", "category": "社交", "name": "采纳之光", "desc": "回答被采纳 1 次", "metric": "accepted_replies", "target": 1, "reward": 15},
    # 收藏
    {"key": "daily_7", "category": "收藏", "name": "七日之约", "desc": "累计领取 7 次每日任务", "metric": "daily_claims", "target": 7, "reward": 15},
    {"key": "daily_30", "category": "收藏", "name": "月度常客", "desc": "累计领取 30 次每日任务", "metric": "daily_claims", "target": 30, "reward": 40},
    {"key": "share_10", "category": "收藏", "name": "传声筒", "desc": "累计分享 10 次委托", "metric": "shares", "target": 10, "reward": 15},
    {"key": "points_100", "category": "收藏", "name": "小有积蓄", "desc": "终身积分达到 100", "metric": "lifetime_points", "target": 100, "reward": 10},
    {"key": "points_1000", "category": "收藏", "name": "富甲一方", "desc": "终身积分达到 1000", "metric": "lifetime_points", "target": 1000, "reward": 50},
    {"key": "house_owner", "category": "收藏", "name": "安家", "desc": "保存一次自己的房屋", "metric": "house_saved", "target": 1, "reward": 15},
)
ACHIEVEMENT_BY_KEY = {item["key"]: item for item in ACHIEVEMENTS}


class UserAchievement(Base):
    __tablename__ = "user_achievements"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_user_achievement"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(32), nullable=False)
    unlocked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


def _scalar(db: Session, statement) -> int:
    return db.scalar(statement) or 0


def achievement_metrics(db: Session, user: User) -> dict[str, int]:
    completed_taken = _scalar(
        db,
        select(func.count(func.distinct(Task.id)))
        .select_from(Task)
        .join(TaskMember, TaskMember.task_id == Task.id)
        .where(
            TaskMember.user_id == user.id,
            TaskMember.response_status == TaskMemberResponse.ACCEPTED,
            Task.status == TaskStatus.COMPLETED,
            Task.is_official.is_(False),
        ),
    )
    published_total = _scalar(
        db,
        select(func.count()).select_from(Task).where(
            Task.publisher_id == user.id,
            Task.is_official.is_(False),
        ),
    )
    good_received = _scalar(
        db,
        select(func.count()).select_from(TaskRating)
        .join(Task, Task.id == TaskRating.task_id)
        .where(
            TaskRating.ratee_id == user.id,
            TaskRating.rater_role == "publisher",
            TaskRating.revoked_at.is_(None),
            TaskRating.stars_half >= 8,
            Task.is_official.is_(False),
        ),
    )
    perfect_received = _scalar(
        db,
        select(func.count()).select_from(TaskRating)
        .join(Task, Task.id == TaskRating.task_id)
        .where(
            TaskRating.ratee_id == user.id,
            TaskRating.rater_role == "publisher",
            TaskRating.revoked_at.is_(None),
            TaskRating.stars_half == 10,
            Task.is_official.is_(False),
        ),
    )
    bad_received = _scalar(
        db,
        select(func.count()).select_from(TaskRating)
        .join(Task, Task.id == TaskRating.task_id)
        .where(
            TaskRating.ratee_id == user.id,
            TaskRating.rater_role == "publisher",
            TaskRating.revoked_at.is_(None),
            TaskRating.stars_half < 8,
            Task.is_official.is_(False),
        ),
    )
    rated_given = _scalar(
        db,
        select(func.count()).select_from(TaskRating)
        .join(Task, Task.id == TaskRating.task_id)
        .where(TaskRating.rater_id == user.id, Task.is_official.is_(False)),
    )
    invite_valid = _scalar(
        db,
        select(func.count()).select_from(PointLedger).where(
            PointLedger.user_id == user.id,
            PointLedger.kind == "invite",
        ),
    )
    stories = _scalar(db, select(func.count()).select_from(Story).where(Story.author_id == user.id))
    accepted_replies = _scalar(
        db,
        select(func.count())
        .select_from(TalkReply)
        .join(TalkThread, TalkThread.accepted_reply_id == TalkReply.id)
        .where(TalkReply.user_id == user.id),
    )
    from .daily import UserDailyClaim

    daily_claims = _scalar(
        db, select(func.count()).select_from(UserDailyClaim).where(UserDailyClaim.user_id == user.id)
    )
    shares = _scalar(db, select(func.count()).select_from(TaskShare).where(TaskShare.user_id == user.id))
    house_saved = _scalar(db, select(func.count()).select_from(HouseRoom).where(HouseRoom.user_id == user.id))
    from .trust import VRChatIdentity

    vrchat_linked = _scalar(
        db, select(func.count()).select_from(VRChatIdentity).where(VRChatIdentity.user_id == user.id)
    )
    account_days = max(0, (datetime.utcnow() - user.created_at).days) if user.created_at else 0
    return {
        "completed_taken": completed_taken,
        "published_total": published_total,
        "good_received": good_received,
        "clean_good": good_received if bad_received == 0 else 0,
        "perfect_received": perfect_received,
        "rated_given": rated_given,
        "invite_valid": invite_valid,
        "stories": stories,
        "accepted_replies": accepted_replies,
        "daily_claims": daily_claims,
        "shares": shares,
        "house_saved": house_saved,
        "vrchat_linked": vrchat_linked,
        "account_days": account_days,
        "lifetime_points": user.lifetime_points,
    }


def evaluate_achievements(db: Session, user: User) -> list[str]:
    """补发所有已达成但未记录的成就；返回本次新解锁的 key。"""
    metrics = achievement_metrics(db, user)
    unlocked = set(
        db.scalars(select(UserAchievement.key).where(UserAchievement.user_id == user.id)).all()
    )
    new_keys: list[str] = []
    for item in ACHIEVEMENTS:
        if item["key"] in unlocked:
            continue
        if metrics.get(item["metric"], 0) < item["target"]:
            continue
        record = UserAchievement(user_id=user.id, key=item["key"])
        db.add(record)
        db.flush()
        award_points(
            db,
            user.id,
            kind="achievement",
            lifetime=item["reward"],
            note=f"成就：{item['name']}",
            source_type="achievement",
            source_id=record.id,
            idempotent=True,
        )
        new_keys.append(item["key"])
    if new_keys:
        db.commit()
    return new_keys


def present_achievement(items: dict[str, UserAchievement], item: dict, metrics: dict[str, int]) -> AchievementOut:
    record = items.get(item["key"])
    return AchievementOut(
        key=item["key"],
        category=item["category"],
        name=item["name"],
        description=item["desc"],
        reward=item["reward"],
        target=item["target"],
        progress=min(metrics.get(item["metric"], 0), item["target"]),
        unlocked=record is not None,
        unlocked_at=record.unlocked_at if record else None,
    )


def wall(db: Session, user: User) -> AchievementWallOut:
    evaluate_achievements(db, user)
    records = {
        row.key: row
        for row in db.scalars(select(UserAchievement).where(UserAchievement.user_id == user.id)).all()
    }
    metrics = achievement_metrics(db, user)
    items = [present_achievement(records, item, metrics) for item in ACHIEVEMENTS]
    return AchievementWallOut(unlocked=sum(1 for item in items if item.unlocked), total=len(items), items=items)


router = APIRouter(prefix="/api", tags=["achievements"])


@router.get("/achievements", response_model=AchievementWallOut)
def my_achievements(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return wall(db, user)


@router.get("/users/{user_id}/achievements", response_model=AchievementWallOut)
def user_achievements(
    user_id: int,
    viewer: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """公开成就墙只展示已解锁项，未解锁的进度不对他人展示。"""
    target = db.get(User, user_id)
    if target is None:
        return AchievementWallOut(unlocked=0, total=len(ACHIEVEMENTS), items=[])
    if viewer is not None and viewer.id == target.id:
        return wall(db, target)
    records = {
        row.key: row
        for row in db.scalars(select(UserAchievement).where(UserAchievement.user_id == user_id)).all()
    }
    metrics = achievement_metrics(db, target)
    items = [
        present_achievement(records, item, metrics) for item in ACHIEVEMENTS if item["key"] in records
    ]
    return AchievementWallOut(unlocked=len(items), total=len(ACHIEVEMENTS), items=items)
