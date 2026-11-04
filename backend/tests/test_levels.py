"""信誉等级：门槛、接单上限与悬赏权限。"""
from fastapi.testclient import TestClient

from app.database import get_db
from app.levels import level_for, next_threshold
from app.main import app

import test_api as api_tests
from test_api import auth, set_qq

from test_points import publish_task, top_up


def setup_function():
    api_tests.setup_function()
    app.dependency_overrides[get_db] = api_tests.override_db


def test_level_thresholds():
    assert level_for(0) == 1
    assert level_for(49) == 1
    assert level_for(50) == 2
    assert level_for(149) == 2
    assert level_for(150) == 3
    assert level_for(8000) == 10
    assert level_for(99999) == 10
    assert next_threshold(0) == 50
    assert next_threshold(8000) is None


def test_bounty_requires_level_three():
    with TestClient(app) as client:
        publisher = auth(client, "level_pub")
        set_qq(client, publisher, "1000000000")

        info = client.get("/api/levels/me", headers=publisher).json()
        assert info["level"] == 1
        assert info["can_post_bounty"] is False
        assert info["taker_limit"] >= 2

        denied = publish_task(client, publisher, bounty_points=1)
        assert denied.status_code == 403
        assert "Lv3" in denied.json()["detail"]

        top_up(client, publisher, 150)
        info = client.get("/api/levels/me", headers=publisher).json()
        assert info["level"] == 3
        assert info["can_post_bounty"] is True
        assert info["bounty_cap"] == 60
        # Lv3：接单上限 = 2 + 3 // 3 = 3
        assert info["taker_limit"] == 3

        created = publish_task(client, publisher, bounty_points=60)
        assert created.status_code == 201, created.text
        over = publish_task(client, publisher, bounty_points=61)
        assert over.status_code == 422
        assert "悬赏上限" in over.json()["detail"]


def test_public_profile_exposes_level_and_lifetime():
    with TestClient(app) as client:
        user = auth(client, "level_public")
        set_qq(client, user, "1000000000")
        top_up(client, user, 350)
        me = client.get("/api/auth/me", headers=user).json()
        assert me["level"] == 4
        public = client.get(f"/api/users/{me['id']}", headers=user).json()
        assert public["lifetime_points"] == 350
        assert public["level"] == 4
