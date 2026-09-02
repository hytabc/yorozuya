from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, Enum as SqlEnum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class TaskStatus(str, Enum):
    PUBLISHED = "published"
    ACCEPTED = "accepted"
    SUBMITTED = "submitted"
    COMPLETED = "completed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    published_tasks: Mapped[list["Task"]] = relationship(
        foreign_keys="Task.publisher_id", back_populates="publisher"
    )
    accepted_tasks: Mapped[list["Task"]] = relationship(
        foreign_keys="Task.assignee_id", back_populates="assignee"
    )


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(80), index=True)
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(24), default="其他")
    reward: Mapped[str | None] = mapped_column(String(60), nullable=True)
    status: Mapped[TaskStatus] = mapped_column(
        SqlEnum(TaskStatus, values_callable=lambda values: [item.value for item in values]),
        default=TaskStatus.PUBLISHED,
        index=True,
    )
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    admin_note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    publisher_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    publisher: Mapped[User] = relationship(foreign_keys=[publisher_id], back_populates="published_tasks")
    assignee: Mapped[User | None] = relationship(foreign_keys=[assignee_id], back_populates="accepted_tasks")
