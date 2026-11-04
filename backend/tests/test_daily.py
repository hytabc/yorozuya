"""每日任务：进度计算、领取、防重复与全清奖励。"""
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app

import test_api as api_tests
from test_api import auth, create_task, set_qq


def setup_function():
    api_tests.setup_function()
    app.dependency_overrides[get_db] = api_tests.override_db


def items(client, headers):
    return {item["key"]: item for item in client.get("/api/daily", headers=headers).json()["items"]}


def publish_long(client, headers):
    """描述 ≥30 字的委托，才算完成「发布」每日任务。"""
    return client.post(
        "/api/tasks",
        headers=headers,
        json={
            "title": "每日任务用委托",
            "description": "这是一段足够长的委托说明，用于验证每日任务的发布计数规则是否正确生效。",
            "category": "其他委托",
            "required_takers": 1,
            "expires_in_days": 2,
        },
    ).json()


def test_daily_progress_and_claim():
    with TestClient(app) as client:
        publisher = auth(client, "daily_pub")
        taker = auth(client, "daily_taker", role="volunteer")
        set_qq(client, publisher, "1000000000")
        taker_id = client.get("/api/auth/me", headers=taker).json()["id"]

        empty = items(client, taker)
        assert set(empty) == {"publish", "complete", "rate", "share", "all_clear"}
        assert all(not item["can_claim"] for item in empty.values())

        # 发布（描述 ≥30 字）→ 发布任务可领取。
        task = publish_long(client, publisher)
        assert items(client, publisher)["publish"]["can_claim"] is True
        claimed = client.post("/api/daily/publish/claim", headers=publisher)
        assert claimed.status_code == 200, claimed.text
        assert claimed.json()["reward"] == 2
        assert {item["key"]: item for item in claimed.json()["daily"]["items"]}["publish"]["claimed"] is True
        assert client.get("/api/points/me", headers=publisher).json()["lifetime_points"] == 2

        again = client.post("/api/daily/publish/claim", headers=publisher)
        assert again.status_code == 409
        not_ready = client.post("/api/daily/complete/claim", headers=publisher)
        assert not_ready.status_code == 409

        # 完成委托 → 接单人的完成任务可领取。
        client.post(f"/api/tasks/{task['id']}/accept", headers=taker)
        client.post(f"/api/tasks/{task['id']}/confirm", headers=taker)
        client.post(f"/api/tasks/{task['id']}/confirm", headers=publisher)
        assert items(client, taker)["complete"]["can_claim"] is True
        assert client.post("/api/daily/complete/claim", headers=taker).json()["reward"] == 4

        # 评价与分享各自计数。
        client.post(
            f"/api/tasks/{task['id']}/ratings",
            headers=publisher,
            json={"ratee_id": taker_id, "stars_half": 10, "comment": "很顺利"},
        )
        assert items(client, publisher)["rate"]["can_claim"] is True
        client.post(f"/api/tasks/{task['id']}/share", headers=publisher, json={"channel": "copy"})
        assert items(client, publisher)["share"]["can_claim"] is True


def test_all_clear_requires_four_claims():
    with TestClient(app) as client:
        publisher = auth(client, "daily_all_pub")
        set_qq(client, publisher, "1000000000")
        task = publish_long(client, publisher)

        client.post("/api/daily/publish/claim", headers=publisher)
        # 只领了 1 项，全清不可领取。
        assert items(client, publisher)["all_clear"]["can_claim"] is False

        client.post(f"/api/tasks/{task['id']}/share", headers=publisher, json={"channel": "copy"})
        client.post("/api/daily/share/claim", headers=publisher)
        # 还剩评价与完成未领取，全清仍不可领。
        assert items(client, publisher)["all_clear"]["can_claim"] is False
