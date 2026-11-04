"""积分账户：概览、流水与历史补偿。"""
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import get_db
from app.main import app
from app.points import award_points

import test_api as api_tests
from test_api import auth, create_task, set_qq


def setup_function():
    api_tests.setup_function()
    app.dependency_overrides[get_db] = api_tests.override_db


def test_new_account_starts_at_zero():
    with TestClient(app) as client:
        headers = auth(client, "points_new")
        summary = client.get("/api/points/me", headers=headers)
        assert summary.status_code == 200
        assert summary.json() == {"lifetime_points": 0, "wallet_points": 0}

        # 公开资料只暴露终身累计，不泄露钱包余额。
        me = client.get("/api/auth/me", headers=headers).json()
        assert me["lifetime_points"] == 0
        assert me["wallet_points"] == 0

        public = client.get(f"/api/creators/{me['id']}").json()
        assert "wallet_points" not in public

        empty = client.get("/api/points/ledger", headers=headers).json()
        assert empty == {"total": 0, "page": 1, "page_size": 20, "items": []}


def test_award_writes_ledger_and_is_idempotent():
    with TestClient(app) as client:
        headers = auth(client, "points_award")
        user_id = client.get("/api/auth/me", headers=headers).json()["id"]

        with api_tests.TestingSession() as db:
            assert award_points(
                db, user_id, kind="daily", lifetime=5, wallet=5,
                note="每日任务", source_type="daily", source_id=1,
            )
            db.commit()
            # 同一来源重复入账被忽略。
            assert not award_points(
                db, user_id, kind="daily", lifetime=5, wallet=5,
                note="每日任务", source_type="daily", source_id=1,
            )
            db.commit()

        summary = client.get("/api/points/me", headers=headers).json()
        assert summary == {"lifetime_points": 5, "wallet_points": 5}

        ledger = client.get("/api/points/ledger", headers=headers).json()
        assert ledger["total"] == 1
        item = ledger["items"][0]
        assert item["kind"] == "daily" and item["kind_label"] == "每日任务"
        assert item["lifetime_delta"] == 5 and item["wallet_delta"] == 5


def test_wallet_never_goes_negative():
    with TestClient(app) as client:
        headers = auth(client, "points_floor")
        user_id = client.get("/api/auth/me", headers=headers).json()["id"]

        with api_tests.TestingSession() as db:
            award_points(db, user_id, kind="daily", lifetime=3, wallet=3, source_type="daily", source_id=2)
            db.commit()
            # 扣 10 分只能扣到 0；终身累计不受影响（只增不减）。
            award_points(
                db, user_id, kind="rating_revoke", lifetime=0, wallet=-10,
                source_type="task", source_id=99,
            )
            db.commit()

        summary = client.get("/api/points/me", headers=headers).json()
        assert summary == {"lifetime_points": 3, "wallet_points": 0}
        ledger = client.get("/api/points/ledger", headers=headers).json()["items"]
        assert ledger[0]["wallet_delta"] == -3


def test_legacy_backfill_compensates_completed_tasks():
    """新增列时按历史完成数一次性补偿终身积分（接单 10/单，发布 3/单）。"""
    with TestClient(app) as client:
        publisher = auth(client, "points_backfill_pub")
        taker = auth(client, "points_backfill_taker", role="volunteer")
        set_qq(client, publisher, "1000000000")
        task = create_task(client, publisher, required=1)
        client.post(f"/api/tasks/{task['id']}/accept", headers=taker)
        client.post(f"/api/tasks/{task['id']}/confirm", headers=taker)
        final = client.post(f"/api/tasks/{task['id']}/confirm", headers=publisher)
        assert final.json()["status"] == "completed"

        # 模拟迁移：清空积分后重新执行一次回填 SQL（等价于旧库首次升级）。
        with api_tests.TestingSession() as db:
            db.execute(text("UPDATE users SET lifetime_points = 0, wallet_points = 0"))
            db.commit()
        with api_tests.engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE users SET lifetime_points = ("
                    "  SELECT COALESCE(COUNT(*), 0) * 10 FROM task_members tm"
                    "  JOIN tasks t ON t.id = tm.task_id"
                    "  WHERE tm.user_id = users.id AND tm.response_status = 'accepted'"
                    "    AND t.status = 'completed'"
                    ") + ("
                    "  SELECT COALESCE(COUNT(*), 0) * 3 FROM tasks t"
                    "  WHERE t.publisher_id = users.id AND t.status = 'completed'"
                    ")"
                )
            )

        assert client.get("/api/points/me", headers=taker).json()["lifetime_points"] == 10
        assert client.get("/api/points/me", headers=publisher).json()["lifetime_points"] == 3


def top_up(client, headers, amount):
    user_id = client.get("/api/auth/me", headers=headers).json()["id"]
    with api_tests.TestingSession() as db:
        award_points(
            db, user_id, kind="daily", lifetime=amount, wallet=amount,
            source_type="test-topup", source_id=user_id,
        )
        db.commit()
    return user_id


def publish_task(client, headers, **overrides):
    payload = {
        "title": "积分测试委托",
        "description": "用于验证基础积分与悬赏托管行为。",
        "category": "其他委托",
        "scale": "small",
        "bounty_points": 0,
        "required_takers": 1,
        "expires_in_days": 2,
    }
    payload.update(overrides)
    return client.post("/api/tasks", headers=headers, json=payload)


def test_rules_endpoint_exposes_economy_constants():
    with TestClient(app) as client:
        rules = client.get("/api/points/rules").json()
        assert rules["scale_points"] == {"small": 5, "medium": 15, "large": 40}
        assert rules["bounty_max"] == 200
        assert rules["advance_ratio"] == 0.6
        assert set(rules["category_factors"]) == {
            "萌新上路", "心理倾听", "技术疑难", "VRC寻图", "搭子召集", "其他委托",
        }


def test_base_points_follow_scale_and_category():
    with TestClient(app) as client:
        publisher = auth(client, "points_scale_pub")
        set_qq(client, publisher, "1000000000")
        small = publish_task(client, publisher, category="萌新上路", scale="small")
        assert small.status_code == 201, small.text
        # round(5 × 0.8) = 4
        assert small.json()["base_points"] == 4
        large = publish_task(client, publisher, category="技术疑难", scale="large")
        # round(40 × 1.3) = 52
        assert large.json()["base_points"] == 52


def test_bounty_is_escrowed_and_refunded_on_cancel():
    with TestClient(app) as client:
        publisher = auth(client, "points_bounty_pub")
        set_qq(client, publisher, "1000000000")
        top_up(client, publisher, 50)

        created = publish_task(client, publisher, bounty_points=30)
        assert created.status_code == 201, created.text
        assert created.json()["bounty_points"] == 30
        assert client.get("/api/points/me", headers=publisher).json()["wallet_points"] == 20

        # 超出余额被拒绝，且不产生委托
        too_much = publish_task(client, publisher, bounty_points=40)
        assert too_much.status_code == 422
        assert "悬赏积分不足" in too_much.json()["detail"]

        cancelled = client.post(f"/api/tasks/{created.json()['id']}/cancel", headers=publisher)
        assert cancelled.json()["status"] == "cancelled"
        assert client.get("/api/points/me", headers=publisher).json()["wallet_points"] == 50


def test_completion_splits_advance_and_bounty():
    with TestClient(app) as client:
        publisher = auth(client, "points_done_pub")
        taker = auth(client, "points_done_taker", role="volunteer")
        set_qq(client, publisher, "1000000000")
        top_up(client, publisher, 40)

        task = publish_task(client, publisher, bounty_points=10).json()
        assert task["base_points"] == 5
        client.post(f"/api/tasks/{task['id']}/accept", headers=taker)
        client.post(f"/api/tasks/{task['id']}/confirm", headers=taker)
        final = client.post(f"/api/tasks/{task['id']}/confirm", headers=publisher)
        assert final.json()["status"] == "completed"

        # 基础积分先发 60%（round(5 × 0.6) = 3），悬赏全额 10。
        taker_points = client.get("/api/points/me", headers=taker).json()
        assert taker_points == {"lifetime_points": 13, "wallet_points": 13}
        publisher_points = client.get("/api/points/me", headers=publisher).json()
        assert publisher_points["wallet_points"] == 30

        kinds = [item["kind"] for item in client.get("/api/points/ledger", headers=taker).json()["items"]]
        assert set(kinds) == {"task_reward", "bounty_reward"}


def test_expired_task_refunds_bounty():
    with TestClient(app) as client:
        publisher = auth(client, "points_expire_pub")
        set_qq(client, publisher, "1000000000")
        top_up(client, publisher, 20)
        task = publish_task(client, publisher, bounty_points=20).json()
        assert client.get("/api/points/me", headers=publisher).json()["wallet_points"] == 0

        with api_tests.TestingSession() as db:
            db.execute(text("UPDATE tasks SET expires_at = '2000-01-01 00:00:00'"))
            db.commit()
        client.get("/api/tasks")  # 触发惰性过期
        assert client.get("/api/points/me", headers=publisher).json()["wallet_points"] == 20
