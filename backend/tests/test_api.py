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
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_task(client, headers, title="帮忙整理一份资料", password="接取密码123"):
    return client.post(
        "/api/tasks",
        headers=headers,
        json={
            "title": title,
            "description": "需要将十条记录整理成清晰的表格文件",
            "category": "学习",
            "reward": "30 元",
            "accept_password": password,
            "expires_at": (datetime.utcnow() + timedelta(days=2)).isoformat() + "Z",
        },
    )


def test_password_gated_accept_and_double_confirm():
    with TestClient(app) as client:
        publisher = auth(client, "publisher")
        assignee_reg = client.post(
            "/api/auth/register",
            json={"username": "assignee", "password": "Password123!", "nickname": "用户assignee"},
        )
        assignee = {"Authorization": f"Bearer {assignee_reg.json()['access_token']}"}
        assignee_id = assignee_reg.json()["user"]["id"]
        stranger = auth(client, "stranger")

        created = create_task(client, publisher, password="correct-pw-1")
        assert created.status_code == 201
        assert "accept_password" not in created.json()
        task_id = created.json()["id"]

        # 委托人不能接取自己的委托
        own_accept = client.post(
            f"/api/tasks/{task_id}/accept", headers=publisher, json={"password": "correct-pw-1"}
        )
        assert own_accept.status_code == 400

        # 错误密码无法接取
        wrong = client.post(f"/api/tasks/{task_id}/accept", headers=assignee, json={"password": "wrong-password"})
        assert wrong.status_code == 403

        # 委托人还未同意（提供密码）时，任何登录用户都看不到联系方式用于洽谈
        assert created.json()["contact_qq"] is None

        # 正确密码接取成功
        accepted = client.post(
            f"/api/tasks/{task_id}/accept", headers=assignee, json={"password": "correct-pw-1"}
        )
        assert accepted.status_code == 200
        assert accepted.json()["status"] == "accepted"
        assert accepted.json()["assignee"]["id"] == assignee_id

        # 已被接取后其他人无法再接取
        second = client.post(f"/api/tasks/{task_id}/accept", headers=stranger, json={"password": "correct-pw-1"})
        assert second.status_code == 409

        # 无关用户不能确认完成
        denied = client.post(f"/api/tasks/{task_id}/confirm", headers=stranger)
        assert denied.status_code == 403

        # 接单人先确认完成 → 待确认（等待委托人）
        first = client.post(f"/api/tasks/{task_id}/confirm", headers=assignee)
        assert first.status_code == 200
        assert first.json()["status"] == "awaiting"
        assert first.json()["assignee_confirmed_at"] is not None
        assert first.json()["publisher_confirmed_at"] is None

        # 接单人重复确认被拒绝
        dup = client.post(f"/api/tasks/{task_id}/confirm", headers=assignee)
        assert dup.status_code == 409

        # 委托人确认后完成
        finished = client.post(f"/api/tasks/{task_id}/confirm", headers=publisher)
        assert finished.status_code == 200
        assert finished.json()["status"] == "completed"
        assert finished.json()["completed_at"] is not None


def test_publisher_can_confirm_first_then_assignee():
    with TestClient(app) as client:
        publisher = auth(client, "pub2")
        assignee = auth(client, "asg2")
        created = create_task(client, publisher, password="pw2-abcde")
        task_id = created.json()["id"]
        client.post(f"/api/tasks/{task_id}/accept", headers=assignee, json={"password": "pw2-abcde"})

        # 委托人先确认完成 → 待确认
        first = client.post(f"/api/tasks/{task_id}/confirm", headers=publisher)
        assert first.json()["status"] == "awaiting"
        assert first.json()["publisher_confirmed_at"] is not None

        # 接单人再确认 → 已完成
        second = client.post(f"/api/tasks/{task_id}/confirm", headers=assignee)
        assert second.json()["status"] == "completed"


def test_published_task_contact_visible_to_logged_in_viewers():
    with TestClient(app) as client:
        publisher = auth(client, "pub3")
        taker = auth(client, "taker3")
        # 发布人补充 QQ
        updated = client.patch(
            "/api/users/me", headers=publisher, json={"nickname": "用户pub3", "qq": "1234567890", "bio": None}
        )
        assert updated.status_code == 200

        created = create_task(client, publisher, password="pw3-abcde")
        task_id = created.json()["id"]

        # 匿名浏览：不暴露联系方式
        anonymous = client.get("/api/tasks").json()
        assert anonymous[0]["contact_qq"] is None

        # 登录后的接单人可看到委托人 QQ，便于洽谈
        listed = client.get("/api/tasks", headers=taker).json()
        assert listed[0]["contact_qq"] == "1234567890"


def test_publisher_resets_password_before_accept():
    with TestClient(app) as client:
        publisher = auth(client, "pub4")
        assignee = auth(client, "asg4")
        created = create_task(client, publisher, password="old-pw-1234")
        task_id = created.json()["id"]

        # 更新密码
        reset = client.patch(f"/api/tasks/{task_id}/password", headers=publisher, json={"password": "new-pw-5678"})
        assert reset.status_code == 200

        # 旧密码失效
        old = client.post(f"/api/tasks/{task_id}/accept", headers=assignee, json={"password": "old-pw-1234"})
        assert old.status_code == 403

        # 新密码可用
        ok = client.post(f"/api/tasks/{task_id}/accept", headers=assignee, json={"password": "new-pw-5678"})
        assert ok.status_code == 200
        assert ok.json()["status"] == "accepted"


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
        created = create_task(client, publisher, title="Listable task")
        assert created.status_code == 201

        without_status = client.get("/api/tasks")
        assert without_status.status_code == 200
        assert [task["id"] for task in without_status.json()] == [created.json()["id"]]

        empty_status = client.get("/api/tasks", params={"status": ""})
        assert empty_status.status_code == 200
        assert [task["id"] for task in empty_status.json()] == [created.json()["id"]]

        invalid_status = client.get("/api/tasks", params={"status": "unknown"})
        assert invalid_status.status_code == 422
