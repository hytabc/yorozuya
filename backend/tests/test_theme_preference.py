"""外观偏好（深色模式档位 + 页面风格）的落库回归测试。

用户诉求：在个人设置里选的选项必须保存到账号上，否则每次登录/换设备都要重选。
覆盖：默认值、PATCH 落库并随 /auth/me 返回、只传一个字段不影响另一个、
清空风格、非法值被拒、未登录不可改。
"""

import re
from urllib.parse import unquote

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import mailer
from app.config import settings
from app.database import Base, get_db
from app.main import app

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def override_db():
    with TestingSession() as db:
        yield db


app.dependency_overrides[get_db] = override_db

client = TestClient(app)


def setup_function():
    app.dependency_overrides[get_db] = override_db
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    settings.email_delivery = "log"
    settings.email_send_cooldown_seconds = 0
    settings.require_email_verification = True
    mailer.OUTBOX.clear()


# ---- 小工具（与其它模块保持同一套注册→取信→验证链路）----


def last_mail_token() -> str:
    """从本地信箱取出最近一封邮件正文里的链接令牌。"""
    assert mailer.OUTBOX, "测试信箱里没有邮件"
    match = re.search(r"[?&]token=([^&\s]+)", mailer.OUTBOX[-1]["text"])
    assert match, f"邮件正文里没有找到令牌：{mailer.OUTBOX[-1]['text']}"
    return unquote(match.group(1))


def auth_headers(username: str, password: str = "Password123!") -> dict:
    registered = client.post(
        "/api/auth/register",
        json={
            "username": username,
            "password": password,
            "nickname": f"用户{username}",
            "email": f"{username}@example.com",
        },
    )
    assert registered.status_code == 201, registered.text
    confirmed = client.post("/api/auth/email/confirm", json={"token": last_mail_token()})
    assert confirmed.status_code == 200, confirmed.text
    logged_in = client.post("/api/auth/login", json={"username": username, "password": password})
    assert logged_in.status_code == 200, logged_in.text
    return {"Authorization": f"Bearer {logged_in.json()['access_token']}"}


# ---- 用例 ----


def test_新账号的默认外观偏好是按时间切换且没选过风格():
    headers = auth_headers("theme_default")
    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200, me.text
    body = me.json()
    assert body["theme_mode"] == "auto"
    assert body["theme_style"] is None


def test_改深色模式会落库并在下次登录时返回():
    headers = auth_headers("theme_mode_save")

    patched = client.patch("/api/users/me/theme", headers=headers, json={"theme_mode": "night"})
    assert patched.status_code == 200, patched.text
    assert patched.json()["theme_mode"] == "night"
    # 只改了明暗，风格应保持原样（未被顺带覆盖）
    assert patched.json()["theme_style"] is None

    # 重新登录（新会话新令牌）后依然读到保存的值——这正是"落库"的意义
    again = client.post(
        "/api/auth/login",
        json={"username": "theme_mode_save", "password": "Password123!"},
    )
    assert again.status_code == 200, again.text
    assert again.json()["user"]["theme_mode"] == "night"

    me = client.get("/api/auth/me", headers=headers)
    assert me.json()["theme_mode"] == "night"


def test_四档明暗都能保存():
    headers = auth_headers("theme_all_modes")
    for mode in ("day", "night", "system", "auto"):
        response = client.patch("/api/users/me/theme", headers=headers, json={"theme_mode": mode})
        assert response.status_code == 200, f"{mode}: {response.text}"
        assert response.json()["theme_mode"] == mode


def test_风格可以与明暗各自独立保存():
    headers = auth_headers("theme_style_save")

    client.patch("/api/users/me/theme", headers=headers, json={"theme_mode": "day"})
    response = client.patch("/api/users/me/theme", headers=headers, json={"theme_style": "pixel"})
    assert response.status_code == 200, response.text
    assert response.json()["theme_style"] == "pixel"
    assert response.json()["theme_mode"] == "day", "改风格不应顺手改掉明暗档位"

    # 传 null 表示清除显式选择，前端会回落到本地默认
    cleared = client.patch("/api/users/me/theme", headers=headers, json={"theme_style": None})
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["theme_style"] is None
    assert cleared.json()["theme_mode"] == "day"


def test_空请求体不改变任何设置():
    headers = auth_headers("theme_noop")
    client.patch("/api/users/me/theme", headers=headers, json={"theme_mode": "night", "theme_style": "pixel"})

    response = client.patch("/api/users/me/theme", headers=headers, json={})
    assert response.status_code == 200, response.text
    assert response.json()["theme_mode"] == "night"
    assert response.json()["theme_style"] == "pixel"


def test_非法取值被拒绝且不改动已保存的值():
    headers = auth_headers("theme_invalid")
    client.patch("/api/users/me/theme", headers=headers, json={"theme_mode": "night", "theme_style": "pixel"})

    for payload in (
        {"theme_mode": "dark"},
        {"theme_mode": "AUTO"},
        {"theme_style": "neon"},
        {"theme_style": "Classic"},
        # RequestModel 设了 extra="forbid"，夹带未知字段同样拒绝
        {"theme_mode": "day", "is_admin": True},
    ):
        response = client.patch("/api/users/me/theme", headers=headers, json=payload)
        assert response.status_code == 422, f"{payload} 应被拒绝，实际 {response.status_code}"

    me = client.get("/api/auth/me", headers=headers)
    assert me.json()["theme_mode"] == "night"
    assert me.json()["theme_style"] == "pixel"


def test_未登录不能修改外观偏好():
    response = client.patch("/api/users/me/theme", json={"theme_mode": "night"})
    assert response.status_code in (401, 403), response.text
