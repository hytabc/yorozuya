"""官方活跃委托：大厅共享池、最多 3 个、抢占式接取与动作核对。"""
from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import text

from app import official as official_module
from app.database import get_db
from app.main import app
from app.models import AppSetting

import test_api as api_tests
from test_api import auth


def _parse_dt(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)


def _force_refresh_due(db):
    """把下一次官方委托刷新时间推到过去，模拟 4~8 小时窗口到点。"""
    row = db.get(AppSetting, official_module.OFFICIAL_NEXT_REFRESH_KEY)
    past = datetime.utcnow() - timedelta(minutes=1)
    if row is None:
        db.add(
            AppSetting(
                key=official_module.OFFICIAL_NEXT_REFRESH_KEY,
                value=past.isoformat(),
            )
        )
    else:
        row.value = past.isoformat()
    db.commit()


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
        # 初始播种的 3 个任务分配连续时间槽，相邻到期时间间隔 4~8 小时。
        expiries = sorted(_parse_dt(task["expires_at"]) for task in tasks)
        gaps = [
            (later - earlier).total_seconds() / 3600
            for earlier, later in zip(expiries, expiries[1:])
        ]
        assert all(4 <= gap <= 8 for gap in gaps), gaps
        with api_tests.TestingSession() as db:
            schedule = db.get(AppSetting, official_module.OFFICIAL_NEXT_REFRESH_KEY)
            assert schedule is not None
            assert abs((_parse_dt(schedule.value) - expiries[0]).total_seconds()) < 2

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


def test_official_completion_stays_out_of_real_boards(monkeypatch):
    enable_official(monkeypatch)
    with TestClient(app) as client:
        taker = auth(client, "official_boards", role="volunteer")
        target = official_tasks(client)[0]
        with api_tests.TestingSession() as db:
            db.execute(
                text("UPDATE tasks SET official_key = 'board_post', base_points = 5 WHERE id = :id"),
                {"id": target["id"]},
            )
            db.commit()

        client.post(f"/api/tasks/{target['id']}/accept", headers=taker)
        client.post("/api/board", headers=taker, json={"content": "官方委托不计入真实榜的测试留言"})
        done = client.post(f"/api/tasks/{target['id']}/confirm", headers=taker)
        assert done.status_code == 200, done.text
        uid = client.get("/api/auth/me", headers=taker).json()["id"]

        # 官方积分保留，但完成数榜不计官方委托。
        assert client.get("/api/points/me", headers=taker).json()["lifetime_points"] == 5
        points_board = client.get("/api/rankings", params={"board": "points"}).json()
        assert any(item["user"]["id"] == uid for item in points_board["items"])
        completed_board = client.get("/api/rankings", params={"board": "completed"}).json()
        assert all(item["user"]["id"] != uid for item in completed_board["items"])

        # 足迹与成就的完成类统计也不计官方委托。
        records = client.get(f"/api/users/{uid}/records").json()
        assert records["completed_taken"] == 0 and records["completed_published"] == 0
        assert records["top_categories"] == []
        achievements = client.get("/api/achievements", headers=taker).json()
        first_done = next(item for item in achievements["items"] if item["key"] == "first_done")
        assert first_done["unlocked"] is False and first_done["progress"] == 0

        # 评分体系完全忽略官方委托：即使超过 7 天也不会自动补评。
        with api_tests.TestingSession() as db:
            db.execute(
                text("UPDATE tasks SET completed_at = :past WHERE id = :id"),
                {"past": datetime.utcnow() - timedelta(days=8), "id": target["id"]},
            )
            db.commit()
        summary = client.get(f"/api/users/{uid}/rating-summary").json()
        assert summary["taker"]["count"] == 0 and summary["publisher"]["count"] == 0
        ratings = client.get(f"/api/users/{uid}/ratings", params={"role": "taker"}).json()
        assert ratings["total"] == 0


def test_official_tasks_refresh_one_per_interval(monkeypatch):
    enable_official(monkeypatch)
    with TestClient(app) as client:
        first_ids = {task["id"] for task in official_tasks(client)}
        assert len(first_ids) == 3

        # 全部过期且调度到点：一次只补 1 个，而不是整批重建。
        with api_tests.TestingSession() as db:
            db.execute(
                text("UPDATE tasks SET expires_at = :past WHERE is_official = 1"),
                {"past": datetime.utcnow() - timedelta(hours=1)},
            )
            _force_refresh_due(db)
        after_one = official_tasks(client)
        assert len(after_one) == 1
        assert first_ids.isdisjoint({task["id"] for task in after_one})
        second_id = after_one[0]["id"]

        with api_tests.TestingSession() as db:
            _force_refresh_due(db)
        after_two = official_tasks(client)
        assert len(after_two) == 2
        assert second_id in {task["id"] for task in after_two}

        with api_tests.TestingSession() as db:
            _force_refresh_due(db)
        after_three = official_tasks(client)
        assert len(after_three) == 3
        assert all(task["status"] == "published" for task in after_three)

        # 池子满 3 个后，下一个窗口只替换最早发布的 1 个。
        before_rotate = {task["id"] for task in after_three}
        with api_tests.TestingSession() as db:
            _force_refresh_due(db)
        after_rotate = official_tasks(client)
        after_ids = {task["id"] for task in after_rotate}
        assert len(after_rotate) == 3
        assert len(before_rotate - after_ids) == 1
        assert len(after_ids - before_rotate) == 1
