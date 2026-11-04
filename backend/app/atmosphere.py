"""委托礼仪确认（准入层）。

用一屏可读完的「委托礼仪」代替法律免责墙的初始位置；完整条款仍在 /terms。
登录用户的确认按账号记录并带版本号（条款更新后需要重新确认），游客只写浏览器本地。
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import DateTime, ForeignKey, Integer, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from .config import settings
from .database import Base, get_db
from .dependencies import get_current_user, get_optional_user
from .models import User
from .ratelimit import enforce
from .schemas import AtmosphereAckRequest, AtmosphereStatusOut

# 版本号与 frontend/src/atmosphereRules.js 的 ATMOSPHERE_VERSION 同步；
# 修改文案或条款后递增，用户会被要求重新确认一次。
ATMOSPHERE_VERSION = 1


class AtmosphereAck(Base):
    __tablename__ = "atmosphere_acks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    accepted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


def gate_required() -> bool:
    """pytest 下跳过（与限流一致），避免所有既有用例都要先点礼仪确认。"""
    return settings.atmosphere_gate_enabled and not settings.testing


def accepted_version(db: Session, user: User | None) -> int:
    if user is None:
        return 0
    return db.scalar(select(AtmosphereAck.version).where(AtmosphereAck.user_id == user.id)) or 0


def enforce_ack(db: Session, user: User) -> None:
    """发布/接取前的服务端闸门；超管豁免，避免运维账号被自己的确认流程挡在门外。"""
    if not gate_required() or user.is_admin:
        return
    if accepted_version(db, user) < ATMOSPHERE_VERSION:
        raise HTTPException(status_code=403, detail="请先完成委托礼仪确认后再发布或接取委托")


router = APIRouter(prefix="/api/atmosphere", tags=["atmosphere"])


@router.get("/status", response_model=AtmosphereStatusOut)
def atmosphere_status(
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """游客也能读；游客的确认状态由前端本地记录，服务端只知道「未确认」。"""
    version = accepted_version(db, user)
    return AtmosphereStatusOut(
        version=ATMOSPHERE_VERSION,
        accepted=version >= ATMOSPHERE_VERSION,
        accepted_version=version,
    )


@router.post("/ack", response_model=AtmosphereStatusOut)
def acknowledge(
    payload: AtmosphereAckRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    enforce("atmosphere-ack", str(user.id), 10, 600)
    if payload.version != ATMOSPHERE_VERSION:
        raise HTTPException(status_code=409, detail="礼仪确认版本已更新，请刷新页面后重新确认")
    record = db.scalar(select(AtmosphereAck).where(AtmosphereAck.user_id == user.id))
    if record is None:
        record = AtmosphereAck(user_id=user.id, version=payload.version, accepted_at=datetime.utcnow())
        db.add(record)
    else:
        record.version = payload.version
        record.accepted_at = datetime.utcnow()
    db.commit()
    return AtmosphereStatusOut(
        version=ATMOSPHERE_VERSION,
        accepted=True,
        accepted_version=payload.version,
    )
