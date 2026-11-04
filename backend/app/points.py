"""积分账户与流水。

积分分两个口袋：

- ``lifetime_points``：终身累计，只增不减，用于等级、排行榜与成就；
- ``wallet_points``：可用余额，只能用于发布悬赏（托管时扣除），不对外公开。

唯一的积分散发入口是 :func:`award_points`，它同时写流水，便于审计与对账。
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func, select, update
from sqlalchemy.orm import Mapped, Session, mapped_column

from .database import Base, get_db
from .dependencies import get_current_user
from .models import User
from .schemas import PointLedgerOut, PointLedgerPage, PointsSummary

POINT_KIND_LABELS = {
    "task_reward": "委托奖励",
    "task_bounty": "悬赏积分",
    "rating_settle": "评价结算",
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
