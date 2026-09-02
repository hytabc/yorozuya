from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
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


def auth(client, username, password="Password123!"):
    response = client.post(
        "/api/auth/register",
        json={"username": username, "password": password, "nickname": f"用户{username}"},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def set_qq(client, headers, qq):
    me = client.get("/api/auth/me", headers=headers)
    nickname = me.json()["nickname"]
    r = client.patch("/api/users/me", headers=headers, json={"nickname": nickname, "qq": qq, "bio": None})
    assert r.status_code == 200, r.text
    return r.json()


def create_task(client, headers, password="接取密码123", required=None, title="帮忙整理一份资料"):
    payload = {
        "title": title,
        "description": "需要将十条记录整理成清晰的表格文件",
        "category": "学习",
        "reward": "30 元",
        "accept_password": password,
        "expires_at": (datetime.utcnow() + timedelta(days=2)).isoformat() + "Z",
    }
    if required is not None:
        payload["required_takers"] = required
    response = client.post("/api/tasks", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def member_ids(task):
    return [m["user"]["id"] for m in task["members"]]


def test_accept_fills_up_until_auto_start():
    with TestClient(app) as client:
        pub = auth(client, "pub")
        a = auth(client, "taker_a")
        b = auth(client, "taker_b")
        c = auth(client, "taker_c")
        d = auth(client, "taker_d")

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
        a = auth(client, "taker_a2")
        b = auth(client, "taker_b2")

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
        a = auth(client, "taker_a3")
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
        a = auth(client, "taker_a4")
        b = auth(client, "taker_b4")
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
        a = auth(client, "taker_a5")
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
        a = auth(client, "taker_a6")
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
        a = auth(client, "taker_a7")
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
        taker = auth(client, "pro_taker")
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
        tasks = client.get("/api/tasks", headers=publisher).json()
        assert tasks[0]["status"] == "expired"


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


def test_user_task_limit_and_admin_control():
    with TestClient(app) as client:
        publishers = [auth(client, f"limit_pub_{index}") for index in range(4)]
        taker = auth(client, "limited_taker")
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
