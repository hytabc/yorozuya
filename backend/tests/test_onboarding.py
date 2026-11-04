"""新手引导记录：账号级一次性、幂等、只增不减、未验证邮箱受闸门保护。"""
from fastapi.testclient import TestClient

from app.config import settings
from app.database import get_db
from app.main import app
from app.models import User
from app.security import hash_password

import test_api as api_tests
from test_api import auth


def setup_function():
    api_tests.setup_function()
    app.dependency_overrides[get_db] = api_tests.override_db
    # 别的模块会临时关闭邮箱闸门（如通知用例）且不回滚，这里显式收紧。
    settings.require_email_verification = True


def test_new_account_starts_at_zero():
    with TestClient(app) as client:
        headers = auth(client, "ob_new")
        assert client.get("/api/auth/me", headers=headers).json()["onboarding_version"] == 0


def test_complete_is_idempotent_and_never_goes_backwards():
    with TestClient(app) as client:
        headers = auth(client, "ob_done")
        assert client.post(
            "/api/onboarding/complete", headers=headers, json={"version": 1}
        ).json() == {"onboarding_version": 1}
        # 重复提交同一版本是幂等的
        assert client.post(
            "/api/onboarding/complete", headers=headers, json={"version": 1}
        ).json() == {"onboarding_version": 1}
        # 更大的版本表示引导更新过，允许覆盖
        assert client.post(
            "/api/onboarding/complete", headers=headers, json={"version": 2}
        ).json() == {"onboarding_version": 2}
        # 迟到的旧版本请求不会把已看过的版本降回去
        assert client.post(
            "/api/onboarding/complete", headers=headers, json={"version": 1}
        ).json() == {"onboarding_version": 2}
        assert client.get("/api/auth/me", headers=headers).json()["onboarding_version"] == 2


def test_requires_login_and_verified_email():
    with TestClient(app) as client:
        assert client.post("/api/onboarding/complete", json={"version": 1}).status_code == 401

        # 存量账号（没有邮箱）可以登录，但会被邮箱验证闸门挡住写操作。
        with api_tests.TestingSession() as db:
            db.add(
                User(
                    username="ob_legacy",
                    nickname="存量账号",
                    password_hash=hash_password("Password123!"),
                )
            )
            db.commit()
        login = client.post(
            "/api/auth/login", json={"username": "ob_legacy", "password": "Password123!"}
        )
        assert login.status_code == 200, login.text
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        blocked = client.post("/api/onboarding/complete", headers=headers, json={"version": 1})
        assert blocked.status_code == 403
        assert "邮箱验证" in blocked.json()["detail"]


def test_rejects_invalid_payload():
    with TestClient(app) as client:
        headers = auth(client, "ob_bad")
        assert client.post(
            "/api/onboarding/complete", headers=headers, json={"version": 0}
        ).status_code == 422
        assert client.post(
            "/api/onboarding/complete", headers=headers, json={"version": 1, "extra": True}
        ).status_code == 422
