"""信誉等级：由终身积分推导，只升不降，并解锁接单/悬赏特权。

等级不落库：始终由 ``User.lifetime_points`` 计算，避免出现「等级与积分不同步」。
"""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .database import get_db
from .dependencies import get_current_user
from .models import User
from .ratings import user_rating_summary
from .schemas import UserLevelOut

LEVEL_THRESHOLDS = (0, 50, 150, 350, 700, 1200, 2000, 3200, 5000, 8000)
LEVEL_BOUNTY_BASE = 20
BOUNTY_ABSOLUTE_CAP = 200
BOUNTY_MIN_LEVEL = 3
PUBLISHER_CONFIDENT_COUNT = 5
DEFAULT_DAILY_PUBLISH_LIMIT = 5


def level_for(points: int) -> int:
    level = 1
    for index, threshold in enumerate(LEVEL_THRESHOLDS, start=1):
        if points >= threshold:
            level = index
    return level


def next_threshold(points: int) -> int | None:
    for threshold in LEVEL_THRESHOLDS:
        if points < threshold:
            return threshold
    return None


@dataclass(frozen=True)
class Privileges:
    level: int
    taker_limit: int
    bounty_cap: int
    can_post_bounty: bool
    multi_taker: bool
    daily_publish_limit: int
    # 委托人评分是否已积累到足以生效的样本量。
    publisher_rating_active: bool
    publisher_bayes: float

    def as_dict(self) -> dict:
        return {
            "level": self.level,
            "taker_limit": self.taker_limit,
            "bounty_cap": self.bounty_cap,
            "can_post_bounty": self.can_post_bounty,
            "multi_taker": self.multi_taker,
            "daily_publish_limit": self.daily_publish_limit,
            "publisher_rating_active": self.publisher_rating_active,
            "publisher_bayes": self.publisher_bayes,
        }


def privileges(db: Session, user: User) -> Privileges:
    level = level_for(user.lifetime_points)
    taker_limit = max(user.max_concurrent_tasks, 2 + level // 3)
    bounty_cap = min(BOUNTY_ABSOLUTE_CAP, level * LEVEL_BOUNTY_BASE)
    can_post_bounty = level >= BOUNTY_MIN_LEVEL
    multi_taker = True
    daily_publish_limit = DEFAULT_DAILY_PUBLISH_LIMIT

    stats = user_rating_summary(db, user.id).publisher
    active = stats.count >= PUBLISHER_CONFIDENT_COUNT
    if active:
        if stats.bayes < 3.0:
            bounty_cap //= 2
        if stats.bayes < 2.5:
            bounty_cap = 0
            can_post_bounty = False
            multi_taker = False
        if stats.bayes < 2.0:
            daily_publish_limit = 1

    return Privileges(
        level=level,
        taker_limit=taker_limit,
        bounty_cap=bounty_cap,
        can_post_bounty=can_post_bounty,
        multi_taker=multi_taker,
        daily_publish_limit=daily_publish_limit,
        publisher_rating_active=active,
        publisher_bayes=stats.bayes,
    )


router = APIRouter(prefix="/api/levels", tags=["levels"])


@router.get("/me", response_model=UserLevelOut)
def my_level(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    info = privileges(db, user)
    return UserLevelOut(
        level=info.level,
        lifetime_points=user.lifetime_points,
        next_threshold=next_threshold(user.lifetime_points),
        taker_limit=info.taker_limit,
        bounty_cap=info.bounty_cap,
        can_post_bounty=info.can_post_bounty,
        multi_taker=info.multi_taker,
        daily_publish_limit=info.daily_publish_limit,
        publisher_rating_active=info.publisher_rating_active,
        publisher_bayes=info.publisher_bayes,
    )
