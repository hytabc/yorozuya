"""VRChat 身份：简介验证码、真实资料快照、披露裁剪与后台黑名单。"""
from datetime import datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import trust
from app.database import get_db
from app.main import app

import test_api as api_tests
from test_api import auth, create_task

PROFILE = {
    "id": "usr_11111111-1111-1111-1111-111111111111",
    "displayName": "ColdRain",
    "bio": "",
    "tags": ["system_trust_trusted"],
    "date_joined": "2020-01-01T00:00:00.000Z",
    "last_platform": "standalonewindows",
}


def setup_function():
    api_tests.setup_function()
    app.dependency_overrides[get_db] = api_tests.override_db
    trust._reset_bot_session()


def use_profile(monkeypatch, **overrides):
    profile = {**PROFILE, **overrides}
    monkeypatch.setattr(trust, "fetch_profile", lambda _user_id: dict(profile))
    return profile


def start(client, headers, profile_id=PROFILE["id"]):
    response = client.post(
        "/api/vrchat/link/start", headers=headers, json={"profile": profile_id}
    )
    assert response.status_code == 200, response.text
    return response.json()


def verify(client, headers, profile, started):
    profile["bio"] = f"欢迎来玩 {started['challenge']['text']}"
    response = client.post("/api/vrchat/link/check", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def admin_headers(client):
    login = client.post(
        "/api/auth/login", json={"username": "admin", "password": "Admin123!"}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def test_bio_challenge_verifies_and_publishes_real_fields(monkeypatch):
    profile = use_profile(monkeypatch)
    with TestClient(app) as client:
        alice = auth(client, "vrchat_alice")
        bob = auth(client, "vrchat_bob")
        uid = client.get("/api/auth/me", headers=alice).json()["id"]

        started = start(client, alice)
        assert started["status"] == "pending" and started["bound"] is True
        code = started["challenge"]["code"]
        assert code.startswith("vrcverify")
        assert started["challenge"]["text"] == f"【万事屋 VRChat 验证 - {code}】"

        # 没写码时失败
        failed = client.post("/api/vrchat/link/check", headers=alice)
        assert failed.status_code == 409
        assert "验证码" in failed.json()["detail"]

        data = verify(client, alice, profile, started)
        assert data["status"] == "verified" and data["verified"] is True
        assert data["trust_rank"] == "known_user" and data["trust_rank_label"] == "熟识用户"
        assert data["account_age_label"]
        assert data["platform"] == "standalonewindows"

        # 默认不披露：他人只能看到 bound / verified。
        public = client.get(f"/api/users/{uid}/trust", headers=bob).json()
        assert public["bound"] is True and public["verified"] is True
        assert "display_name" not in public
        assert "trust_rank" not in public
        assert "account_age_label" not in public
        assert "platform" not in public

        # 打开披露后他人可见。
        disclosed = client.patch(
            "/api/vrchat/disclosure",
            headers=alice,
            json={
                "identity": True,
                "trust_rank": True,
                "account_age": True,
                "platform": True,
            },
        )
        assert disclosed.status_code == 200, disclosed.text
        public = client.get(f"/api/users/{uid}/trust", headers=bob).json()
        assert public["display_name"] == "ColdRain"
        assert public["trust_rank"] == "known_user"
        assert public["account_age_label"]
        assert public["platform"] == "standalonewindows"

        # 游客也能读取已披露的信任摘要。
        guest = client.get(f"/api/users/{uid}/trust").json()
        assert guest["verified"] is True and guest["display_name"] == "ColdRain"


def test_bio_matching_accepts_old_tokens_and_zero_width(monkeypatch):
    profile = use_profile(monkeypatch)
    with TestClient(app) as client:
        alice = auth(client, "vrchat_bio_match")
        started = start(client, alice)
        code = started["challenge"]["code"]
        spaced = " \u200b".join(code)
        # 旧验证码在前、当前验证码在后，且当前码被空格/零宽字符拆开。
        profile["bio"] = f"旧的 vrcverify{'0' * 32} 新的 {spaced}"
        checked = client.post("/api/vrchat/link/check", headers=alice)
        assert checked.status_code == 200, checked.text
        assert checked.json()["verified"] is True


def test_refresh_downgrades_and_restores_when_bio_changes(monkeypatch):
    profile = use_profile(monkeypatch)
    with TestClient(app) as client:
        alice = auth(client, "vrchat_refresh")
        started = start(client, alice)
        verify(client, alice, profile, started)

        profile["bio"] = "简介改掉了，没有验证码"
        refreshed = client.post("/api/vrchat/refresh", headers=alice)
        assert refreshed.status_code == 200, refreshed.text
        body = refreshed.json()
        assert body["status"] == "unverified" and body["verified"] is False
        assert body["last_verified_at"] is not None

        profile["bio"] = f"又写回来了 {started['challenge']['text']}"
        restored = client.post("/api/vrchat/refresh", headers=alice)
        assert restored.status_code == 200
        assert restored.json()["verified"] is True


def test_social_snapshot_and_manual_worlds(monkeypatch):
    profile = use_profile(monkeypatch)
    social = {
        PROFILE["id"]: {
            "groups": [{"id": "grp_a", "name": "砂糖社", "short_code": "SUGAR"}],
            "mutual_friends": 3,
            "home_world": {"id": "wrld_1", "name": "万事屋"},
        }
    }
    monkeypatch.setattr(
        trust,
        "fetch_social",
        lambda user_id, profile=None: social.get(user_id, {}),
    )
    with TestClient(app) as client:
        alice = auth(client, "vrchat_social")
        bob = auth(client, "vrchat_social_viewer")
        uid = client.get("/api/auth/me", headers=alice).json()["id"]
        started = start(client, alice)
        data = verify(client, alice, profile, started)
        assert data["trust_rank_color"] == "#FF7B42"
        assert data["mutual_friends"] == 3
        assert data["group_count"] == 1
        assert data["home_world"]["name"] == "万事屋"
        assert [world["name"] for world in data["worlds"]] == ["万事屋"]

        saved = client.patch(
            "/api/vrchat/worlds",
            headers=alice,
            json={"worlds": ["世界A", "世界B", "世界C"]},
        )
        assert saved.status_code == 200, saved.text
        body = saved.json()
        assert body["manual_worlds"] == ["世界A", "世界B", "世界C"]
        assert [world["name"] for world in body["worlds"]] == ["万事屋", "世界A", "世界B"]

        client.patch(
            "/api/vrchat/disclosure",
            headers=alice,
            json={"common_friends": True, "worlds": True},
        )
        public = client.get(f"/api/users/{uid}/trust", headers=bob).json()
        assert public["common_friends"] == 3
        assert public["common_friends_scope"] == "site_bot"
        assert [world["name"] for world in public["worlds"]] == ["万事屋", "世界A", "世界B"]


def test_common_groups_requires_both_sides(monkeypatch):
    alice_vrc = "usr_aaaaaaaa-1111-1111-1111-111111111111"
    bob_vrc = "usr_bbbbbbbb-2222-2222-2222-222222222222"
    profiles = {
        alice_vrc: {**PROFILE, "id": alice_vrc, "bio": ""},
        bob_vrc: {**PROFILE, "id": bob_vrc, "bio": ""},
    }
    socials = {
        alice_vrc: {
            "groups": [
                {"id": "grp_shared", "name": "共同社群", "short_code": "SHARED"},
                {"id": "grp_alice", "name": "Alice 社群", "short_code": "A"},
            ],
            "mutual_friends": 1,
            "home_world": None,
        },
        bob_vrc: {
            "groups": [
                {"id": "grp_shared", "name": "共同社群", "short_code": "SHARED"},
                {"id": "grp_bob", "name": "Bob 社群", "short_code": "B"},
            ],
            "mutual_friends": 2,
            "home_world": None,
        },
    }
    monkeypatch.setattr(trust, "fetch_profile", lambda user_id: dict(profiles[user_id]))
    monkeypatch.setattr(
        trust, "fetch_social", lambda user_id, profile=None: socials.get(user_id, {})
    )
    with TestClient(app) as client:
        alice = auth(client, "vrchat_groups_alice")
        bob = auth(client, "vrchat_groups_bob")
        alice_uid = client.get("/api/auth/me", headers=alice).json()["id"]

        alice_started = start(client, alice, alice_vrc)
        profiles[alice_vrc]["bio"] = f"欢迎 {alice_started['challenge']['text']}"
        assert client.post("/api/vrchat/link/check", headers=alice).status_code == 200
        bob_started = start(client, bob, bob_vrc)
        profiles[bob_vrc]["bio"] = f"欢迎 {bob_started['challenge']['text']}"
        assert client.post("/api/vrchat/link/check", headers=bob).status_code == 200

        # 双方默认关闭：不返回共同社群。
        public = client.get(f"/api/users/{alice_uid}/trust", headers=bob).json()
        assert "common_groups" not in public

        # 只有目标开启：仍不返回。
        client.patch("/api/vrchat/disclosure", headers=alice, json={"common_groups": True})
        public = client.get(f"/api/users/{alice_uid}/trust", headers=bob).json()
        assert "common_groups" not in public

        # 双方都开启：返回真实交集。
        client.patch("/api/vrchat/disclosure", headers=bob, json={"common_groups": True})
        public = client.get(f"/api/users/{alice_uid}/trust", headers=bob).json()
        assert public["common_groups_count"] == 1
        assert public["common_groups"][0]["name"] == "共同社群"

        # 游客看不到共同社群。
        guest = client.get(f"/api/users/{alice_uid}/trust").json()
        assert "common_groups" not in guest

        # 目标关闭后立即隐藏。
        client.patch("/api/vrchat/disclosure", headers=alice, json={"common_groups": False})
        public = client.get(f"/api/users/{alice_uid}/trust", headers=bob).json()
        assert "common_groups" not in public


def test_fetch_social_reads_groups_mutuals_and_home_world(monkeypatch):
    monkeypatch.setattr(trust.settings, "vrchat_bot_auth_cookie", "")
    monkeypatch.setattr(trust.settings, "vrchat_bot_username", "bot")
    monkeypatch.setattr(trust.settings, "vrchat_bot_password", "secret")
    monkeypatch.setattr(trust.settings, "vrchat_bot_totp_secret", "")
    clock = {"now": 0.0}
    monkeypatch.setattr(trust.time, "monotonic", lambda: clock["now"])
    monkeypatch.setattr(
        trust.time, "sleep", lambda seconds: clock.__setitem__("now", clock["now"] + seconds)
    )

    def handler(request):
        path = request.url.path
        if path.endswith("/auth/user"):
            return httpx.Response(200, json={"id": "usr_bot"})
        if path.endswith("/users/usr_target/groups"):
            return httpx.Response(
                200,
                json=[
                    {
                        "groupId": "grp_public",
                        "name": "公开社群",
                        "shortCode": "PUB",
                        "privacy": "default",
                    },
                    {
                        "groupId": "grp_private",
                        "name": "私密社群",
                        "shortCode": "PRIV",
                        "privacy": "private",
                    },
                ],
            )
        if path.endswith("/users/usr_target/mutuals"):
            return httpx.Response(200, json={"friends": 4, "groups": 1})
        if path.endswith("/worlds/wrld_home"):
            return httpx.Response(200, json={"id": "wrld_home", "name": "常驻世界"})
        return httpx.Response(404)

    monkeypatch.setattr(
        trust,
        "_new_http_client",
        lambda: httpx.Client(
            transport=httpx.MockTransport(handler), headers={"User-Agent": "test"}
        ),
    )
    trust._reset_bot_session()
    social = trust.fetch_social("usr_target", {"homeLocation": "wrld_home:123~private"})
    assert social["groups"] == [
        {"id": "grp_public", "name": "公开社群", "short_code": "PUB"}
    ]
    assert social["mutual_friends"] == 4
    assert social["home_world"] == {"id": "wrld_home", "name": "常驻世界"}


def test_anonymous_task_trust_is_cropped(monkeypatch):
    use_profile(monkeypatch)
    with TestClient(app) as client:
        alice = auth(client, "vrchat_anon")
        bob = auth(client, "vrchat_anon_viewer")
        task = create_task(client, alice, required=1, title="匿名信任裁剪测试")
        with api_tests.TestingSession() as db:
            db.execute(
                text("UPDATE tasks SET is_anonymous = 1 WHERE id = :id"),
                {"id": task["id"]},
            )
            db.commit()

        stranger = client.get(f"/api/tasks/{task['id']}/trust", headers=bob)
        assert stranger.status_code == 200
        assert stranger.json() == {"anonymous": True, "publisher": None, "members": []}

        # 委托人本人仍能看到自己的信任摘要。
        own = client.get(f"/api/tasks/{task['id']}/trust", headers=alice).json()
        assert own["anonymous"] is True and own["publisher"]["bound"] is False


def test_admin_can_lookup_unbind_and_ban(monkeypatch):
    profile = use_profile(monkeypatch)
    monkeypatch.setattr(trust.settings, "vrchat_bot_auth_cookie", "")
    monkeypatch.setattr(trust.settings, "vrchat_bot_username", "")
    monkeypatch.setattr(trust.settings, "vrchat_bot_password", "")
    with TestClient(app) as client:
        alice = auth(client, "vrchat_admin_target")
        bob = auth(client, "vrchat_admin_other")
        admin = admin_headers(client)
        started = start(client, alice)
        verify(client, alice, profile, started)

        status = client.get("/api/admin/vrchat/status", headers=admin).json()
        assert status["verified"] == 1
        assert status["bot_configured"] is False  # 测试里走 mock，未配置真实 cookie

        lookup = client.get(
            "/api/admin/vrchat/accounts",
            headers=admin,
            params={"vrchat_user_id": PROFILE["id"]},
        ).json()
        assert len(lookup["bindings"]) == 1
        assert lookup["bindings"][0]["verified"] is True
        assert lookup["banned"] is False

        unbound = client.post(
            f"/api/admin/vrchat/accounts/{PROFILE['id']}/unbind", headers=admin
        )
        assert unbound.status_code == 200 and unbound.json()["unbound"] == 1
        assert client.get("/api/vrchat/status", headers=alice).json()["bound"] is False

        # 重新验证后拉黑，其他账号不能再绑定同一 VRChat ID。
        started = start(client, alice)
        verify(client, alice, profile, started)
        banned = client.post(
            f"/api/admin/vrchat/accounts/{PROFILE['id']}/ban",
            headers=admin,
            json={"note": "冒用身份"},
        )
        assert banned.status_code == 200 and banned.json()["banned"] is True
        assert client.get("/api/vrchat/status", headers=alice).json()["status"] == "unlinked"

        blocked = client.post(
            "/api/vrchat/link/start",
            headers=bob,
            json={"profile": PROFILE["id"]},
        )
        assert blocked.status_code == 403

        unbanned = client.delete(
            f"/api/admin/vrchat/accounts/{PROFILE['id']}/ban", headers=admin
        )
        assert unbanned.status_code == 200 and unbanned.json()["banned"] is False


def test_bot_unavailable_fails_closed(monkeypatch):
    def unavailable(_user_id):
        raise trust.VRChatError(503, "VRChat 暂时不可用")

    monkeypatch.setattr(trust, "fetch_profile", unavailable)
    with TestClient(app) as client:
        alice = auth(client, "vrchat_bot_down")
        response = client.post(
            "/api/vrchat/link/start", headers=alice, json={"profile": PROFILE["id"]}
        )
        assert response.status_code == 503
        assert client.get("/api/vrchat/status", headers=alice).json()["bound"] is False


def test_challenge_expiry_and_failure_cooldown(monkeypatch):
    use_profile(monkeypatch)
    with TestClient(app) as client:
        alice = auth(client, "vrchat_expiry")
        started = start(client, alice)
        with api_tests.TestingSession() as db:
            db.execute(
                text("UPDATE vrchat_identities SET challenge_expires_at = :past WHERE user_id = (SELECT id FROM users WHERE username = 'vrchat_expiry')"),
                {"past": datetime.utcnow() - timedelta(minutes=1)},
            )
            db.commit()
        expired = client.post("/api/vrchat/link/check", headers=alice)
        assert expired.status_code == 409
        assert "过期" in expired.json()["detail"]

        start(client, alice)
        for _ in range(5):
            failed = client.post("/api/vrchat/link/check", headers=alice)
            assert failed.status_code == 409
        locked = client.post("/api/vrchat/link/check", headers=alice)
        assert locked.status_code == 429


def test_same_profile_and_invalid_inputs(monkeypatch):
    profile = use_profile(monkeypatch)
    with TestClient(app) as client:
        alice = auth(client, "vrchat_unique_a")
        bob = auth(client, "vrchat_unique_b")
        started = start(client, alice)
        verify(client, alice, profile, started)

        taken = client.post(
            "/api/vrchat/link/start", headers=bob, json={"profile": PROFILE["id"]}
        )
        assert taken.status_code == 409

        assert client.post(
            "/api/vrchat/link/start", headers=bob, json={"profile": "http://vrchat.com/home/user/usr_abc"}
        ).status_code == 422
        assert client.post(
            "/api/vrchat/link/start", headers=bob, json={"profile": "https://example.com/usr_abc"}
        ).status_code == 422
        assert client.post(
            "/api/vrchat/link/start", headers=bob, json={"profile": "not-a-vrchat-id"}
        ).status_code == 422


def test_disabled_and_allow_new_links(monkeypatch):
    use_profile(monkeypatch)
    with TestClient(app) as client:
        alice = auth(client, "vrchat_switch")
        admin = admin_headers(client)

        off = client.patch(
            "/api/admin/vrchat/config", headers=admin, json={"enabled": False}
        )
        assert off.status_code == 200
        assert client.post(
            "/api/vrchat/link/start", headers=alice, json={"profile": PROFILE["id"]}
        ).status_code == 503

        paused = client.patch(
            "/api/admin/vrchat/config",
            headers=admin,
            json={"enabled": True, "allow_new_links": False},
        )
        assert paused.status_code == 200
        assert client.post(
            "/api/vrchat/link/start", headers=alice, json={"profile": PROFILE["id"]}
        ).status_code == 503

        client.patch(
            "/api/admin/vrchat/config",
            headers=admin,
            json={"enabled": True, "allow_new_links": True},
        )
        assert start(client, alice)["status"] == "pending"


def test_admin_endpoints_require_roles(monkeypatch):
    use_profile(monkeypatch)
    with TestClient(app) as client:
        alice = auth(client, "vrchat_plain")
        assert client.get("/api/admin/vrchat/status", headers=alice).status_code == 403
        assert client.patch(
            "/api/admin/vrchat/config", headers=alice, json={"enabled": True}
        ).status_code == 403


def test_bot_auth_mode_prefers_cookie_then_password(monkeypatch):
    monkeypatch.setattr(trust.settings, "vrchat_bot_auth_cookie", "auth=cookie")
    monkeypatch.setattr(trust.settings, "vrchat_bot_username", "bot")
    monkeypatch.setattr(trust.settings, "vrchat_bot_password", "secret")
    assert trust.bot_auth_mode() == "cookie"
    assert trust.bot_configured() is True

    monkeypatch.setattr(trust.settings, "vrchat_bot_auth_cookie", "")
    assert trust.bot_auth_mode() == "password"

    monkeypatch.setattr(trust.settings, "vrchat_bot_password", "")
    assert trust.bot_auth_mode() is None
    assert trust.bot_configured() is False


def test_totp_code_matches_rfc_vector(monkeypatch):
    monkeypatch.setattr(trust.time, "time", lambda: 59)
    assert trust._totp_code("GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ") == "287082"


def test_password_bot_login_with_totp_and_retry(monkeypatch):
    monkeypatch.setattr(trust.settings, "vrchat_bot_auth_cookie", "")
    monkeypatch.setattr(trust.settings, "vrchat_bot_username", "bot@example.com")
    monkeypatch.setattr(trust.settings, "vrchat_bot_password", "secret")
    monkeypatch.setattr(trust.settings, "vrchat_bot_totp_secret", "JBSWY3DPEHPK3PXP")
    calls = []

    def handler(request):
        calls.append(request)
        path = request.url.path
        if path.endswith("/auth/user"):
            auth_calls = [item for item in calls if item.url.path.endswith("/auth/user")]
            if len(auth_calls) == 1:
                assert request.headers.get("authorization", "").startswith("Basic ")
                return httpx.Response(
                    200,
                    json={"requiresTwoFactorAuth": ["totp"]},
                    headers={"set-cookie": "auth=abc; Path=/"},
                )
            return httpx.Response(200, json={"id": "usr_bot"})
        if path.endswith("/auth/twofactorauth/totp/verify"):
            return httpx.Response(
                200,
                json={},
                headers={"set-cookie": "twoFactorAuth=def; Path=/"},
            )
        if path.endswith("/users/usr_target"):
            # 用户端点没有 bio；About Me 只在公开资料端点返回。
            return httpx.Response(
                200,
                json={
                    "id": "usr_target",
                    "displayName": "ColdRain",
                    "tags": ["system_trust_known"],
                    "date_joined": "2020-01-01T00:00:00.000Z",
                    "last_platform": "standalonewindows",
                },
            )
        if path.endswith("/profile/usr_target"):
            return httpx.Response(
                200,
                json={
                    "id": "usr_target",
                    "displayName": "ColdRain",
                    "bio": "简介里的验证码",
                    "trustTags": ["system_trust_trusted"],
                },
            )
        return httpx.Response(404)

    def client_factory():
        return httpx.Client(
            transport=httpx.MockTransport(handler),
            headers={"User-Agent": "test"},
        )

    monkeypatch.setattr(trust, "_new_http_client", client_factory)
    trust._reset_bot_session()
    profile = trust.fetch_profile("usr_target")
    assert profile["id"] == "usr_target"
    assert profile["bio"] == "简介里的验证码"
    assert profile["date_joined"] == "2020-01-01T00:00:00.000Z"
    assert profile["last_platform"] == "standalonewindows"
    assert profile["trustTags"] == ["system_trust_trusted"]
    assert any("twofactorauth" in item.url.path for item in calls)
    assert any(item.url.path.endswith("/profile/usr_target") for item in calls)


def test_public_profile_forbidden_reports_visibility(monkeypatch):
    monkeypatch.setattr(trust.settings, "vrchat_bot_auth_cookie", "")
    monkeypatch.setattr(trust.settings, "vrchat_bot_username", "bot")
    monkeypatch.setattr(trust.settings, "vrchat_bot_password", "secret")
    monkeypatch.setattr(trust.settings, "vrchat_bot_totp_secret", "")

    def handler(request):
        path = request.url.path
        if path.endswith("/auth/user"):
            return httpx.Response(200, json={"id": "usr_bot"})
        if path.endswith("/users/usr_target"):
            return httpx.Response(
                200, json={"id": "usr_target", "displayName": "ColdRain"}
            )
        if path.endswith("/profile/usr_target"):
            return httpx.Response(403)
        return httpx.Response(404)

    def client_factory():
        return httpx.Client(
            transport=httpx.MockTransport(handler), headers={"User-Agent": "test"}
        )

    monkeypatch.setattr(trust, "_new_http_client", client_factory)
    trust._reset_bot_session()
    with pytest.raises(trust.VRChatError) as error:
        trust.fetch_profile("usr_target")
    assert error.value.status_code == 503
    assert "公开资料" in error.value.detail
