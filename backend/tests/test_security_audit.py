"""安全审计回归：凭证撤销、真实限流、媒体失败、可信邮件来源。"""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

import test_email_flow as email_tests
from app import main, media, ratelimit
from app.config import Settings, settings
from app.database import Base
from app.email_flow import (
    CHANGE_EMAIL, RESET_PASSWORD, base_url, consume_link_token, issue_link_token,
    lock_credentials, revoke_credentials,
)
from app.models import EmailToken, Task, User, UserPhoto
from app.security import hash_password
from test_api import make_png


def setup_function():
    email_tests.setup_function()


def enable_limits(monkeypatch):
    # 显式启用真实实现，不修改 sys.modules 或干扰验证码/pytest 本身。
    limiter = ratelimit.SlidingWindowLimiter()
    monkeypatch.setattr(ratelimit, "limiter", limiter)
    monkeypatch.setattr(ratelimit, "_testing", lambda: False)


@pytest.mark.parametrize("password,status", [(None, 422), ("wrong", 403)])
def test_binding_requires_current_password(password, status):
    with TestClient(main.app) as client:
        headers, _ = email_tests.auth(client, "bind_auth")
        payload = {"email": "new@example.com"}
        if password is not None:
            payload["current_password"] = password
        count = len(email_tests.mailer.OUTBOX)
        assert client.post("/api/users/me/email", headers=headers, json=payload).status_code == status
        assert len(email_tests.mailer.OUTBOX) == count
        assert client.get("/api/auth/me", headers=headers).json()["pending_email"] is None


@pytest.mark.parametrize("action", ["password", "admin", "reset", "email"])
def test_sensitive_change_revokes_every_old_link_and_session(action):
    with TestClient(main.app) as client:
        headers, address = email_tests.auth(client, "revoke_all")
        uid = client.get("/api/auth/me", headers=headers).json()["id"]
        assert client.post("/api/auth/password-reset/request", json={"account": address}).status_code == 200
        reset = email_tests.token_from(address)
        assert client.post("/api/users/me/email", headers=headers, json={
            "email": "next@example.com", "current_password": "Password123!",
        }).status_code == 200
        binding = email_tests.token_from("next@example.com")
        if action == "password":
            response = client.patch("/api/users/me/password", headers=headers, json={
                "current_password": "Password123!", "password": "Changed123!",
            })
        elif action == "admin":
            admin = email_tests.login(client, "admin", "Admin123!").json()["access_token"]
            response = client.patch(f"/api/admin/users/{uid}/password", headers={"Authorization": f"Bearer {admin}"}, json={"password": "Changed123!"})
        elif action == "reset":
            response = client.post("/api/auth/password-reset/confirm", json={"token": reset, "password": "Changed123!"})
        else:
            response = client.post("/api/auth/email/confirm", json={"token": binding})
        assert response.status_code == 200, response.text
        assert client.get("/api/auth/me", headers=headers).status_code == 401
        assert client.post("/api/auth/password-reset/confirm", json={"token": reset, "password": "Replay123!"}).status_code == 422
        assert client.post("/api/auth/email/confirm", json={"token": binding}).status_code == 422
        with email_tests.TestingSession() as db:
            assert db.get(User, uid).pending_email is None
            assert not db.scalars(select(EmailToken).where(EmailToken.user_id == uid, EmailToken.used_at.is_(None))).all()


def credential_database(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'concurrent.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False)
    with sessions() as db:
        user = User(username="concurrent", nickname="并发", email="parallel@example.com", email_verified=True, password_hash=hash_password("Password123!"))
        db.add(user)
        db.flush()
        token = issue_link_token(db, user, CHANGE_EMAIL, ttl_minutes=30, new_email="next@example.com")
        uid = user.id
        db.commit()
    return engine, sessions, uid, token


def test_concurrent_link_consumption_has_one_winner(tmp_path):
    engine, sessions, _, token = credential_database(tmp_path)
    barrier = Barrier(2)
    def consume():
        with sessions() as db:
            barrier.wait(timeout=5)
            try:
                row = consume_link_token(db, CHANGE_EMAIL, token)
                user = db.get(User, row.user_id)
                user.email = row.new_email
                revoke_credentials(db, user)
                db.commit()
                return 200
            except HTTPException as error:
                return error.status_code
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: consume(), range(2)))
        assert results.count(200) == 1
        assert all(result in (200, 401, 422) for result in results)
    finally:
        engine.dispose()


def test_stale_request_cannot_issue_link_after_password_change(tmp_path):
    engine, sessions, uid, _ = credential_database(tmp_path)
    try:
        with sessions() as stale, sessions() as current:
            old_user = stale.get(User, uid)
            user = current.get(User, uid)
            lock_credentials(current, user)
            revoke_credentials(current, user)
            current.commit()
            with pytest.raises(HTTPException) as caught:
                issue_link_token(stale, old_user, CHANGE_EMAIL, ttl_minutes=30, new_email="stale@example.com")
            assert caught.value.status_code == 401
    finally:
        engine.dispose()


def test_old_database_token_migration_is_idempotent(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    try:
        Base.metadata.create_all(engine)
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE email_tokens DROP COLUMN credential_version"))
            conn.execute(text("INSERT INTO email_tokens (user_id,purpose,token_hash,salt,attempts,expires_at,created_at) VALUES (1,'change_email','hash','',0,'2099-01-01','2026-01-01')"))
        monkeypatch.setattr(main, "engine", engine)
        main.migrate_schema()
        main.migrate_schema()
        with engine.connect() as conn:
            version, used = conn.execute(text("SELECT credential_version, used_at FROM email_tokens")).one()
            assert version == -1 and used is not None
    finally:
        engine.dispose()


def test_login_aliases_share_account_limit(monkeypatch):
    with TestClient(main.app) as client:
        email_tests.auth(client, "rate_user")
        enable_limits(monkeypatch)
        names = ["rate_user", " rate_user ", "rate_user@example.com", "RATE_USER@EXAMPLE.COM"]
        for i in range(10):
            assert email_tests.login(client, names[i % 4], "wrong").status_code == 401
        response = email_tests.login(client, "  RATE_USER@EXAMPLE.COM ", "wrong")
        assert response.status_code == 429
        assert int(response.headers["Retry-After"]) > 0


def test_binding_password_attempts_are_limited(monkeypatch):
    with TestClient(main.app) as client:
        headers, _ = email_tests.auth(client, "bind_rate")
        enable_limits(monkeypatch)
        for i in range(11):
            response = client.post("/api/users/me/email", headers=headers, json={"email": "next@example.com", "current_password": "wrong"})
            assert response.status_code == (403 if i < 10 else 429)


def test_task_create_limit_stops_writes(monkeypatch):
    with TestClient(main.app) as client:
        headers, _ = email_tests.auth(client, "task_rate")
        assert client.patch("/api/users/me", headers=headers, json={"nickname": "限流用户", "qq": "12345678"}).status_code == 200
        enable_limits(monkeypatch)
        payload = {"title": "限流测试", "description": "用于确认超限不再写入数据库", "category": "other", "expires_in_days": 2}
        for _ in range(20):
            response = client.post("/api/tasks", headers=headers, json=payload)
            assert response.status_code == 201, response.text
        response = client.post("/api/tasks", headers=headers, json=payload)
        assert response.status_code == 429 and "Retry-After" in response.headers
        with email_tests.TestingSession() as db:
            assert len(db.scalars(select(Task)).all()) == 20


def test_mail_origin_ignores_host_and_forwarded_headers(monkeypatch):
    req = Request({"type": "http", "scheme": "http", "path": "/", "headers": [(b"host", b"attacker.example"), (b"x-forwarded-proto", b"javascript")]})
    monkeypatch.setattr(settings, "site_base_url", "https://example.com/")
    assert base_url(req) == "https://example.com"
    monkeypatch.setattr(settings, "site_base_url", "")
    with pytest.raises(HTTPException) as caught:
        base_url(req)
    assert caught.value.status_code == 503


@pytest.mark.parametrize("origin", ["", "http://example.com", "https://example.com/evil", "https://user:secret@example.com", "https://example.com?evil=1"])
def test_production_origin_rejects_unsafe_config(origin):
    with pytest.raises(RuntimeError):
        Settings(_env_file=None, behind_proxy=True, site_base_url=origin)


def test_local_origin_is_explicit():
    assert Settings(_env_file=None, behind_proxy=False, site_base_url="http://localhost:5173").site_base_url == "http://localhost:5173"


def uploaded_avatar(client, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "sugar_upload_dir", str(tmp_path / "uploads"))
    headers, _ = email_tests.auth(client, "media_owner")
    uid = client.get("/api/auth/me", headers=headers).json()["id"]
    response = client.post("/api/users/me/avatar", headers=headers, files={"avatar": ("a.png", make_png(), "image/png")})
    assert response.status_code == 201
    admin = {"Authorization": "Bearer " + email_tests.login(client, "admin", "Admin123!").json()["access_token"]}
    return headers, admin, uid, response.json()["avatar_url"].split("?", 1)[0].removeprefix("/api/media/")


def test_failed_revoke_returns_503_and_preserves_db(tmp_path, monkeypatch):
    with TestClient(main.app) as client:
        _, admin, uid, key = uploaded_avatar(client, monkeypatch, tmp_path)
        route = f"/api/admin/users/{uid}/avatar"
        assert client.patch(route, headers=admin, json={"is_visible": True}).status_code == 200
        def deny(*args, **kwargs):
            raise PermissionError("simulated")
        monkeypatch.setattr(media.shutil, "move", deny)
        assert client.patch(route, headers=admin, json={"is_visible": False}).status_code == 503
        with email_tests.TestingSession() as db:
            assert db.get(User, uid).avatar_visible is True
        assert media.storage_file(key, public=True).is_file()


def test_database_commit_failure_keeps_approval_private(tmp_path, monkeypatch):
    with TestClient(main.app, raise_server_exceptions=False) as client:
        _, admin, uid, key = uploaded_avatar(client, monkeypatch, tmp_path)
        def deny(*args, **kwargs):
            raise RuntimeError("simulated commit failure")
        monkeypatch.setattr(email_tests.TestingSession.class_, "commit", deny)
        assert client.patch(f"/api/admin/users/{uid}/avatar", headers=admin, json={"is_visible": True}).status_code == 503
        assert not media.storage_file(key, public=True).exists()
        assert client.get(f"/uploads/{key}").status_code == 404


def test_delete_failure_preserves_record_and_retry(tmp_path, monkeypatch):
    with TestClient(main.app) as client:
        headers, admin, uid, key = uploaded_avatar(client, monkeypatch, tmp_path)
        assert client.patch(f"/api/admin/users/{uid}/avatar", headers=admin, json={"is_visible": True}).status_code == 200
        original = Path.unlink
        def deny(path, *args, **kwargs):
            if path == media.storage_file(key, public=False):
                raise PermissionError("simulated")
            return original(path, *args, **kwargs)
        with monkeypatch.context() as m:
            m.setattr(Path, "unlink", deny)
            assert client.delete("/api/users/me/avatar", headers=headers).status_code == 503
        with email_tests.TestingSession() as db:
            assert db.get(User, uid).avatar_path == key
        assert client.get(f"/uploads/{key}").status_code == 404
        assert client.delete("/api/users/me/avatar", headers=headers).status_code == 200


def test_duplicate_and_orphan_public_files_fail_closed(tmp_path, monkeypatch):
    with TestClient(main.app) as client:
        _, _, _, key = uploaded_avatar(client, monkeypatch, tmp_path)
        media.write_media(key, make_png(), public=True)
        assert client.get(f"/uploads/{key}").status_code == 404
        media.place_media(key, public=False)
        assert not media.storage_file(key, public=True).exists()
        media.write_media("sugar/orphan.png", make_png(), public=True)
        assert client.get("/uploads/sugar/orphan.png").status_code == 404
        # 生活素材只放行服务端 UUID 形态的文件名，杜绝任意文件借这条捷径公开。
        asset_key = "life/" + "a" * 32 + ".png"
        media.write_media(asset_key, make_png(), public=True)
        assert client.get(f"/uploads/{asset_key}").status_code == 200
        media.write_media("life/anything.png", make_png(), public=True)
        assert client.get("/uploads/life/anything.png").status_code == 404
        assert client.get("/uploads/life/%2e%2e/sugar/orphan.png").status_code == 404


def test_startup_reconciliation_does_not_ignore_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "sugar_upload_dir", str(tmp_path / "uploads"))
    with email_tests.TestingSession() as db:
        admin = db.scalar(select(User).where(User.username == "admin"))
        db.add(UserPhoto(user_id=admin.id, file_path="sugar/hidden.png", is_visible=False))
        db.commit()
        media.write_media("sugar/hidden.png", make_png(), public=True)
        def deny(*args, **kwargs):
            raise PermissionError("simulated")
        monkeypatch.setattr(media.shutil, "move", deny)
        with pytest.raises(HTTPException):
            main.sync_media_zones(db)
