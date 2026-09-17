"""导入应用前隔离存储和邮件，pytest 不能触碰本机/生产数据。"""
import os
import tempfile

import pytest


_storage = tempfile.TemporaryDirectory(prefix="yorozuya-tests-")
os.environ.update(
    DATABASE_URL=f"sqlite:///{_storage.name}/test.db",
    SUGAR_UPLOAD_DIR=f"{_storage.name}/uploads",
    MEDIA_PRIVATE_DIR="",
    EMAIL_DELIVERY="log",
    SITE_BASE_URL="https://example.com",
    # 备案号等站点信息也必须显式固定：宿主机 shell 里 export 过 SITE_ICP 时，
    # 断言「未配置时为空」的用例会随环境飘（本地开发机就踩过这个坑）。
    SITE_ICP="",
    SITE_ICP_URL="https://beian.miit.gov.cn/",
    BEHIND_PROXY="false",
    # 显式声明测试模式：限流与人机验证据此关闭，不再依赖「进程里 import 了 pytest」。
    TESTING="true",
)


@pytest.fixture(autouse=True)
def mail_origin(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "site_base_url", "https://example.com")


def pytest_unconfigure(config):
    _storage.cleanup()
