from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session as BaseSession, sessionmaker

from .config import settings

settings.ensure_sqlite_directory()
settings.ensure_storage_directory()

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)


class AppSession(BaseSession):
    """应用统一会话类：用于让自动快照仅作用于应用数据库，不干扰测试的内存会话。"""


SessionLocal = sessionmaker(bind=engine, class_=AppSession, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


# 每次有内容写入并提交后，自动把数据库快照到宿主机（见 backup.py）
from .backup import install_auto_backup as _install_auto_backup  # noqa: E402

_install_auto_backup(AppSession)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
