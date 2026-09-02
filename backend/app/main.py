from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session, joinedload

from .config import settings
from .database import Base, SessionLocal, engine, get_db
from .dependencies import get_admin, get_current_user
from .models import Task, TaskStatus, User
from .schemas import (
    AdminStats,
    AdminTaskUpdate,
    LoginRequest,
    RegisterRequest,
    TaskCreate,
    TaskOut,
    TokenResponse,
    UserSelf,
    UserUpdate,
)
from .security import create_access_token, hash_password, verify_password


def initialize_database() -> None:
    Base.metadata.create_all(bind=engine)
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


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)
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
            Task.status.in_([TaskStatus.PUBLISHED, TaskStatus.ACCEPTED, TaskStatus.SUBMITTED]),
        )
        .values(status=TaskStatus.EXPIRED, updated_at=datetime.utcnow())
    )
    if result.rowcount:
        db.commit()


def task_query():
    return select(Task).options(joinedload(Task.publisher), joinedload(Task.assignee))


def present_task(task: Task, viewer: User | None = None) -> TaskOut:
    data = TaskOut.model_validate(task)
    if viewer and (viewer.is_admin or viewer.id in {task.publisher_id, task.assignee_id}):
        contact = task.assignee.qq if viewer.id == task.publisher_id and task.assignee else task.publisher.qq
        data.contact_qq = contact
    return data


def get_task_or_404(db: Session, task_id: int) -> Task:
    task = db.scalar(task_query().where(Task.id == task_id))
    if task is None:
        raise HTTPException(status_code=404, detail="委托不存在")
    return task


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


@app.get("/api/tasks", response_model=list[TaskOut])
def list_tasks(
    search: str = Query(default="", max_length=80),
    category: str = Query(default=""),
    task_status: TaskStatus | None = Query(default=None, alias="status"),
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
    tasks = db.scalars(query.order_by(Task.created_at.desc()).limit(200)).unique().all()
    return [present_task(task) for task in tasks]


@app.get("/api/tasks/mine", response_model=list[TaskOut])
def my_tasks(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    expire_due_tasks(db)
    tasks = db.scalars(
        task_query()
        .where(or_(Task.publisher_id == user.id, Task.assignee_id == user.id))
        .order_by(Task.updated_at.desc())
    ).unique().all()
    return [present_task(task, user) for task in tasks]


@app.get("/api/tasks/{task_id}", response_model=TaskOut)
def task_detail(task_id: int, db: Session = Depends(get_db)):
    expire_due_tasks(db)
    task = get_task_or_404(db, task_id)
    if not task.is_visible:
        raise HTTPException(status_code=404, detail="委托不存在")
    return present_task(task)


@app.post("/api/tasks", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    now = datetime.utcnow()
    if payload.expires_at < now + timedelta(hours=1):
        raise HTTPException(status_code=422, detail="有效期至少需要 1 小时")
    if payload.expires_at > now + timedelta(days=90):
        raise HTTPException(status_code=422, detail="有效期最长为 90 天")
    task_data = payload.model_dump()
    task_data.update(
        title=payload.title.strip(),
        description=payload.description.strip(),
        reward=payload.reward.strip() if payload.reward else None,
        publisher_id=user.id,
    )
    task = Task(**task_data)
    db.add(task)
    db.commit()
    return present_task(get_task_or_404(db, task.id), user)


@app.post("/api/tasks/{task_id}/accept", response_model=TaskOut)
def accept_task(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    expire_due_tasks(db)
    task = get_task_or_404(db, task_id)
    if not task.is_visible:
        raise HTTPException(status_code=403, detail="该委托已被管理员隐藏")
    if task.publisher_id == user.id:
        raise HTTPException(status_code=400, detail="不能接受自己发布的委托")
    result = db.execute(
        update(Task)
        .where(Task.id == task_id, Task.status == TaskStatus.PUBLISHED, Task.assignee_id.is_(None))
        .values(status=TaskStatus.ACCEPTED, assignee_id=user.id, accepted_at=datetime.utcnow(), updated_at=datetime.utcnow())
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="该委托已被接受或不可处理")
    db.commit()
    return present_task(get_task_or_404(db, task_id), user)


@app.post("/api/tasks/{task_id}/submit", response_model=TaskOut)
def submit_task(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    expire_due_tasks(db)
    task = get_task_or_404(db, task_id)
    if task.assignee_id != user.id or task.status != TaskStatus.ACCEPTED:
        raise HTTPException(status_code=403, detail="当前委托不可提交")
    task.status = TaskStatus.SUBMITTED
    task.submitted_at = datetime.utcnow()
    db.commit()
    return present_task(get_task_or_404(db, task_id), user)


@app.post("/api/tasks/{task_id}/confirm", response_model=TaskOut)
def confirm_task(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    expire_due_tasks(db)
    task = get_task_or_404(db, task_id)
    if task.publisher_id != user.id or task.status != TaskStatus.SUBMITTED:
        raise HTTPException(status_code=403, detail="当前委托不可验收")
    task.status = TaskStatus.COMPLETED
    task.completed_at = datetime.utcnow()
    db.commit()
    return present_task(get_task_or_404(db, task_id), user)


@app.post("/api/tasks/{task_id}/cancel", response_model=TaskOut)
def cancel_task(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    task = get_task_or_404(db, task_id)
    if task.publisher_id != user.id or task.status != TaskStatus.PUBLISHED:
        raise HTTPException(status_code=403, detail="只能取消自己尚未被接受的委托")
    task.status = TaskStatus.CANCELLED
    db.commit()
    return present_task(get_task_or_404(db, task_id), user)


@app.get("/api/admin/stats", response_model=AdminStats)
def admin_stats(_: User = Depends(get_admin), db: Session = Depends(get_db)):
    expire_due_tasks(db)
    return AdminStats(
        users=db.scalar(select(func.count()).select_from(User)) or 0,
        tasks=db.scalar(select(func.count()).select_from(Task)) or 0,
        published=db.scalar(select(func.count()).select_from(Task).where(Task.status == TaskStatus.PUBLISHED)) or 0,
        processing=db.scalar(select(func.count()).select_from(Task).where(Task.status.in_([TaskStatus.ACCEPTED, TaskStatus.SUBMITTED]))) or 0,
        completed=db.scalar(select(func.count()).select_from(Task).where(Task.status == TaskStatus.COMPLETED)) or 0,
        hidden=db.scalar(select(func.count()).select_from(Task).where(Task.is_visible.is_(False))) or 0,
    )


@app.get("/api/admin/tasks", response_model=list[TaskOut])
def admin_tasks(_: User = Depends(get_admin), db: Session = Depends(get_db)):
    expire_due_tasks(db)
    tasks = db.scalars(task_query().order_by(Task.updated_at.desc()).limit(500)).unique().all()
    return [present_task(task, _) for task in tasks]


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
