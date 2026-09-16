"""存储目录不可写时的报错文案。

这些 ensure_* 方法会在导入 database.py 时（早于 main.py 的启动自检）执行，
所以它们必须自己把 PermissionError 翻译成可执行的中文提示，否则运维只能看到裸堆栈。
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from app.config import Settings


def make_settings(tmp_path: Path) -> Settings:
    """构造一份指向临时目录的配置，避免测试碰到仓库里的 backend/data。"""
    return Settings(
        secret_key="test-secret-" + "0" * 32,
        database_url=f"sqlite:///{tmp_path / 'data' / 'wsw.db'}",
        sugar_upload_dir=str(tmp_path / "uploads"),
        media_private_dir=str(tmp_path / "private_media"),
    )


def deny_mkdir_for(target: Path):
    """让 mkdir 只对 target 抛 PermissionError，其余照常创建。"""
    real_mkdir = Path.mkdir

    def fake_mkdir(self, *args, **kwargs):
        if Path(self) == target:
            raise PermissionError(13, "Permission denied", str(self))
        return real_mkdir(self, *args, **kwargs)

    return fake_mkdir


def test_ensure_storage_directory_hints_chown_for_private_media(tmp_path):
    settings = make_settings(tmp_path)

    with patch.object(Path, "mkdir", deny_mkdir_for(settings.media_private_path)):
        with pytest.raises(RuntimeError) as excinfo:
            settings.ensure_storage_directory()

    message = str(excinfo.value)
    assert "私有媒体目录" in message
    assert "chown -R 10001:10001 backend/data" in message


def test_ensure_sqlite_directory_hints_chown(tmp_path):
    settings = make_settings(tmp_path)
    db_dir = tmp_path / "data"

    with patch.object(Path, "mkdir", deny_mkdir_for(db_dir)):
        with pytest.raises(RuntimeError) as excinfo:
            settings.ensure_sqlite_directory()

    message = str(excinfo.value)
    assert "数据库目录" in message
    assert "chown -R 10001:10001 backend/data" in message
