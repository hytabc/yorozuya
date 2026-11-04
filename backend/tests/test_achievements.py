"""成就系统：解锁条件、一次性积分与公开成就墙。"""
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app

import test_api as api_tests
from test_api import auth, create_task, set_qq

from test_points import age_account


def setup_function():
    api_tests.setup_function()
    app.dependency_overrides[get_db] = api_tests.override_db


def wall(client, headers):
    return {item["key"]: item for item in client.get("/api/achievements", headers=headers).json()["items"]}


def test_first_completion_unlocks_journey_achievements_once():
    with TestClient(app) as client:
        publisher = auth(client, "ach_pub")
        taker = auth(client, "ach_taker", role="volunteer")
        age_account(client, taker)
        set_qq(client, publisher, "1000000000")

        before = wall(client, taker)
        assert before["first_done"]["unlocked"] is False
        assert before["first_done"]["progress"] == 0

        task = create_task(client, publisher, required=1)
        client.post(f"/api/tasks/{task['id']}/accept", headers=taker)
        client.post(f"/api/tasks/{task['id']}/confirm", headers=taker)
        client.post(f"/api/tasks/{task['id']}/confirm", headers=publisher)

        after = wall(client, taker)
        assert after["first_done"]["unlocked"] is True
        assert after["first_done"]["progress"] == 1
        # 成就只发终身积分，不进钱包（基础积分预付款为 技术疑难 small = round(7×0.6)=4）。
        points = client.get("/api/points/me", headers=taker).json()
        assert points["wallet_points"] == 4
        assert points["lifetime_points"] >= 4 + 10

        # 重复访问不会重复发放。
        frozen = points["lifetime_points"]
        client.get("/api/achievements", headers=taker)
        assert client.get("/api/points/me", headers=taker).json()["lifetime_points"] == frozen

        kinds = [item["kind"] for item in client.get("/api/points/ledger", headers=taker).json()["items"]]
        assert "achievement" in kinds


def test_public_wall_hides_locked_items():
    with TestClient(app) as client:
        owner = auth(client, "ach_owner")
        viewer = auth(client, "ach_viewer")
        wall(client, owner)  # 触发一次评估
        owner_id = client.get("/api/auth/me", headers=owner).json()["id"]
        public = client.get(f"/api/users/{owner_id}/achievements", headers=viewer).json()
        assert all(item["unlocked"] for item in public["items"])
        assert public["total"] >= 20
        # 本人能看到未解锁项与进度。
        mine = client.get("/api/achievements", headers=owner).json()
        assert any(not item["unlocked"] for item in mine["items"])
