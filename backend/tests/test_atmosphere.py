"""礼仪确认（准入层）：先确认后发布/接取、版本升级重新触发、游客本地记录。"""
from fastapi.testclient import TestClient

from app import atmosphere
from app.database import get_db
from app.main import app

import test_api as api_tests
from test_api import auth, create_task, set_qq


def setup_function():
    api_tests.setup_function()
    app.dependency_overrides[get_db] = api_tests.override_db


def test_status_and_ack_flow():
    with TestClient(app) as client:
        # 游客可读状态，但服务端不知道游客本地确认过什么。
        guest = client.get("/api/atmosphere/status")
        assert guest.status_code == 200
        assert guest.json() == {
            "version": atmosphere.ATMOSPHERE_VERSION,
            "accepted": False,
            "accepted_version": 0,
        }

        user = auth(client, "atm_user")
        assert client.get("/api/atmosphere/status", headers=user).json()["accepted"] is False

        # 未登录不能写入确认记录。
        assert client.post("/api/atmosphere/ack", json={"version": 1}).status_code == 401

        # 版本不一致（前端拿到旧页面）时拒绝，避免把旧条款当成新条款确认。
        stale = client.post("/api/atmosphere/ack", headers=user, json={"version": 99})
        assert stale.status_code == 409
        assert "版本已更新" in stale.json()["detail"]

        acked = client.post(
            "/api/atmosphere/ack",
            headers=user,
            json={"version": atmosphere.ATMOSPHERE_VERSION},
        )
        assert acked.status_code == 200, acked.text
        assert acked.json()["accepted"] is True

        status = client.get("/api/atmosphere/status", headers=user).json()
        assert status["accepted"] is True
        assert status["accepted_version"] == atmosphere.ATMOSPHERE_VERSION

        # 重复确认是幂等的（同一账号只保留一行）。
        assert client.post(
            "/api/atmosphere/ack",
            headers=user,
            json={"version": atmosphere.ATMOSPHERE_VERSION},
        ).status_code == 200
        assert client.get("/api/atmosphere/status", headers=user).json()["accepted"] is True


def test_gate_blocks_publish_and_accept_until_acknowledged(monkeypatch):
    # pytest 下默认跳过闸门，这里显式打开以验证服务端强制力。
    monkeypatch.setattr(atmosphere, "gate_required", lambda: True)
    with TestClient(app) as client:
        publisher = auth(client, "atm_pub")
        taker = auth(client, "atm_taker", role="volunteer")
        set_qq(client, publisher, "1000000000")

        blocked = client.post(
            "/api/tasks",
            headers=publisher,
            json={
                "title": "未确认礼仪的委托",
                "description": "未完成礼仪确认时发布应当被拒绝。",
                "category": "其他委托",
                "expires_in_days": 1,
            },
        )
        assert blocked.status_code == 403
        assert "礼仪确认" in blocked.json()["detail"]

        client.post(
            "/api/atmosphere/ack",
            headers=publisher,
            json={"version": atmosphere.ATMOSPHERE_VERSION},
        )
        created = create_task(client, publisher, required=1)
        assert created["id"] > 0

        # 接取同样受闸门保护；确认后即可凭密码接取。
        assert client.post(
            f"/api/tasks/{created['id']}/accept", headers=taker, json={"password": "atm-pw-1"}
        ).status_code == 403
        client.post(
            "/api/atmosphere/ack",
            headers=taker,
            json={"version": atmosphere.ATMOSPHERE_VERSION},
        )
        accepted = client.post(
            f"/api/tasks/{created['id']}/accept", headers=taker, json={"password": "atm-pw-1"}
        )
        assert accepted.status_code == 200
        assert accepted.json()["status"] == "accepted"

        # 超管豁免：运维账号不会被确认流程挡在门外。
        admin = {"Authorization": f"Bearer {client.post('/api/auth/login', json={'username': 'admin', 'password': 'Admin123!'}).json()['access_token']}"}
        set_qq(client, admin, "1000000001")
        admin_task = client.post(
            "/api/tasks",
            headers=admin,
            json={
                "title": "超管发布的委托",
                "description": "超管不应被礼仪闸门拦住，但仍需先填写 QQ。",
                "category": "其他委托",
                "expires_in_days": 1,
            },
        )
        assert admin_task.status_code == 201, admin_task.text


def test_version_upgrade_requires_reconfirm(monkeypatch):
    with TestClient(app) as client:
        user = auth(client, "atm_upgrade")
        client.post(
            "/api/atmosphere/ack",
            headers=user,
            json={"version": atmosphere.ATMOSPHERE_VERSION},
        )

        # 模拟条款更新：版本号上调后，旧的确认记录不再算数。
        monkeypatch.setattr(atmosphere, "ATMOSPHERE_VERSION", atmosphere.ATMOSPHERE_VERSION + 1)
        status = client.get("/api/atmosphere/status", headers=user).json()
        assert status["accepted"] is False
        assert status["accepted_version"] == 1

        # 用新版本确认后重新生效。
        assert client.post(
            "/api/atmosphere/ack", headers=user, json={"version": atmosphere.ATMOSPHERE_VERSION}
        ).status_code == 200
        assert client.get("/api/atmosphere/status", headers=user).json()["accepted"] is True
