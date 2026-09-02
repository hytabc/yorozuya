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


def auth(client, username):
    response = client.post(
        "/api/auth/register",
        json={"username": username, "password": "Password123!", "nickname": f"用户{username}"},
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_task_workflow_and_permissions():
    with TestClient(app) as client:
        publisher = auth(client, "publisher")
        assignee = auth(client, "assignee")
        created = client.post(
            "/api/tasks",
            headers=publisher,
            json={
                "title": "帮忙整理一份资料",
                "description": "需要将十条记录整理成清晰的表格文件",
                "category": "学习",
                "reward": "30 元",
                "expires_at": (datetime.utcnow() + timedelta(days=2)).isoformat() + "Z",
            },
        )
        assert created.status_code == 201
        task_id = created.json()["id"]

        own_accept = client.post(f"/api/tasks/{task_id}/accept", headers=publisher)
        assert own_accept.status_code == 400

        accepted = client.post(f"/api/tasks/{task_id}/accept", headers=assignee)
        assert accepted.status_code == 200
        assert accepted.json()["status"] == "accepted"

        submitted = client.post(f"/api/tasks/{task_id}/submit", headers=assignee)
        assert submitted.json()["status"] == "submitted"

        confirmed = client.post(f"/api/tasks/{task_id}/confirm", headers=publisher)
        assert confirmed.json()["status"] == "completed"


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

