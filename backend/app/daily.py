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
from .house import HouseRoom
from .models import (
    BoardMessage,
    FriendProfile,
    Story,
    StoryComment,
    TalkReply,
    TalkThread,
    Task,
    TaskMember,
    TaskMemberResponse,
    TaskStatus,
    User,
    VrMapLike,
    VrMapPhoto,
)
from .points import award_points, day_start_utc
from .ratings import TaskRating
from .schemas import DailyOut, DailyTaskOut, DailyClaimOut, OfficialQuestOut
from .shares import TaskShare
from .sugar_frost import SugarFrostSave

DAILY_TASKS = (
    {"key": "publish", "label": "发布 1 份委托", "detail": "描述不少于 30 字", "reward": 2, "target": 1},
    {"key": "complete", "label": "完成 1 次委托", "detail": "完成确认后计入", "reward": 4, "target": 1},
    {"key": "rate", "label": "评价 1 次协作", "detail": "半星也算", "reward": 1, "target": 1},
    {"key": "share", "label": "分享 1 份委托", "detail": "同一份委托每天只计一次", "reward": 1, "target": 1},
    {"key": "all_clear", "label": "完成全部每日任务", "detail": "额外奖励", "reward": 2, "target": 4},
)
DAILY_KEYS = {item["key"] for item in DAILY_TASKS}
MAIN_TASKS = ("publish", "complete", "rate", "share")

# 官方活跃委托：每天按日期确定性抽 3 条（所有用户相同），完成后领取少量积分。
OFFICIAL_POOL = (
    {"key": "board_post", "label": "在留言板发一条留言", "reward": 5, "target": 1},
    {"key": "story_comment", "label": "给一篇故事写评论", "reward": 5, "target": 1},
    {"key": "story_publish", "label": "发布一篇故事", "reward": 8, "target": 1},
    {"key": "friend_profile", "label": "更新交友厅资料", "reward": 5, "target": 1},
    {"key": "map_photo", "label": "上传一张地图实拍", "reward": 5, "target": 1},
    {"key": "map_like", "label": "给一张推荐地图点赞", "reward": 2, "target": 1},
    {"key": "talk_post", "label": "在疑难解答发一个主题", "reward": 3, "target": 1},
    {"key": "talk_reply", "label": "回复一条疑难解答", "reward": 3, "target": 1},
    {"key": "frost_play", "label": "推进一局糖霜世界", "reward": 3, "target": 1},
    {"key": "house_save", "label": "保存一次自己的房屋", "reward": 8, "target": 1},
)
DAILY_OFFICIAL_COUNT = 3


class OfficialQuestClaim(Base):
    __tablename__ = "official_quest_claims"
    __table_args__ = (UniqueConstraint("user_id", "day", "quest_key", name="uq_official_claim"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    day: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    quest_key: Mapped[str] = mapped_column(String(16), nullable=False)
    reward: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


def official_quests_for_day(day: str) -> list[dict]:
    """按日期确定性抽取，保证同一天所有用户看到同一组委托。"""
    import random

    keys = sorted(OFFICIAL_POOL, key=lambda item: item["key"])
    return random.Random(f"wsw-{day}").sample(keys, DAILY_OFFICIAL_COUNT)


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


def _count(db: Session, model, *conditions) -> int:
    return db.scalar(select(func.count()).select_from(model).where(*conditions)) or 0


def _official_progress(db: Session, user_id: int, start: datetime) -> dict[str, int]:
    iso = start.isoformat()
    return {
        "board_post": _count(db, BoardMessage, BoardMessage.user_id == user_id, BoardMessage.created_at >= start),
        "story_comment": _count(db, StoryComment, StoryComment.user_id == user_id, StoryComment.created_at >= start),
        "story_publish": _count(db, Story, Story.author_id == user_id, Story.created_at >= start),
        "friend_profile": _count(db, FriendProfile, FriendProfile.user_id == user_id, FriendProfile.updated_at >= start),
        "map_photo": _count(db, VrMapPhoto, VrMapPhoto.user_id == user_id, VrMapPhoto.created_at >= start),
        "map_like": _count(db, VrMapLike, VrMapLike.user_id == user_id, VrMapLike.created_at >= start),
        "talk_post": _count(db, TalkThread, TalkThread.user_id == user_id, TalkThread.created_at >= start),
        "talk_reply": _count(db, TalkReply, TalkReply.user_id == user_id, TalkReply.created_at >= start),
        "frost_play": _count(db, SugarFrostSave, SugarFrostSave.user_id == user_id, SugarFrostSave.updated_at >= iso),
        "house_save": _count(db, HouseRoom, HouseRoom.user_id == user_id, HouseRoom.updated_at >= iso),
    }


def _official_claims(db: Session, user_id: int, day: str) -> set[str]:
    return set(
        db.scalars(
            select(OfficialQuestClaim.quest_key).where(
                OfficialQuestClaim.user_id == user_id,
                OfficialQuestClaim.day == day,
            )
        ).all()
    )


def _official_snapshot(db: Session, user_id: int, day: str, start: datetime) -> list[OfficialQuestOut]:
    progress = _official_progress(db, user_id, start)
    claimed = _official_claims(db, user_id, day)
    items = []
    for quest in official_quests_for_day(day):
        done = progress.get(quest["key"], 0) >= quest["target"]
        items.append(
            OfficialQuestOut(
                key=quest["key"],
                label=quest["label"],
                reward=quest["reward"],
                target=quest["target"],
                progress=min(progress.get(quest["key"], 0), quest["target"]),
                claimed=quest["key"] in claimed,
                can_claim=done and quest["key"] not in claimed,
            )
        )
    return items


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
    return DailyOut(day=day, items=items, claimed_count=len(claims), official=_official_snapshot(db, user.id, day, start))


router = APIRouter(prefix="/api/daily", tags=["daily"])


@router.post("/official/{quest_key}/claim", response_model=DailyClaimOut)
def claim_official(
    quest_key: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    day = current_day()
    start = day_start_utc()
    quest = next((item for item in official_quests_for_day(day) if item["key"] == quest_key), None)
    if quest is None:
        raise HTTPException(status_code=404, detail="今天的官方委托里没有这一项")
    if quest_key in _official_claims(db, user.id, day):
        raise HTTPException(status_code=409, detail="今日已领取过该委托")
    if _official_progress(db, user.id, start).get(quest_key, 0) < quest["target"]:
        raise HTTPException(status_code=409, detail="委托尚未完成")
    claim = OfficialQuestClaim(user_id=user.id, day=day, quest_key=quest_key, reward=quest["reward"])
    db.add(claim)
    db.flush()
    award_points(
        db,
        user.id,
        kind="daily",
        lifetime=quest["reward"],
        wallet=quest["reward"],
        note=f"官方委托：{quest['label']}",
        source_type="official_claim",
        source_id=claim.id,
        idempotent=True,
    )
    db.commit()
    db.refresh(user)
    return DailyClaimOut(
        key=quest_key,
        reward=quest["reward"],
        day=day,
        lifetime_points=user.lifetime_points,
        wallet_points=user.wallet_points,
        daily=daily_snapshot(db, user),
    )


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
