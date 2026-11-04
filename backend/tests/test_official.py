"""官方活跃委托：大厅共享池、最多 3 个、抢占式接取与动作核对。"""
from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import text

from app import official as official_module
from app.database import get_db
from app.main import app

import test_api as api_tests
from test_api import auth


def setup_function():
    api_tests.setup_function()
    app.dependency_overrides[get_db] = api_tests.override_db


def enable_official(monkeypatch):
    monkeypatch.setattr(official_module, "FORCE_ENABLED", True)


def official_tasks(client):
    return [task for task in client.get("/api/tasks").json() if task["is_official"]]


def test_pool_is_shared_and_capped_at_three(monkeypatch):
    enable_official(monkeypatch)
    with TestClient(app) as client:
        tasks = official_tasks(client)
        assert len(tasks) == 3
        assert all(task["publisher"]["nickname"] == "万事屋官方" for task in tasks)
        assert {task["official_key"] for task in tasks} == {
            task["official_key"] for task in official_tasks(client)
        }

        taker_a = auth(client, "official_a", role="volunteer")
        taker_b = auth(client, "official_b", role="volunteer")
        target = tasks[0]

        # 大厅刷新不会重复播种。
        assert len(official_tasks(client)) == 3

        first = client.post(f"/api/tasks/{target['id']}/accept", headers=taker_a)
        assert first.status_code == 200, first.text
        assert first.json()["status"] == "accepted"

        # 池子是共享的：A 接走后 B 不能再接。
        second = client.post(f"/api/tasks/{target['id']}/accept", headers=taker_b)
        assert second.status_code == 409

        # 被接取的官方委托离开大厅（占着池子的名额），剩余 2 个仍可被其他人接。
        assert len(official_tasks(client)) == 2
        with api_tests.TestingSession() as db:
            active = db.execute(
                text("SELECT COUNT(*) FROM tasks WHERE is_official = 1 AND status IN ('published','accepted')")
            ).scalar()
        assert active == 3


def test_completion_requires_real_activity(monkeypatch):
    enable_official(monkeypatch)
    with TestClient(app) as client:
        taker = auth(client, "official_done", role="volunteer")
        target = official_tasks(client)[0]
        # 固定成本用例可控的动作：留言板留言。
        with api_tests.TestingSession() as db:
            db.execute(
                text("UPDATE tasks SET official_key = 'board_post', base_points = 5 WHERE id = :id"),
                {"id": target["id"]},
            )
            db.commit()

        client.post(f"/api/tasks/{target['id']}/accept", headers=taker)

        # 还没有站内动作时不能确认。
        denied = client.post(f"/api/tasks/{target['id']}/confirm", headers=taker)
        assert denied.status_code == 409
        assert "站内动作" in denied.json()["detail"]

        client.post("/api/board", headers=taker, json={"content": "官方委托打卡：今天也来留言板看看。"})
        done = client.post(f"/api/tasks/{target['id']}/confirm", headers=taker)
        assert done.status_code == 200, done.text
        assert done.json()["status"] == "completed"
        assert client.get("/api/points/me", headers=taker).json()["lifetime_points"] == 5

        # 官方委托不参与评价。
        ratings = client.get(f"/api/tasks/{target['id']}/ratings", headers=taker).json()
        assert ratings["slots"] == [] and ratings["can_rate"] is False


def test_expired_official_tasks_rotate(monkeypatch):
    enable_official(monkeypatch)
    with TestClient(app) as client:
        first_ids = {task["id"] for task in official_tasks(client)}
        with api_tests.TestingSession() as db:
            db.execute(
                text("UPDATE tasks SET expires_at = :past WHERE is_official = 1"),
                {"past": datetime.utcnow() - timedelta(hours=1)},
            )
            db.commit()

        rotated = official_tasks(client)
        assert len(rotated) == 3
        assert all(task["status"] == "published" for task in rotated)
        # 旧的一批全部过期，新一批重新随机补位。
        assert first_ids.isdisjoint({task["id"] for task in rotated})
