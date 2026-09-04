from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BeforeValidator
from sqlalchemy import func, or_, select, text, update
from sqlalchemy.orm import Session, joinedload

from .config import settings
from .database import Base, SessionLocal, engine, get_db
from .dependencies import get_admin, get_current_user, get_optional_user, get_role_manager
from .models import (
    Feedback,
    FeedbackStatus,
    SugarPair,
    SugarPairStatus,
    SugarPhoto,
    SugarProfile,
    Task,
    TaskMember,
    TaskMemberResponse,
    TaskStatus,
    User,
    UserPhoto,
    UserRole,
)
from .schemas import (
    AcceptRequest,
    AdminStats,
    AdminTaskUpdate,
    AdminUserLimitUpdate,
    AdminUserOut,
    AdminUserRoleUpdate,
    AdminPhotoUpdate,
    FeedbackCreate,
    FeedbackOut,
    FeedbackUpdate,
    LoginRequest,
    PasswordUpdate,
    RegisterRequest,
    TaskCreate,
    TaskMemberOut,
    TaskOut,
    StaffDirectoryOut,
    SugarPairOut,
    SugarPhotoOut,
    SugarProfileCardOut,
    SugarProfileDetailOut,
    TokenResponse,
    UserPasswordUpdate,
    UserPublic,
    UserProfileOut,
    UserPhotoOut,
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
            if "qq_public" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN qq_public BOOLEAN NOT NULL DEFAULT 0"))
        if not inspector.has_table("tasks"):
            return
        task_columns = {column["name"] for column in inspector.get_columns("tasks")}
        if "required_takers" not in task_columns:
            connection.execute(text("ALTER TABLE tasks ADD COLUMN required_takers INTEGER"))
        if "is_designated" not in task_columns:
            connection.execute(text("ALTER TABLE tasks ADD COLUMN is_designated BOOLEAN NOT NULL DEFAULT 0"))
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
        if "is_visible" not in task_columns:
            connection.execute(text("ALTER TABLE tasks ADD COLUMN is_visible BOOLEAN NOT NULL DEFAULT 1"))
        if "admin_note" not in task_columns:
            connection.execute(text("ALTER TABLE tasks ADD COLUMN admin_note VARCHAR(200)"))
        if inspector.has_table("task_members"):
            member_columns = {column["name"] for column in inspector.get_columns("task_members")}
            if "cancel_confirmed_at" not in member_columns:
                connection.execute(text("ALTER TABLE task_members ADD COLUMN cancel_confirmed_at DATETIME"))
            if "response_status" not in member_columns:
                connection.execute(
                    text("ALTER TABLE task_members ADD COLUMN response_status VARCHAR(16) NOT NULL DEFAULT 'accepted'")
                )
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
        # 用户介绍页图片使用独立表；文件仍统一落在 uploads 挂载目录。
        if inspector.has_table("user_photos"):
            photo_columns = {column["name"] for column in inspector.get_columns("user_photos")}
            if "is_visible" not in photo_columns:
                connection.execute(text("ALTER TABLE user_photos ADD COLUMN is_visible BOOLEAN NOT NULL DEFAULT 1"))
            if "moderated_by_id" not in photo_columns:
                connection.execute(text("ALTER TABLE user_photos ADD COLUMN moderated_by_id INTEGER"))
            if "moderated_at" not in photo_columns:
                connection.execute(text("ALTER TABLE user_photos ADD COLUMN moderated_at DATETIME"))


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
app.mount("/uploads", StaticFiles(directory=settings.sugar_upload_path), name="uploads")

# 万事屋看板娘(站内 AI 助手)
from .mascot import router as mascot_router  # noqa: E402

app.include_router(mascot_router)


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
    return select(Task).options(
        joinedload(Task.publisher).joinedload(User.photos),
        joinedload(Task.members).joinedload(TaskMember.user).joinedload(User.photos),
    )


def visible_user_photos(user: User, viewer: User | None = None) -> list[UserPhotoOut]:
    """资料主人和审核人员可看全部；其他访问者只能看已通过展示的图片。"""
    can_manage = viewer is not None and (viewer.id == user.id or viewer.is_admin or viewer.role == UserRole.STAFF)
    return [
        UserPhotoOut(id=photo.id, image_url=photo.image_url, is_visible=photo.is_visible)
        for photo in user.photos
        if can_manage or photo.is_visible
    ]


def present_user_public(user: User, viewer: User | None = None) -> UserPublic:
    return UserPublic(id=user.id, nickname=user.nickname, bio=user.bio, photos=visible_user_photos(user, viewer))


def present_user_profile(user: User, viewer: User | None = None) -> UserProfileOut:
    return UserProfileOut(
        id=user.id, nickname=user.nickname, bio=user.bio, qq=user.qq, qq_public=user.qq_public,
        is_admin=user.is_admin,
        role=user.role, created_at=user.created_at, photos=visible_user_photos(user, viewer),
    )


def present_members(task: Task, viewer: User | None) -> list[TaskMemberOut]:
    """成员序列化；qq 只在协作相关方（委托人/成员/管理员）可见。"""
    can_see_qq = viewer is not None and (viewer.is_admin or viewer.id == task.publisher_id or any(m.user_id == viewer.id for m in task.members))
    out: list[TaskMemberOut] = []
    for member in task.members:
        item = TaskMemberOut(
            user=present_user_public(member.user, viewer), joined_at=member.joined_at,
            response_status=member.response_status, confirmed_at=member.confirmed_at,
            cancel_confirmed_at=member.cancel_confirmed_at,
        )
        if can_see_qq:
            item.qq = member.user.qq
        out.append(item)
    return out


def present_task(task: Task, viewer: User | None = None) -> TaskOut:
    data = TaskOut.model_validate(task)
    can_see_hidden = viewer is not None and (
        viewer.is_admin or viewer.role == UserRole.STAFF or viewer.id == task.publisher_id
    )
    # 屏蔽原因只对监管人员和委托人返回，避免通过“我的委托”泄露给接单人。
    data.admin_note = task.admin_note if (not task.is_visible and can_see_hidden) else None
    data.publisher = present_user_public(task.publisher, viewer)
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


def can_view_hidden_task(task: Task, viewer: User | None) -> bool:
    return viewer is not None and (
        viewer.is_admin or viewer.role == UserRole.STAFF or viewer.id == task.publisher_id
    )


def present_feedback(feedback: Feedback) -> FeedbackOut:
    return FeedbackOut.model_validate(feedback)


def member_of(db: Session, task_id: int, user_id: int) -> TaskMember | None:
    return db.scalar(select(TaskMember).where(TaskMember.task_id == task_id, TaskMember.user_id == user_id))


def accepted_member_of(db: Session, task_id: int, user_id: int) -> TaskMember | None:
    return db.scalar(
        select(TaskMember).where(
            TaskMember.task_id == task_id,
            TaskMember.user_id == user_id,
            TaskMember.response_status == TaskMemberResponse.ACCEPTED,
        )
    )


def shares_task_with(db: Session, viewer_id: int, target_id: int) -> bool:
    """两人是否在同一委托中共事过（一个委托人发布、另一个成员接取，或同为成员）。"""
    if viewer_id == target_id:
        return True
    viewer_tasks = set(db.scalars(select(Task.id).where(Task.publisher_id == viewer_id)))
    viewer_tasks |= set(db.scalars(select(TaskMember.task_id).where(TaskMember.user_id == viewer_id)))
    target_tasks = set(db.scalars(select(Task.id).where(Task.publisher_id == target_id)))
    target_tasks |= set(db.scalars(select(TaskMember.task_id).where(TaskMember.user_id == target_id)))
    return bool(viewer_tasks & target_tasks)


def can_view_user_qq(db: Session, viewer: User | None, target: User) -> bool:
    """店员及主动公开的志愿者对外可见；原有协作关系始终优先放行。"""
    if target.role == UserRole.STAFF:
        return True
    if target.role == UserRole.VOLUNTEER and target.qq_public:
        return True
    if viewer is None:
        return False
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


MAX_SUGAR_PHOTOS = 6
MAX_SUGAR_IMAGE_BYTES = 5 * 1024 * 1024
IMAGE_SIGNATURES = (
    (b"\xff\xd8\xff", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"GIF87a", ".gif"),
    (b"GIF89a", ".gif"),
)


def sugar_profile_query():
    return select(SugarProfile).options(joinedload(SugarProfile.user), joinedload(SugarProfile.photos))


def sugar_pair_query():
    return select(SugarPair).options(joinedload(SugarPair.first_user), joinedload(SugarPair.second_user))


def photo_url(photo: SugarPhoto) -> str:
    return f"/uploads/{photo.file_path}"


def present_sugar_profile(
    profile: SugarProfile,
    *,
    qq: str | None = None,
    relationship: SugarPair | None = None,
    detailed: bool = False,
) -> SugarProfileCardOut | SugarProfileDetailOut:
    data = {
        "id": profile.id,
        "user": profile.user,
        "about": profile.about,
        "photos": [SugarPhotoOut(id=photo.id, image_url=photo_url(photo)) for photo in profile.photos],
        "created_at": profile.created_at,
        "updated_at": profile.updated_at,
    }
    if detailed:
        return SugarProfileDetailOut(
            **data,
            qq=qq,
            relationship=present_sugar_pair(relationship) if relationship else None,
        )
    return SugarProfileCardOut(**data)


def sugar_pair_duration(pair: SugarPair) -> int:
    if pair.activated_at is None:
        return 0
    finish = pair.ended_at or datetime.utcnow()
    return max(0, int((finish - pair.activated_at).total_seconds()))


def present_sugar_pair(pair: SugarPair) -> SugarPairOut:
    return SugarPairOut.model_validate(pair).model_copy(update={"duration_seconds": sugar_pair_duration(pair)})


def get_sugar_profile_or_404(db: Session, user_id: int) -> SugarProfile:
    profile = db.scalars(sugar_profile_query().where(SugarProfile.user_id == user_id)).unique().one_or_none()
    if profile is None:
        raise HTTPException(status_code=404, detail="该用户尚未登记砂糖社档案")
    return profile


def pair_between(db: Session, first_user_id: int, second_user_id: int) -> SugarPair | None:
    return db.scalar(
        sugar_pair_query()
        .where(
            SugarPair.status.in_([SugarPairStatus.PENDING, SugarPairStatus.ACTIVE]),
            or_(
                (SugarPair.first_user_id == first_user_id) & (SugarPair.second_user_id == second_user_id),
                (SugarPair.first_user_id == second_user_id) & (SugarPair.second_user_id == first_user_id),
            ),
        )
        .order_by(SugarPair.initiated_at.desc())
    )


def ongoing_sugar_pair_for(db: Session, user_id: int, exclude_pair_id: int | None = None) -> SugarPair | None:
    filters = [
        SugarPair.status.in_([SugarPairStatus.PENDING, SugarPairStatus.ACTIVE]),
        or_(SugarPair.first_user_id == user_id, SugarPair.second_user_id == user_id),
    ]
    if exclude_pair_id is not None:
        filters.append(SugarPair.id != exclude_pair_id)
    return db.scalar(sugar_pair_query().where(*filters).order_by(SugarPair.initiated_at.desc()))


def image_extension(content: bytes) -> str | None:
    for signature, extension in IMAGE_SIGNATURES:
        if content.startswith(signature):
            return extension
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return ".webp"
    return None


async def read_sugar_images(photos: list[UploadFile]) -> list[tuple[str, bytes]]:
    images: list[tuple[str, bytes]] = []
    for photo in photos:
        content = await photo.read(MAX_SUGAR_IMAGE_BYTES + 1)
        if not content:
            raise HTTPException(status_code=422, detail="上传的照片不能为空")
        if len(content) > MAX_SUGAR_IMAGE_BYTES:
            raise HTTPException(status_code=422, detail="单张照片不能超过 5 MiB")
        extension = image_extension(content)
        if extension is None:
            raise HTTPException(status_code=422, detail="仅支持 JPEG、PNG、GIF 或 WebP 图片")
        images.append((extension, content))
    return images


def store_sugar_images(profile: SugarProfile, images: list[tuple[str, bytes]]) -> list[SugarPhoto]:
    settings.ensure_storage_directory()
    stored: list[tuple[str, str]] = []
    try:
        for extension, content in images:
            file_path = f"sugar/{uuid4().hex}{extension}"
            destination = settings.sugar_upload_path / file_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
            stored.append((file_path, str(destination)))
    except OSError as error:
        for _, destination in stored:
            try:
                Path(destination).unlink(missing_ok=True)
            except OSError:
                pass
        raise HTTPException(status_code=500, detail="照片保存失败，请稍后重试") from error
    records = [SugarPhoto(profile=profile, file_path=file_path) for file_path, _ in stored]
    return records


ACTIVE_TAKEN_STATUSES = (TaskStatus.PUBLISHED, TaskStatus.ACCEPTED, TaskStatus.AWAITING, TaskStatus.CANCELLING)


def active_task_count(db: Session, user_id: int) -> int:
    return db.scalar(
        select(func.count())
        .select_from(TaskMember)
        .join(Task, Task.id == TaskMember.task_id)
        .where(
            TaskMember.user_id == user_id,
            TaskMember.response_status == TaskMemberResponse.ACCEPTED,
            Task.status.in_(ACTIVE_TAKEN_STATUSES),
        )
    ) or 0


def start_if_ready(db: Session, task: Task) -> None:
    """达到所需人数时自动开始。required_takers 为 null 表示不限人数，只有委托人手动开始。"""
    if task.status != TaskStatus.PUBLISHED:
        return
    if task.required_takers is None or task.is_designated:
        return
    count = db.scalar(
        select(func.count()).select_from(TaskMember).where(
            TaskMember.task_id == task.id,
            TaskMember.response_status == TaskMemberResponse.ACCEPTED,
        )
    ) or 0
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
    user.qq_public = payload.qq_public if user.role == UserRole.VOLUNTEER else False
    user.bio = payload.bio.strip() if payload.bio else None
    db.commit()
    db.refresh(user)
    return user


@app.patch("/api/users/me/password", response_model=UserSelf)
def update_my_password(
    payload: UserPasswordUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user.password_hash = hash_password(payload.password)
    db.commit()
    db.refresh(user)
    return user


MAX_USER_PHOTOS = 3


def user_with_photos_query():
    return select(User).options(joinedload(User.photos))


async def save_user_photos(photos: list[UploadFile], user: User, db: Session) -> User:
    if len(photos) > MAX_USER_PHOTOS:
        raise HTTPException(status_code=422, detail=f"最多上传 {MAX_USER_PHOTOS} 张图片")
    images = await read_sugar_images(photos)
    existing = len(user.photos)
    if existing + len(images) > MAX_USER_PHOTOS:
        raise HTTPException(status_code=422, detail=f"每位用户最多保存 {MAX_USER_PHOTOS} 张图片")
    records = store_user_images(user, images)
    db.add_all(records)
    try:
        db.commit()
    except Exception:
        db.rollback()
        for record in records:
            try:
                (settings.sugar_upload_path / record.file_path).unlink(missing_ok=True)
            except OSError:
                pass
        raise
    db.refresh(user)
    return user


def store_user_images(user: User, images: list[tuple[str, bytes]]) -> list[UserPhoto]:
    settings.ensure_storage_directory()
    stored: list[tuple[str, Path]] = []
    try:
        for extension, content in images:
            file_path = f"users/{user.id}/{uuid4().hex}{extension}"
            destination = settings.sugar_upload_path / file_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
            stored.append((file_path, destination))
    except OSError as error:
        for _, destination in stored:
            destination.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="图片保存失败，请稍后重试") from error
    return [UserPhoto(user=user, file_path=file_path) for file_path, _ in stored]


@app.post("/api/users/me/photos", response_model=UserProfileOut, status_code=status.HTTP_201_CREATED)
async def upload_user_photos(
    photos: list[UploadFile] = File(default=[]),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not photos:
        raise HTTPException(status_code=422, detail="请选择要上传的图片")
    user = await save_user_photos(photos, user, db)
    return present_user_profile(user, user)


@app.delete("/api/users/me/photos/{photo_id}", response_model=UserProfileOut)
def delete_user_photo(photo_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    photo = db.get(UserPhoto, photo_id)
    if photo is None or photo.user_id != user.id:
        raise HTTPException(status_code=404, detail="图片不存在")
    path = photo.file_path
    db.delete(photo)
    db.commit()
    root = settings.sugar_upload_path.resolve()
    destination = (root / path).resolve()
    if destination.is_relative_to(root):
        try:
            destination.unlink(missing_ok=True)
        except OSError:
            pass
    db.refresh(user)
    return present_user_profile(user, user)


@app.get("/api/users/{user_id}", response_model=UserProfileOut)
def user_profile(user_id: int, viewer: User | None = Depends(get_optional_user), db: Session = Depends(get_db)):
    """名录中的店员/志愿者允许匿名查看，QQ 仍按公开偏好和协作关系脱敏。"""
    target = db.scalar(user_with_photos_query().where(User.id == user_id))
    if target is None or not target.is_active:
        raise HTTPException(status_code=404, detail="用户不存在")
    data = present_user_profile(target, viewer)
    if target.role not in (UserRole.STAFF, UserRole.VOLUNTEER) and viewer is None:
        raise HTTPException(status_code=401, detail="请先登录")
    if not can_view_user_qq(db, viewer, target):
        data.qq = None
    return data


@app.get("/api/staff", response_model=StaffDirectoryOut)
def staff_directory(db: Session = Depends(get_db)):
    staff = db.scalars(
        user_with_photos_query().where(User.role == UserRole.STAFF, User.is_active.is_(True), User.is_admin.is_(False)).order_by(User.created_at.asc())
    ).unique().all()
    volunteers = db.scalars(
        user_with_photos_query().where(User.role == UserRole.VOLUNTEER, User.is_active.is_(True), User.is_admin.is_(False)).order_by(User.created_at.asc())
    ).unique().all()
    return StaffDirectoryOut(
        group_chat_id=settings.staff_group_id,
        staff=[present_user_profile(user) for user in staff],
        volunteers=[
            present_user_profile(user).model_copy(update={"qq": user.qq if user.qq_public else None})
            for user in volunteers
        ],
    )


@app.get("/api/sugar/profiles", response_model=list[SugarProfileCardOut])
def list_sugar_profiles(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """砂糖社卡片列表不含 QQ；查看详情时才按一对一上下文提供联系方式。"""
    profiles = db.scalars(
        sugar_profile_query()
        .join(SugarProfile.user)
        .where(User.is_active.is_(True), User.is_admin.is_(False))
        .order_by(SugarProfile.updated_at.desc())
        .limit(200)
    ).unique().all()
    return [present_sugar_profile(profile) for profile in profiles]


@app.get("/api/sugar/profiles/{user_id}", response_model=SugarProfileDetailOut)
def sugar_profile_detail(
    user_id: int,
    viewer: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    target = db.get(User, user_id)
    if target is None or not target.is_active or target.is_admin:
        raise HTTPException(status_code=404, detail="用户不存在")
    profile = get_sugar_profile_or_404(db, user_id)
    relationship = pair_between(db, viewer.id, target.id) if viewer.id != target.id else None
    # QQ 不出现在公共列表；此详情请求的查看者与资料主人构成唯一的可见双方。
    return present_sugar_profile(
        profile,
        qq=target.qq,
        relationship=relationship,
        detailed=True,
    )


@app.post("/api/sugar/profile", response_model=SugarProfileDetailOut)
async def save_sugar_profile(
    response: Response,
    about: Annotated[str, Form(...)],
    photos: list[UploadFile] = File(default=[]),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """新建或更新砂糖社档案。每次追加上传最多 6 张，单张最多 5 MiB。"""
    if user.is_admin:
        raise HTTPException(status_code=403, detail="管理员账号不能登记砂糖社档案")
    about = about.strip()
    if not 1 <= len(about) <= 1000:
        raise HTTPException(status_code=422, detail="砂糖社介绍需要 1 至 1000 个字符")
    if len(photos) > MAX_SUGAR_PHOTOS:
        raise HTTPException(status_code=422, detail=f"最多上传 {MAX_SUGAR_PHOTOS} 张照片")
    images = await read_sugar_images(photos)
    profile = db.scalars(sugar_profile_query().where(SugarProfile.user_id == user.id)).unique().one_or_none()
    is_new = profile is None
    if profile is None:
        if not images:
            raise HTTPException(status_code=422, detail="首次登记请至少上传一张照片")
        profile = SugarProfile(user_id=user.id, about=about)
        db.add(profile)
        db.flush()
    else:
        if len(profile.photos) + len(images) > MAX_SUGAR_PHOTOS:
            raise HTTPException(status_code=422, detail=f"每个档案最多保存 {MAX_SUGAR_PHOTOS} 张照片")
        profile.about = about
        profile.updated_at = datetime.utcnow()
    records = store_sugar_images(profile, images)
    db.add_all(records)
    try:
        db.commit()
    except Exception:
        db.rollback()
        for record in records:
            try:
                (settings.sugar_upload_path / record.file_path).unlink(missing_ok=True)
            except OSError:
                pass
        raise
    saved = get_sugar_profile_or_404(db, user.id)
    response.status_code = status.HTTP_201_CREATED if is_new else status.HTTP_200_OK
    return present_sugar_profile(saved, qq=user.qq, detailed=True)


@app.delete("/api/sugar/photos/{photo_id}", response_model=SugarProfileDetailOut)
def delete_sugar_photo(photo_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    photo = db.get(SugarPhoto, photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="照片不存在")
    profile = get_sugar_profile_or_404(db, user.id)
    if photo.profile_id != profile.id:
        raise HTTPException(status_code=403, detail="只能删除自己的照片")
    if len(profile.photos) <= 1:
        raise HTTPException(status_code=409, detail="档案至少需要保留一张照片")
    file_path = photo.file_path
    db.delete(photo)
    db.commit()
    root = settings.sugar_upload_path.resolve()
    destination = (root / file_path).resolve()
    if destination.is_relative_to(root):
        try:
            destination.unlink(missing_ok=True)
        except OSError:
            pass
    return present_sugar_profile(get_sugar_profile_or_404(db, user.id), qq=user.qq, detailed=True)


@app.get("/api/sugar/pairs/mine", response_model=list[SugarPairOut])
def my_sugar_pairs(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    pairs = db.scalars(
        sugar_pair_query()
        .where(
            SugarPair.status.in_([SugarPairStatus.PENDING, SugarPairStatus.ACTIVE]),
            or_(SugarPair.first_user_id == user.id, SugarPair.second_user_id == user.id),
        )
        .order_by(SugarPair.initiated_at.desc())
    ).all()
    return [present_sugar_pair(pair) for pair in pairs]


@app.get("/api/sugar/pairs/top", response_model=list[SugarPairOut])
def top_sugar_pairs(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    pairs = db.scalars(
        sugar_pair_query()
        .where(SugarPair.status.in_([SugarPairStatus.ACTIVE, SugarPairStatus.ENDED]))
        .order_by(SugarPair.activated_at.asc())
        .limit(1000)
    ).all()
    return [present_sugar_pair(pair) for pair in sorted(pairs, key=sugar_pair_duration, reverse=True)[:3]]


@app.post("/api/sugar/pairs/{target_user_id}/confirm", response_model=SugarPairOut, status_code=status.HTTP_201_CREATED)
def confirm_sugar_pair(
    target_user_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """第一次点击建立待确认记录；被邀请的一方点击同一操作后正式开始计时。"""
    if target_user_id == user.id:
        raise HTTPException(status_code=400, detail="不能与自己登记为砂糖")
    target = db.get(User, target_user_id)
    if target is None or not target.is_active or target.is_admin:
        raise HTTPException(status_code=404, detail="用户不存在")
    get_sugar_profile_or_404(db, user.id)
    get_sugar_profile_or_404(db, target_user_id)
    existing = pair_between(db, user.id, target_user_id)
    now = datetime.utcnow()
    if existing is not None:
        if existing.status == SugarPairStatus.ACTIVE:
            raise HTTPException(status_code=409, detail="你们已经是砂糖")
        if existing.initiated_by_id == user.id:
            raise HTTPException(status_code=409, detail="已等待对方确认")
        conflict = ongoing_sugar_pair_for(db, user.id, existing.id) or ongoing_sugar_pair_for(db, target_user_id, existing.id)
        if conflict is not None:
            raise HTTPException(status_code=409, detail="双方有人已有待确认或进行中的砂糖关系")
        existing.status = SugarPairStatus.ACTIVE
        existing.activated_at = now
        db.commit()
        return present_sugar_pair(existing)
    if ongoing_sugar_pair_for(db, user.id) or ongoing_sugar_pair_for(db, target_user_id):
        raise HTTPException(status_code=409, detail="双方有人已有待确认或进行中的砂糖关系")
    pair = SugarPair(
        first_user_id=user.id,
        second_user_id=target_user_id,
        initiated_by_id=user.id,
        initiated_at=now,
    )
    db.add(pair)
    db.commit()
    db.refresh(pair)
    return present_sugar_pair(db.scalar(sugar_pair_query().where(SugarPair.id == pair.id)))


@app.post("/api/sugar/pairs/{pair_id}/end", response_model=SugarPairOut)
def end_sugar_pair(pair_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    pair = db.scalar(sugar_pair_query().where(SugarPair.id == pair_id))
    if pair is None:
        raise HTTPException(status_code=404, detail="砂糖关系不存在")
    if user.id not in (pair.first_user_id, pair.second_user_id):
        raise HTTPException(status_code=403, detail="只有砂糖双方可以结束关系")
    if pair.status != SugarPairStatus.ACTIVE:
        raise HTTPException(status_code=409, detail="当前关系不能结束")
    pair.status = SugarPairStatus.ENDED
    pair.ended_at = datetime.utcnow()
    db.commit()
    return present_sugar_pair(pair)


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
    participation = or_(
        Task.publisher_id == user.id,
        Task.id.in_(select(TaskMember.task_id).where(TaskMember.user_id == user.id)),
    )
    visibility = or_(
        Task.is_visible.is_(True),
        Task.publisher_id == user.id,
        user.is_admin,
        user.role == UserRole.STAFF,
    )
    tasks = db.scalars(task_query().where(participation, visibility).order_by(Task.updated_at.desc())).unique().all()
    return [present_task(task, user) for task in tasks]


@app.get("/api/tasks/{task_id}", response_model=TaskOut)
def task_detail(task_id: int, viewer: User | None = Depends(get_optional_user), db: Session = Depends(get_db)):
    expire_due_tasks(db)
    task = get_task_or_404(db, task_id)
    if not task.is_visible and not can_view_hidden_task(task, viewer):
        raise HTTPException(status_code=404, detail="委托不存在")
    return present_task(task, viewer)


@app.post("/api/tasks", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    now = datetime.utcnow()
    designated_user_ids = list(dict.fromkeys(payload.designated_user_ids))
    if user.id in designated_user_ids:
        raise HTTPException(status_code=422, detail="不能指定自己接取委托")
    designated_users: list[User] = []
    if designated_user_ids:
        designated_users = db.scalars(
            select(User).where(
                User.id.in_(designated_user_ids),
                User.is_active.is_(True),
                User.is_admin.is_(False),
                User.role.in_([UserRole.VOLUNTEER, UserRole.STAFF]),
            )
        ).all()
        if len(designated_users) != len(designated_user_ids):
            raise HTTPException(status_code=422, detail="只能指定当前可用的店员或志愿者")
    task = Task(
        title=payload.title.strip(),
        description=payload.description.strip(),
        category=payload.category,
        pay_type=payload.pay_type,
        reward=payload.reward.strip() if payload.reward else None,
        expires_at=now + timedelta(days=payload.expires_in_days),
        publisher_id=user.id,
        required_takers=len(designated_user_ids) if designated_user_ids else payload.required_takers,
        # 指定委托无须密码，响应权限由指定名单保证。
        accept_password_hash=None if designated_user_ids else (hash_password(payload.accept_password) if payload.accept_password else None),
        is_designated=bool(designated_user_ids),
    )
    db.add(task)
    db.flush()
    for designated_user in designated_users:
        db.add(
            TaskMember(
                task_id=task.id,
                user_id=designated_user.id,
                response_status=TaskMemberResponse.PENDING,
            )
        )
    db.commit()
    return present_task(get_task_or_404(db, task.id), user)


@app.post("/api/tasks/{task_id}/accept", response_model=TaskOut)
def accept_task(
    task_id: int,
    payload: AcceptRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """加入委托（有密码时限志愿者/店员，无密码时所有非管理员用户可加入）。"""
    expire_due_tasks(db)
    task = get_task_or_404(db, task_id)
    if not task.is_visible:
        raise HTTPException(status_code=403, detail="该委托已被管理员隐藏")
    if task.publisher_id == user.id:
        raise HTTPException(status_code=400, detail="不能接取自己发布的委托")
    if user.is_admin:
        raise HTTPException(status_code=403, detail="管理员不接取委托")
    if task.status != TaskStatus.PUBLISHED:
        raise HTTPException(status_code=409, detail="委托已开始或不可接取")
    existing_member = member_of(db, task_id, user.id)
    if task.is_designated:
        if existing_member is None:
            raise HTTPException(status_code=403, detail="该委托已指定其他店员或志愿者")
        if existing_member.response_status != TaskMemberResponse.PENDING:
            raise HTTPException(status_code=409, detail="你已响应此指定委托")
        # 在支持行锁的数据库上串行化同一用户的接单操作，避免并发突破个人上限。
        db.scalar(select(User).where(User.id == user.id).with_for_update())
        if active_task_count(db, user.id) >= user.max_concurrent_tasks:
            raise HTTPException(
                status_code=409,
                detail=f"你同时接取的委托已达上限（{user.max_concurrent_tasks} 个）",
            )
        existing_member.response_status = TaskMemberResponse.ACCEPTED
        task.updated_at = datetime.utcnow()
        # 指定单人接受后立即开始；多人须等所有指定人员均响应后开始。
        if all(member.response_status != TaskMemberResponse.PENDING for member in task.members):
            if any(member.response_status == TaskMemberResponse.ACCEPTED for member in task.members):
                task.status = TaskStatus.ACCEPTED
                task.started_at = task.started_at or datetime.utcnow()
            else:
                task.status = TaskStatus.CANCELLED
                task.cancelled_at = datetime.utcnow()
        db.commit()
        return present_task(get_task_or_404(db, task_id), user)
    if existing_member is not None:
        raise HTTPException(status_code=409, detail="你已经接取过该委托")
    if task.required_takers is not None:
        joined = db.scalar(select(func.count()).select_from(TaskMember).where(TaskMember.task_id == task.id)) or 0
        if joined >= task.required_takers:
            raise HTTPException(status_code=409, detail="需要的人数已满，委托即将开始")
    if task.requires_password:
        if user.role not in (UserRole.VOLUNTEER, UserRole.STAFF):
            raise HTTPException(status_code=403, detail="有密码委托只有志愿者或店员可以接取，请联系店员申请升级")
        if not payload.password or not verify_password(payload.password, task.accept_password_hash):
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
    if task.is_designated:
        raise HTTPException(status_code=409, detail="指定委托须等待所有被指定人员响应")
    if not task.members:
        raise HTTPException(status_code=409, detail="至少需要一名接单人才能开始，请先等待接单人加入")
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
    if task.is_designated:
        if membership.response_status != TaskMemberResponse.PENDING:
            raise HTTPException(status_code=409, detail="已接受指定委托，不能拒绝")
        membership.response_status = TaskMemberResponse.DECLINED
        task.updated_at = datetime.utcnow()
        if all(member.response_status != TaskMemberResponse.PENDING for member in task.members):
            if any(member.response_status == TaskMemberResponse.ACCEPTED for member in task.members):
                task.status = TaskStatus.ACCEPTED
                task.started_at = datetime.utcnow()
            else:
                task.status = TaskStatus.CANCELLED
                task.cancelled_at = datetime.utcnow()
        db.commit()
        return present_task(get_task_or_404(db, task_id), user)
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
        membership = accepted_member_of(db, task_id, user.id)
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
    if task.publisher_id != user.id and accepted_member_of(db, task_id, user.id) is None:
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
        membership = accepted_member_of(db, task_id, user.id)
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
    if task.publisher_id != user.id and accepted_member_of(db, task_id, user.id) is None:
        raise HTTPException(status_code=403, detail="只有委托人或接单人可确认取消")
    now = datetime.utcnow()
    if task.publisher_id == user.id:
        if task.publisher_cancel_confirmed_at is not None:
            raise HTTPException(status_code=409, detail="你已同意取消")
        task.publisher_cancel_confirmed_at = now
    else:
        membership = accepted_member_of(db, task_id, user.id)
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
    if task.publisher_id != user.id and accepted_member_of(db, task_id, user.id) is None:
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
def admin_tasks(_: User = Depends(get_role_manager), db: Session = Depends(get_db)):
    expire_due_tasks(db)
    tasks = db.scalars(task_query().order_by(Task.updated_at.desc()).limit(500)).unique().all()
    return [present_task(task, _) for task in tasks]


@app.get("/api/admin/users", response_model=list[AdminUserOut])
def admin_users(manager: User = Depends(get_role_manager), db: Session = Depends(get_db)):
    expire_due_tasks(db)
    query = select(User).order_by(User.created_at.desc())
    if not manager.is_admin:
        query = query.where(User.is_admin.is_(False))
    users = db.scalars(query.options(joinedload(User.photos))).unique().all()
    return [
        AdminUserOut.model_validate(user).model_copy(
            update={"active_task_count": active_task_count(db, user.id)}
        )
        for user in users
    ]


@app.get("/api/admin/photos", response_model=list[UserProfileOut])
def admin_photos(_: User = Depends(get_role_manager), db: Session = Depends(get_db)):
    users = db.scalars(user_with_photos_query().order_by(User.created_at.desc())).unique().all()
    return [present_user_profile(user, _) for user in users if user.photos]


@app.patch("/api/admin/photos/{photo_id}", response_model=UserProfileOut)
def moderate_user_photo(
    photo_id: int,
    payload: AdminPhotoUpdate,
    manager: User = Depends(get_role_manager),
    db: Session = Depends(get_db),
):
    photo = db.get(UserPhoto, photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="图片不存在")
    photo.is_visible = payload.is_visible
    photo.moderated_by_id = manager.id
    photo.moderated_at = datetime.utcnow()
    db.commit()
    user = db.scalar(user_with_photos_query().where(User.id == photo.user_id))
    return present_user_profile(user, manager)


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


@app.patch("/api/admin/users/{user_id}/password", response_model=AdminUserOut)
def reset_user_password(
    user_id: int,
    payload: UserPasswordUpdate,
    _: User = Depends(get_admin),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    user.password_hash = hash_password(payload.password)
    db.commit()
    db.refresh(user)
    return AdminUserOut.model_validate(user).model_copy(
        update={"active_task_count": active_task_count(db, user.id)}
    )


@app.patch("/api/admin/users/{user_id}/role", response_model=AdminUserOut)
def update_user_role(
    user_id: int,
    payload: AdminUserRoleUpdate,
    manager: User = Depends(get_role_manager),
    db: Session = Depends(get_db),
):
    """管理员可设置全部角色；店员只能把非管理员账号设为普通用户或志愿者。"""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.is_admin:
        raise HTTPException(status_code=409, detail="管理员账号的权限等级不可修改")
    if not manager.is_admin and payload.role == UserRole.STAFF:
        raise HTTPException(status_code=403, detail="只有管理员可以授予店员权限")
    if payload.role == UserRole.VOLUNTEER and user.role != UserRole.VOLUNTEER:
        user.qq_public = False
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
    admin: User = Depends(get_role_manager),
    db: Session = Depends(get_db),
):
    task = get_task_or_404(db, task_id)
    note = payload.admin_note.strip() if payload.admin_note else None
    if not payload.is_visible and not note:
        raise HTTPException(status_code=422, detail="屏蔽委托时必须填写理由")
    task.is_visible = payload.is_visible
    task.admin_note = note if not payload.is_visible else None
    db.commit()
    return present_task(get_task_or_404(db, task_id), admin)
