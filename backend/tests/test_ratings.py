"""委托评价：双向互评、双盲、校验、积分结算与逾期自动补评。"""
from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import get_db
from app.main import app

import test_api as api_tests
from test_api import auth, set_qq

from test_points import age_account


def setup_function():
    api_tests.setup_function()
    app.dependency_overrides[get_db] = api_tests.override_db


def publish(client, headers):
    return client.post(
        "/api/tasks",
        headers=headers,
        json={
            "title": "评价测试委托",
            "description": "用于验证双向评价、双盲与积分结算。",
            "category": "其他委托",
            "scale": "small",
            "required_takers": 1,
            "expires_in_days": 2,
        },
    ).json()


def finish(client, task_id, publisher, taker):
    client.post(f"/api/tasks/{task_id}/accept", headers=taker)
    client.post(f"/api/tasks/{task_id}/confirm", headers=taker)
    final = client.post(f"/api/tasks/{task_id}/confirm", headers=publisher)
    assert final.json()["status"] == "completed"
    return final.json()


def setup_pair(client, publisher_name, taker_name):
    publisher = auth(client, publisher_name)
    taker = auth(client, taker_name, role="volunteer")
    age_account(client, taker)
    set_qq(client, publisher, "1000000000")
    publisher_id = client.get("/api/auth/me", headers=publisher).json()["id"]
    taker_id = client.get("/api/auth/me", headers=taker).json()["id"]
    task = publish(client, publisher)
    finish(client, task["id"], publisher, taker)
    return publisher, taker, publisher_id, taker_id, task


def test_mutual_ratings_and_settlement():
    with TestClient(app) as client:
        publisher, taker, publisher_id, taker_id, task = setup_pair(client, "rate_pub", "rate_taker")
        # 预付款 round(5 × 0.6) = 3。
        assert client.get("/api/points/me", headers=taker).json()["lifetime_points"] == 3

        created = client.post(
            f"/api/tasks/{task['id']}/ratings",
            headers=publisher,
            json={"ratee_id": taker_id, "stars_half": 10, "comment": "交付很快，沟通顺畅"},
        )
        assert created.status_code == 201, created.text
        assert created.json()["stars"] == 5.0
        # 5 星：目标 5 分，已发 3 分，补 2 分。
        assert client.get("/api/points/me", headers=taker).json()["lifetime_points"] == 5

        replied = client.post(
            f"/api/tasks/{task['id']}/ratings",
            headers=taker,
            json={"ratee_id": publisher_id, "stars_half": 9},
        )
        assert replied.status_code == 201

        # 双方都已提交 → 立即互相可见。
        view = client.get(f"/api/tasks/{task['id']}/ratings", headers=taker).json()
        assert view["role"] == "taker"
        assert view["slots"][0]["my_rating"]["stars"] == 4.5
        assert view["slots"][0]["their_rating"]["stars"] == 5.0


def test_single_side_stays_blind_until_deadline():
    with TestClient(app) as client:
        publisher, taker, publisher_id, taker_id, task = setup_pair(client, "blind_pub", "blind_taker")
        client.post(
            f"/api/tasks/{task['id']}/ratings",
            headers=publisher,
            json={"ratee_id": taker_id, "stars_half": 8, "comment": "整体不错，细节还能更好"},
        )
        view = client.get(f"/api/tasks/{task['id']}/ratings", headers=taker).json()
        # 对方还没提交，接单人暂时看不到内容。
        assert view["slots"][0]["their_rating"] is None
        public = client.get(f"/api/users/{taker_id}/ratings").json()
        assert public["total"] == 0


def test_rating_validation_rules():
    with TestClient(app) as client:
        publisher, taker, publisher_id, taker_id, task = setup_pair(client, "valid_pub", "valid_taker")
        url = f"/api/tasks/{task['id']}/ratings"

        zero = client.post(url, headers=publisher, json={"ratee_id": taker_id, "stars_half": 0})
        assert zero.status_code == 422 and "原因" in zero.json()["detail"]

        short = client.post(
            url, headers=publisher,
            json={"ratee_id": taker_id, "stars_half": 2, "comment": "不行"},
        )
        assert short.status_code == 422 and "15" in short.json()["detail"]

        ok = client.post(
            url, headers=publisher,
            json={"ratee_id": taker_id, "stars_half": 0, "reason_code": "not_delivered", "comment": "说好的交付时间一直往后拖，最后没有完成约定内容"},
        )
        assert ok.status_code == 201
        assert ok.json()["reason_label"] == "未交付"

        duplicate = client.post(url, headers=publisher, json={"ratee_id": taker_id, "stars_half": 5})
        assert duplicate.status_code == 409

        stranger = auth(client, "valid_stranger")
        denied = client.post(
            f"/api/tasks/{task['id']}/ratings",
            headers=stranger,
            json={"ratee_id": taker_id, "stars_half": 5},
        )
        assert denied.status_code == 403


def test_edit_recalculates_settlement():
    with TestClient(app) as client:
        publisher, taker, publisher_id, taker_id, task = setup_pair(client, "edit_pub", "edit_taker")
        client.post(
            f"/api/tasks/{task['id']}/ratings",
            headers=publisher,
            json={"ratee_id": taker_id, "stars_half": 10, "comment": "很满意"},
        )
        assert client.get("/api/points/me", headers=taker).json()["lifetime_points"] == 5

        edited = client.patch(
            f"/api/tasks/{task['id']}/ratings/{taker_id}",
            headers=publisher,
            json={"stars_half": 2, "comment": "后来发现交付内容和约定差距较大"},
        )
        assert edited.status_code == 200
        points = client.get("/api/points/me", headers=taker).json()
        # 目标 1 分，已发 3 分：只从钱包扣 2 分，终身累计不回退。
        assert points == {"lifetime_points": 5, "wallet_points": 3}


def test_overdue_ratings_auto_settle_three_stars():
    with TestClient(app) as client:
        publisher, taker, publisher_id, taker_id, task = setup_pair(client, "auto_pub", "auto_taker")
        with api_tests.TestingSession() as db:
            db.execute(
                text("UPDATE tasks SET completed_at = :t WHERE id = :id"),
                {"t": datetime.utcnow() - timedelta(days=8), "id": task["id"]},
            )
            db.commit()

        view = client.get(f"/api/tasks/{task['id']}/ratings", headers=taker).json()
        assert view["slots"][0]["my_rating"]["automatic"] is True
        assert view["slots"][0]["my_rating"]["stars"] == 3.0
        # 3 星目标 = round(5 × 0.6) = 3，与预付款相同，不再补发。
        assert client.get("/api/points/me", headers=taker).json()["lifetime_points"] == 3


def test_rating_summary_uses_bayesian_prior():
    with TestClient(app) as client:
        publisher, taker, publisher_id, taker_id, task = setup_pair(client, "sum_pub", "sum_taker")
        client.post(
            f"/api/tasks/{task['id']}/ratings",
            headers=publisher,
            json={"ratee_id": taker_id, "stars_half": 10, "comment": "很好"},
        )
        summary = client.get(f"/api/users/{taker_id}/rating-summary").json()
        assert summary["taker"]["count"] == 1
        assert summary["taker"]["average"] == 5.0
        # (10 × 4.0 + 5) / (10 + 1) = 4.09：一单 5 星不会直接变成满分。
        assert summary["taker"]["bayes"] == 4.09
        assert summary["taker"]["good"] == 1
        assert summary["publisher"]["count"] == 0

        # 资料接口会带上聚合分，列表接口不带（避免 N+1）。
        profile = client.get(f"/api/users/{taker_id}", headers=taker).json()
        assert profile["ratings"]["taker"]["count"] == 1


def admin_headers(client):
    login = client.post("/api/auth/login", json={"username": "admin", "password": "Admin123!"})
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_appeal_revoke_recalculates_and_is_moderated():
    with TestClient(app) as client:
        publisher, taker, publisher_id, taker_id, task = setup_pair(client, "appeal_pub", "appeal_taker")
        rating = client.post(
            f"/api/tasks/{task['id']}/ratings",
            headers=publisher,
            json={"ratee_id": taker_id, "stars_half": 4, "comment": "交付内容和约定差距比较大，很多细节没有按要求完成"},
        ).json()
        assert client.get("/api/points/me", headers=taker).json()["wallet_points"] == 2

        # 只有被评价人可以申诉。
        denied = client.post(f"/api/ratings/{rating['id']}/appeal", headers=publisher, json={"reason": "我就是想试试申诉能不能用，随便写一段够长的话"})
        assert denied.status_code == 403

        appeal = client.post(
            f"/api/ratings/{rating['id']}/appeal",
            headers=taker,
            json={"reason": "对方没有按照约定提供协作条件，实际交付标准与我完成的内容一致，请复核。"},
        )
        assert appeal.status_code == 201, appeal.text
        appeal_id = appeal.json()["id"]

        duplicated = client.post(
            f"/api/ratings/{rating['id']}/appeal",
            headers=taker,
            json={"reason": "重复提交一次，应该被拒绝，因为已经有待处理的申诉了。"},
        )
        assert duplicated.status_code == 409

        admin = admin_headers(client)
        pending = client.get("/api/admin/rating-appeals", headers=admin).json()
        assert any(item["id"] == appeal_id for item in pending)

        resolved = client.post(
            f"/api/admin/rating-appeals/{appeal_id}/resolve",
            headers=admin,
            json={"action": "revoke", "note": "核实后撤销该评价"},
        )
        assert resolved.status_code == 200
        assert resolved.json()["status"] == "approved"

        # 撤销后不再计入聚合分，积分按 0 星重算（只扣钱包，不追债）。
        summary = client.get(f"/api/users/{taker_id}/rating-summary").json()
        assert summary["taker"]["count"] == 0
        assert client.get("/api/points/me", headers=taker).json() == {"lifetime_points": 3, "wallet_points": 0}


def test_appeal_limits_and_moderator_only():
    with TestClient(app) as client:
        publisher, taker, publisher_id, taker_id, task = setup_pair(client, "limit_appeal_pub", "limit_appeal_taker")
        rating = client.post(
            f"/api/tasks/{task['id']}/ratings",
            headers=publisher,
            json={"ratee_id": taker_id, "stars_half": 4, "comment": "交付内容和约定差距比较大，很多细节没有按要求完成"},
        ).json()
        mine = client.get("/api/ratings/appeals/mine", headers=taker)
        assert mine.status_code == 200 and mine.json() == []

        # 普通用户不能看管理员列表。
        assert client.get("/api/admin/rating-appeals", headers=taker).status_code == 403

        appeal = client.post(
            f"/api/ratings/{rating['id']}/appeal",
            headers=taker,
            json={"reason": "对方没有按照约定提供协作条件，实际交付标准与我完成的内容一致，请复核。"},
        ).json()
        admin = admin_headers(client)
        rejected = client.post(
            f"/api/admin/rating-appeals/{appeal['id']}/resolve",
            headers=admin,
            json={"action": "reject", "note": "证据不足"},
        )
        assert rejected.json()["status"] == "rejected"
        # 驳回后评价仍然有效。
        assert client.get(f"/api/users/{taker_id}/rating-summary").json()["taker"]["count"] == 1

        again = client.post(
            f"/api/admin/rating-appeals/{appeal['id']}/resolve",
            headers=admin,
            json={"action": "reject"},
        )
        assert again.status_code == 409
