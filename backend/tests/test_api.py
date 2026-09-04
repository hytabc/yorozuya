from datetime import datetime, timedelta
from errno import ENOSPC
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.config import settings
from app.main import app
from app.models import User
from app.security import hash_password


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def override_db():
    with TestingSession() as db:
        yield db


app.dependency_overrides[get_db] = override_db


def setup_function():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestingSession() as db:
        db.add(User(username="admin", nickname="管理员", password_hash=hash_password("Admin123!"), is_admin=True))
        db.commit()


def auth(client, username, password="Password123!", role="user"):
    response = client.post(
        "/api/auth/register",
        json={"username": username, "password": password, "nickname": f"用户{username}"},
    )
    assert response.status_code == 201, response.text
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    if role == "volunteer":
        promote(client, headers)
    return headers


def promote(client, user_headers):
    """管理员把某用户升级为志愿者（测试用，普通用户默认不能接取委托）。"""
    user_id = client.get("/api/auth/me", headers=user_headers).json()["id"]
    admin_login = client.post("/api/auth/login", json={"username": "admin", "password": "Admin123!"})
    admin = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}
    r = client.patch(f"/api/admin/users/{user_id}/role", headers=admin, json={"role": "volunteer"})
    assert r.status_code == 200, r.text
    return user_headers


def set_qq(client, headers, qq):
    me = client.get("/api/auth/me", headers=headers)
    nickname = me.json()["nickname"]
    r = client.patch("/api/users/me", headers=headers, json={"nickname": nickname, "qq": qq, "bio": None})
    assert r.status_code == 200, r.text
    return r.json()


TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0dIDAT\x08\xd7c\xf8\xcf\xc0\xf0\x1f\x00\x05\x00\x01\xff\x89\x99=\x1d\x00\x00\x00\x00IEND\xaeB`\x82"
)


def register_sugar_profile(client, headers, about="喜欢在周末散步"):
    response = client.post(
        "/api/sugar/profile",
        headers=headers,
        data={"about": about},
        files=[("photos", ("portrait.png", TINY_PNG, "image/png"))],
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_task(client, headers, password="接取密码123", required=None, title="帮忙整理一份资料", expiry_days=2):
    me = client.get("/api/auth/me", headers=headers).json()
    if not me.get("qq"):
        set_qq(client, headers, "1000000000")
    payload = {
        "title": title,
        "description": "需要将十条记录整理成清晰的表格文件",
        "category": "学习",
        "reward": "30 元",
        "accept_password": password,
        "expires_in_days": expiry_days,
    }
    if required is not None:
        payload["required_takers"] = required
    response = client.post("/api/tasks", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def member_ids(task):
    return [m["user"]["id"] for m in task["members"]]


def test_create_task_requires_contact():
    with TestClient(app) as client:
        publisher = auth(client, "no_contact_pub")
        payload = {
            "title": "没有联系方式的委托",
            "description": "发布者尚未填写 QQ，不应允许发布",
            "category": "其他",
            "pay_type": "free",
            "accept_password": "pw-no-contact",
            "required_takers": 1,
            "expires_in_days": 1,
        }
        rejected = client.post("/api/tasks", headers=publisher, json=payload)
        assert rejected.status_code == 422
        assert "联系方式" in rejected.json()["detail"]

        # 填写 QQ 后即可正常发布
        set_qq(client, publisher, "1000000001")
        created = create_task(client, publisher, password="pw-no-contact", required=1)
        assert created["id"] > 0


def test_accept_fills_up_until_auto_start():
    with TestClient(app) as client:
        pub = auth(client, "pub")
        a = auth(client, "taker_a", role="volunteer")
        b = auth(client, "taker_b", role="volunteer")
        c = auth(client, "taker_c", role="volunteer")
        d = auth(client, "taker_d", role="volunteer")

        task = create_task(client, pub, password="pw-abc-1", required=3)
        tid = task["id"]
        assert task["required_takers"] == 3
        assert task["status"] == "published"
        assert task["members"] == []

        # 委托人不能接取自己的委托
        own = client.post(f"/api/tasks/{tid}/accept", headers=pub, json={"password": "pw-abc-1"})
        assert own.status_code == 400

        # 错误密码不可接取
        wrong = client.post(f"/api/tasks/{tid}/accept", headers=a, json={"password": "nope"})
        assert wrong.status_code == 403

        # 第一、二人加入，仍未开始
        after_a = client.post(f"/api/tasks/{tid}/accept", headers=a, json={"password": "pw-abc-1"}).json()
        assert after_a["status"] == "published"
        assert len(after_a["members"]) == 1
        after_b = client.post(f"/api/tasks/{tid}/accept", headers=b, json={"password": "pw-abc-1"}).json()
        assert after_b["status"] == "published"
        assert len(after_b["members"]) == 2

        # 第三人加入，人数足够 → 自动开始
        after_c = client.post(f"/api/tasks/{tid}/accept", headers=c, json={"password": "pw-abc-1"}).json()
        assert after_c["status"] == "accepted"
        assert after_c["started_at"] is not None
        assert len(after_c["members"]) == 3

        # 重复加入被拒绝
        dup = client.post(f"/api/tasks/{tid}/accept", headers=c, json={"password": "pw-abc-1"})
        assert dup.status_code == 409

        # 已开始，第四人无法加入
        extra = client.post(f"/api/tasks/{tid}/accept", headers=d, json={"password": "pw-abc-1"})
        assert extra.status_code == 409

        # 发布人可看到成员 QQ
        set_qq(client, a, "1111111111")
        listed = client.get(f"/api/tasks/{tid}", headers=pub).json()
        assert len(listed["members"]) == 3
        assert any(m["qq"] == "1111111111" for m in listed["members"])


def test_publisher_manual_start_and_leave():
    with TestClient(app) as client:
        pub = auth(client, "pub2")
        a = auth(client, "taker_a2", role="volunteer")
        b = auth(client, "taker_b2", role="volunteer")

        task = create_task(client, pub, password="pw-manual-1", required=5)
        tid = task["id"]

        # 无成员不能开始
        empty_start = client.post(f"/api/tasks/{tid}/start", headers=pub)
        assert empty_start.status_code == 409

        a_member = client.post(f"/api/tasks/{tid}/accept", headers=a, json={"password": "pw-manual-1"}).json()
        assert a_member["status"] == "published"

        # 人数不足也可由委托人手动开始
        started = client.post(f"/api/tasks/{tid}/start", headers=pub)
        assert started.status_code == 200
        assert started.json()["status"] == "accepted"
        assert started.json()["started_at"] is not None

        # 开始后不能再接取、不能退出
        b_add = client.post(f"/api/tasks/{tid}/accept", headers=b, json={"password": "pw-manual-1"})
        assert b_add.status_code == 409
        leave = client.post(f"/api/tasks/{tid}/leave", headers=a)
        assert leave.status_code == 409

        # 只有委托人能开始
        other_start = client.post(f"/api/tasks/{tid}/start", headers=a)
        assert other_start.status_code == 403


def test_leave_before_start():
    with TestClient(app) as client:
        pub = auth(client, "pub3")
        a = auth(client, "taker_a3", role="volunteer")
        task = create_task(client, pub, password="pw-leave-1", required=2)
        tid = task["id"]
        client.post(f"/api/tasks/{tid}/accept", headers=a, json={"password": "pw-leave-1"})

        # 未开始时接单人可退出
        left = client.post(f"/api/tasks/{tid}/leave", headers=a)
        assert left.status_code == 200
        assert left.json()["members"] == []

        # 非成员不能退出
        stranger = auth(client, "stranger3")
        deny = client.post(f"/api/tasks/{tid}/leave", headers=stranger)
        assert deny.status_code == 403


def test_all_members_and_publisher_must_confirm():
    with TestClient(app) as client:
        pub = auth(client, "pub4")
        a = auth(client, "taker_a4", role="volunteer")
        b = auth(client, "taker_b4", role="volunteer")
        stranger = auth(client, "stranger4")

        task = create_task(client, pub, password="pw-confirm-1", required=2)
        tid = task["id"]
        client.post(f"/api/tasks/{tid}/accept", headers=a, json={"password": "pw-confirm-1"})
        accepted = client.post(f"/api/tasks/{tid}/accept", headers=b, json={"password": "pw-confirm-1"}).json()
        assert accepted["status"] == "accepted"

        # 无关人员不能确认
        deny = client.post(f"/api/tasks/{tid}/confirm", headers=stranger)
        assert deny.status_code == 403

        # 接单人 a 先确认 → awaiting
        c1 = client.post(f"/api/tasks/{tid}/confirm", headers=a).json()
        assert c1["status"] == "awaiting"
        assert c1["members"][0]["confirmed_at"] is not None
        # a 重复确认被拒
        dup = client.post(f"/api/tasks/{tid}/confirm", headers=a)
        assert dup.status_code == 409

        # 还差委托人 + b
        still = client.get(f"/api/tasks/{tid}", headers=pub).json()
        assert still["status"] == "awaiting" and still["publisher_confirmed_at"] is None

        # 委托人确认，仍差 b
        c2 = client.post(f"/api/tasks/{tid}/confirm", headers=pub).json()
        assert c2["status"] == "awaiting"

        # b 最后确认 → completed
        c3 = client.post(f"/api/tasks/{tid}/confirm", headers=b).json()
        assert c3["status"] == "completed"
        assert c3["completed_at"] is not None
        assert c3["publisher_confirmed_at"] is not None
        assert all(m["confirmed_at"] is not None for m in c3["members"])


def test_unlimited_task_needs_manual_start_and_publisher_confirm_only():
    with TestClient(app) as client:
        pub = auth(client, "pub5")
        a = auth(client, "taker_a5", role="volunteer")
        # required_takers 省略 = 不限
        task = create_task(client, pub, password="pw-unlimited-1", required=None)
        tid = task["id"]
        assert task["required_takers"] is None

        joined = client.post(f"/api/tasks/{tid}/accept", headers=a, json={"password": "pw-unlimited-1"}).json()
        # 不限人数：加入后不会自动开始
        assert joined["status"] == "published"

        # 委托人手动开始
        started = client.post(f"/api/tasks/{tid}/start", headers=pub).json()
        assert started["status"] == "accepted"

        # 接单人 + 委托人都确认后完成
        a_ok = client.post(f"/api/tasks/{tid}/confirm", headers=a).json()
        assert a_ok["status"] == "awaiting"
        final = client.post(f"/api/tasks/{tid}/confirm", headers=pub).json()
        assert final["status"] == "completed"


def test_contacts_and_cancel():
    with TestClient(app) as client:
        pub = auth(client, "pub6")
        a = auth(client, "taker_a6", role="volunteer")
        guest = auth(client, "guest6")
        set_qq(client, pub, "1234567890")
        set_qq(client, a, "2222222222")

        task = create_task(client, pub, password="pw-contact-1", required=1)
        tid = task["id"]

        # 匿名看不到联系方式
        anon = client.get(f"/api/tasks/{tid}").json()
        assert anon["contact_qq"] is None

        # 登录的其他用户可看到委托人 QQ（洽谈用），但看不到成员 QQ
        viewed = client.get(f"/api/tasks/{tid}", headers=guest).json()
        assert viewed["contact_qq"] == "1234567890"

        # 委托人可看到接单人的 QQ
        joined = client.post(f"/api/tasks/{tid}/accept", headers=a, json={"password": "pw-contact-1"}).json()
        assert joined["status"] == "accepted"
        as_pub = client.get(f"/api/tasks/{tid}", headers=pub).json()
        assert as_pub["members"][0]["qq"] == "2222222222"
        assert as_pub["contact_qq"] is None

        # 接单人可看到委托人 QQ
        as_taker = client.get(f"/api/tasks/{tid}", headers=a).json()
        assert as_taker["contact_qq"] == "1234567890"

        # 未开始前委托人可取消
        task2 = create_task(client, pub, password="pw-cancel-1", required=2)
        tid2 = task2["id"]
        cancelled = client.post(f"/api/tasks/{tid2}/cancel", headers=pub)
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"


def test_reset_password_before_start():
    with TestClient(app) as client:
        pub = auth(client, "pub7")
        a = auth(client, "taker_a7", role="volunteer")
        task = create_task(client, pub, password="old-pw-1234", required=1)
        tid = task["id"]

        reset = client.patch(f"/api/tasks/{tid}/password", headers=pub, json={"password": "new-pw-5678"})
        assert reset.status_code == 200
        old = client.post(f"/api/tasks/{tid}/accept", headers=a, json={"password": "old-pw-1234"})
        assert old.status_code == 403
        ok = client.post(f"/api/tasks/{tid}/accept", headers=a, json={"password": "new-pw-5678"})
        assert ok.status_code == 200


def test_profile_visibility_rules():
    with TestClient(app) as client:
        pub = auth(client, "pro_pub")
        taker = auth(client, "pro_taker", role="volunteer")
        stranger = auth(client, "pro_stranger")
        set_qq(client, pub, "8888888888")

        pub_id = client.get("/api/auth/me", headers=pub).json()["id"]
        taker_id = client.get("/api/auth/me", headers=taker).json()["id"]

        # 未登录不可访问
        assert client.get(f"/api/users/{pub_id}").status_code == 401

        # 陌生人只能看到公开资料，看不到 QQ
        as_stranger = client.get(f"/api/users/{pub_id}", headers=stranger).json()
        assert as_stranger["qq"] is None
        assert as_stranger["nickname"] == "用户pro_pub"

        # 发布人有招募中的公开委托：登录用户可见其 QQ（洽谈用）
        task = create_task(client, pub, password="pw-profile-1", required=2)
        tid = task["id"]
        open_view = client.get(f"/api/users/{pub_id}", headers=taker).json()
        assert open_view["qq"] == "8888888888"

        # 同为该委托成员后可见
        client.post(f"/api/tasks/{tid}/accept", headers=taker, json={"password": "pw-profile-1"})
        member_view = client.get(f"/api/users/{pub_id}", headers=taker).json()
        assert member_view["qq"] == "8888888888"

        # 委托人可看到成员资料（成员未填 QQ → null）
        as_pub = client.get(f"/api/users/{taker_id}", headers=pub).json()
        assert as_pub["qq"] is None
        assert as_pub["bio"] is None

        # 不存在的用户 404
        assert client.get("/api/users/999999", headers=taker).status_code == 404


def test_sugar_club_profiles_pairing_and_ranking(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "sugar_upload_dir", str(tmp_path / "uploads"))
    with TestClient(app) as client:
        alice = auth(client, "sugar_alice")
        bob = auth(client, "sugar_bob")
        set_qq(client, alice, "1111111111")
        set_qq(client, bob, "2222222222")
        alice_profile = register_sugar_profile(client, alice, "喜欢摄影和散步")
        bob_profile = register_sugar_profile(client, bob, "喜欢展览和咖啡")
        alice_id = alice_profile["user"]["id"]
        bob_id = bob_profile["user"]["id"]

        # 公共卡片不返回 QQ，详情只在当前查看人与档案主人之间提供联系方式。
        cards = client.get("/api/sugar/profiles", headers=alice).json()
        assert {card["user"]["id"] for card in cards} == {alice_id, bob_id}
        assert all("qq" not in card for card in cards)
        detail = client.get(f"/api/sugar/profiles/{bob_id}", headers=alice).json()
        assert detail["qq"] == "2222222222"
        assert detail["photos"][0]["image_url"].startswith("/uploads/sugar/")
        assert list((tmp_path / "uploads" / "sugar").iterdir())

        # 第一次确认进入待确认；第二人确认后才开始计时。
        pending = client.post(f"/api/sugar/pairs/{bob_id}/confirm", headers=alice)
        assert pending.status_code == 201, pending.text
        assert pending.json()["status"] == "pending"
        active = client.post(f"/api/sugar/pairs/{alice_id}/confirm", headers=bob)
        assert active.status_code == 201, active.text
        assert active.json()["status"] == "active"
        pair_id = active.json()["id"]

        ended = client.post(f"/api/sugar/pairs/{pair_id}/end", headers=alice)
        assert ended.status_code == 200
        assert ended.json()["status"] == "ended"
        leaderboard = client.get("/api/sugar/pairs/top", headers=bob).json()
        assert leaderboard[0]["id"] == pair_id
        assert leaderboard[0]["status"] == "ended"


def test_feedback_flow():
    with TestClient(app) as client:
        user = auth(client, "fb_user")
        admin = {"Authorization": f"Bearer {client.post('/api/auth/login', json={'username': 'admin', 'password': 'Admin123!'}).json()['access_token']}"}

        # 登录用户提交反馈
        created = client.post(
            "/api/feedback",
            headers=user,
            json={"content": "建议增加深色模式，晚上看委托很刺眼", "page": "委托大厅"},
        )
        assert created.status_code == 201, created.text
        fb_id = created.json()["id"]
        assert created.json()["status"] == "pending"
        assert created.json()["user"] is not None

        # 游客未登录且无联系方式 → 422
        guest_no_contact = client.post("/api/feedback", json={"content": "游客想留言但是没有联系方式"})
        assert guest_no_contact.status_code == 422

        # 游客带联系方式可提交
        guest = client.post(
            "/api/feedback",
            json={"content": "游客留言，建议开个 Telegram 频道", "contact": "QQ 12345"},
        )
        assert guest.status_code == 201
        assert guest.json()["user"] is None
        assert guest.json()["contact"] == "QQ 12345"

        # 用户可查看自己的反馈
        mine = client.get("/api/feedback/mine", headers=user).json()
        assert len(mine) == 1 and mine[0]["id"] == fb_id

        # 普通用户不能访问管理反馈列表
        assert client.get("/api/admin/feedback", headers=user).status_code == 403

        # 管理员查看
        admin_list = client.get("/api/admin/feedback", headers=admin).json()
        assert len(admin_list) == 2

        # 管理员处理
        handled = client.patch(
            f"/api/admin/feedback/{fb_id}",
            headers=admin,
            json={"status": "handled", "reply": "已记录，深色模式已在规划中"},
        )
        assert handled.status_code == 200
        assert handled.json()["status"] == "handled"
        assert handled.json()["handled_at"] is not None

        # 用户端能看到处理结果
        after = client.get("/api/feedback/mine", headers=user).json()
        assert after[0]["reply"] == "已记录，深色模式已在规划中"


def test_expired_task_is_updated_when_listed():
    with TestClient(app) as client:
        publisher = auth(client, "expirer")
        with TestingSession() as db:
            user = db.query(User).filter_by(username="expirer").one()
            from app.models import Task

            db.add(
                Task(
                    title="已经过期的任务",
                    description="这是一个用于验证自动过期行为的任务",
                    category="其他",
                    publisher_id=user.id,
                    expires_at=datetime.utcnow() - timedelta(minutes=1),
                )
            )
            db.commit()
        # 大厅对普通用户仅展示招募中；过期委托通过“我的委托”验证自动过期。
        mine = client.get("/api/tasks/mine", headers=publisher).json()
        assert mine[0]["status"] == "expired"


def test_task_expiry_only_accepts_fixed_day_options():
    with TestClient(app) as client:
        publisher = auth(client, "expiry_options_publisher")
        for days in (1, 2, 3, 5, 10):
            before = datetime.utcnow()
            task = create_task(
                client,
                publisher,
                title=f"有效期 {days} 天的委托",
                expiry_days=days,
            )
            expires_at = datetime.fromisoformat(task["expires_at"].removesuffix("Z"))
            assert abs((expires_at - before).total_seconds() - days * 86400) < 2

        rejected = client.post(
            "/api/tasks",
            headers=publisher,
            json={
                "title": "非法有效期委托",
                "description": "这个委托使用了固定选项之外的有效期",
                "category": "其他",
                "expires_in_days": 4,
            },
        )
        assert rejected.status_code == 422


def test_list_tasks_without_status_filter():
    with TestClient(app) as client:
        publisher = auth(client, "list_publisher")
        created = create_task(client, publisher, title="Listable task", required=1)
        assert created["id"] > 0

        without_status = client.get("/api/tasks")
        assert without_status.status_code == 200
        assert [task["id"] for task in without_status.json()] == [created["id"]]

        empty_status = client.get("/api/tasks", params={"status": ""})
        assert empty_status.status_code == 200

        invalid_status = client.get("/api/tasks", params={"status": "unknown"})
        assert invalid_status.status_code == 422


def test_pay_type_create_and_filter():
    with TestClient(app) as client:
        publisher = auth(client, "pay_publisher")
        # 有偿（默认）
        paid = create_task(client, publisher, title="付费委托", required=1)
        paid_task_id = paid["id"]
        assert paid["pay_type"] == "paid"
        # 无偿
        free_resp = client.post(
            "/api/tasks",
            headers=publisher,
            json={
                "title": "无偿互助委托",
                "description": "需要有人帮忙翻译一段英文说明",
                "category": "学习",
                "pay_type": "free",
                "reward": None,
                "accept_password": "pw-free-1",
                "required_takers": 1,
                "expires_in_days": 2,
            },
        )
        assert free_resp.status_code == 201, free_resp.text
        free_task_id = free_resp.json()["id"]
        assert free_resp.json()["pay_type"] == "free"

        paid_list = client.get("/api/tasks", params={"pay_type": "paid"}).json()
        assert {task["id"] for task in paid_list} >= {paid_task_id}
        assert free_task_id not in {task["id"] for task in paid_list}

        free_list = client.get("/api/tasks", params={"pay_type": "free"}).json()
        assert {task["id"] for task in free_list} == {free_task_id}

        # 非法 pay_type 直接返回空
        weird = client.get("/api/tasks", params={"pay_type": "banana"}).json()
        assert all(task["pay_type"] in ("paid", "free") for task in weird)


def test_user_task_limit_and_admin_control():
    with TestClient(app) as client:
        publishers = [auth(client, f"limit_pub_{index}") for index in range(4)]
        taker = auth(client, "limited_taker", role="volunteer")
        stranger = auth(client, "limit_stranger")
        admin_login = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "Admin123!"},
        )
        admin = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}

        me = client.get("/api/auth/me", headers=taker)
        assert me.status_code == 200
        assert me.json()["max_concurrent_tasks"] == 2

        tasks = [
            create_task(client, publisher, password=f"limit-pw-{index}", required=5)
            for index, publisher in enumerate(publishers)
        ]
        for index in range(2):
            accepted = client.post(
                f"/api/tasks/{tasks[index]['id']}/accept",
                headers=taker,
                json={"password": f"limit-pw-{index}"},
            )
            assert accepted.status_code == 200

        over_limit = client.post(
            f"/api/tasks/{tasks[2]['id']}/accept",
            headers=taker,
            json={"password": "limit-pw-2"},
        )
        assert over_limit.status_code == 409
        assert "2 个" in over_limit.json()["detail"]

        denied = client.patch(
            f"/api/admin/users/{me.json()['id']}/task-limit",
            headers=stranger,
            json={"max_concurrent_tasks": 3},
        )
        assert denied.status_code == 403

        users = client.get("/api/admin/users", headers=admin)
        limited_user = next(user for user in users.json() if user["id"] == me.json()["id"])
        assert limited_user["active_task_count"] == 2
        assert limited_user["max_concurrent_tasks"] == 2

        updated = client.patch(
            f"/api/admin/users/{me.json()['id']}/task-limit",
            headers=admin,
            json={"max_concurrent_tasks": 3},
        )
        assert updated.status_code == 200
        assert updated.json()["max_concurrent_tasks"] == 3
        assert updated.json()["active_task_count"] == 2

        accepted_third = client.post(
            f"/api/tasks/{tasks[2]['id']}/accept",
            headers=taker,
            json={"password": "limit-pw-2"},
        )
        assert accepted_third.status_code == 200

        cancelled = client.post(
            f"/api/tasks/{tasks[0]['id']}/cancel",
            headers=publishers[0],
        )
        assert cancelled.status_code == 200
        # 发起取消后进入“取消确认中”，接单人同意后才会真正取消
        assert cancelled.json()["status"] == "cancelling"
        agreed = client.post(
            f"/api/tasks/{tasks[0]['id']}/confirm-cancel",
            headers=taker,
        )
        assert agreed.status_code == 200
        assert agreed.json()["status"] == "cancelled"

        accepted_after_cancel = client.post(
            f"/api/tasks/{tasks[3]['id']}/accept",
            headers=taker,
            json={"password": "limit-pw-3"},
        )
        assert accepted_after_cancel.status_code == 200


def test_admin_task_limit_validation():
    with TestClient(app) as client:
        taker = auth(client, "validation_taker")
        user_id = client.get("/api/auth/me", headers=taker).json()["id"]
        admin_login = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "Admin123!"},
        )
        admin = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}

        negative = client.patch(
            f"/api/admin/users/{user_id}/task-limit",
            headers=admin,
            json={"max_concurrent_tasks": -1},
        )
        too_large = client.patch(
            f"/api/admin/users/{user_id}/task-limit",
            headers=admin,
            json={"max_concurrent_tasks": 1000},
        )
        assert negative.status_code == 422
        assert too_large.status_code == 422


def test_mutual_cancel_flow_after_start():
    with TestClient(app) as client:
        pub = auth(client, "cancel_pub")
        a = auth(client, "cancel_a", role="volunteer")
        b = auth(client, "cancel_b", role="volunteer")

        task = create_task(client, pub, password="pw-cancel-2", required=2)
        tid = task["id"]
        client.post(f"/api/tasks/{tid}/accept", headers=a, json={"password": "pw-cancel-2"})
        started = client.post(f"/api/tasks/{tid}/accept", headers=b, json={"password": "pw-cancel-2"})
        assert started.status_code == 200 and started.json()["status"] == "accepted"

        # 接单人 a 发起取消 → 取消确认中，发起者自动算已同意
        req = client.post(f"/api/tasks/{tid}/cancel", headers=a)
        assert req.status_code == 200
        body = req.json()
        assert body["status"] == "cancelling"
        assert body["cancel_requested_by"] is not None
        a_member = next(m for m in body["members"] if m["user"]["nickname"] == "用户cancel_a")
        assert a_member["cancel_confirmed_at"] is not None

        # 接单人 b 尚未同意，重复发起取消被拒
        dup = client.post(f"/api/tasks/{tid}/cancel", headers=b)
        assert dup.status_code == 409

        # 无关用户不能确认
        stranger = auth(client, "cancel_stranger")
        deny = client.post(f"/api/tasks/{tid}/confirm-cancel", headers=stranger)
        assert deny.status_code == 403

        # b 同意 → 还差委托人
        b_ok = client.post(f"/api/tasks/{tid}/confirm-cancel", headers=b)
        assert b_ok.status_code == 200 and b_ok.json()["status"] == "cancelling"

        # 委托人同意 → 全员同意，最终取消
        final = client.post(f"/api/tasks/{tid}/confirm-cancel", headers=pub)
        assert final.status_code == 200
        assert final.json()["status"] == "cancelled"
        assert final.json()["cancelled_at"] is not None

        # 已取消后不能再确认/继续
        assert client.post(f"/api/tasks/{tid}/confirm-cancel", headers=pub).status_code == 409
        assert client.post(f"/api/tasks/{tid}/cancel-continue", headers=pub).status_code == 409


def test_cancel_continue_restores_task():
    with TestClient(app) as client:
        pub = auth(client, "cont_pub")
        a = auth(client, "cont_a", role="volunteer")
        task = create_task(client, pub, password="pw-cont-1", required=1)
        tid = task["id"]
        accepted = client.post(f"/api/tasks/{tid}/accept", headers=a, json={"password": "pw-cont-1"})
        assert accepted.json()["status"] == "accepted"

        # 委托人发起取消
        req = client.post(f"/api/tasks/{tid}/cancel", headers=pub)
        assert req.json()["status"] == "cancelling"

        # 接单人不同意 → 继续委托，恢复为处理中
        cont = client.post(f"/api/tasks/{tid}/cancel-continue", headers=a)
        assert cont.status_code == 200
        body = cont.json()
        assert body["status"] == "accepted"
        assert body["cancel_requested_by"] is None
        assert all(m["cancel_confirmed_at"] is None for m in body["members"])
        assert body["publisher_cancel_confirmed_at"] is None

        # 委托可继续正常结束
        a_ok = client.post(f"/api/tasks/{tid}/confirm", headers=a).json()
        assert a_ok["status"] == "awaiting"
        fin = client.post(f"/api/tasks/{tid}/confirm", headers=pub).json()
        assert fin["status"] == "completed"


def test_publisher_can_direct_cancel_when_no_member():
    with TestClient(app) as client:
        pub = auth(client, "direct_pub")
        task = create_task(client, pub, password="pw-direct-1", required=2)
        tid = task["id"]
        # 无人接取时委托人直接取消（无需确认对象）
        res = client.post(f"/api/tasks/{tid}/cancel", headers=pub)
        assert res.status_code == 200
        assert res.json()["status"] == "cancelled"
        # 接单阶段外人不能取消
        stranger = auth(client, "direct_stranger")
        task2 = create_task(client, pub, password="pw-direct-2", required=2)
        denied = client.post(f"/api/tasks/{task2['id']}/cancel", headers=stranger)
        assert denied.status_code == 403


def test_user_role_permissions():
    with TestClient(app) as client:
        pub = auth(client, "role_pub")
        regular = auth(client, "role_regular")
        admin_login = client.post("/api/auth/login", json={"username": "admin", "password": "Admin123!"})
        admin = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}
        regular_id = client.get("/api/auth/me", headers=regular).json()["id"]

        # 默认是普通用户
        me = client.get("/api/auth/me", headers=regular).json()
        assert me["role"] == "user"
        assert me["is_admin"] is False

        # 普通用户可以发布，但不能接取
        task = create_task(client, pub, password="pw-role-1", required=1)
        tid = task["id"]
        denied = client.post(f"/api/tasks/{tid}/accept", headers=regular, json={"password": "pw-role-1"})
        assert denied.status_code == 403
        assert "志愿者" in denied.json()["detail"]

        # 管理员升级该用户为志愿者
        promoted = client.patch(f"/api/admin/users/{regular_id}/role", headers=admin, json={"role": "volunteer"})
        assert promoted.status_code == 200
        assert promoted.json()["role"] == "volunteer"
        me_after = client.get("/api/auth/me", headers=regular).json()
        assert me_after["role"] == "volunteer"

        # 志愿者可正常接取
        accepted = client.post(f"/api/tasks/{tid}/accept", headers=regular, json={"password": "pw-role-1"})
        assert accepted.status_code == 200
        assert accepted.json()["status"] == "accepted"

        # 管理员账号不能修改自己的权限等级，也不可接取
        admin_me = client.get("/api/auth/me", headers=admin).json()
        admin_change = client.patch(
            f"/api/admin/users/{admin_me['id']}/role", headers=admin, json={"role": "volunteer"}
        )
        assert admin_change.status_code == 409

        # 降级回普通用户：另开新委托验证不能接取
        demoted = client.patch(f"/api/admin/users/{regular_id}/role", headers=admin, json={"role": "user"})
        assert demoted.status_code == 200
        assert demoted.json()["role"] == "user"

        task2 = create_task(client, pub, password="pw-role-2", required=1)
        again_denied = client.post(f"/api/tasks/{task2['id']}/accept", headers=regular, json={"password": "pw-role-2"})
        assert again_denied.status_code == 403


def test_passwordless_task_can_be_accepted_by_all_non_admin_roles():
    with TestClient(app) as client:
        publisher = auth(client, "open_pub")
        regular = auth(client, "open_regular")
        volunteer = auth(client, "open_volunteer", role="volunteer")
        admin_login = client.post("/api/auth/login", json={"username": "admin", "password": "Admin123!"})
        admin = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}

        task = create_task(client, publisher, password=None, required=2, title="任何用户都能接取的委托")
        assert task["requires_password"] is False

        joined = client.post(f"/api/tasks/{task['id']}/accept", headers=regular, json={})
        assert joined.status_code == 200
        assert joined.json()["status"] == "published"
        assert len(joined.json()["members"]) == 1

        started = client.post(f"/api/tasks/{task['id']}/accept", headers=volunteer, json={})
        assert started.status_code == 200
        assert started.json()["status"] == "accepted"
        assert len(started.json()["members"]) == 2

        another = create_task(client, publisher, password=None, required=1, title="管理员不能接取的委托")
        denied = client.post(f"/api/tasks/{another['id']}/accept", headers=admin, json={})
        assert denied.status_code == 403

        protected = create_task(client, publisher, password="protected-123", required=1, title="高权限用户接取的委托")
        assert protected["requires_password"] is True
        denied = client.post(f"/api/tasks/{protected['id']}/accept", headers=regular, json={"password": "protected-123"})
        assert denied.status_code == 403
        assert "志愿者" in denied.json()["detail"]


def test_staff_role_management_and_public_directory(monkeypatch):
    monkeypatch.setattr(settings, "staff_group_id", "987654321")
    with TestClient(app) as client:
        admin_login = client.post("/api/auth/login", json={"username": "admin", "password": "Admin123!"})
        admin = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}
        admin_id = client.get("/api/auth/me", headers=admin).json()["id"]

        staff_headers = auth(client, "staff_member")
        staff_me = client.get("/api/auth/me", headers=staff_headers).json()
        staff_id = staff_me["id"]
        profile = client.patch(
            "/api/users/me",
            headers=staff_headers,
            json={"nickname": "公开店员", "qq": "123456789", "bio": "负责处理权限申请"},
        )
        assert profile.status_code == 200

        granted = client.patch(
            f"/api/admin/users/{staff_id}/role", headers=admin, json={"role": "staff"}
        )
        assert granted.status_code == 200
        assert granted.json()["role"] == "staff"

        # 店员具备志愿者的有密码接取能力。
        publisher = auth(client, "staff_task_pub")
        protected = create_task(client, publisher, password="staff-can-take", required=1)
        accepted = client.post(
            f"/api/tasks/{protected['id']}/accept",
            headers=staff_headers,
            json={"password": "staff-can-take"},
        )
        assert accepted.status_code == 200
        assert accepted.json()["status"] == "accepted"

        target = auth(client, "staff_managed_user")
        target_id = client.get("/api/auth/me", headers=target).json()["id"]
        managed_users = client.get("/api/admin/users", headers=staff_headers)
        assert managed_users.status_code == 200
        assert all(not user["is_admin"] for user in managed_users.json())

        promoted = client.patch(
            f"/api/admin/users/{target_id}/role", headers=staff_headers, json={"role": "volunteer"}
        )
        assert promoted.status_code == 200
        assert promoted.json()["role"] == "volunteer"
        demoted = client.patch(
            f"/api/admin/users/{target_id}/role", headers=staff_headers, json={"role": "user"}
        )
        assert demoted.status_code == 200
        assert demoted.json()["role"] == "user"

        volunteer_headers = auth(client, "public_volunteer", role="volunteer")
        volunteer_me = client.patch(
            "/api/users/me",
            headers=volunteer_headers,
            json={"nickname": "公开志愿者", "qq": "223344556", "bio": "可协助接取委托"},
        )
        assert volunteer_me.status_code == 200

        cannot_grant_staff = client.patch(
            f"/api/admin/users/{target_id}/role", headers=staff_headers, json={"role": "staff"}
        )
        assert cannot_grant_staff.status_code == 403
        cannot_change_admin = client.patch(
            f"/api/admin/users/{admin_id}/role", headers=staff_headers, json={"role": "user"}
        )
        assert cannot_change_admin.status_code == 409

        # 其他监管功能仍为管理员专属。
        assert client.get("/api/admin/stats", headers=staff_headers).status_code == 403
#         assert client.get("/api/admin/tasks", headers=staff_headers).status_code == 403
        assert client.get("/api/admin/feedback", headers=staff_headers).status_code == 403
        assert client.patch(
            f"/api/admin/users/{target_id}/task-limit",
            headers=staff_headers,
            json={"max_concurrent_tasks": 5},
        ).status_code == 403

        # 店员 QQ 公开；志愿者 QQ 默认隐藏。
        directory = client.get("/api/staff")
        assert directory.status_code == 200
        assert directory.json()["group_chat_id"] == "987654321"
        public_staff = next(user for user in directory.json()["staff"] if user["id"] == staff_id)
        assert public_staff["nickname"] == "公开店员"
        assert public_staff["qq"] == "123456789"
        assert public_staff["bio"] == "负责处理权限申请"
        public_volunteer = next(
            user for user in directory.json()["volunteers"] if user["id"] == volunteer_me.json()["id"]
        )
        assert public_volunteer["nickname"] == "公开志愿者"
        assert public_volunteer["qq"] is None
        assert public_volunteer["qq_public"] is False
        assert public_volunteer["bio"] == "可协助接取委托"

        public_profile = client.get(f"/api/users/{staff_id}")
        assert public_profile.status_code == 200
        assert public_profile.json()["qq"] == "123456789"
        hidden_volunteer_profile = client.get(f"/api/users/{volunteer_me.json()['id']}")
        assert hidden_volunteer_profile.status_code == 200
        assert hidden_volunteer_profile.json()["qq"] is None

        # 志愿者可在个人设置中主动公开，名录与公开资料同步生效。
        volunteer_me = client.patch(
            "/api/users/me",
            headers=volunteer_headers,
            json={
                "nickname": "公开志愿者",
                "qq": "223344556",
                "qq_public": True,
                "bio": "可协助接取委托",
            },
        )
        assert volunteer_me.status_code == 200
        assert volunteer_me.json()["qq_public"] is True
        directory = client.get("/api/staff").json()
        public_volunteer = next(
            user for user in directory["volunteers"] if user["id"] == volunteer_me.json()["id"]
        )
        assert public_volunteer["qq"] == "223344556"
        assert client.get(f"/api/users/{volunteer_me.json()['id']}").json()["qq"] == "223344556"
        assert client.get(f"/api/users/{target_id}").status_code == 401


def test_hidden_volunteer_qq_remains_visible_to_task_parties():
    with TestClient(app) as client:
        publisher = auth(client, "qq_privacy_publisher")
        volunteer = auth(client, "qq_privacy_volunteer", role="volunteer")
        publisher_me = set_qq(client, publisher, "334455667")
        volunteer_me = set_qq(client, volunteer, "776655443")

        assert volunteer_me["qq_public"] is False
        directory = client.get("/api/staff").json()
        listed = next(user for user in directory["volunteers"] if user["id"] == volunteer_me["id"])
        assert listed["qq"] is None

        task = create_task(client, publisher, password="privacy-task", required=1)
        accepted = client.post(
            f"/api/tasks/{task['id']}/accept",
            headers=volunteer,
            json={"password": "privacy-task"},
        )
        assert accepted.status_code == 200

        as_publisher = client.get(f"/api/tasks/{task['id']}", headers=publisher).json()
        assert as_publisher["members"][0]["qq"] == "776655443"
        volunteer_profile = client.get(f"/api/users/{volunteer_me['id']}", headers=publisher).json()
        assert volunteer_profile["qq"] == "776655443"

        as_volunteer = client.get(f"/api/tasks/{task['id']}", headers=volunteer).json()
        assert as_volunteer["contact_qq"] == publisher_me["qq"]


def test_user_profile_photos_upload_limits_task_visibility_and_moderation(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "sugar_upload_dir", str(tmp_path / "uploads"))
    with TestClient(app) as client:
        owner = auth(client, "photo_owner", role="volunteer")
        viewer = auth(client, "photo_viewer")
        owner_id = client.get("/api/auth/me", headers=owner).json()["id"]
        admin_login = client.post("/api/auth/login", json={"username": "admin", "password": "Admin123!"})
        admin = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}

        files = [("photos", (f"photo-{i}.png", TINY_PNG, "image/png")) for i in range(3)]
        uploaded = client.post("/api/users/me/photos", headers=owner, files=files)
        assert uploaded.status_code == 201, uploaded.text
        assert len(uploaded.json()["photos"]) == 3
        assert all(photo["image_url"].startswith("/uploads/users/") for photo in uploaded.json()["photos"])
        assert len(list((tmp_path / "uploads" / "users" / str(owner_id)).iterdir())) == 3

        over_count = client.post(
            "/api/users/me/photos",
            headers=owner,
            files=[("photos", ("fourth.png", TINY_PNG, "image/png"))],
        )
        assert over_count.status_code == 422
        too_large = client.post(
            "/api/users/me/photos",
            headers=viewer,
            files=[("photos", ("large.png", b"\x89PNG\r\n\x1a\n" + b"0" * (5 * 1024 * 1024), "image/png"))],
        )
        assert too_large.status_code == 422
        assert too_large.json()["detail"] == "单张照片不能超过 5 MiB"

        empty_file = client.post(
            "/api/users/me/photos",
            headers=viewer,
            files=[("photos", ("empty.png", b"", "image/png"))],
        )
        assert empty_file.status_code == 422
        assert empty_file.json()["detail"] == "上传的照片不能为空"

        invalid_format = client.post(
            "/api/users/me/photos",
            headers=viewer,
            files=[("photos", ("not-an-image.png", b"not an image", "image/png"))],
        )
        assert invalid_format.status_code == 422
        assert invalid_format.json()["detail"] == "仅支持 JPEG、PNG、GIF 或 WebP 图片"

        # 图片会随委托中的用户摘要返回，便于接取前查看委托人资料。
        task = create_task(client, owner, password=None, required=1, title="带个人图片的委托")
        task_detail = client.get(f"/api/tasks/{task['id']}", headers=viewer).json()
        assert len(task_detail["publisher"]["photos"]) == 3

        photo_id = uploaded.json()["photos"][0]["id"]
        assert client.patch(
            f"/api/admin/photos/{photo_id}", headers=viewer, json={"is_visible": False}
        ).status_code == 403
        hidden = client.patch(
            f"/api/admin/photos/{photo_id}", headers=admin, json={"is_visible": False}
        )
        assert hidden.status_code == 200
        assert next(photo for photo in hidden.json()["photos"] if photo["id"] == photo_id)["is_visible"] is False

        # 名录资料对访客公开，但被屏蔽图片不会对普通访客返回；本人仍可管理它。
        public_profile = client.get(f"/api/users/{owner_id}").json()
        assert len(public_profile["photos"]) == 2
        self_profile = client.get(f"/api/users/{owner_id}", headers=owner).json()
        assert len(self_profile["photos"]) == 3

        staff = auth(client, "photo_staff")
        staff_id = client.get("/api/auth/me", headers=staff).json()["id"]
        client.patch(f"/api/admin/users/{staff_id}/role", headers=admin, json={"role": "staff"})
        restored = client.patch(
            f"/api/admin/photos/{photo_id}", headers=staff, json={"is_visible": True}
        )
        assert restored.status_code == 200
        assert all(photo["is_visible"] for photo in restored.json()["photos"])

        deleted = client.delete(f"/api/users/me/photos/{photo_id}", headers=owner)
        assert deleted.status_code == 200
        assert len(deleted.json()["photos"]) == 2


def test_image_upload_reports_storage_space_error(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "sugar_upload_dir", str(tmp_path / "uploads"))

    def no_space_left(_: Path, __: bytes) -> int:
        raise OSError(ENOSPC, "No space left on device")

    monkeypatch.setattr(Path, "write_bytes", no_space_left)
    with TestClient(app) as client:
        user = auth(client, "photo_storage_error")
        response = client.post(
            "/api/users/me/photos",
            headers=user,
            files=[("photos", ("portrait.png", TINY_PNG, "image/png"))],
        )
        assert response.status_code == 500
        assert response.json()["detail"] == "服务器存储空间不足，请稍后重试"


def test_designated_single_member_accepts_or_declines_without_password():
    with TestClient(app) as client:
        publisher = auth(client, "designated_pub")
        set_qq(client, publisher, "10086041")
        volunteer = auth(client, "designated_one", role="volunteer")
        volunteer_id = client.get("/api/auth/me", headers=volunteer).json()["id"]
        # 指定委托由创建请求中的名单决定，密码字段被忽略。
        task = client.post(
            "/api/tasks",
            headers=publisher,
            json={
                "title": "指定单人委托",
                "description": "请完成一项指定人员才能处理的工作内容",
                "category": "其他",
                "pay_type": "free",
                "accept_password": "should-not-apply",
                "designated_user_ids": [volunteer_id],
                "expires_in_days": 2,
            },
        ).json()
        assert task["is_designated"] is True and task["requires_password"] is False
        assert task["members"][0]["response_status"] == "pending"
        tid = task["id"]
        accepted = client.post(f"/api/tasks/{tid}/accept", headers=volunteer, json={"password": "wrong"})
        assert accepted.status_code == 200
        assert accepted.json()["status"] == "accepted"


def test_designated_multiple_waits_for_all_and_cancels_when_all_decline():
    with TestClient(app) as client:
        publisher = auth(client, "designated_pub2")
        set_qq(client, publisher, "10086042")
        one = auth(client, "designated_two", role="volunteer")
        two = auth(client, "designated_three", role="volunteer")
        outsider = auth(client, "designated_outsider", role="volunteer")
        ids = [client.get("/api/auth/me", headers=h).json()["id"] for h in (one, two)]
        payload = {
            "title": "指定多人委托",
            "description": "请完成一项需要多人响应后才能开始的工作内容",
            "category": "其他",
            "pay_type": "free",
            "designated_user_ids": ids,
            "expires_in_days": 2,
        }
        created = client.post("/api/tasks", headers=publisher, json=payload)
        assert created.status_code == 201, created.text
        task = created.json()
        tid = task["id"]
        assert client.post(f"/api/tasks/{tid}/accept", headers=outsider, json={}).status_code == 403
        assert client.post(f"/api/tasks/{tid}/accept", headers=one, json={}).json()["status"] == "published"
        # 另一人拒绝不会取消；全部响应后有一人接受则开始。
        declined = client.post(f"/api/tasks/{tid}/leave", headers=two)
        assert declined.status_code == 200 and declined.json()["status"] == "accepted"

        payload["title"] = "指定多人全拒绝"
        created2 = client.post("/api/tasks", headers=publisher, json=payload)
        assert created2.status_code == 201, created2.text
        task2 = created2.json()
        tid2 = task2["id"]
        assert client.post(f"/api/tasks/{tid2}/leave", headers=one).json()["status"] == "published"
        assert client.post(f"/api/tasks/{tid2}/leave", headers=two).json()["status"] == "cancelled"


def test_anonymous_task_hides_publisher_until_accepted_then_reveals_contacts():
    with TestClient(app) as client:
        publisher = auth(client, "anon_pub")
        publisher_id = client.get("/api/auth/me", headers=publisher).json()["id"]
        set_qq(client, publisher, "10086001")
        volunteer = auth(client, "anon_taker", role="volunteer")
        volunteer_id = client.get("/api/auth/me", headers=volunteer).json()["id"]
        set_qq(client, volunteer, "10086002")
        outsider = auth(client, "anon_outsider", role="volunteer")

        created = client.post(
            "/api/tasks",
            headers=publisher,
            json={
                "title": "匿名整理的委托",
                "description": "这是一份不公开发布人身份的匿名委托内容说明",
                "category": "其他",
                "pay_type": "free",
                "accept_password": "pw-anon-1",
                "is_anonymous": True,
                "expires_in_days": 2,
            },
        )
        assert created.status_code == 201, created.text
        task = created.json()
        tid = task["id"]
        assert task["is_anonymous"] is True

        # 委托人自己仍能看到完整信息与自己的真实 id。
        assert task["publisher_id"] == publisher_id
        assert task["publisher"]["id"] == publisher_id

        # 未接取时：对外只显示标题和内容，发布人与成员信息全部脱敏。
        public_detail = client.get(f"/api/tasks/{tid}").json()
        assert public_detail["publisher_id"] == 0
        assert public_detail["publisher"]["id"] == 0
        assert public_detail["publisher"]["nickname"] == "匿名委托人"
        assert public_detail["members"] == []
        assert public_detail["contact_qq"] is None

        before = client.get(f"/api/tasks/{tid}", headers=volunteer).json()
        assert before["publisher_id"] == 0
        assert before["publisher"]["nickname"] == "匿名委托人"
        assert before["members"] == []
        assert before["contact_qq"] is None

        listed = client.get("/api/tasks", headers=volunteer).json()
        anon_listed = next(item for item in listed if item["id"] == tid)
        assert anon_listed["publisher"]["nickname"] == "匿名委托人"
        assert anon_listed["members"] == []
        assert anon_listed["contact_qq"] is None

        # 接取后：双方联系方式互见。
        accepted = client.post(f"/api/tasks/{tid}/accept", headers=volunteer, json={"password": "pw-anon-1"}).json()
        assert accepted["publisher"]["id"] == publisher_id
        assert accepted["publisher"]["nickname"] != "匿名委托人"
        assert accepted["contact_qq"] == "10086001"
        assert [member["user"]["id"] for member in accepted["members"]] == [volunteer_id]

        publisher_view = client.get(f"/api/tasks/{tid}", headers=publisher).json()
        assert publisher_view["publisher_id"] == publisher_id
        volunteer_member = next(member for member in publisher_view["members"] if member["user"]["id"] == volunteer_id)
        assert volunteer_member["qq"] == "10086002"

        # 未参与的其他登录用户仍只能看到脱敏视图。
        outsider_view = client.get(f"/api/tasks/{tid}", headers=outsider).json()
        assert outsider_view["publisher_id"] == 0
        assert outsider_view["publisher"]["nickname"] == "匿名委托人"
        assert outsider_view["members"] == []
        assert outsider_view["contact_qq"] is None


def test_anonymous_free_task_accept_shows_publisher_contact_to_regular_user():
    with TestClient(app) as client:
        publisher = auth(client, "anon_free_pub")
        publisher_id = client.get("/api/auth/me", headers=publisher).json()["id"]
        set_qq(client, publisher, "10086123")
        taker = auth(client, "anon_free_taker")
        created = client.post(
            "/api/tasks",
            headers=publisher,
            json={
                "title": "匿名无偿委托",
                "description": "一份无需密码即可接取的匿名委托内容说明",
                "category": "其他",
                "pay_type": "free",
                "accept_password": None,
                "is_anonymous": True,
                "expires_in_days": 1,
            },
        ).json()
        tid = created["id"]
        assert created["is_anonymous"] is True
        assert created["publisher"]["id"] == publisher_id
        assert created["contact_qq"] is None
        accepted = client.post(f"/api/tasks/{tid}/accept", headers=taker, json={"password": None}).json()
        assert accepted["publisher"]["nickname"] != "匿名委托人"
        assert accepted["contact_qq"] == "10086123"


def test_anonymous_designated_task_shows_only_own_pending_status_until_accept():
    with TestClient(app) as client:
        publisher = auth(client, "anon_design_pub")
        set_qq(client, publisher, "10086031")
        volunteer = auth(client, "anon_design_one", role="volunteer")
        volunteer_id = client.get("/api/auth/me", headers=volunteer).json()["id"]
        other = auth(client, "anon_design_two", role="volunteer")
        other_id = client.get("/api/auth/me", headers=other).json()["id"]
        created = client.post(
            "/api/tasks",
            headers=publisher,
            json={
                "title": "匿名指定委托",
                "description": "一份指定专人响应的匿名委托内容说明",
                "category": "其他",
                "pay_type": "free",
                "designated_user_ids": [volunteer_id, other_id],
                "is_anonymous": True,
                "expires_in_days": 2,
            },
        ).json()
        tid = created["id"]
        assert created["is_anonymous"] is True
        # 被指定者：仅看到自己的待响应状态，发布人与其他成员均不可见。
        pending_view = client.get(f"/api/tasks/{tid}", headers=volunteer).json()
        assert pending_view["publisher_id"] == 0
        assert pending_view["publisher"]["nickname"] == "匿名委托人"
        assert [member["user"]["id"] for member in pending_view["members"]] == [volunteer_id]
        assert pending_view["members"][0]["response_status"] == "pending"
        assert pending_view["contact_qq"] is None
        # 其他被指定者也看不到他人信息。
        other_view = client.get(f"/api/tasks/{tid}", headers=other).json()
        assert [member["user"]["id"] for member in other_view["members"]] == [other_id]
        # 接受后双方联系方式可见。
        accepted = client.post(f"/api/tasks/{tid}/accept", headers=volunteer, json={"password": None}).json()
        assert accepted["publisher_id"] == created["publisher_id"]
        assert accepted["publisher"]["nickname"] != "匿名委托人"
        assert accepted["contact_qq"] == "10086031"


def test_hall_only_shows_published_for_regular_users():
    with TestClient(app) as client:
        publisher = auth(client, "hall_pub")
        taker = auth(client, "hall_taker", role="volunteer")
        admin_login = client.post("/api/auth/login", json={"username": "admin", "password": "Admin123!"})
        admin = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}

        published_task = create_task(client, publisher, password="pw-hall-1", required=1)
        processing = create_task(client, publisher, password="pw-hall-2", required=1)
        client.post(f"/api/tasks/{processing['id']}/accept", headers=taker, json={"password": "pw-hall-2"}).json()

        # 普通用户（志愿者）在大厅只能看到招募中的委托
        hall = client.get("/api/tasks", headers=taker).json()
        ids = [item["id"] for item in hall]
        assert published_task["id"] in ids
        assert processing["id"] not in ids
        assert all(item["status"] == "published" for item in hall)

        # 未登录同样只能看到招募中的委托
        anon_hall = client.get("/api/tasks").json()
        assert all(item["status"] == "published" for item in anon_hall)

        # 管理员可查看全部状态
        admin_hall = client.get("/api/tasks", headers=admin).json()
        admin_ids = [item["id"] for item in admin_hall]
        assert published_task["id"] in admin_ids
        assert processing["id"] in admin_ids

        # 处理中的委托详情仅委托双方可见
        assert client.get(f"/api/tasks/{processing['id']}", headers=publisher).status_code == 200
        assert client.get(f"/api/tasks/{processing['id']}", headers=taker).status_code == 200
        stranger = auth(client, "hall_stranger")
        assert client.get(f"/api/tasks/{processing['id']}", headers=stranger).status_code == 404
        assert client.get(f"/api/tasks/{processing['id']}").status_code == 404


def test_report_flow_daily_limit_and_resolve():
    with TestClient(app) as client:
        publisher = auth(client, "report_pub")
        reporter = auth(client, "report_reporter")
        second = auth(client, "report_second")

        task1 = create_task(client, publisher, password="pw-report-1", required=1)
        task2 = create_task(client, publisher, password="pw-report-2", required=1)
        task3 = create_task(client, publisher, password="pw-report-3", required=1)

        # 不能举报自己的委托
        own = client.post(f"/api/tasks/{task1['id']}/report", headers=publisher, json={"reason": "自己举报自己"})
        assert own.status_code == 422

        # 未登录不能举报
        assert client.post(f"/api/tasks/{task1['id']}/report", json={"reason": "匿名举报"}).status_code == 401

        # 默认每日最多 2 个
        r1 = client.post(f"/api/tasks/{task1['id']}/report", headers=reporter, json={"reason": "违规内容测试"})
        assert r1.status_code == 201
        r2 = client.post(f"/api/tasks/{task2['id']}/report", headers=reporter, json={"reason": "诈骗嫌疑测试"})
        assert r2.status_code == 201
        r3 = client.post(f"/api/tasks/{task3['id']}/report", headers=reporter, json={"reason": "超限举报测试"})
        assert r3.status_code == 429

        # 同一委托重复举报被拒
        dup = client.post(f"/api/tasks/{task1['id']}/report", headers=reporter, json={"reason": "重复举报"})
        assert dup.status_code == 409

        # 被举报的委托不显示在大厅
        hall = client.get("/api/tasks", headers=second).json()
        hall_ids = [item["id"] for item in hall]
        assert task1["id"] not in hall_ids
        assert task2["id"] not in hall_ids

        # 被举报的委托详情：普通第三方不可见，委托双方可见
        assert client.get(f"/api/tasks/{task1['id']}", headers=second).status_code == 404
        assert client.get(f"/api/tasks/{task1['id']}", headers=publisher).status_code == 200

        # 普通用户不能访问举报管理接口
        assert client.get("/api/admin/reports", headers=reporter).status_code == 403
        assert client.get("/api/admin/settings/report-limit", headers=reporter).status_code == 403

        # 店员可查看举报并处理
        staff = auth(client, "report_staff")
        staff_id = client.get("/api/auth/me", headers=staff).json()["id"]
        admin_login = client.post("/api/auth/login", json={"username": "admin", "password": "Admin123!"})
        admin = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}
        promote_staff = client.patch(f"/api/admin/users/{staff_id}/role", headers=admin, json={"role": "staff"})
        assert promote_staff.status_code == 200

        reports = client.get("/api/admin/reports", headers=staff).json()
        assert len(reports) == 2
        assert all(item["status"] == "pending" for item in reports)

        # 关闭举报：委托恢复显示
        close_report = next(item for item in reports if item["task_id"] == task1["id"])
        closed = client.post(f"/api/admin/reports/{close_report['id']}/resolve", headers=staff, json={"action": "close"})
        assert closed.status_code == 200
        assert closed.json()["status"] == "handled"
        hall_after = client.get("/api/tasks", headers=second).json()
        assert task1["id"] in [item["id"] for item in hall_after]

        # 屏蔽委托：要求理由，委托从大厅与详情消失
        hide_report = next(item for item in reports if item["task_id"] == task2["id"])
        no_note = client.post(f"/api/admin/reports/{hide_report['id']}/resolve", headers=staff, json={"action": "hide"})
        assert no_note.status_code == 422
        hidden = client.post(
            f"/api/admin/reports/{hide_report['id']}/resolve", headers=staff,
            json={"action": "hide", "admin_note": "核实为违规内容"},
        )
        assert hidden.status_code == 200
        hidden_task = client.get(f"/api/tasks/{task2['id']}", headers=staff).json()
        assert hidden_task["is_visible"] is False
        assert hidden_task["admin_note"] == "核实为违规内容"
        assert client.get(f"/api/tasks/{task2['id']}", headers=second).status_code == 404

        # 重新放开：委托恢复可见
        reopened = client.post(
            f"/api/admin/reports/{hide_report['id']}/resolve", headers=staff,
            json={"action": "restore"},
        )
        assert reopened.status_code == 200
        reopened_task = client.get(f"/api/tasks/{task2['id']}", headers=staff).json()
        assert reopened_task["is_visible"] is True
        assert client.get(f"/api/tasks/{task2['id']}", headers=second).status_code == 200


def test_report_daily_limit_configurable():
    with TestClient(app) as client:
        publisher = auth(client, "limit_pub")
        reporter = auth(client, "limit_reporter")
        staff = auth(client, "limit_staff")
        staff_id = client.get("/api/auth/me", headers=staff).json()["id"]
        admin_login = client.post("/api/auth/login", json={"username": "admin", "password": "Admin123!"})
        admin = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}
        assert client.patch(f"/api/admin/users/{staff_id}/role", headers=admin, json={"role": "staff"}).status_code == 200

        # 默认上限 2
        assert client.get("/api/admin/settings/report-limit", headers=staff).json()["daily_limit"] == 2
        tasks = [create_task(client, publisher, password=f"pw-limit-{i}", required=1) for i in range(3)]
        client.post(f"/api/tasks/{tasks[0]['id']}/report", headers=reporter, json={"reason": "第一条"})
        client.post(f"/api/tasks/{tasks[1]['id']}/report", headers=reporter, json={"reason": "第二条"})
        assert client.post(f"/api/tasks/{tasks[2]['id']}/report", headers=reporter, json={"reason": "第三条"}).status_code == 429

        # 店员/管理员可调整上限
        updated = client.patch("/api/admin/settings/report-limit", headers=staff, json={"daily_limit": 5})
        assert updated.status_code == 200
        assert updated.json()["daily_limit"] == 5
        assert client.get("/api/admin/settings/report-limit", headers=staff).json()["daily_limit"] == 5
        assert client.post(f"/api/tasks/{tasks[2]['id']}/report", headers=reporter, json={"reason": "第三条重试"}).status_code == 201

        # 非法值被拒绝
        assert client.patch("/api/admin/settings/report-limit", headers=staff, json={"daily_limit": 0}).status_code == 422
