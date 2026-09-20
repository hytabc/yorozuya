"""邮箱验证与邮件相关流程的回归测试。

覆盖：注册必须验证、邮箱登录、邮件找回密码、换绑邮箱、
未验证闸门与超管豁免、邮件服务不可用时的 fail-closed、以及令牌只以哈希入库。
"""

import re
from io import BytesIO
from pathlib import Path
from urllib.parse import unquote

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import mailer
from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models import EmailToken, User
from app.security import create_access_token, hash_password

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def override_db():
    with TestingSession() as db:
        yield db


app.dependency_overrides[get_db] = override_db


def setup_function():
    app.dependency_overrides[get_db] = override_db
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    # 本地信箱 + 关掉冷却，让用例能连续发信。
    settings.email_delivery = "log"
    settings.email_send_cooldown_seconds = 0
    settings.require_email_verification = True
    settings.smtp_username = "smtp-user"
    settings.smtp_password = "smtp-key"
    settings.email_from_address = "sender@example.com"
    mailer.OUTBOX.clear()
    with TestingSession() as db:
        db.add(User(username="admin", nickname="管理员", password_hash=hash_password("Admin123!"), is_admin=True))
        db.commit()


# ---- 小工具 ----


def mails_to(address: str) -> list[dict]:
    return [item for item in mailer.OUTBOX if item["to"] == address]


def token_from(address: str) -> str:
    """取出寄给该地址的最近一封邮件里的链接令牌。"""
    found = mails_to(address)
    assert found, f"没有寄给 {address} 的邮件：{[m['to'] for m in mailer.OUTBOX]}"
    match = re.search(r"[?&]token=([^&\s]+)", found[-1]["text"])
    assert match, f"邮件正文里没有链接：{found[-1]['text']}"
    return unquote(match.group(1))


def register(client, username, email=None, password="Password123!"):
    address = email or f"{username}@example.com"
    response = client.post(
        "/api/auth/register",
        json={"username": username, "password": password, "nickname": f"用户{username}", "email": address},
    )
    assert response.status_code == 201, response.text
    return address


def verify(client, address):
    assert client.post("/api/auth/email/confirm", json={"token": token_from(address)}).status_code == 200


def login(client, account, password="Password123!"):
    return client.post("/api/auth/login", json={"username": account, "password": password})


def auth(client, username, email=None, password="Password123!"):
    address = register(client, username, email=email, password=password)
    verify(client, address)
    response = login(client, username, password)
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}, address


# ---- 1. 注册必须验证 ----


def test_registration_requires_email_verification_before_login():
    with TestClient(app) as client:
        address = register(client, "verify_user")
        created = client.post(
            "/api/auth/register",
            json={
                "username": "verify_user2",
                "password": "Password123!",
                "nickname": "重复邮箱",
                "email": address,
            },
        )
        # 邮箱唯一
        assert created.status_code == 409

        blocked = login(client, "verify_user")
        assert blocked.status_code == 403
        assert "邮箱尚未验证" in blocked.json()["detail"]

        # 邮箱也能作为登录名（验证后）
        verify(client, address)
        assert login(client, address).status_code == 200
        assert login(client, "verify_user").status_code == 200


def test_registration_sends_mail_containing_only_hashed_token():
    with TestClient(app) as client:
        address = register(client, "hash_user")
        token = token_from(address)
        with TestingSession() as db:
            rows = db.scalars(select(EmailToken).where(EmailToken.purpose == "verify_email")).all()
        assert len(rows) == 1
        stored = rows[0]
        # 库里只有 sha256(明文)，明文本身不落库
        assert stored.token_hash != token
        assert token not in stored.token_hash
        assert len(stored.token_hash) == 64


def test_verification_token_is_single_use():
    with TestClient(app) as client:
        address = register(client, "once_user")
        token = token_from(address)
        assert client.post("/api/auth/email/confirm", json={"token": token}).status_code == 200
        # 同一个链接不能用第二次
        assert client.post("/api/auth/email/confirm", json={"token": token}).status_code == 422
        assert client.post("/api/auth/email/confirm", json={"token": "not-a-real-token"}).status_code == 422


# ---- 2. 邮件找回密码 ----


def test_password_reset_request_does_not_leak_account_existence():
    with TestClient(app) as client:
        auth(client, "reset_user")
        mailer.OUTBOX.clear()

        unknown = client.post("/api/auth/password-reset/request", json={"account": "nobody_here"})
        assert unknown.status_code == 200
        assert unknown.json()["ok"] is True
        # 不存在的账号不发信，但响应与存在时完全一致
        assert mailer.OUTBOX == []

        known = client.post("/api/auth/password-reset/request", json={"account": "reset_user"})
        assert known.status_code == 200
        assert len(mailer.OUTBOX) == 1


def test_password_reset_changes_password_and_revokes_sessions():
    with TestClient(app) as client:
        headers, address = auth(client, "reset_pw")
        old_session = headers["Authorization"].split(" ")[1]

        assert client.post(
            "/api/auth/password-reset/request", json={"account": address}
        ).status_code == 200
        token = token_from(address)

        confirmed = client.post(
            "/api/auth/password-reset/confirm",
            json={"token": token, "password": "BrandNewPass123!"},
        )
        assert confirmed.status_code == 200, confirmed.text

        # 旧会话立即失效
        assert client.get("/api/auth/me", headers=headers).status_code == 401
        assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {old_session}"}).status_code == 401
        # 旧密码失效，新密码可用
        assert login(client, "reset_pw").status_code == 401
        assert login(client, "reset_pw", "BrandNewPass123!").status_code == 200
        # 重置链接一次性
        assert client.post(
            "/api/auth/password-reset/confirm",
            json={"token": token, "password": "AnotherPass123!"},
        ).status_code == 422
        # 改密后会给账号邮箱发一封通知
        assert any("密码已修改" in item["subject"] for item in mails_to(address))


def test_password_reset_rejects_bad_or_expired_token():
    with TestClient(app) as client:
        auth(client, "reset_bad")
        assert client.post(
            "/api/auth/password-reset/confirm",
            json={"token": "definitely-not-valid", "password": "WhateverPass123!"},
        ).status_code == 422


# ---- 4. 换绑邮箱 ----


def test_email_change_takes_effect_only_after_confirmation():
    with TestClient(app) as client:
        headers, old_address = auth(client, "change_user")
        new_address = "changed@example.com"
        mailer.OUTBOX.clear()

        requested = client.post("/api/users/me/email", headers=headers, json={"email": new_address, "current_password": "Password123!"})
        assert requested.status_code == 200, requested.text

        # 确认前：邮箱不变，只是 pending_email
        me = client.get("/api/auth/me", headers=headers).json()
        assert me["email"] == old_address
        assert me["pending_email"] == new_address
        assert me["email_verified"] is True

        # 新地址收到确认信，旧地址收到变更提醒
        assert token_from(new_address)
        assert any("更换你的邮箱" in item["subject"] for item in mails_to(old_address))

        confirmed = client.post(
            "/api/auth/email/confirm", json={"token": token_from(new_address)}
        )
        assert confirmed.status_code == 200, confirmed.text
        assert client.get("/api/auth/me", headers=headers).status_code == 401
        headers = {"Authorization": f"Bearer {login(client, new_address).json()['access_token']}"}
        me = client.get("/api/auth/me", headers=headers).json()
        assert me["email"] == new_address
        assert me["pending_email"] is None
        assert me["email_verified"] is True

        # 变更完成后旧邮箱会收到通知
        assert any("邮箱已变更" in item["subject"] for item in mails_to(old_address))
        # 新邮箱同样可以登录
        assert login(client, new_address).status_code == 200


def test_email_change_rejects_address_owned_by_someone_else():
    with TestClient(app) as client:
        headers, _ = auth(client, "owner_user")
        auth(client, "other_user", email="taken@example.com")

        conflict = client.post("/api/users/me/email", headers=headers, json={"email": "taken@example.com", "current_password": "Password123!"})
        assert conflict.status_code == 409
        assert "已被其他账号使用" in conflict.json()["detail"]

        same = client.post(
            "/api/users/me/email", headers=headers, json={"email": "owner_user@example.com", "current_password": "Password123!"}
        )
        assert same.status_code == 409


# ---- 5. 未验证闸门 ----


def test_unverified_account_is_gated_but_super_admin_is_exempt():
    with TestClient(app) as client:
        with TestingSession() as db:
            legacy = User(username="legacy_user", nickname="存量用户", password_hash=hash_password("Password123!"))
            db.add(legacy)
            db.commit()
            legacy_id = legacy.id
        legacy_headers = {"Authorization": f"Bearer {create_access_token(legacy_id)}"}

        # 未验证也能读到自己的状态，前端据此弹强制绑定框
        me = client.get("/api/auth/me", headers=legacy_headers)
        assert me.status_code == 200
        assert me.json()["email_gate_required"] is True
        assert me.json()["email_verified"] is False

        # 但写操作被闸门挡住
        blocked = client.post("/api/board", headers=legacy_headers, json={"content": "未验证不该能发帖"})
        assert blocked.status_code == 403
        assert "请先完成邮箱验证" in blocked.json()["detail"]

        # 绑定邮箱这类动作仍然放行（这是唯一的出路）
        allowed = client.post(
            "/api/users/me/email", headers=legacy_headers, json={"email": "legacy_user@example.com", "current_password": "Password123!"}
        )
        assert allowed.status_code == 200, allowed.text

        # 走完验证后恢复可用
        assert client.post(
            "/api/auth/email/confirm", json={"token": token_from("legacy_user@example.com")}
        ).status_code == 200
        assert client.get("/api/auth/me", headers=legacy_headers).status_code == 401
        legacy_headers = {"Authorization": f"Bearer {login(client, 'legacy_user').json()['access_token']}"}
        assert client.post("/api/board", headers=legacy_headers, json={"content": "验证后可以发帖"}).status_code == 201

        # 超级管理员（运维救援账号）不受闸门限制
        admin_login = client.post("/api/auth/login", json={"username": "admin", "password": "Admin123!"})
        assert admin_login.status_code == 200
        admin = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}
        assert client.get("/api/auth/me", headers=admin).json()["email_gate_required"] is False
        assert client.post("/api/board", headers=admin, json={"content": "管理员不受闸门限制"}).status_code == 201


def test_gate_can_be_disabled_for_rescue():
    with TestClient(app) as client:
        with TestingSession() as db:
            legacy = User(username="rescue_user", nickname="存量用户", password_hash=hash_password("Password123!"))
            db.add(legacy)
            db.commit()
            legacy_id = legacy.id
        legacy_headers = {"Authorization": f"Bearer {create_access_token(legacy_id)}"}

        assert client.post("/api/board", headers=legacy_headers, json={"content": "先被挡住"}).status_code == 403
        # 邮件配置坏掉时的救援开关
        settings.require_email_verification = False
        assert client.post("/api/board", headers=legacy_headers, json={"content": "关掉闸门后可发"}).status_code == 201


# ---- 6. 邮件服务不可用：fail-closed ----


def test_registration_fails_closed_when_mail_service_unavailable(monkeypatch):
    with TestClient(app) as client:
        # 模拟「EMAIL_DELIVERY=smtp 但凭据缺失」：发信直接抛未配置
        monkeypatch.setattr(mailer, "delivery_is_local", lambda: False)
        monkeypatch.setattr(settings, "smtp_username", "")
        monkeypatch.setattr(settings, "email_from_address", "")

        response = client.post(
            "/api/auth/register",
            json={
                "username": "no_mail_user",
                "password": "Password123!",
                "nickname": "收不到信",
                "email": "no_mail_user@example.com",
            },
        )
        assert response.status_code == 503
        assert "邮件服务" in response.json()["detail"]

        # 事务回滚：不能留下「建好了却收不到验证信」的半成品账号
        with TestingSession() as db:
            assert db.scalar(select(User).where(User.username == "no_mail_user")) is None
            assert db.scalars(select(EmailToken)).all() == []


# ---- 7. 通知开关 ----


def test_notification_switch_is_respected():
    with TestClient(app) as client:
        publisher, publisher_mail = auth(client, "notify_pub")
        taker, taker_mail = auth(client, "notify_taker")

        # 委托人是发布委托的必要条件：先填 QQ
        me = client.get("/api/auth/me", headers=publisher).json()
        assert client.patch(
            "/api/users/me",
            headers=publisher,
            json={"nickname": me["nickname"], "qq": "1000000001", "bio": None},
        ).status_code == 200

        task = client.post(
            "/api/tasks",
            headers=publisher,
            json={
                "title": "通知开关测试委托",
                "description": "用于验证关掉通知后不再收到事件邮件。",
                "category": "其他委托",
                "pay_type": "free",
                "expires_in_days": 1,
            },
        )
        assert task.status_code == 201, task.text
        task_id = task.json()["id"]

        # 打开通知时，接取委托会给委托人发信
        mailer.OUTBOX.clear()
        assert client.post(f"/api/tasks/{task_id}/accept", headers=taker, json={}).status_code == 200
        assert any("有人接取了你的委托" in item["subject"] for item in mails_to(publisher_mail))
        # 发起接取的人自己不该收到通知
        assert mails_to(taker_mail) == []

        # 委托人关掉通知后，后续事件不再发信给他
        assert client.patch(
            "/api/users/me/email-notify", headers=publisher, json={"notify_email": False}
        ).status_code == 200
        mailer.OUTBOX.clear()
        assert client.post(f"/api/tasks/{task_id}/start", headers=publisher, json={}).status_code == 200
        assert mails_to(publisher_mail) == []


def test_notification_skips_accounts_without_verified_email():
    with TestClient(app) as client:
        with TestingSession() as db:
            stranger = User(
                username="no_mail_publisher",
                nickname="没邮箱的委托人",
                password_hash=hash_password("Password123!"),
                qq="1000000002",
                email_verified=False,
            )
            db.add(stranger)
            db.commit()
            stranger_id = stranger.id
        stranger_headers = {"Authorization": f"Bearer {create_access_token(stranger_id)}"}
        settings.require_email_verification = False  # 放行发委托，专测通知条件

        task = client.post(
            "/api/tasks",
            headers=stranger_headers,
            json={
                "title": "无邮箱账号的委托",
                "description": "未验证邮箱的账号不应收到事件邮件。",
                "category": "其他委托",
                "pay_type": "free",
                "expires_in_days": 1,
            },
        )
        assert task.status_code == 201, task.text
        taker, _ = auth(client, "notify_taker2")
        mailer.OUTBOX.clear()
        assert client.post(f"/api/tasks/{task.json()['id']}/accept", headers=taker, json={}).status_code == 200
        # 没有邮箱可发，整个信箱里不该出现任何寄给该账号的信
        assert all(item["to"] != "no_mail_publisher@example.com" for item in mailer.OUTBOX)
