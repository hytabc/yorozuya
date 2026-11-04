"""官方活跃委托：以真实 Task 的形式出现在大厅，全局共享、最多 3 个、定时随机刷新。

- 由隐藏的系统账号 ``__official__`` 发布，外观与普通委托一致（只是带「官方」标记）；
- 池子里最多 3 个「未结束」的官方委托；被接取后其他人不能再接，等过期自动刷新；
- 完成时由系统核对对应站内动作（留言、发帖、点赞……），核对通过后一次性发放积分。
"""
from __future__ import annotations

import os
import random
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

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
from .points import day_start_utc
from .security import hash_password
from .sugar_frost import SugarFrostSave

SYSTEM_USERNAME = "__official__"
SYSTEM_NICKNAME = "万事屋官方"
OFFICIAL_POOL_LIMIT = 3
# 每个官方委托存活 2~6 小时，到期由 expire_due_tasks 清理，下次进入大厅时随机补位。
OFFICIAL_TTL_MINUTES = (120, 360)
CATEGORY = "其他委托"

OFFICIAL_POOL = (
    {
        "key": "board_post",
        "title": "在留言板发一条留言",
        "description": "到「留言板」发布一条新留言，内容不限（遵守社区规则）。完成后回到这里确认，系统会自动核对今天的记录并发放积分。",
        "reward": 5,
    },
    {
        "key": "story_comment",
        "title": "给一篇故事写评论",
        "description": "在「故事会」任意一篇故事下写一条评论，表达你的想法即可。完成后回到这里确认，系统会自动核对。",
        "reward": 5,
    },
    {
        "key": "story_publish",
        "title": "发布一篇故事",
        "description": "在「故事会」发布一篇你自己的故事（可匿名），字数不限。完成后回到这里确认，系统会自动核对。",
        "reward": 8,
    },
    {
        "key": "friend_profile",
        "title": "更新交友厅资料",
        "description": "到「交友厅」更新你的公开资料（VRC 昵称与介绍）。完成后回到这里确认，系统会自动核对。",
        "reward": 5,
    },
    {
        "key": "map_photo",
        "title": "上传一张地图实拍",
        "description": "在「地图推荐」为任意地图上传一张实拍截图（需审核）。完成后回到这里确认，系统会自动核对。",
        "reward": 5,
    },
    {
        "key": "map_like",
        "title": "给一张推荐地图点赞",
        "description": "在「地图推荐」给任意一张地图点个赞。完成后回到这里确认，系统会自动核对。",
        "reward": 2,
    },
    {
        "key": "talk_post",
        "title": "在疑难解答发一个主题",
        "description": "到「交流大厅 · 疑难解答」发布一个提问或分享帖。完成后回到这里确认，系统会自动核对。",
        "reward": 3,
    },
    {
        "key": "talk_reply",
        "title": "回复一条疑难解答",
        "description": "在「疑难解答」回复任意一个帖子，帮别人一把。完成后回到这里确认，系统会自动核对。",
        "reward": 3,
    },
    {
        "key": "frost_play",
        "title": "推进一局糖霜世界",
        "description": "打开「糖霜世界」并推进一次存档。完成后回到这里确认，系统会自动核对。",
        "reward": 3,
    },
    {
        "key": "house_save",
        "title": "保存一次自己的房屋",
        "description": "在「房屋」工坊里保存一次自己的房间。完成后回到这里确认，系统会自动核对。",
        "reward": 8,
    },
)
POOL_BY_KEY = {item["key"]: item for item in OFFICIAL_POOL}
ACTIVE_STATUSES = (
    TaskStatus.PUBLISHED,
    TaskStatus.ACCEPTED,
    TaskStatus.AWAITING,
    TaskStatus.CANCELLING,
)
# pytest 下默认不自动播种官方委托，避免污染其他用例的大厅断言；
# 官方委托自己的用例会把这个开关打开。
FORCE_ENABLED = False


def enabled() -> bool:
    return FORCE_ENABLED or os.environ.get("PYTEST_CURRENT_TEST") is None


def ensure_official_user(db: Session) -> User:
    user = db.scalar(select(User).where(User.username == SYSTEM_USERNAME))
    if user is None:
        user = User(
            username=SYSTEM_USERNAME,
            password_hash=hash_password(f"disabled-{random.random()}"),
            nickname=SYSTEM_NICKNAME,
            is_admin=False,
            is_active=False,
        )
        db.add(user)
        db.flush()
    return user


def _count(db: Session, model, *conditions) -> int:
    return db.scalar(select(func.count()).select_from(model).where(*conditions)) or 0


def quest_progress_today(db: Session, user_id: int, key: str) -> int:
    start = day_start_utc()
    iso = start.isoformat()
    return {
        "board_post": lambda: _count(db, BoardMessage, BoardMessage.user_id == user_id, BoardMessage.created_at >= start),
        "story_comment": lambda: _count(db, StoryComment, StoryComment.user_id == user_id, StoryComment.created_at >= start),
        "story_publish": lambda: _count(db, Story, Story.author_id == user_id, Story.created_at >= start),
        "friend_profile": lambda: _count(db, FriendProfile, FriendProfile.user_id == user_id, FriendProfile.updated_at >= start),
        "map_photo": lambda: _count(db, VrMapPhoto, VrMapPhoto.user_id == user_id, VrMapPhoto.created_at >= start),
        "map_like": lambda: _count(db, VrMapLike, VrMapLike.user_id == user_id, VrMapLike.created_at >= start),
        "talk_post": lambda: _count(db, TalkThread, TalkThread.user_id == user_id, TalkThread.created_at >= start),
        "talk_reply": lambda: _count(db, TalkReply, TalkReply.user_id == user_id, TalkReply.created_at >= start),
        "frost_play": lambda: _count(db, SugarFrostSave, SugarFrostSave.user_id == user_id, SugarFrostSave.updated_at >= iso),
        "house_save": lambda: _count(db, HouseRoom, HouseRoom.user_id == user_id, HouseRoom.updated_at >= iso),
    }.get(key, lambda: 0)()


def ensure_official_tasks(db: Session) -> None:
    """把大厅里的官方委托补齐到 3 个（已有被接取/进行中的也占位）。"""
    if not enabled():
        return
    expire_due = db.scalars(
        select(Task).where(
            Task.is_official.is_(True),
            Task.status.in_(ACTIVE_STATUSES),
            Task.expires_at <= datetime.utcnow(),
        )
    ).all()
    for task in expire_due:
        task.status = TaskStatus.EXPIRED
        task.updated_at = datetime.utcnow()

    active = db.scalars(
        select(Task).where(Task.is_official.is_(True), Task.status.in_(ACTIVE_STATUSES))
    ).all()
    if len(active) >= OFFICIAL_POOL_LIMIT:
        db.commit() if expire_due else None
        return

    publisher = ensure_official_user(db)
    used_keys = {task.official_key for task in active if task.official_key}
    candidates = [item for item in OFFICIAL_POOL if item["key"] not in used_keys]
    shortfall = OFFICIAL_POOL_LIMIT - len(active)
    for item in random.sample(candidates, min(shortfall, len(candidates))):
        minutes = random.randint(*OFFICIAL_TTL_MINUTES)
        db.add(
            Task(
                title=item["title"],
                description=item["description"],
                category=CATEGORY,
                scale="small",
                base_points=item["reward"],
                bounty_points=0,
                status=TaskStatus.PUBLISHED,
                expires_at=datetime.utcnow() + timedelta(minutes=minutes),
                publisher_id=publisher.id,
                required_takers=1,
                is_official=True,
                official_key=item["key"],
            )
        )
    db.commit()


def complete_official_task(db: Session, task: Task, user: User) -> bool:
    """核对站内动作并完成官方委托；返回是否成功。"""
    if not task.is_official or not task.official_key:
        return False
    if task.status not in (TaskStatus.ACCEPTED, TaskStatus.AWAITING):
        return False
    membership = db.scalar(
        select(TaskMember).where(
            TaskMember.task_id == task.id,
            TaskMember.user_id == user.id,
            TaskMember.response_status == TaskMemberResponse.ACCEPTED,
        )
    )
    if membership is None:
        return False
    if quest_progress_today(db, user.id, task.official_key) <= 0:
        return False
    now = datetime.utcnow()
    membership.confirmed_at = now
    task.publisher_confirmed_at = now
    task.status = TaskStatus.COMPLETED
    task.completed_at = now
    task.updated_at = now
    from .points import award_points

    award_points(
        db,
        user.id,
        kind="official_task",
        lifetime=task.base_points,
        wallet=task.base_points,
        note=f"官方委托：{task.title}",
        source_type="task",
        source_id=task.id,
        idempotent=True,
    )
    return True
