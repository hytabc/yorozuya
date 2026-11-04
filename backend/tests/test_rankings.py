"""排行榜：积分/完成数/评分榜与「不参与排行榜」开关。"""
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app

import test_api as api_tests
from test_api import auth, create_task, set_qq

from test_points import age_account, top_up


def setup_function():
    api_tests.setup_function()
    app.dependency_overrides[get_db] = api_tests.override_db


def board(client, key, headers=None):
    return client.get("/api/rankings", params={"board": key}, headers=headers or {}).json()


def test_points_board_and_opt_out():
    with TestClient(app) as client:
        low = auth(client, "rank_low")
        high = auth(client, "rank_high")
        top_up(client, low, 20)
        top_up(client, high, 200)

        points = board(client, "points", high)
        ranked = [(item["user"]["nickname"], item["value"]) for item in points["items"]]
        assert ranked[0][0] == "用户rank_high"
        assert ranked[0][1] == 200
        # 查看者自己会被标记。
        assert points["items"][0]["is_me"] is True

        opt_out = client.patch("/api/rankings/opt-out", headers=high, json={"opt_out": True})
        assert opt_out.json()["rank_opt_out"] is True
        names = [item["user"]["nickname"] for item in board(client, "points", low)["items"]]
        assert "用户rank_high" not in names
        assert "用户rank_low" in names
        # 资料页仍然展示等级与积分。
        me = client.get("/api/auth/me", headers=high).json()
        assert me["rank_opt_out"] is True and me["level"] >= 3


def test_rating_board_requires_five_reviews():
    with TestClient(app) as client:
        publisher = auth(client, "rank_pub")
        taker = auth(client, "rank_taker", role="volunteer")
        age_account(client, taker)
        set_qq(client, publisher, "1000000000")

        task = create_task(client, publisher, required=1)
        client.post(f"/api/tasks/{task['id']}/accept", headers=taker)
        client.post(f"/api/tasks/{task['id']}/confirm", headers=taker)
        client.post(f"/api/tasks/{task['id']}/confirm", headers=publisher)
        taker_id = client.get("/api/auth/me", headers=taker).json()["id"]
        client.post(
            f"/api/tasks/{task['id']}/ratings",
            headers=publisher,
            json={"ratee_id": taker_id, "stars_half": 10, "comment": "很好"},
        )

        empty = board(client, "taker_rating")
        assert all(item["user"]["nickname"] != "用户rank_taker" for item in empty["items"])
        assert empty["min_count"] == 5


def test_completed_board_counts_both_roles():
    with TestClient(app) as client:
        publisher = auth(client, "rank_done_pub")
        taker = auth(client, "rank_done_taker", role="volunteer")
        set_qq(client, publisher, "1000000000")
        task = create_task(client, publisher, required=1)
        client.post(f"/api/tasks/{task['id']}/accept", headers=taker)
        client.post(f"/api/tasks/{task['id']}/confirm", headers=taker)
        client.post(f"/api/tasks/{task['id']}/confirm", headers=publisher)

        data = board(client, "completed")
        values = {item["user"]["nickname"]: item["value"] for item in data["items"]}
        assert values.get("用户rank_done_pub") == 1
        assert values.get("用户rank_done_taker") == 1
