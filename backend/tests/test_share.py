"""委托分享：记录分享动作并返回站内深链。"""
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app

import test_api as api_tests
from test_api import auth, create_task, set_qq


def setup_function():
    api_tests.setup_function()
    app.dependency_overrides[get_db] = api_tests.override_db


def test_share_records_once_per_task_per_day():
    with TestClient(app) as client:
        publisher = auth(client, "share_pub")
        set_qq(client, publisher, "1000000000")
        task = create_task(client, publisher)
        other = create_task(client, publisher, title="另一份委托")

        first = client.post(f"/api/tasks/{task['id']}/share", headers=publisher, json={"channel": "copy"})
        assert first.status_code == 200, first.text
        assert first.json()["path"] == f"/?task={task['id']}"
        assert first.json()["channel"] == "copy"
        assert first.json()["shared_tasks_today"] == 1

        # 同一委托重复分享不重复计数，换一份委托才 +1。
        client.post(f"/api/tasks/{task['id']}/share", headers=publisher, json={"channel": "qrcode"})
        again = client.post(f"/api/tasks/{other['id']}/share", headers=publisher)
        assert again.json()["shared_tasks_today"] == 2


def test_share_requires_login_and_valid_channel():
    with TestClient(app) as client:
        publisher = auth(client, "share_login_pub")
        set_qq(client, publisher, "1000000000")
        task = create_task(client, publisher)

        anonymous = client.post(f"/api/tasks/{task['id']}/share")
        assert anonymous.status_code in (401, 403)

        invalid = client.post(f"/api/tasks/{task['id']}/share", headers=publisher, json={"channel": "weibo"})
        assert invalid.status_code == 422

        missing = client.post("/api/tasks/999999/share", headers=publisher)
        assert missing.status_code == 404


def test_og_landing_page_escapes_and_hides_anonymous_publisher():
    with TestClient(app) as client:
        publisher = auth(client, "og_pub")
        set_qq(client, publisher, "1000000000")
        task = client.post(
            "/api/tasks",
            headers=publisher,
            json={
                "title": "标题 <script>alert(1)</script>",
                "description": "用于验证 OG 落地页转义与匿名裁剪的委托内容。",
                "category": "其他委托",
                "required_takers": 1,
                "expires_in_days": 2,
                "is_anonymous": True,
            },
        ).json()

        page = client.get(f"/share/task/{task['id']}")
        assert page.status_code == 200
        body = page.text
        assert "<script>alert(1)</script>" not in body
        assert "&lt;script&gt;" in body
        assert 'property="og:title"' in body
        assert f"task={task['id']}" in body
        assert "icon" not in body  # 不渲染任何用户内容
        assert "用户og_pub" not in body  # 匿名委托不暴露发布人

        # 已完成/不存在的委托不再作为分享落地页，直接回首页。
        not_found = client.get("/share/task/999999")
        assert not_found.status_code == 200
        assert "url=/" in not_found.text
