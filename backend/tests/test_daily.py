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


def test_official_quests_are_stable_per_day():
    from app import daily as daily_module

    first = [item["key"] for item in daily_module.official_quests_for_day("2026-11-04")]
    second = [item["key"] for item in daily_module.official_quests_for_day("2026-11-04")]
    assert first == second and len(first) == 3
    assert set(first).issubset({item["key"] for item in daily_module.OFFICIAL_POOL})
    # 换一天通常会换一批（至少不是硬编码同一组）。
    other = [item["key"] for item in daily_module.official_quests_for_day("2026-11-05")]
    assert other != first


def test_official_quest_claim(monkeypatch):
    from app import daily as daily_module

    quest = {"key": "board_post", "label": "在留言板发一条留言", "reward": 5, "target": 1}
    monkeypatch.setattr(daily_module, "official_quests_for_day", lambda day: [quest])

    with TestClient(app) as client:
        user = auth(client, "official_user")
        snapshot = client.get("/api/daily", headers=user).json()
        assert snapshot["official"] == [
            {"key": "board_post", "label": quest["label"], "reward": 5, "target": 1, "progress": 0, "claimed": False, "can_claim": False}
        ]

        client.post("/api/board", headers=user, json={"content": "今天的官方委托：来留言板打个卡。"})
        assert client.get("/api/daily", headers=user).json()["official"][0]["can_claim"] is True

        claimed = client.post("/api/daily/official/board_post/claim", headers=user)
        assert claimed.status_code == 200, claimed.text
        assert claimed.json()["reward"] == 5
        assert client.get("/api/points/me", headers=user).json()["lifetime_points"] == 5
        assert client.post("/api/daily/official/board_post/claim", headers=user).status_code == 409

        # 不在今日列表里的 key 不能领。
        assert client.post("/api/daily/official/map_like/claim", headers=user).status_code == 404
