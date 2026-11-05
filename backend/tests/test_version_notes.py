"""版本更新确认：账号级记录、只前进不后退、幂等、未验证邮箱也能确认。"""
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import User
from app.security import hash_password

import test_api as api_tests
from test_api import auth


def setup_function():
    api_tests.setup_function()
    app.dependency_overrides[get_db] = api_tests.override_db


def test_new_account_has_no_ack():
    with TestClient(app) as client:
        headers = auth(client, "ver_new")
        assert client.get("/api/auth/me", headers=headers).json()["version_ack"] is None


def test_ack_is_idempotent_and_moves_forward_only():
    with TestClient(app) as client:
        headers = auth(client, "ver_forward")
        assert client.post(
            "/api/version-ack", headers=headers, json={"version": "V1.0"}
        ).json() == {"version_ack": "V1.0"}
        # 重复提交同一版本是幂等的
        assert client.post(
            "/api/version-ack", headers=headers, json={"version": "V1.0"}
        ).json() == {"version_ack": "V1.0"}
        # 新版本覆盖
        assert client.post(
            "/api/version-ack", headers=headers, json={"version": "V1.1"}
        ).json() == {"version_ack": "V1.1"}
        # 迟到的旧版本请求不会把记录降回去
        assert client.post(
            "/api/version-ack", headers=headers, json={"version": "V1.0"}
        ).json() == {"version_ack": "V1.1"}
        assert client.get("/api/auth/me", headers=headers).json()["version_ack"] == "V1.1"


def test_ack_requires_login_but_not_verified_email():
    with TestClient(app) as client:
        assert client.post("/api/version-ack", json={"version": "V1.0"}).status_code == 401

        # 版本确认只是界面状态：未验证邮箱的存量账号也能确认，否则弹窗关不掉。
        with api_tests.TestingSession() as db:
            db.add(
                User(
                    username="ver_legacy",
                    nickname="存量账号",
                    password_hash=hash_password("Password123!"),
                )
            )
            db.commit()
        login = client.post(
            "/api/auth/login", json={"username": "ver_legacy", "password": "Password123!"}
        )
        assert login.status_code == 200, login.text
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        acked = client.post("/api/version-ack", headers=headers, json={"version": "V1.0"})
        assert acked.status_code == 200, acked.text
        assert acked.json() == {"version_ack": "V1.0"}


def test_rejects_invalid_payload():
    with TestClient(app) as client:
        headers = auth(client, "ver_bad")
        assert client.post("/api/version-ack", headers=headers, json={"version": ""}).status_code == 422
        assert client.post(
            "/api/version-ack", headers=headers, json={"version": "V1.0", "extra": True}
        ).status_code == 422
        assert client.post(
            "/api/version-ack", headers=headers, json={"version": "x" * 33}
        ).status_code == 422
