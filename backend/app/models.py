from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SqlEnum,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class TaskStatus(str, Enum):
    PUBLISHED = "published"  # 已发布/待开始：正在招募接单人
    ACCEPTED = "accepted"  # 处理中：人数足够或委托人已点击开始
    AWAITING = "awaiting"  # 待确认：有人已确认完成，等其余人
    COMPLETED = "completed"  # 已完成：委托人与全部接单人确认完成
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class FeedbackStatus(str, Enum):
    PENDING = "pending"  # 待处理
    HANDLED = "handled"  # 已处理


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    nickname: Mapped[str] = mapped_column(String(32))
    qq: Mapped[str | None] = mapped_column(String(20), nullable=True)
    bio: Mapped[str | None] = mapped_column(String(300), nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    max_concurrent_tasks: Mapped[int] = mapped_column(default=2)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    published_tasks: Mapped[list["Task"]] = relationship(
        foreign_keys="Task.publisher_id", back_populates="publisher"
    )
    memberships: Mapped[list["TaskMember"]] = relationship(
        foreign_keys="TaskMember.user_id", back_populates="user"
    )


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(80), index=True)
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(24), default="其他")
    # 是否有偿：paid=有偿, free=无偿
    pay_type: Mapped[str] = mapped_column(String(8), default="paid", index=True)
    reward: Mapped[str | None] = mapped_column(String(60), nullable=True)
    status: Mapped[TaskStatus] = mapped_column(
        SqlEnum(TaskStatus, values_callable=lambda values: [item.value for item in values]),
        default=TaskStatus.PUBLISHED,
        index=True,
    )
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    admin_note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    publisher_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    # 委托人设置的接取密码（只存哈希，任何接口都不会回传明文）
    accept_password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # 需要几人接取该委托：null 表示人数不限（仅能由委托人手动点击开始）
    required_takers: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # 完成确认：委托人（发布人）也需要确认
    publisher_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    publisher: Mapped[User] = relationship(foreign_keys=[publisher_id], back_populates="published_tasks")
    members: Mapped[list["TaskMember"]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="TaskMember.joined_at",
    )

    # ---- 便捷判断 ----
    @property
    def all_confirmed(self) -> bool:
        """委托人与所有接单人都已确认完成。"""
        if self.publisher_confirmed_at is None:
            return False
        if not self.members:
            return False
        return all(member.confirmed_at is not None for member in self.members)


class TaskMember(Base):
    """委托的接单人（多人）。joined 表示已接取；confirmed_at 表示该成员确认完成。"""

    __tablename__ = "task_members"
    __table_args__ = (UniqueConstraint("task_id", "user_id", name="uq_task_member"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    task: Mapped[Task] = relationship(back_populates="members")
    user: Mapped[User] = relationship(foreign_keys=[user_id], back_populates="memberships")


class Feedback(Base):
    """用户反馈/建议。"""

    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    page: Mapped[str | None] = mapped_column(String(120), nullable=True)
    content: Mapped[str] = mapped_column(Text)
    contact: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[FeedbackStatus] = mapped_column(
        SqlEnum(FeedbackStatus, values_callable=lambda values: [item.value for item in values]),
        default=FeedbackStatus.PENDING,
        index=True,
    )
    reply: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    handled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped[User | None] = relationship(foreign_keys=[user_id])
