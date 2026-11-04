"""完成凭证与作品集：幂等签发、快照不可篡改、可见性越权、匿名裁剪与撤销。"""
import re

from fastapi.testclient import TestClient

from app import credentials
from app.database import get_db
from app.main import app
from app.models import Task

import test_api as api_tests
from test_api import auth, set_qq, TestingSession


def setup_function():
    api_tests.setup_function()
    app.dependency_overrides[get_db] = api_tests.override_db


def publish(client, publisher, title, skills=None, password="cred-pw-1", anonymous=False):
    if not client.get("/api/auth/me", headers=publisher).json().get("qq"):
        set_qq(client, publisher, "1000000000")
    payload = {
        "title": title,
        "description": "用于验证完成凭证与作品集聚合的正文内容。",
        "category": "技术疑难",
        "pay_type": "free",
        "required_takers": 1,
        "expires_in_days": 2,
        "accept_password": password,
        "is_anonymous": anonymous,
        "facets": [{"facet_type": "skill", "value": value} for value in (skills or [])],
    }
    response = client.post("/api/tasks", headers=publisher, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def complete(client, publisher, taker, title, skills=None, password="cred-pw-1", anonymous=False):
    task = publish(client, publisher, title, skills=skills, password=password, anonymous=anonymous)
    accepted = client.post(
        f"/api/tasks/{task['id']}/accept", headers=taker, json={"password": password}
    )
    assert accepted.status_code == 200, accepted.text
    assert client.post(f"/api/tasks/{task['id']}/confirm", headers=taker).status_code == 200
    final = client.post(f"/api/tasks/{task['id']}/confirm", headers=publisher)
    assert final.status_code == 200, final.text
    assert final.json()["status"] == "completed"
    return task


def test_completion_issues_credential_once():
    with TestClient(app) as client:
        publisher = auth(client, "cred_pub")
        taker = auth(client, "cred_taker", role="volunteer")
        task = complete(client, publisher, taker, "凭证签发委托", skills=["Blender", "Unity"])

        mine = client.get("/api/credentials/mine", headers=taker)
        assert mine.status_code == 200
        items = mine.json()
        assert len(items) == 1
        credential = items[0]
        assert re.fullmatch(r"WS-\d{4}-\d{6}", credential["serial"])
        assert credential["title"] == "凭证签发委托"
        assert credential["skills"] == ["Blender", "Unity"]
        assert credential["taker"] == "用户cred_taker"
        assert credential["visibility"] == "link"
        assert credential["revoked"] is False
        assert credential["task_id"] == task["id"]

        # 幂等：重复调用签发不会再生成第二张。
        with TestingSession() as db:
            stored = db.get(Task, task["id"])
            assert credentials.issue_for_task(db, stored) == []
            db.commit()
        assert len(client.get("/api/credentials/mine", headers=taker).json()) == 1

        # 凭证快照不随委托后续变化：直接改库里的标题也不影响已签发内容。
        with TestingSession() as db:
            stored = db.get(Task, task["id"])
            stored.title = "被篡改的标题"
            db.commit()
        assert client.get(f"/api/credentials/{credential['serial']}").json()["title"] == "凭证签发委托"


def test_visibility_rules_and_portfolio_listing():
    with TestClient(app) as client:
        publisher = auth(client, "cred_vis_pub")
        taker = auth(client, "cred_vis_taker", role="volunteer")
        guest_viewer = auth(client, "cred_vis_other")
        task = complete(client, publisher, taker, "可见性委托", skills=["Blender"])
        serial = client.get("/api/credentials/mine", headers=taker).json()[0]["serial"]
        taker_id = client.get("/api/auth/me", headers=taker).json()["id"]

        # 默认「仅链接」：任何人凭编号可看，但不出现在作品集列表里。
        assert client.get(f"/api/credentials/{serial}").status_code == 200
        wall = client.get(f"/api/creators/{taker_id}/credentials").json()
        assert wall == {"total": 0, "page": 1, "page_size": 20, "items": []}

        # 私有：只有本人可见，其他登录用户与游客都是 404。
        assert client.patch(
            f"/api/credentials/{serial}/visibility", headers=taker, json={"visibility": "private"}
        ).status_code == 200
        assert client.get(f"/api/credentials/{serial}").status_code == 404
        assert client.get(f"/api/credentials/{serial}", headers=guest_viewer).status_code == 404
        assert client.get(f"/api/credentials/{serial}", headers=taker).status_code == 200

        # 非本人不能修改可见性。
        assert client.patch(
            f"/api/credentials/{serial}/visibility", headers=guest_viewer, json={"visibility": "public"}
        ).status_code == 403

        # 公开：进入作品集凭证墙，作品集计数同步。
        client.patch(f"/api/credentials/{serial}/visibility", headers=taker, json={"visibility": "public"})
        wall = client.get(f"/api/creators/{taker_id}/credentials").json()
        assert wall["total"] == 1
        assert wall["items"][0]["serial"] == serial
        portfolio = client.get(f"/api/creators/{taker_id}").json()
        assert portfolio["user"]["id"] == taker_id
        assert portfolio["credential_count"] == 1
        # 只有一次完成，技能标签不满足「≥2 次」的门槛。
        assert portfolio["tags"] == []

        # 非法可见性由 Literal 白名单拦下。
        assert client.patch(
            f"/api/credentials/{serial}/visibility", headers=taker, json={"visibility": "friends"}
        ).status_code == 422


def test_anonymous_task_credential_does_not_leak_publisher():
    with TestClient(app) as client:
        publisher = auth(client, "cred_anon_pub")
        taker = auth(client, "cred_anon_taker", role="volunteer")
        complete(client, publisher, taker, "匿名凭证委托", anonymous=True)
        credential = client.get("/api/credentials/mine", headers=taker).json()[0]
        assert credential["publisher"] == "匿名委托"
        assert credential["publisher_id"] is None


def test_portfolio_tags_require_repeated_completion():
    with TestClient(app) as client:
        publisher = auth(client, "cred_tag_pub")
        taker = auth(client, "cred_tag_taker", role="volunteer")
        taker_id = client.get("/api/auth/me", headers=taker).json()["id"]

        complete(client, publisher, taker, "标签委托一", skills=["Blender"], password="tag-pw-1")
        with TestingSession() as db:
            from app.credentials import TaskCredential

            for row in db.query(TaskCredential).all():
                row.visibility = "public"
            db.commit()

        portfolio = client.get(f"/api/creators/{taker_id}").json()
        assert portfolio["tags"] == []

        complete(client, publisher, taker, "标签委托二", skills=["Blender", "音频"], password="tag-pw-2")
        with TestingSession() as db:
            from app.credentials import TaskCredential

            for row in db.query(TaskCredential).all():
                row.visibility = "public"
            db.commit()

        tags = {item["value"]: item["count"] for item in client.get(f"/api/creators/{taker_id}").json()["tags"]}
        assert tags == {"Blender": 2}


def test_moderation_revokes_and_restores():
    with TestClient(app) as client:
        admin_login = client.post(
            "/api/auth/login", json={"username": "admin", "password": "Admin123!"}
        )
        admin = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}
        publisher = auth(client, "cred_mod_pub")
        taker = auth(client, "cred_mod_taker", role="volunteer")
        regular = auth(client, "cred_mod_regular")
        complete(client, publisher, taker, "撤销凭证委托")
        credential = client.get("/api/credentials/mine", headers=taker).json()[0]
        serial = credential["serial"]
        client.patch(f"/api/credentials/{serial}/visibility", headers=taker, json={"visibility": "public"})

        # 普通用户不能撤销；管理员组可以。
        assert client.patch(
            "/api/admin/credentials/1", headers=regular, json={"revoked": True, "admin_note": "刷单"}
        ).status_code == 403
        revoked = client.patch(
            "/api/admin/credentials/1", headers=admin, json={"revoked": True, "admin_note": "刷单"}
        )
        assert revoked.status_code == 200, revoked.text
        assert revoked.json()["revoked"] is True

        # 撤销后公开页仍可打开，但明确显示已失效；作品集不再列出。
        page = client.get(f"/api/credentials/{serial}")
        assert page.status_code == 200
        assert page.json()["revoked"] is True
        taker_id = client.get("/api/auth/me", headers=taker).json()["id"]
        assert client.get(f"/api/creators/{taker_id}/credentials").json()["total"] == 0
        assert client.get(f"/api/creators/{taker_id}").json()["credential_count"] == 0

        restored = client.patch(
            "/api/admin/credentials/1", headers=admin, json={"revoked": False}
        )
        assert restored.status_code == 200
        assert restored.json()["revoked"] is False
        assert client.get(f"/api/creators/{taker_id}/credentials").json()["total"] == 1

        assert client.patch(
            "/api/admin/credentials/99999", headers=admin, json={"revoked": True}
        ).status_code == 404
