"""SQLite 数据库自动快照备份。

数据库每次发生内容写入并成功提交后，自动把主数据库文件复制一份带时间戳的
快照到其同级 ``backups/`` 目录（例如 ``backend/data/backups/wsw-20260902-113000.db``），
并只保留最近若干份。快照文件与主数据库同处宿主机目录，可随时用 SQLite 工具打开。

监听逻辑只作用于应用自身的 ``AppSession`` 会话，不影响测试使用的内存会话。
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import event

from .config import settings

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

BACKUP_DIR_NAME = "backups"
# 用于在会话内标记“本事务是否写入了数据库”的 key
_CHANGED_KEY = "_yorozuya_db_changed"


def sqlite_db_path() -> Path | None:
    """返回主 SQLite 数据库文件路径；非 SQLite 配置返回 None。"""
    url = settings.database_url
    if not url.startswith("sqlite:///"):
        return None
    return Path(url.removeprefix("sqlite:///"))


def _mark_changed(session: Session, value: bool = True) -> None:
    session.info[_CHANGED_KEY] = value


def _on_before_flush(session, flush_context, instances) -> None:
    """flush 即将执行前标记：存在新增/修改/删除的 ORM 对象。"""
    if session.new or session.dirty or session.deleted:
        _mark_changed(session)


def _on_do_orm_execute(orm_execute_state) -> None:
    """session.execute() 直接执行了 DML（例如批量 UPDATE 过期任务）时标记。"""
    if orm_execute_state.is_insert or orm_execute_state.is_update or orm_execute_state.is_delete:
        _mark_changed(orm_execute_state.session)


def _on_after_commit(session: Session) -> None:
    if not session.info.pop(_CHANGED_KEY, False):
        return
    try:
        take_snapshot()
    except Exception:  # noqa: BLE001 - 备份失败不应影响业务请求
        logger.exception("数据库自动快照失败")


def _next_snapshot_path(db_path: Path) -> Path:
    backup_dir = db_path.parent / BACKUP_DIR_NAME
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = backup_dir / f"{db_path.stem}-{stamp}.db"
    index = 1
    while dest.exists():  # 同一秒内多次写入时追加序号避免覆盖
        dest = backup_dir / f"{db_path.stem}-{stamp}-{index}.db"
        index += 1
    return dest


def take_snapshot(db_path: Path | None = None) -> Path | None:
    """把当前数据库一致性快照到 backups/ 并清理过期文件。返回快照路径。"""
    db_path = db_path or sqlite_db_path()
    if db_path is None or not db_path.is_file():
        return None

    dest = _next_snapshot_path(db_path)
    # 通过独立的 sqlite3 连接读取，拿到事务一致的数据，不会影响正在运行的应用
    source = sqlite3.connect(str(db_path))
    try:
        target = sqlite3.connect(str(dest))
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()

    prune(db_path)
    logger.info("已生成数据库快照：%s", dest)
    return dest


def _snapshot_key(path: Path) -> tuple:
    """按（修改时间，同秒内序号）排序，保证同一秒多次快照仍按创建先后排序。"""
    return (path.stat().st_mtime, _same_second_index(path))


def _same_second_index(path: Path) -> int:
    # 时间戳里的“秒”是 6 位数字；只有附加的同秒序号（如 -1、-2）才是 1~3 位数字
    tail = path.stem.rsplit("-", 1)[-1]
    return int(tail) if tail.isdigit() and len(tail) <= 3 else 0


def prune(db_path: Path, keep: int | None = None) -> None:
    """只保留最近 keep 份快照，删除更早的。"""
    keep = settings.db_backup_keep if keep is None else keep
    backup_dir = db_path.parent / BACKUP_DIR_NAME
    snapshots = sorted(backup_dir.glob(f"{db_path.stem}-*.db"), key=_snapshot_key)
    for stale in snapshots[:-keep]:
        try:
            stale.unlink()
        except OSError:
            logger.warning("清理旧快照失败：%s", stale)


def install_auto_backup(session_class) -> None:
    """为指定 Session 类安装自动备份监听。"""
    event.listen(session_class, "before_flush", _on_before_flush)
    event.listen(session_class, "do_orm_execute", _on_do_orm_execute)
    event.listen(session_class, "after_commit", _on_after_commit)
