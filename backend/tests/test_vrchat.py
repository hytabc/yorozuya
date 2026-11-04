"""VRChat 身份软绑定：格式校验、唯一占用、逐项披露、匿名裁剪与解绑清理。"""
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app

import test_api as api_tests
from test_api import auth, create_task, set_qq

PROFILE = "https://vrchat.com/home/user/usr_c1644b5b-3ca4-45b4-97c6-a2a0de70d469"


def setup_function():
    api_tests.setup_function()
    app.dependency_overrides[get_db] = api_tests.override_db


def bind(client, headers, name="VRC 昵称", profile=PROFILE):
    return client.post(
        "/api/vrchat/link", headers=headers, json={"display_name": name, "profile": profile}
    )


def test_soft_link_requires_login_and_valid_profile():
    with TestClient(app) as client:
        assert client.get("/api/vrchat/status").status_code == 401
        assert client.post(
            "/api/vrchat/link", json={"display_name": "x", "profile": PROFILE}
        ).status_code == 401

        user = auth(client, "vr_link_user")
        status = client.get("/api/vrchat/status", headers=user).json()
        assert status["bound"] is False
        assert status["disclosure"] == {
            "identity": False,
            "trust_rank": False,
            "account_age": False,
            "common_friends": False,
            "common_groups": False,
            "worlds": False,
        }
        assert status["enabled"] is True and status["allow_new_links"] is True

        # 只接受 https 的 vrchat.com 主页，并且链接里必须能取出 usr_ 开头的 ID。
        assert bind(client, user, profile="http://vrchat.com/home/user/usr_abcd1234").status_code == 422
        assert bind(client, user, profile="https://example.com/home/user/usr_abcd1234").status_code == 422
        assert bind(client, user, profile="https://vrchat.com/home/user/unknown").status_code == 422
        # 直接粘贴 usr_ ID 也可以，服务端会补全主页地址。
        raw = client.post(
            "/api/vrchat/link",
            headers=user,
            json={"display_name": "VRC 昵称", "profile": "usr_abcd1234"},
        )
        assert raw.status_code == 200, raw.text
        assert raw.json()["bound"] is True
        assert raw.json()["verified"] is False
        assert raw.json()["profile_url"] == "https://vrchat.com/home/user/usr_abcd1234"

        # 软绑定没有外部数据源：刷新接口明确返回「未接入」，不假装成功。
        refresh = client.post("/api/vrchat/refresh", headers=user)
        assert refresh.status_code == 400
        assert "未接入" in refresh.json()["detail"]


def test_same_profile_cannot_be_claimed_twice():
    with TestClient(app) as client:
        first = auth(client, "vr_claim_a")
        second = auth(client, "vr_claim_b")
        assert bind(client, first).status_code == 200
        conflict = bind(client, second)
        assert conflict.status_code == 409
        assert "已被其他账号绑定" in conflict.json()["detail"]
        # 本人重新绑定同一主页是允许的（相当于更新显示名）。
        assert bind(client, first, name="新昵称").status_code == 200
        assert client.get("/api/vrchat/status", headers=first).json()["display_name"] == "新昵称"


def test_disclosure_is_enforced_in_the_api():
    with TestClient(app) as client:
        owner = auth(client, "vr_owner")
        viewer = auth(client, "vr_viewer")
        owner_id = client.get("/api/auth/me", headers=owner).json()["id"]
        bind(client, owner)

        # 默认全关：他人只知道「有绑定」，拿不到显示名与主页链接。
        hidden = client.get(f"/api/users/{owner_id}/trust", headers=viewer).json()
        assert hidden["bound"] is True
        assert hidden["verified"] is False
        assert "display_name" not in hidden
        assert "profile_url" not in hidden

        # 本人始终能看到自己的数据。
        own = client.get(f"/api/users/{owner_id}/trust", headers=owner).json()
        assert own["display_name"] == "VRC 昵称"

        # 只开启 identity 一项后才对他人可见；其余项没有真实数据，也不会伪造。
        updated = client.patch(
            "/api/vrchat/disclosure", headers=owner, json={"identity": True}
        )
        assert updated.status_code == 200
        assert updated.json()["disclosure"]["identity"] is True
        visible = client.get(f"/api/users/{owner_id}/trust", headers=viewer).json()
        assert visible["display_name"] == "VRC 昵称"
        assert visible["profile_url"] == PROFILE
        assert "trust_rank" not in visible

        # 关闭后立即恢复不可见。
        client.patch("/api/vrchat/disclosure", headers=owner, json={"identity": False})
        assert "display_name" not in client.get(
            f"/api/users/{owner_id}/trust", headers=viewer
        ).json()

        # 未绑定用户没有任何信任数据，也不会被标记成负面。
        viewer_id = client.get("/api/auth/me", headers=viewer).json()["id"]
        unbound = client.get(f"/api/users/{viewer_id}/trust", headers=viewer)
        assert unbound.status_code == 200
        assert unbound.json()["bound"] is False
        assert "display_name" not in unbound.json()


def test_anonymous_task_trims_publisher_trust():
    with TestClient(app) as client:
        publisher = auth(client, "vr_anon_pub")
        taker = auth(client, "vr_anon_taker", role="volunteer")
        stranger = auth(client, "vr_anon_stranger")
        set_qq(client, publisher, "1000000000")
        bind(client, publisher)
        client.patch("/api/vrchat/disclosure", headers=publisher, json={"identity": True})

        created = client.post(
            "/api/tasks",
            headers=publisher,
            json={
                "title": "匿名委托信任裁剪",
                "description": "匿名委托不得在接口层泄露发布者的 VRChat 身份。",
                "category": "其他委托",
                "pay_type": "free",
                "is_anonymous": True,
                "required_takers": 1,
                "expires_in_days": 2,
            },
        )
        assert created.status_code == 201, created.text
        task_id = created.json()["id"]

        trimmed = client.get(f"/api/tasks/{task_id}/trust", headers=stranger).json()
        assert trimmed == {"anonymous": True, "publisher": None, "members": []}

        # 接单一员能看到发布者（协作关系内），但匿名委托仍不对外公开。
        client.post(f"/api/tasks/{task_id}/accept", headers=taker, json={})
        participant = client.get(f"/api/tasks/{task_id}/trust", headers=taker).json()
        assert participant["publisher"]["display_name"] == "VRC 昵称"

        # 普通非匿名委托：发布者与已接受成员都在返回里。
        public = create_task(client, publisher, password="vr-pub-1", required=1, title="公开委托信任")
        bind(client, taker, name="接单人昵称", profile="usr_beef1234")
        client.post(f"/api/tasks/{public['id']}/accept", headers=taker, json={"password": "vr-pub-1"})
        summary = client.get(f"/api/tasks/{public['id']}/trust", headers=stranger).json()
        assert summary["anonymous"] is False
        # 发布者在前面已开启 identity 披露，因此这里可见其显示名。
        assert summary["publisher"]["display_name"] == "VRC 昵称"
        assert len(summary["members"]) == 1
        assert summary["members"][0]["bound"] is True


def test_unlink_and_delete_clear_public_summary():
    with TestClient(app) as client:
        owner = auth(client, "vr_unlink")
        viewer = auth(client, "vr_unlink_viewer")
        owner_id = client.get("/api/auth/me", headers=owner).json()["id"]
        bind(client, owner)
        client.patch("/api/vrchat/disclosure", headers=owner, json={"identity": True})
        assert client.get(f"/api/users/{owner_id}/trust", headers=viewer).json()["bound"] is True

        unlinked = client.post("/api/vrchat/unlink", headers=owner)
        assert unlinked.status_code == 200
        assert unlinked.json()["bound"] is False
        assert unlinked.json()["status"] == "unlinked"
        assert unlinked.json()["display_name"] is None
        assert client.get(f"/api/users/{owner_id}/trust", headers=viewer).json()["bound"] is False

        # 解绑后可以绑定另一个主页。
        assert bind(client, owner, profile="usr_aaaa1111").status_code == 200

        # 彻底删除数据后，绑定信息不存在。
        assert client.delete("/api/vrchat/data", headers=owner).status_code == 200
        assert client.get("/api/vrchat/status", headers=owner).json()["bound"] is False
        assert client.delete("/api/vrchat/data", headers=owner).status_code == 404

        # 重复解绑同样 404。
        assert client.post("/api/vrchat/unlink", headers=owner).status_code == 404

        # 披露开关在未绑定时不可用。
        assert client.patch(
            "/api/vrchat/disclosure", headers=owner, json={"identity": True}
        ).status_code == 409


def test_admin_switch_blocks_new_links():
    with TestClient(app) as client:
        admin_login = client.post(
            "/api/auth/login", json={"username": "admin", "password": "Admin123!"}
        )
        admin = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}
        staff = auth(client, "vr_staff")
        staff_id = client.get("/api/auth/me", headers=staff).json()["id"]
        assert client.patch(
            f"/api/admin/users/{staff_id}/role", headers=admin, json={"role": "staff"}
        ).status_code == 200

        # 管理员组可读状态，但只有超管能改配置。
        assert client.get("/api/admin/vrchat/status", headers=staff).status_code == 200
        assert client.patch(
            "/api/admin/vrchat/config", headers=staff, json={"enabled": False}
        ).status_code == 403
        assert client.get("/api/admin/vrchat/status", headers=auth(client, "vr_plain")).status_code == 403

        disabled = client.patch(
            "/api/admin/vrchat/config", headers=admin, json={"enabled": False}
        )
        assert disabled.status_code == 200
        assert disabled.json()["enabled"] is False
        blocked = bind(client, auth(client, "vr_blocked"))
        assert blocked.status_code == 503
        assert "已关闭" in blocked.json()["detail"]

        # 重新开启但暂停新绑定。
        client.patch("/api/admin/vrchat/config", headers=admin, json={"enabled": True})
        paused = client.patch(
            "/api/admin/vrchat/config", headers=admin, json={"allow_new_links": False}
        )
        assert paused.json()["allow_new_links"] is False
        assert "暂停" in bind(client, auth(client, "vr_paused")).json()["detail"]

        client.patch("/api/admin/vrchat/config", headers=admin, json={"allow_new_links": True})
        assert bind(client, auth(client, "vr_allowed")).status_code == 200
        status = client.get("/api/admin/vrchat/status", headers=admin).json()
        assert status["bound"] >= 1
        # 管理端状态不含任何用户社交数据。
        assert set(status.keys()) == {"enabled", "allow_new_links", "bound", "unlinked"}
