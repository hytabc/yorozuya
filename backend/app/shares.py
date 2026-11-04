"""委托分享：记录分享动作（用于每日任务与后续邀请绑定），并提供二维码落地所需的短链。

分享本身不做权限限制：任何能看到委托的人都能复制链接；只有登录用户的分享才计入
``task_shares``，游客复制不计数。
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import DateTime, ForeignKey, Integer, String, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from .database import Base, get_db
from .dependencies import get_current_user
from .models import Task, User
from .schemas import ShareCreate, ShareOut

SHARE_CHANNELS = {"dialog", "copy", "qrcode", "native"}


class TaskShare(Base):
    __tablename__ = "task_shares"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(16), default="dialog", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


router = APIRouter(prefix="/api", tags=["shares"])


@router.post("/tasks/{task_id}/share", response_model=ShareOut)
def share_task(
    task_id: int,
    payload: ShareCreate | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """记录一次分享；返回可直接发给别人的站内路径。"""
    task = db.get(Task, task_id)
    if task is None or not task.is_visible:
        raise HTTPException(status_code=404, detail="委托不存在")
    channel = payload.channel if payload else "dialog"
    db.add(TaskShare(user_id=user.id, task_id=task.id, channel=channel))
    db.commit()
    today = db.scalar(
        select(func.count(func.distinct(TaskShare.task_id))).where(
            TaskShare.user_id == user.id,
            TaskShare.created_at >= datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0),
        )
    ) or 0
    return ShareOut(path=f"/?task={task.id}", title=task.title, channel=channel, shared_tasks_today=today)
