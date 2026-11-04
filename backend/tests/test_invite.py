"""邀请码：注册绑定、7 天补填、首单奖励与月度上限。"""
from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import get_db
from app.main import app

import test_api as api_tests
from test_api import auth, create_task, set_qq


def setup_function():
    api_tests.setup_function()
    app.dependency_overrides[get_db] = api_tests.override_db


def register_with_code(client, username, code=None):
    payload = {
        "username": username,
        "password": "Password123!",
        "nickname": f"用户{username}",
        "email": f"{username}@example.com",
    }
    if code:
        payload["invite_code"] = code
    created = client.post("/api/auth/register", json=payload)
    assert created.status_code == 201, created.text
    token = api_tests.last_mail_token()
    assert client.post("/api/auth/email/confirm", json={"token": token}).status_code == 200
    login = client.post("/api/auth/login", json={"username": username, "password": "Password123!"})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def finish_published_task(client, publisher, taker):
    set_qq(client, publisher, "1000000000")
    task = create_task(client, publisher, required=1)
    client.post(f"/api/tasks/{task['id']}/accept", headers=taker)
    client.post(f"/api/tasks/{task['id']}/confirm", headers=taker)
    final = client.post(f"/api/tasks/{task['id']}/confirm", headers=publisher)
    assert final.status_code == 200, final.text
    assert final.json()["status"] == "completed"


def test_invite_rewards_on_invitee_first_completion():
    with TestClient(app) as client:
        inviter = auth(client, "inviter_a")
        info = client.get("/api/invite/me", headers=inviter).json()
        assert len(info["code"]) == 8
        assert info["invited_total"] == 0

        invitee = register_with_code(client, "invitee_a", info["code"])
        taker = auth(client, "invitee_helper", role="volunteer")
        assert client.get("/api/invite/me", headers=invitee).json()["invited_by"] is True

        finish_published_task(client, invitee, taker)

        assert client.get("/api/points/me", headers=inviter).json() == {
            "lifetime_points": 20, "wallet_points": 20,
        }
        assert client.get("/api/points/me", headers=invitee).json() == {
            "lifetime_points": 10, "wallet_points": 10,
        }
        after = client.get("/api/invite/me", headers=inviter).json()
        assert after["invited_total"] == 1
        assert after["valid_this_month"] == 1


def test_bind_after_registration_within_window():
    with TestClient(app) as client:
        inviter = auth(client, "inviter_b")
        code = client.get("/api/invite/me", headers=inviter).json()["code"]
        invitee = auth(client, "invitee_b")

        bound = client.post("/api/invite/bind", headers=invitee, json={"code": code.lower()})
        assert bound.status_code == 200
        assert bound.json()["invited_by"] is True

        again = client.post("/api/invite/bind", headers=invitee, json={"code": code})
        assert again.status_code == 409

        missing = client.post("/api/invite/bind", headers=auth(client, "invitee_c"), json={"code": "ZZZZZZZZ"})
        assert missing.status_code == 404


def test_bind_window_expires():
    with TestClient(app) as client:
        inviter = auth(client, "inviter_d")
        code = client.get("/api/invite/me", headers=inviter).json()["code"]
        invitee = auth(client, "invitee_d")
        user_id = client.get("/api/auth/me", headers=invitee).json()["id"]
        with api_tests.TestingSession() as db:
            db.execute(
                text("UPDATE users SET created_at = :created WHERE id = :id"),
                {"created": datetime.utcnow() - timedelta(days=8), "id": user_id},
            )
            db.commit()
        expired = client.post("/api/invite/bind", headers=invitee, json={"code": code})
        assert expired.status_code == 409
        assert "7 天" in expired.json()["detail"]


def test_monthly_valid_invite_limit():
    with TestClient(app) as client:
        inviter = auth(client, "inviter_limit")
        code = client.get("/api/invite/me", headers=inviter).json()["code"]
        helper = auth(client, "inviter_limit_helper", role="volunteer")

        for index in range(6):
            invitee = register_with_code(client, f"invitee_limit_{index}", code)
            finish_published_task(client, invitee, helper)

        points = client.get("/api/points/me", headers=inviter).json()
        assert points["lifetime_points"] == 20 * 5
        assert client.get("/api/invite/me", headers=inviter).json()["valid_this_month"] == 5
