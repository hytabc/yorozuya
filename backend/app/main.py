from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BeforeValidator
from sqlalchemy import func, or_, select, text, update
from sqlalchemy.orm import Session, joinedload

from .config import settings
from .database import Base, SessionLocal, engine, get_db
from .dependencies import get_admin, get_current_user, get_optional_user
from .models import Feedback, FeedbackStatus, Task, TaskMember, TaskStatus, User, UserRole
from .schemas import (
    AcceptRequest,
    AdminStats,
    AdminTaskUpdate,
    AdminUserLimitUpdate,
    AdminUserOut,
    AdminUserRoleUpdate,
    FeedbackCreate,
    FeedbackOut,
    FeedbackUpdate,
    LoginRequest,
    PasswordUpdate,
    RegisterRequest,
    TaskCreate,
    TaskMemberOut,
    TaskOut,
    TokenResponse,
    UserProfileOut,
    UserSelf,
    UserUpdate,
)
from .security import create_access_token, hash_password, verify_password


TaskStatusFilter = Annotated[
    TaskStatus | None,
    BeforeValidator(lambda value: None if value == "" else value),
]


def initialize_database() -> None:
    Base.metadata.create_all(bind=engine)
    migrate_schema()
    with SessionLocal() as db:
        admin = db.scalar(select(User).where(User.username == settings.admin_username))
        if admin is None:
            db.add(
                User(
                    username=settings.admin_username,
                    password_hash=hash_password(settings.admin_password),
                    nickname=settings.admin_nickname,
                    is_admin=True,
                )
            )
            db.commit()


def migrate_schema() -> None:
    """把旧版数据库升级到当前多接单人模型（SQLite 轻量迁移）。"""
    if not settings.database_url.startswith("sqlite"):
        return
    from sqlalchemy import inspect as sa_inspect

    inspector = sa_inspect(engine)
    with engine.begin() as connection:
        if inspector.has_table("users"):
            user_columns = {column["name"] for column in inspector.get_columns("users")}
            if "max_concurrent_tasks" not in user_columns:
                connection.execute(
                    text("ALTER TABLE users ADD COLUMN max_concurrent_tasks INTEGER NOT NULL DEFAULT 2")
                )
            if "role" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR(16) NOT NULL DEFAULT 'user'"))
        if not inspector.has_table("tasks"):
            return
        task_columns = {column["name"] for column in inspector.get_columns("tasks")}
        if "required_takers" not in task_columns:
            connection.execute(text("ALTER TABLE tasks ADD COLUMN required_takers INTEGER"))
        if "started_at" not in task_columns:
            connection.execute(text("ALTER TABLE tasks ADD COLUMN started_at DATETIME"))
        if "pay_type" not in task_columns:
            connection.execute(text("ALTER TABLE tasks ADD COLUMN pay_type VARCHAR(8)"))
            # 旧委托回填：填了报酬说明视为有偿，否则视为无偿
            connection.execute(
                text("UPDATE tasks SET pay_type = 'paid' WHERE pay_type IS NULL AND reward IS NOT NULL AND reward <> ''")
            )
            connection.execute(
                text("UPDATE tasks SET pay_type = 'free' WHERE pay_type IS NULL")
            )
        if "cancelled_at" not in task_columns:
            connection.execute(text("ALTER TABLE tasks ADD COLUMN cancelled_at DATETIME"))
        if "cancel_requested_by" not in task_columns:
            connection.execute(text("ALTER TABLE tasks ADD COLUMN cancel_requested_by INTEGER"))
        if "cancel_requested_at" not in task_columns:
            connection.execute(text("ALTER TABLE tasks ADD COLUMN cancel_requested_at DATETIME"))
        if "cancel_resume_status" not in task_columns:
            connection.execute(text("ALTER TABLE tasks ADD COLUMN cancel_resume_status VARCHAR(16)"))
        if "publisher_cancel_confirmed_at" not in task_columns:
            connection.execute(text("ALTER TABLE tasks ADD COLUMN publisher_cancel_confirmed_at DATETIME"))
        if inspector.has_table("task_members"):
            member_columns = {column["name"] for column in inspector.get_columns("task_members")}
            if "cancel_confirmed_at" not in member_columns:
                connection.execute(text("ALTER TABLE task_members ADD COLUMN cancel_confirmed_at DATETIME"))
        # 旧版单接单人数据升级：
        # 1) submitted(已提交待验收) -> awaiting(待确认)，以提交时间作为接单人确认时间
        # 2) 有 assignee_id 的任务，把接单人搬进 task_members
        if "assignee_id" in task_columns:
            connection.execute(
                text(
                    "UPDATE tasks SET status='awaiting', assignee_confirmed_at = COALESCE(assignee_confirmed_at, submitted_at)"
                    " WHERE status='submitted' AND assignee_id IS NOT NULL"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO task_members (task_id, user_id, joined_at, confirmed_at) "
                    "SELECT t.id, t.assignee_id, COALESCE(t.accepted_at, t.created_at), t.assignee_confirmed_at "
                    "FROM tasks t "
                    "WHERE t.assignee_id IS NOT NULL "
                    "AND NOT EXISTS (SELECT 1 FROM task_members m WHERE m.task_id = t.id AND m.user_id = t.assignee_id)"
                )
            )
            if "accepted_at" in task_columns:
                connection.execute(
                    text(
                        "UPDATE tasks SET started_at = COALESCE(started_at, accepted_at) "
                        "WHERE assignee_id IS NOT NULL AND started_at IS NULL AND accepted_at IS NOT NULL"
                    )
                )
            connection.execute(
                text(
                    "UPDATE tasks SET required_takers = COALESCE(required_takers, 1) "
                    "WHERE assignee_id IS NOT NULL AND required_takers IS NULL"
                )
            )


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


app = FastAPI(title=settings.app_name, version="1.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def expire_due_tasks(db: Session) -> None:
    result = db.execute(
        update(Task)
        .where(
            Task.expires_at <= datetime.utcnow(),
            Task.status.in_([TaskStatus.PUBLISHED, TaskStatus.ACCEPTED, TaskStatus.AWAITING, TaskStatus.CANCELLING]),
        )
        .values(status=TaskStatus.EXPIRED, updated_at=datetime.utcnow())
    )
    if result.rowcount:
        db.commit()


def task_query():
    return select(Task).options(joinedload(Task.publisher), joinedload(Task.members).joinedload(TaskMember.user))


def present_members(task: Task, viewer: User | None) -> list[TaskMemberOut]:
    """成员序列化；qq 只在协作相关方（委托人/成员/管理员）可见。"""
    can_see_qq = viewer is not None and (viewer.is_admin or viewer.id == task.publisher_id or any(m.user_id == viewer.id for m in task.members))
    out: list[TaskMemberOut] = []
    for member in task.members:
        item = TaskMemberOut.model_validate(member)
        if can_see_qq:
            item.qq = member.user.qq
        out.append(item)
    return out


def present_task(task: Task, viewer: User | None = None) -> TaskOut:
    data = TaskOut.model_validate(task)
    data.members = present_members(task, viewer)
    if viewer is None:
        return data
    if viewer.is_admin:
        # 管理员可看到发布人联系方式，便于处理纠纷
        data.contact_qq = task.publisher.qq
        return data
    if task.publisher_id == viewer.id:
        # 委托人：成员 QQ 已在成员列表可见
        return data
    if any(m.user_id == viewer.id for m in task.members):
        # 接单人：可见委托人联系方式
        data.contact_qq = task.publisher.qq
        return data
    if task.status == TaskStatus.PUBLISHED and task.is_visible:
        # 待开始的委托：登录用户可看到委托人 QQ，用于联系洽谈
        data.contact_qq = task.publisher.qq
    return data


def get_task_or_404(db: Session, task_id: int) -> Task:
    task = db.scalar(task_query().where(Task.id == task_id))
    if task is None:
        raise HTTPException(status_code=404, detail="委托不存在")
    return task


def present_feedback(feedback: Feedback) -> FeedbackOut:
    return FeedbackOut.model_validate(feedback)


def member_of(db: Session, task_id: int, user_id: int) -> TaskMember | None:
    return db.scalar(select(TaskMember).where(TaskMember.task_id == task_id, TaskMember.user_id == user_id))


def shares_task_with(db: Session, viewer_id: int, target_id: int) -> bool:
    """两人是否在同一委托中共事过（一个委托人发布、另一个成员接取，或同为成员）。"""
    if viewer_id == target_id:
        return True
    viewer_tasks = set(db.scalars(select(Task.id).where(Task.publisher_id == viewer_id)))
    viewer_tasks |= set(db.scalars(select(TaskMember.task_id).where(TaskMember.user_id == viewer_id)))
    target_tasks = set(db.scalars(select(Task.id).where(Task.publisher_id == target_id)))
    target_tasks |= set(db.scalars(select(TaskMember.task_id).where(TaskMember.user_id == target_id)))
    return bool(viewer_tasks & target_tasks)


def can_view_user_qq(db: Session, viewer: User, target: User) -> bool:
    """能否看到该用户的 QQ：本人/管理员/共同协作双方可见；此外对方有正在招募的公开委托时也开放（洽谈用）。"""
    if viewer.is_admin or viewer.id == target.id:
        return True
    if shares_task_with(db, viewer.id, target.id):
        return True
    recruiting = db.scalar(
        select(Task.id)
        .where(
            Task.publisher_id == target.id,
            Task.status == TaskStatus.PUBLISHED,
            Task.is_visible.is_(True),
        )
        .limit(1)
    )
    return recruiting is not None


ACTIVE_TAKEN_STATUSES = (TaskStatus.PUBLISHED, TaskStatus.ACCEPTED, TaskStatus.AWAITING, TaskStatus.CANCELLING)


def active_task_count(db: Session, user_id: int) -> int:
    return db.scalar(
        select(func.count())
        .select_from(TaskMember)
        .join(Task, Task.id == TaskMember.task_id)
        .where(TaskMember.user_id == user_id, Task.status.in_(ACTIVE_TAKEN_STATUSES))
    ) or 0


def start_if_ready(db: Session, task: Task) -> None:
    """达到所需人数时自动开始。required_takers 为 null 表示不限人数，只有委托人手动开始。"""
    if task.status != TaskStatus.PUBLISHED:
        return
    if task.required_takers is None:
        return
    count = db.scalar(select(func.count()).select_from(TaskMember).where(TaskMember.task_id == task.id)) or 0
    if count >= task.required_takers:
        task.status = TaskStatus.ACCEPTED
        task.started_at = task.started_at or datetime.utcnow()
        task.updated_at = datetime.utcnow()


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/auth/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.username == payload.username)):
        raise HTTPException(status_code=409, detail="用户名已被使用")
    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        nickname=payload.nickname,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return TokenResponse(access_token=create_access_token(user.id), user=UserSelf.model_validate(user))


@app.post("/api/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == payload.username))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="账号已停用")
    return TokenResponse(access_token=create_access_token(user.id), user=UserSelf.model_validate(user))


@app.get("/api/auth/me", response_model=UserSelf)
def me(user: User = Depends(get_current_user)):
    return user


@app.patch("/api/users/me", response_model=UserSelf)
def update_profile(payload: UserUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.nickname = payload.nickname.strip()
    user.qq = payload.qq
    user.bio = payload.bio.strip() if payload.bio else None
    db.commit()
    db.refresh(user)
    return user


@app.get("/api/users/{user_id}", response_model=UserProfileOut)
def user_profile(user_id: int, viewer: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """查看用户个人资料：昵称/简介/加入时间公开；QQ 仅在可协作洽谈范围内可见。"""
    target = db.get(User, user_id)
    if target is None or not target.is_active:
        raise HTTPException(status_code=404, detail="用户不存在")
    data = UserProfileOut.model_validate(target)
    if not can_view_user_qq(db, viewer, target):
        data.qq = None
    return data


@app.post("/api/feedback", response_model=FeedbackOut, status_code=status.HTTP_201_CREATED)
def create_feedback(
    payload: FeedbackCreate,
    viewer: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """提交反馈/建议。登录用户可留空联系方式；游客需填写联系方式便于管理员回复。"""
    if viewer is None and not payload.contact:
        raise HTTPException(status_code=422, detail="请先登录，或填写联系方式以便管理员联系你")
    if viewer is None and payload.contact and len(payload.contact) < 2:
        raise HTTPException(status_code=422, detail="联系方式至少需要 2 个字符")
    feedback = Feedback(
        user_id=viewer.id if viewer else None,
        page=payload.page.strip() if payload.page else None,
        content=payload.content.strip(),
        contact=payload.contact.strip() if payload.contact else None,
    )
    db.add(feedback)
    db.commit()
    return present_feedback(feedback)


@app.get("/api/feedback/mine", response_model=list[FeedbackOut])
def my_feedback(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """当前用户提交过的反馈及其处理状态。"""
    feedback_list = db.scalars(
        select(Feedback).where(Feedback.user_id == user.id).order_by(Feedback.created_at.desc())
    ).all()
    return [present_feedback(item) for item in feedback_list]


@app.get("/api/admin/feedback", response_model=list[FeedbackOut])
def admin_feedback(_: User = Depends(get_admin), db: Session = Depends(get_db)):
    feedback_list = db.scalars(select(Feedback).order_by(Feedback.created_at.desc()).limit(500)).all()
    return [present_feedback(item) for item in feedback_list]


@app.patch("/api/admin/feedback/{feedback_id}", response_model=FeedbackOut)
def handle_feedback(
    feedback_id: int,
    payload: FeedbackUpdate,
    _: User = Depends(get_admin),
    db: Session = Depends(get_db),
):
    """管理员处理反馈：标记状态并填写处理回复。"""
    feedback = db.get(Feedback, feedback_id)
    if feedback is None:
        raise HTTPException(status_code=404, detail="反馈不存在")
    if payload.status is not None:
        feedback.status = payload.status
        feedback.handled_at = datetime.utcnow() if payload.status == FeedbackStatus.HANDLED else None
    if payload.reply is not None:
        feedback.reply = payload.reply.strip() or None
    feedback.handled_at = datetime.utcnow() if feedback.status == FeedbackStatus.HANDLED else feedback.handled_at
    db.commit()
    return present_feedback(feedback)


@app.get("/api/tasks", response_model=list[TaskOut])
def list_tasks(
    search: str = Query(default="", max_length=80),
    category: str = Query(default=""),
    task_status: Annotated[TaskStatusFilter, Query(alias="status")] = None,
    pay_type: str = Query(default=""),
    viewer: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    expire_due_tasks(db)
    query = task_query().where(Task.is_visible.is_(True))
    if search:
        query = query.where(or_(Task.title.contains(search), Task.description.contains(search)))
    if category:
        query = query.where(Task.category == category)
    if task_status:
        query = query.where(Task.status == task_status)
    if pay_type in ("paid", "free"):
        query = query.where(Task.pay_type == pay_type)
    tasks = db.scalars(query.order_by(Task.created_at.desc()).limit(200)).unique().all()
    return [present_task(task, viewer) for task in tasks]


@app.get("/api/tasks/mine", response_model=list[TaskOut])
def my_tasks(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    expire_due_tasks(db)
    tasks = db.scalars(
        task_query()
        .where(
            or_(
                Task.publisher_id == user.id,
                Task.id.in_(select(TaskMember.task_id).where(TaskMember.user_id == user.id)),
            )
        )
        .order_by(Task.updated_at.desc())
    ).unique().all()
    return [present_task(task, user) for task in tasks]


@app.get("/api/tasks/{task_id}", response_model=TaskOut)
def task_detail(task_id: int, viewer: User | None = Depends(get_optional_user), db: Session = Depends(get_db)):
    expire_due_tasks(db)
    task = get_task_or_404(db, task_id)
    if not task.is_visible:
        raise HTTPException(status_code=404, detail="委托不存在")
    return present_task(task, viewer)


@app.post("/api/tasks", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    now = datetime.utcnow()
    if payload.expires_at < now + timedelta(hours=1):
        raise HTTPException(status_code=422, detail="有效期至少需要 1 小时")
    if payload.expires_at > now + timedelta(days=90):
        raise HTTPException(status_code=422, detail="有效期最长为 90 天")
    task = Task(
        title=payload.title.strip(),
        description=payload.description.strip(),
        category=payload.category,
        pay_type=payload.pay_type,
        reward=payload.reward.strip() if payload.reward else None,
        expires_at=payload.expires_at,
        publisher_id=user.id,
        required_takers=payload.required_takers,
        accept_password_hash=hash_password(payload.accept_password),
    )
    db.add(task)
    db.commit()
    return present_task(get_task_or_404(db, task.id), user)


@app.post("/api/tasks/{task_id}/accept", response_model=TaskOut)
def accept_task(
    task_id: int,
    payload: AcceptRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """接单人凭密码加入委托（按人数计算：一个账号算一位）。人数足够时自动开始。"""
    expire_due_tasks(db)
    task = get_task_or_404(db, task_id)
    if not task.is_visible:
        raise HTTPException(status_code=403, detail="该委托已被管理员隐藏")
    if task.publisher_id == user.id:
        raise HTTPException(status_code=400, detail="不能接取自己发布的委托")
    if user.is_admin:
        raise HTTPException(status_code=403, detail="管理员不接取委托")
    if user.role != UserRole.VOLUNTEER:
        raise HTTPException(status_code=403, detail="只有志愿者可以接取委托，请联系管理员升级")
    if task.status != TaskStatus.PUBLISHED:
        raise HTTPException(status_code=409, detail="委托已开始或不可接取")
    if member_of(db, task_id, user.id) is not None:
        raise HTTPException(status_code=409, detail="你已经接取过该委托")
    if task.required_takers is not None:
        joined = db.scalar(select(func.count()).select_from(TaskMember).where(TaskMember.task_id == task.id)) or 0
        if joined >= task.required_takers:
            raise HTTPException(status_code=409, detail="需要的人数已满，委托即将开始")
    if not task.accept_password_hash:
        raise HTTPException(status_code=403, detail="该委托尚未设置接取密码，请联系委托人处理")
    if not verify_password(payload.password, task.accept_password_hash):
        raise HTTPException(status_code=403, detail="接取密码不正确，请联系委托人确认")
    # 在支持行锁的数据库上串行化同一用户的接单操作，避免并发突破个人上限。
    db.scalar(select(User).where(User.id == user.id).with_for_update())
    if active_task_count(db, user.id) >= user.max_concurrent_tasks:
        raise HTTPException(
            status_code=409,
            detail=f"你同时接取的委托已达上限（{user.max_concurrent_tasks} 个）",
        )
    db.add(TaskMember(task_id=task.id, user_id=user.id))
    db.commit()
    task = get_task_or_404(db, task_id)
    start_if_ready(db, task)
    db.commit()
    return present_task(get_task_or_404(db, task_id), user)


@app.post("/api/tasks/{task_id}/start", response_model=TaskOut)
def start_task(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """委托人手动开始委托任务（即使人数不足也可以开始）。"""
    expire_due_tasks(db)
    task = get_task_or_404(db, task_id)
    if task.publisher_id != user.id:
        raise HTTPException(status_code=403, detail="只有委托人（发布人）可以开始委托")
    if task.status != TaskStatus.PUBLISHED:
        raise HTTPException(status_code=409, detail="委托已开始或不可开始")
    if not task.members:
        raise HTTPException(status_code=409, detail="至少需要一名接单人才能开始，先把密码告知接单人吧")
    task.status = TaskStatus.ACCEPTED
    task.started_at = datetime.utcnow()
    task.updated_at = datetime.utcnow()
    db.commit()
    return present_task(get_task_or_404(db, task_id), user)


@app.post("/api/tasks/{task_id}/leave", response_model=TaskOut)
def leave_task(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """接单人在委托开始前退出接取。"""
    expire_due_tasks(db)
    task = get_task_or_404(db, task_id)
    membership = member_of(db, task_id, user.id)
    if membership is None:
        raise HTTPException(status_code=403, detail="你不是该委托的接单人")
    if task.status != TaskStatus.PUBLISHED:
        raise HTTPException(status_code=409, detail="委托已经开始，不能退出")
    db.delete(membership)
    db.commit()
    return present_task(get_task_or_404(db, task_id), user)


@app.post("/api/tasks/{task_id}/confirm", response_model=TaskOut)
def confirm_task(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """完成确认：委托人（发布人）与每一位接单人都需要确认；全部确认后委托才算完成。"""
    expire_due_tasks(db)
    task = get_task_or_404(db, task_id)
    if task.status not in (TaskStatus.ACCEPTED, TaskStatus.AWAITING):
        raise HTTPException(status_code=409, detail="当前状态不能确认完成")
    now = datetime.utcnow()
    if task.publisher_id == user.id:
        if task.publisher_confirmed_at is not None:
            raise HTTPException(status_code=409, detail="你已确认完成")
        task.publisher_confirmed_at = now
    else:
        membership = member_of(db, task_id, user.id)
        if membership is None:
            raise HTTPException(status_code=403, detail="只有委托人和接单人可确认完成")
        if membership.confirmed_at is not None:
            raise HTTPException(status_code=409, detail="你已确认完成")
        membership.confirmed_at = now
    task = get_task_or_404(db, task_id)
    if task.all_confirmed:
        task.status = TaskStatus.COMPLETED
        task.completed_at = now
    elif any(member.confirmed_at is not None for member in task.members) or task.publisher_confirmed_at is not None:
        task.status = TaskStatus.AWAITING
    else:
        task.status = TaskStatus.ACCEPTED
    task.updated_at = now
    db.commit()
    return present_task(get_task_or_404(db, task_id), user)


@app.patch("/api/tasks/{task_id}/password", response_model=TaskOut)
def update_task_password(
    task_id: int,
    payload: PasswordUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """委托人重设接取密码：仅在委托尚未开始时可用。"""
    task = get_task_or_404(db, task_id)
    if task.publisher_id != user.id:
        raise HTTPException(status_code=403, detail="只有委托人可以重设接取密码")
    if task.status != TaskStatus.PUBLISHED:
        raise HTTPException(status_code=409, detail="委托开始后不能重设密码")
    task.accept_password_hash = hash_password(payload.password)
    task.updated_at = datetime.utcnow()
    db.commit()
    return present_task(get_task_or_404(db, task_id), user)


@app.post("/api/tasks/{task_id}/cancel", response_model=TaskOut)
def request_cancel_task(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """发起取消委托：委托人或任一接单人都可在未完成阶段发起，进入取消确认(cancelling)。

    委托仍无人接取（published 且无成员）时，委托人可直接取消；否则需委托人+全体接单人确认。
    """
    expire_due_tasks(db)
    task = get_task_or_404(db, task_id)
    if task.publisher_id != user.id and member_of(db, task_id, user.id) is None:
        raise HTTPException(status_code=403, detail="只有委托人或接单人能发起取消")
    if task.status == TaskStatus.CANCELLING:
        raise HTTPException(status_code=409, detail="已发起取消，等待双方确认")
    if task.status not in (TaskStatus.PUBLISHED, TaskStatus.ACCEPTED, TaskStatus.AWAITING):
        raise HTTPException(status_code=409, detail="当前状态不能取消委托")
    now = datetime.utcnow()
    # 尚未有人接取：委托人直接取消
    if task.publisher_id == user.id and not task.members:
        task.status = TaskStatus.CANCELLED
        task.cancelled_at = now
        task.updated_at = now
        db.commit()
        return present_task(get_task_or_404(db, task_id), user)
    # 进入取消确认：记录发起人与要恢复的状态，发起人视为已同意
    original_status = task.status
    task.status = TaskStatus.CANCELLING
    task.cancel_requested_by = user.id
    task.cancel_requested_at = now
    task.cancel_resume_status = original_status
    if task.publisher_id == user.id:
        task.publisher_cancel_confirmed_at = now
    else:
        membership = member_of(db, task_id, user.id)
        if membership is not None:
            membership.cancel_confirmed_at = now
    task.updated_at = now
    db.commit()
    return present_task(get_task_or_404(db, task_id), user)


@app.post("/api/tasks/{task_id}/confirm-cancel", response_model=TaskOut)
def confirm_cancel_task(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """同意取消：委托人或接单人各自确认，全部同意后委托才取消。"""
    expire_due_tasks(db)
    task = get_task_or_404(db, task_id)
    if task.status != TaskStatus.CANCELLING:
        raise HTTPException(status_code=409, detail="当前没有待确认的取消请求")
    if task.publisher_id != user.id and member_of(db, task_id, user.id) is None:
        raise HTTPException(status_code=403, detail="只有委托人或接单人可确认取消")
    now = datetime.utcnow()
    if task.publisher_id == user.id:
        if task.publisher_cancel_confirmed_at is not None:
            raise HTTPException(status_code=409, detail="你已同意取消")
        task.publisher_cancel_confirmed_at = now
    else:
        membership = member_of(db, task_id, user.id)
        if membership is None or membership.cancel_confirmed_at is not None:
            raise HTTPException(status_code=409, detail="你已同意取消")
        membership.cancel_confirmed_at = now
    task = get_task_or_404(db, task_id)
    if task.all_agree_to_cancel:
        task.status = TaskStatus.CANCELLED
        task.cancelled_at = now
    task.updated_at = now
    db.commit()
    return present_task(get_task_or_404(db, task_id), user)


@app.post("/api/tasks/{task_id}/cancel-continue", response_model=TaskOut)
def reject_cancel_task(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """不同意取消 / 撤回取消请求：委托继续，恢复到发起取消前的状态。"""
    expire_due_tasks(db)
    task = get_task_or_404(db, task_id)
    if task.status != TaskStatus.CANCELLING:
        raise HTTPException(status_code=409, detail="当前没有可撤回的取消请求")
    if task.publisher_id != user.id and member_of(db, task_id, user.id) is None:
        raise HTTPException(status_code=403, detail="只有委托人或接单人可操作取消请求")
    now = datetime.utcnow()
    resume = task.cancel_resume_status or TaskStatus.ACCEPTED
    task.status = resume
    task.cancel_requested_by = None
    task.cancel_requested_at = None
    task.cancel_resume_status = None
    task.publisher_cancel_confirmed_at = None
    for member in task.members:
        member.cancel_confirmed_at = None
    task.updated_at = now
    db.commit()
    return present_task(get_task_or_404(db, task_id), user)


@app.get("/api/admin/stats", response_model=AdminStats)
def admin_stats(_: User = Depends(get_admin), db: Session = Depends(get_db)):
    expire_due_tasks(db)
    return AdminStats(
        users=db.scalar(select(func.count()).select_from(User)) or 0,
        tasks=db.scalar(select(func.count()).select_from(Task)) or 0,
        published=db.scalar(select(func.count()).select_from(Task).where(Task.status == TaskStatus.PUBLISHED)) or 0,
        processing=db.scalar(select(func.count()).select_from(Task).where(Task.status.in_([TaskStatus.ACCEPTED, TaskStatus.AWAITING]))) or 0,
        completed=db.scalar(select(func.count()).select_from(Task).where(Task.status == TaskStatus.COMPLETED)) or 0,
        hidden=db.scalar(select(func.count()).select_from(Task).where(Task.is_visible.is_(False))) or 0,
    )


@app.get("/api/admin/tasks", response_model=list[TaskOut])
def admin_tasks(_: User = Depends(get_admin), db: Session = Depends(get_db)):
    expire_due_tasks(db)
    tasks = db.scalars(task_query().order_by(Task.updated_at.desc()).limit(500)).unique().all()
    return [present_task(task, _) for task in tasks]


@app.get("/api/admin/users", response_model=list[AdminUserOut])
def admin_users(_: User = Depends(get_admin), db: Session = Depends(get_db)):
    expire_due_tasks(db)
    users = db.scalars(select(User).order_by(User.created_at.desc())).all()
    return [
        AdminUserOut.model_validate(user).model_copy(
            update={"active_task_count": active_task_count(db, user.id)}
        )
        for user in users
    ]


@app.patch("/api/admin/users/{user_id}/task-limit", response_model=AdminUserOut)
def update_user_task_limit(
    user_id: int,
    payload: AdminUserLimitUpdate,
    _: User = Depends(get_admin),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    user.max_concurrent_tasks = payload.max_concurrent_tasks
    db.commit()
    db.refresh(user)
    return AdminUserOut.model_validate(user).model_copy(
        update={"active_task_count": active_task_count(db, user.id)}
    )


@app.patch("/api/admin/users/{user_id}/role", response_model=AdminUserOut)
def update_user_role(
    user_id: int,
    payload: AdminUserRoleUpdate,
    _: User = Depends(get_admin),
    db: Session = Depends(get_db),
):
    """升级/降级权限：普通用户(user) <-> 志愿者(volunteer)。管理员账号不参与该设置。"""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.is_admin:
        raise HTTPException(status_code=409, detail="管理员账号的权限等级不可修改")
    user.role = payload.role
    db.commit()
    db.refresh(user)
    return AdminUserOut.model_validate(user).model_copy(
        update={"active_task_count": active_task_count(db, user.id)}
    )


@app.patch("/api/admin/tasks/{task_id}", response_model=TaskOut)
def moderate_task(
    task_id: int,
    payload: AdminTaskUpdate,
    admin: User = Depends(get_admin),
    db: Session = Depends(get_db),
):
    task = get_task_or_404(db, task_id)
    task.is_visible = payload.is_visible
    task.admin_note = payload.admin_note.strip() if payload.admin_note else None
    db.commit()
    return present_task(get_task_or_404(db, task_id), admin)
