"""安全回归：媒体泄露、分区签名访问、图片净化、越权细节。

这些用例覆盖本轮加固的每条结论，任何一条回归都会立刻在这里失败：

- 未过审头像 / 待审图片的地址不再从列表接口泄露；
- 待审与被屏蔽的媒体在私有区，只有有效签名才能读取，撤回后旧公开地址立即失效；
- 上传图片会剥掉 EXIF（含 GPS）并限制像素与长边；
- 称号等权限边界与备案链接协议校验。
"""

import re
import time
from io import BytesIO
from pathlib import Path
from urllib.parse import unquote

from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import images as images_module
from app import mailer
from app.config import settings
from app.database import Base, get_db
from app.main import app, sync_media_zones
from app.media import sign_media_signature, sign_media_url, verify_media_signature
from app.models import User, UserPhoto
from app.ratelimit import limiter
from app.security import hash_password

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def override_db():
    with TestingSession() as db:
        yield db


app.dependency_overrides[get_db] = override_db


def setup_function():
    # 多个测试模块共用同一个 app，各自在 import 时设置过 get_db 覆盖，
    # 因此这里每次用例前重新指向本模块的内存库，避免被其它模块的覆盖抢走。
    app.dependency_overrides[get_db] = override_db
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    # 邮箱相关：走本地信箱、关掉发信冷却，保持用例简短。
    settings.email_delivery = "log"
    settings.email_send_cooldown_seconds = 0
    mailer.OUTBOX.clear()
    with TestingSession() as db:
        db.add(User(username="admin", nickname="管理员", password_hash=hash_password("Admin123!"), is_admin=True))
        db.commit()


def last_mail_token() -> str:
    assert mailer.OUTBOX, "本地信箱里没有邮件"
    match = re.search(r"[?&]token=([^&\s]+)", mailer.OUTBOX[-1]["text"])
    assert match, f"邮件正文里没有找到令牌：{mailer.OUTBOX[-1]['text']}"
    return unquote(match.group(1))


def auth(client, username, password="Password123!"):
    """注册 + 完成邮箱验证 + 登录（注册不再直接返回令牌）。"""
    assert client.post(
        "/api/auth/register",
        json={
            "username": username,
            "password": password,
            "nickname": f"用户{username}",
            "email": f"{username}@example.com",
        },
    ).status_code == 201
    assert client.post("/api/auth/email/confirm", json={"token": last_mail_token()}).status_code == 200
    login = client.post("/api/auth/login", json={"username": username, "password": password})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def admin_headers(client):
    login = client.post("/api/auth/login", json={"username": "admin", "password": "Admin123!"})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def me_id(client, headers):
    return client.get("/api/auth/me", headers=headers).json()["id"]


def make_png(size=(4, 4), color=(1, 2, 3, 255)) -> bytes:
    buffer = BytesIO()
    Image.new("RGBA", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def make_exif_jpeg(size=(8, 8)) -> bytes:
    """带设备信息与 GPS 的 JPEG。"""
    buffer = BytesIO()
    exif = Image.Exif()
    exif[0x010F] = "SecretCam"  # Make
    exif[0x0110] = "SecretModel"  # Model
    exif[0x0112] = 1  # Orientation
    exif[0x8825] = {1: "N"}  # GPSInfo（纬度参考）
    Image.new("RGB", size, (9, 9, 9)).save(buffer, format="JPEG", exif=exif)
    return buffer.getvalue()


def media_path(tmp_path: Path, url: str) -> Path:
    """把接口返回的媒体地址还原成磁盘路径（公开区 /uploads/，私有区 /api/media/）。"""
    if url.startswith("/api/media/"):
        key = url.removeprefix("/api/media/").split("?", 1)[0]
        return tmp_path / "private_media" / key
    return tmp_path / "uploads" / url.removeprefix("/uploads/")


# ---- 信息泄露：未过审媒体不得从列表接口出现 ----------------


def test_sugar_endpoints_do_not_leak_unapproved_media(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "sugar_upload_dir", str(tmp_path / "uploads"))
    with TestClient(app) as client:
        alice = auth(client, "leak_alice")
        bob = auth(client, "leak_bob")
        alice_id = me_id(client, alice)

        # 未过审头像 + 一条被屏蔽的介绍图片
        assert client.post(
            "/api/users/me/avatar", headers=alice, files={"avatar": ("a.png", make_png(), "image/png")}
        ).status_code == 201
        with TestingSession() as db:
            db.add(UserPhoto(user_id=alice_id, file_path=f"users/{alice_id}/hidden.png", is_visible=False))
            db.commit()
            hidden_file = tmp_path / "private_media" / f"users/{alice_id}/hidden.png"
            hidden_file.parent.mkdir(parents=True, exist_ok=True)
            hidden_file.write_bytes(make_png())

        # 建立砂糖档案（需要至少一张可见照片）；关系双方都必须先有档案
        for headers, name in ((alice, "alice"), (bob, "bob")):
            assert client.post(
                "/api/sugar/profile", headers=headers, data={"about": f"{name} 的砂糖介绍"},
                files=[("photos", ("p.png", make_png(), "image/png"))],
            ).status_code == 201

        for url in ("/api/sugar/profiles", f"/api/sugar/profiles/{alice_id}"):
            payload = client.get(url, headers=bob)
            assert payload.status_code == 200, payload.text
            body = payload.json()
            entry = body if url.endswith(str(alice_id)) else next(p for p in body if p["user"]["id"] == alice_id)
            # 未过审头像对外不可见
            assert entry["user"]["avatar_url"] is None
            # 被屏蔽的介绍图片不出现在其他人的响应里
            assert all("/hidden.png" not in (photo["image_url"] or "") for photo in entry["user"]["photos"])
            assert "hidden.png" not in payload.text

        # 上榜（砂糖关系）同样不能把未过审头像带出去
        bob_id = me_id(client, bob)
        assert alice_id != bob_id
        assert client.post(f"/api/sugar/pairs/{bob_id}/confirm", headers=alice).status_code == 201
        assert client.post(f"/api/sugar/pairs/{alice_id}/confirm", headers=bob).status_code == 201
        top = client.get("/api/sugar/pairs/top", headers=bob)
        assert top.status_code == 200
        assert "avatars/" not in top.text
        assert "hidden.png" not in top.text


def test_admin_feedback_does_not_leak_unapproved_avatar(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "sugar_upload_dir", str(tmp_path / "uploads"))
    with TestClient(app) as client:
        user = auth(client, "fb_avatar")
        assert client.post(
            "/api/users/me/avatar", headers=user, files={"avatar": ("a.png", make_png(), "image/png")}
        ).status_code == 201
        assert client.post("/api/feedback", headers=user, json={"content": "建议加暗色模式"}).status_code == 201

        listed = client.get("/api/admin/feedback", headers=admin_headers(client))
        assert listed.status_code == 200, listed.text
        assert "avatars/" not in listed.text


# ---- 分区与签名访问 ----------------


def test_pending_media_is_private_and_moves_zones_on_moderation(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "sugar_upload_dir", str(tmp_path / "uploads"))
    with TestClient(app) as client:
        alice = auth(client, "zone_alice")
        admin = admin_headers(client)
        alice_id = me_id(client, alice)

        uploaded = client.post(
            "/api/users/me/avatar", headers=alice, files={"avatar": ("a.png", make_png(), "image/png")}
        )
        assert uploaded.status_code == 201, uploaded.text
        pending_url = uploaded.json()["avatar_url"]
        # 待审 → 私有区签名地址，且文件确实不在公开目录里
        assert pending_url.startswith("/api/media/")
        assert media_path(tmp_path, pending_url).is_file()
        assert not list((tmp_path / "uploads" / "avatars").rglob("*.png"))

        # 审核通过 → 搬进公开区，地址变成 /uploads/
        client.patch(f"/api/admin/users/{alice_id}/avatar", headers=admin, json={"is_visible": True})
        approved = client.get("/api/auth/me", headers=alice).json()["avatar_url"]
        assert approved.startswith("/uploads/avatars/")
        assert media_path(tmp_path, approved).is_file()

        # 再次屏蔽 → 撤回立即生效：旧公开地址对应的文件已不在公开目录
        client.patch(f"/api/admin/users/{alice_id}/avatar", headers=admin, json={"is_visible": False})
        assert not media_path(tmp_path, approved).exists()
        hidden_url = client.get("/api/auth/me", headers=alice).json()["avatar_url"]
        assert hidden_url.startswith("/api/media/")
        assert media_path(tmp_path, hidden_url).is_file()


def test_gated_media_requires_valid_signature(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "sugar_upload_dir", str(tmp_path / "uploads"))
    with TestClient(app) as client:
        alice = auth(client, "gate_alice")
        uploaded = client.post(
            "/api/users/me/avatar", headers=alice, files={"avatar": ("a.png", make_png(), "image/png")}
        )
        signed_url = uploaded.json()["avatar_url"]
        bare = signed_url.split("?", 1)[0]

        assert client.get(signed_url).status_code == 200
        # 无签名 / 伪造签名 / 换 key 复用签名 一律 404
        assert client.get(bare).status_code == 404
        assert client.get(f"{bare}?exp=99999999999&sig=forgedsignature").status_code == 404
        forged = sign_media_url("sugar/other.png")
        assert client.get(f"{bare}?{forged.split('?', 1)[1]}").status_code == 404
        # 不存在的文件也 404（签名有效但文件缺失）
        assert client.get(sign_media_url("avatars/404/missing.png")).status_code == 404


def test_signature_window_rejects_expired_and_preissued():
    key = "sugar/demo.png"
    now = int(time.time())
    assert verify_media_signature(key, now + 60, sign_media_signature(key, now + 60))
    # 已过期
    assert not verify_media_signature(key, now - 1, sign_media_signature(key, now - 1))
    # 超前签发（超过配置的 TTL + 容差）
    far = now + settings.media_token_ttl_seconds + 3600
    assert not verify_media_signature(key, far, sign_media_signature(key, far))
    # 篡改 key
    assert not verify_media_signature(key + "x", now + 60, sign_media_signature(key, now + 60))


def test_sync_media_zones_moves_legacy_hidden_files(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "sugar_upload_dir", str(tmp_path / "uploads"))
    public_file = tmp_path / "uploads" / "sugar" / "legacy.png"
    public_file.parent.mkdir(parents=True, exist_ok=True)
    public_file.write_bytes(make_png())

    with TestingSession() as db:
        legacy_user = User(username="legacy", nickname="老用户", password_hash="unused")
        db.add(legacy_user)
        db.commit()
        db.add(UserPhoto(user_id=legacy_user.id, file_path="sugar/legacy.png", is_visible=False))
        db.commit()
        sync_media_zones(db)

    # 升级前被屏蔽、却还留在公开区的文件，启动对账后应搬进私有区
    assert not public_file.exists()
    assert (tmp_path / "private_media" / "sugar" / "legacy.png").is_file()


# ---- 图片净化 ----------------


def test_upload_strips_exif_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "sugar_upload_dir", str(tmp_path / "uploads"))
    with TestClient(app) as client:
        user = auth(client, "exif_user")
        uploaded = client.post(
            "/api/users/me/photos", headers=user,
            files=[("photos", ("photo.jpg", make_exif_jpeg(), "image/jpeg"))],
        )
        assert uploaded.status_code == 201, uploaded.text
        stored = media_path(tmp_path, uploaded.json()["photos"][0]["image_url"])
        assert stored.is_file()

        with Image.open(stored) as saved:
            exif = saved.getexif()
        assert 0x010F not in exif  # Make
        assert 0x0110 not in exif  # Model
        assert 0x8825 not in exif  # GPSInfo
        assert len(exif) == 0


def test_upload_rejects_pixel_bomb_and_downscales_large_images(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "sugar_upload_dir", str(tmp_path / "uploads"))
    monkeypatch.setattr(images_module, "MAX_IMAGE_PIXELS", 100)
    monkeypatch.setattr(images_module, "MAX_IMAGE_EDGE", 32)
    with TestClient(app) as client:
        user = auth(client, "pixel_user")

        # 超过像素上限 → 422（先看文件头，不解码炸弹）
        too_many = client.post(
            "/api/users/me/photos", headers=user,
            files=[("photos", ("big.png", make_png(size=(20, 20)), "image/png"))],
        )
        assert too_many.status_code == 422
        assert "像素过大" in too_many.json()["detail"]

        # 长边超限 → 等比缩小
        wide = client.post(
            "/api/users/me/photos", headers=user,
            files=[("photos", ("wide.png", make_png(size=(40, 10)), "image/png"))],
        )
        assert wide.status_code == 422  # 40*10=400 > 100 像素上限，先被拦下
        monkeypatch.setattr(images_module, "MAX_IMAGE_PIXELS", 25_000_000)
        ok = client.post(
            "/api/users/me/photos", headers=user,
            files=[("photos", ("wide.png", make_png(size=(200, 100)), "image/png"))],
        )
        assert ok.status_code == 201, ok.text
        with Image.open(media_path(tmp_path, ok.json()["photos"][0]["image_url"])) as saved:
            assert max(saved.size) == 32


def test_animated_gif_keeps_only_first_frame(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "sugar_upload_dir", str(tmp_path / "uploads"))
    frames = [Image.new("RGB", (8, 8), color) for color in ((255, 0, 0), (0, 255, 0), (0, 0, 255))]
    buffer = BytesIO()
    frames[0].save(buffer, format="GIF", save_all=True, append_images=frames[1:], duration=100)
    with TestClient(app) as client:
        user = auth(client, "gif_user")
        uploaded = client.post(
            "/api/users/me/photos", headers=user,
            files=[("photos", ("anim.gif", buffer.getvalue(), "image/gif"))],
        )
        assert uploaded.status_code == 201, uploaded.text
        with Image.open(media_path(tmp_path, uploaded.json()["photos"][0]["image_url"])) as saved:
            assert getattr(saved, "n_frames", 1) == 1


def test_unreadable_image_is_rejected():
    with TestClient(app) as client:
        user = auth(client, "broken_user")
        response = client.post(
            "/api/users/me/photos", headers=user,
            files=[("photos", ("fake.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 64, "image/png"))],
        )
        assert response.status_code == 422
        assert "无法解析" in response.json()["detail"]


# ---- 越权与配置 ----------------


def test_only_super_admin_can_retitle_protected_roles():
    with TestClient(app) as client:
        admin = admin_headers(client)
        superadmin_id = me_id(client, admin)

        first_staff = auth(client, "title_staff_a")
        first_id = me_id(client, first_staff)
        second_staff = auth(client, "title_staff_b")
        second_id = me_id(client, second_staff)
        for uid in (first_id, second_id):
            assert client.patch(
                f"/api/admin/users/{uid}/role", headers=admin, json={"role": "staff"}
            ).status_code == 200

        plain = auth(client, "title_plain")
        plain_id = me_id(client, plain)

        # 管理员（staff）不能设置同为 staff 的账号称号，也不能设置超管的称号
        assert client.patch(
            f"/api/admin/users/{second_id}/title", headers=first_staff, json={"title": "越权称号"}
        ).status_code == 403
        assert client.patch(
            f"/api/admin/users/{superadmin_id}/title", headers=first_staff, json={"title": "越权称号"}
        ).status_code == 403
        # 普通用户仍可由管理员设置称号
        assert client.patch(
            f"/api/admin/users/{plain_id}/title", headers=first_staff, json={"title": "正式称号"}
        ).status_code == 200
        # 超管可以给管理员设称号
        assert client.patch(
            f"/api/admin/users/{second_id}/title", headers=admin, json={"title": "管理称号"}
        ).status_code == 200


def test_site_config_rejects_non_https_icp_url(monkeypatch):
    with TestClient(app) as client:
        monkeypatch.setattr(settings, "site_icp", "京ICP备00000000号")
        monkeypatch.setattr(settings, "site_icp_url", "javascript:alert(1)")
        payload = client.get("/api/site-config").json()
        assert payload["icp"] == "京ICP备00000000号"
        assert payload["icp_url"].startswith("https://")

        monkeypatch.setattr(settings, "site_icp_url", "https://beian.example.com/")
        assert client.get("/api/site-config").json()["icp_url"] == "https://beian.example.com/"


def test_rate_limiter_blocks_after_limit():
    bucket = f"test-bucket-{time.time()}"
    for _ in range(3):
        limiter.hit(bucket, 3, 60)
    try:
        limiter.hit(bucket, 3, 60)
    except HTTPException as error:
        assert error.status_code == 429
        assert "Retry-After" in (error.headers or {})
    else:  # pragma: no cover - 断言失败路径
        raise AssertionError("超过限额后应当抛出 429")
