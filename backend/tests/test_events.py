"""站内事件流：只记当事人自己的委托事件、未读计数与已读标记。"""
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app

import test_api as api_tests
from test_api import auth, set_qq


def setup_function():
    api_tests.setup_function()
    app.dependency_overrides[get_db] = api_tests.override_db


def kinds(client, headers):
    return [item["kind"] for item in client.get("/api/events", headers=headers).json()["items"]]


def test_events_follow_task_lifecycle():
    with TestClient(app) as client:
        publisher = auth(client, "evt_pub")
        taker = auth(client, "evt_taker", role="volunteer")
        set_qq(client, publisher, "1000000000")
        publisher_id = client.get("/api/auth/me", headers=publisher).json()["id"]
        taker_id = client.get("/api/auth/me", headers=taker).json()["id"]

        task = client.post(
            "/api/tasks",
            headers=publisher,
            json={
                "title": "事件流委托",
                "description": "用于验证站内事件流在生命周期各节点的写入。",
                "category": "其他委托",
                "required_takers": 1,
                "expires_in_days": 2,
            },
        ).json()
        task_id = task["id"]

        client.post(f"/api/tasks/{task_id}/accept", headers=taker)
        # required_takers=1：接取即自动开始。
        client.post(f"/api/tasks/{task_id}/confirm", headers=taker)
        final = client.post(f"/api/tasks/{task_id}/confirm", headers=publisher)
        assert final.json()["status"] == "completed"

        publisher_events = kinds(client, publisher)
        assert publisher_events == ["awaiting", "started", "accepted"]
        assert kinds(client, taker) == ["completed"]

        # 事件内容只包含标题与类型，不含委托正文或其他人的数据。
        item = client.get("/api/events", headers=publisher).json()["items"][0]
        assert set(item.keys()) == {"id", "task_id", "kind", "title", "read", "created_at"}
        assert item["task_id"] == task_id
        assert "事件流委托" in item["title"]

        # 第三方看不到别人的事件。
        stranger = auth(client, "evt_stranger")
        assert kinds(client, stranger) == []

        # 未读计数与已读标记。
        listing = client.get("/api/events", headers=publisher).json()
        assert listing["unread"] == 3
        assert listing["total"] == 3
        first_id = listing["items"][0]["id"]
        read_one = client.post("/api/events/read", headers=publisher, json={"ids": [first_id]})
        assert read_one.status_code == 200
        assert read_one.json()["updated"] == 1
        assert client.get("/api/events", headers=publisher).json()["unread"] == 2

        # 空 ids 表示全部已读。
        assert client.post("/api/events/read", headers=publisher, json={"ids": []}).json()["updated"] == 2
        assert client.get("/api/events/summary", headers=publisher).json() == {"unread": 0}

        # 未登录不可访问。
        assert client.get("/api/events").status_code == 401
        assert client.get("/api/events/summary").status_code == 401
        assert client.post("/api/events/read", json={"ids": []}).status_code == 401

        # 不能把别人的事件标记成已读。
        other = client.get("/api/events", headers=taker).json()["items"][0]["id"]
        assert client.post("/api/events/read", headers=publisher, json={"ids": [other]}).json()["updated"] == 0
        assert client.get("/api/events", headers=taker).json()["unread"] == 1
        assert publisher_id != taker_id


def test_event_pagination_and_designated_notice():
    with TestClient(app) as client:
        publisher = auth(client, "evt_page_pub")
        taker = auth(client, "evt_page_taker", role="volunteer")
        set_qq(client, publisher, "1000000000")
        taker_id = client.get("/api/auth/me", headers=taker).json()["id"]

        for index in range(3):
            created = client.post(
                "/api/tasks",
                headers=publisher,
                json={
                    "title": f"指定委托 {index}",
                    "description": "用于验证指定委托的站内事件与分页约定。",
                    "category": "其他委托",
                    "designated_user_ids": [taker_id],
                    "expires_in_days": 2,
                },
            )
            assert created.status_code == 201, created.text

        listing = client.get("/api/events", headers=taker, params={"page": 1, "page_size": 2}).json()
        assert (listing["total"], listing["page"], listing["page_size"], listing["unread"]) == (3, 1, 2, 3)
        assert len(listing["items"]) == 2
        assert all(item["kind"] == "designated" for item in listing["items"])
        second = client.get("/api/events", headers=taker, params={"page": 2, "page_size": 2}).json()
        assert len(second["items"]) == 1


def test_cancel_and_hidden_events():
    with TestClient(app) as client:
        admin_login = client.post(
            "/api/auth/login", json={"username": "admin", "password": "Admin123!"}
        )
        admin = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}
        publisher = auth(client, "evt_cancel_pub")
        taker = auth(client, "evt_cancel_taker", role="volunteer")
        set_qq(client, publisher, "1000000000")

        task = client.post(
            "/api/tasks",
            headers=publisher,
            json={
                "title": "取消事件委托",
                "description": "用于验证取消发起与最终取消的站内事件。",
                "category": "其他委托",
                "required_takers": 3,
                "expires_in_days": 2,
            },
        ).json()
        task_id = task["id"]
        client.post(f"/api/tasks/{task_id}/accept", headers=taker)

        assert client.post(f"/api/tasks/{task_id}/cancel", headers=publisher).json()["status"] == "cancelling"
        assert "cancel_requested" in kinds(client, taker)
        assert client.post(f"/api/tasks/{task_id}/confirm-cancel", headers=taker).json()["status"] == "cancelled"
        assert "cancelled" in kinds(client, publisher)

        hidden = client.post(
            "/api/tasks",
            headers=publisher,
            json={
                "title": "将被隐藏的委托",
                "description": "用于验证管理员隐藏委托时会给发布者写入事件。",
                "category": "其他委托",
                "expires_in_days": 2,
            },
        ).json()
        client.patch(
            f"/api/admin/tasks/{hidden['id']}",
            headers=admin,
            json={"is_visible": False, "admin_note": "测试屏蔽"},
        )
        assert "hidden" in kinds(client, publisher)
