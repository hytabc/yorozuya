"""站内事件流（通知中心）。

只记录「与当事人自己有关」的委托事件，不做全站新委托时间线。
邮件通知仍走原有 ``queue_task_notification``；事件流是同一批触发点上的站内副本，
区别是不依赖邮箱配置，也不会因为发信失败而丢失。
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import Field
from sqlalchemy import DateTime, ForeignKey, Integer, String, func, select, update
from sqlalchemy.orm import Mapped, Session, mapped_column

from .database import Base, get_db
from .dependencies import get_current_user
from .models import Task, TaskMemberResponse, User
from .ratelimit import enforce
from .schemas import RequestModel

# 前端 frontend/src/events.js 的 EVENT_LABELS 必须覆盖同一批 kind。
EVENT_KINDS = (
    "designated",
    "accepted",
    "started",
    "awaiting",
    "completed",
    "cancel_requested",
    "cancelled",
    "hidden",
)


class TaskEvent(Base):
    __tablename__ = "task_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ReadRequest(RequestModel):
    # 空数组表示「全部标记已读」。
    ids: list[int] = Field(default_factory=list, max_length=200)


def participant_ids(task: Task, *, include_publisher: bool = True, include_members: bool = True) -> list[int]:
    ids: list[int] = []
    if include_publisher and task.publisher_id:
        ids.append(task.publisher_id)
    if include_members:
        ids.extend(
            member.user_id
            for member in task.members
            if member.response_status == TaskMemberResponse.ACCEPTED
        )
    return ids


def record_event(
    db: Session,
    task: Task,
    kind: str,
    title: str,
    *,
    recipients: list[int] | None = None,
    exclude: User | None = None,
) -> list[TaskEvent]:
    """在状态变更的同一事务里写事件；调用方负责 commit。"""
    if kind not in EVENT_KINDS:
        raise ValueError(f"unknown task event kind: {kind}")
    targets = recipients if recipients is not None else participant_ids(task)
    created: list[TaskEvent] = []
    seen: set[int] = set()
    for user_id in targets:
        if not user_id or user_id in seen:
            continue
        if exclude is not None and user_id == exclude.id:
            continue
        seen.add(user_id)
        event = TaskEvent(user_id=user_id, task_id=task.id, kind=kind, title=title)
        db.add(event)
        created.append(event)
    return created


router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("")
def list_events(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    enforce("events-read", str(user.id), 120, 600)
    base = select(TaskEvent).where(TaskEvent.user_id == user.id)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    unread = db.scalar(
        select(func.count()).select_from(
            select(TaskEvent.id).where(
                TaskEvent.user_id == user.id, TaskEvent.read_at.is_(None)
            ).subquery()
        )
    ) or 0
    rows = db.scalars(
        base.order_by(TaskEvent.created_at.desc(), TaskEvent.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "unread": unread,
        "items": [
            {
                "id": row.id,
                "task_id": row.task_id,
                "kind": row.kind,
                "title": row.title,
                "read": row.read_at is not None,
                "created_at": row.created_at.isoformat() + "Z",
            }
            for row in rows
        ],
    }


@router.get("/summary")
def event_summary(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    enforce("events-read", str(user.id), 120, 600)
    unread = db.scalar(
        select(func.count()).select_from(
            select(TaskEvent.id).where(
                TaskEvent.user_id == user.id, TaskEvent.read_at.is_(None)
            ).subquery()
        )
    ) or 0
    return {"unread": unread}


@router.post("/read")
def mark_read(
    payload: ReadRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    enforce("events-read", str(user.id), 120, 600)
    query = update(TaskEvent).where(
        TaskEvent.user_id == user.id, TaskEvent.read_at.is_(None)
    )
    if payload.ids:
        query = query.where(TaskEvent.id.in_(payload.ids))
    result = db.execute(query.values(read_at=datetime.utcnow()))
    db.commit()
    return {"updated": result.rowcount or 0}
