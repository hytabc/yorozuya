"""委托模块化标签：技能 / 平台 / 参考 World / 氛围。

标签落在独立表 ``task_facets`` 上（不塞进 Task 自由文本），筛选走
``(facet_type, value)`` 索引。词表必须与 ``frontend/src/constants.js`` 的
``TASK_SKILLS`` / ``TASK_PLATFORMS`` / ``ATMOSPHERE_GROUPS`` 保持同步。
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    delete,
    func,
    select,
)
from sqlalchemy.orm import Mapped, Session, mapped_column

from .database import Base, get_db
from .dependencies import get_current_user
from .models import Task, TaskStatus, User
from .ratelimit import enforce
from .schemas import TaskFacetIn, TaskFacetOut, TaskFacetUpdate

FACET_LIMITS = {"skill": 6, "platform": 2, "world": 3, "atmosphere": 5}
FACET_LABELS = {"skill": "技能", "platform": "平台", "world": "参考 World", "atmosphere": "氛围"}

# 前端 constants.js 中的同名常量是唯一事实来源的镜像，改动必须两边同步。
SKILLS = (
    "Blender",
    "Unity",
    "PhysBones",
    "lilToon",
    "Udon",
    "VRChat SDK",
    "灯光",
    "世界优化",
    "Quest 兼容",
    "音频",
)
PLATFORMS = ("PCVR", "Quest", "Desktop", "不限")
ATMOSPHERE_GROUPS = (
    {"key": "contact", "label": "沟通方式", "options": ("文字为主", "语音沟通", "游戏内沟通")},
    {"key": "pace", "label": "节奏", "options": ("轻松推进", "紧凑交付", "可长期协作")},
    {"key": "boundary", "label": "边界", "options": ("可录屏", "不录屏", "可二次创作", "不可二次创作")},
    {"key": "expectation", "label": "期望", "options": ("新手友好", "需要经验", "可指导")},
)
ATMOSPHERES = tuple(option for group in ATMOSPHERE_GROUPS for option in group["options"])
ALLOWED_VALUES = {"skill": SKILLS, "platform": PLATFORMS, "atmosphere": ATMOSPHERES}


class TaskFacet(Base):
    __tablename__ = "task_facets"
    __table_args__ = (
        UniqueConstraint("task_id", "facet_type", "value", name="uq_task_facet"),
        Index("ix_task_facets_type_value", "facet_type", "value"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), nullable=False, index=True)
    facet_type: Mapped[str] = mapped_column(String(16), nullable=False)
    value: Mapped[str] = mapped_column(String(64), nullable=False)
    sort: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


def validate_facets(items: list[TaskFacetIn]) -> list[TaskFacetIn]:
    """白名单 + 数量上限 + 去重；非法值统一 422（与 TASK_CATEGORIES 一致）。"""
    counts = {key: 0 for key in FACET_LIMITS}
    seen: set[tuple[str, str]] = set()
    cleaned: list[TaskFacetIn] = []
    for item in items:
        facet_type = item.facet_type
        value = item.value.strip()
        if facet_type not in FACET_LIMITS:
            raise HTTPException(status_code=422, detail="委托标签类型不正确")
        if not value:
            raise HTTPException(status_code=422, detail=f"{FACET_LABELS[facet_type]}标签不能为空")
        if (facet_type, value) in seen:
            continue
        if facet_type == "world":
            if len(value) > 60:
                raise HTTPException(status_code=422, detail="参考 World 名称不能超过 60 个字符")
        elif value not in ALLOWED_VALUES[facet_type]:
            raise HTTPException(status_code=422, detail=f"{FACET_LABELS[facet_type]}标签不在允许范围内")
        counts[facet_type] += 1
        if counts[facet_type] > FACET_LIMITS[facet_type]:
            raise HTTPException(
                status_code=422,
                detail=f"{FACET_LABELS[facet_type]}最多选择 {FACET_LIMITS[facet_type]} 个",
            )
        seen.add((facet_type, value))
        cleaned.append(TaskFacetIn(facet_type=facet_type, value=value))
    return cleaned


def store_facets(db: Session, task_id: int, items: list[TaskFacetIn]) -> None:
    db.execute(delete(TaskFacet).where(TaskFacet.task_id == task_id))
    for index, item in enumerate(items):
        db.add(
            TaskFacet(
                task_id=task_id,
                facet_type=item.facet_type,
                value=item.value,
                sort=index,
            )
        )


def facets_for_tasks(db: Session, task_ids: list[int]) -> dict[int, list[TaskFacetOut]]:
    """批量读取，避免列表接口对每条委托单独查一次（N+1）。"""
    if not task_ids:
        return {}
    rows = db.scalars(
        select(TaskFacet)
        .where(TaskFacet.task_id.in_(task_ids))
        .order_by(TaskFacet.sort, TaskFacet.id)
    ).all()
    grouped: dict[int, list[TaskFacetOut]] = {}
    for row in rows:
        grouped.setdefault(row.task_id, []).append(
            TaskFacetOut(facet_type=row.facet_type, value=row.value)
        )
    return grouped


def facets_for_task(db: Session, task_id: int) -> list[TaskFacetOut]:
    return facets_for_tasks(db, [task_id]).get(task_id, [])


def facet_filter_ids(facet_type: str, value: str):
    """返回「带该标签的委托 ID」子查询，供大厅筛选拼接。"""
    return select(TaskFacet.task_id).where(
        TaskFacet.facet_type == facet_type,
        TaskFacet.value == value,
    )


router = APIRouter(prefix="/api/tasks", tags=["task facets"])


@router.get("/facets")
def facet_catalog(db: Session = Depends(get_db)):
    """词表 + 当前招募中委托的标签计数，供大厅筛选器使用。"""
    rows = db.execute(
        select(TaskFacet.facet_type, TaskFacet.value, func.count())
        .join(Task, Task.id == TaskFacet.task_id)
        .where(Task.is_visible.is_(True), Task.status == TaskStatus.PUBLISHED)
        .group_by(TaskFacet.facet_type, TaskFacet.value)
    ).all()
    counts: dict[str, dict[str, int]] = {}
    for facet_type, value, count in rows:
        counts.setdefault(facet_type, {})[value] = count

    return {
        "skills": [
            {"value": value, "count": counts.get("skill", {}).get(value, 0)} for value in SKILLS
        ],
        "platforms": [
            {"value": value, "count": counts.get("platform", {}).get(value, 0)}
            for value in PLATFORMS
        ],
        "atmospheres": [
            {
                "key": group["key"],
                "label": group["label"],
                "options": [
                    {"value": value, "count": counts.get("atmosphere", {}).get(value, 0)}
                    for value in group["options"]
                ],
            }
            for group in ATMOSPHERE_GROUPS
        ],
        "limits": FACET_LIMITS,
    }


@router.patch("/{task_id}/facets")
def update_task_facets(
    task_id: int,
    payload: TaskFacetUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """委托开始前，委托人可调整技能/平台/World/氛围标签。"""
    enforce("task-facets", str(user.id), 30, 600)
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="委托不存在")
    if task.publisher_id != user.id:
        raise HTTPException(status_code=403, detail="只有委托人可以修改委托标签")
    if task.status != TaskStatus.PUBLISHED:
        raise HTTPException(status_code=409, detail="委托已开始或结束，不能再修改标签")
    store_facets(db, task_id, validate_facets(payload.facets))
    db.commit()
    from .main import get_task_or_404, present_task

    refreshed = get_task_or_404(db, task_id)
    return present_task(refreshed, user, facets_for_task(db, task_id))
