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
