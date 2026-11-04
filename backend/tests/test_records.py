"""人生记录：汇总完成数、评分、成就与分类偏好。"""
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app

import test_api as api_tests
from test_api import auth, create_task, set_qq


def setup_function():
    api_tests.setup_function()
    app.dependency_overrides[get_db] = api_tests.override_db


def test_records_summarise_real_activity():
    with TestClient(app) as client:
        publisher = auth(client, "rec_pub")
        taker = auth(client, "rec_taker", role="volunteer")
        set_qq(client, publisher, "1000000000")

        empty = client.get(f"/api/users/{client.get('/api/auth/me', headers=taker).json()['id']}/records").json()
        assert empty["completed_taken"] == 0
        assert empty["completed_published"] == 0

        task = create_task(client, publisher, required=1)
        client.post(f"/api/tasks/{task['id']}/accept", headers=taker)
        client.post(f"/api/tasks/{task['id']}/confirm", headers=taker)
        client.post(f"/api/tasks/{task['id']}/confirm", headers=publisher)

        taker_id = client.get("/api/auth/me", headers=taker).json()["id"]
        publisher_id = client.get("/api/auth/me", headers=publisher).json()["id"]
        ratings = client.post(
            f"/api/tasks/{task['id']}/ratings",
            headers=publisher,
            json={"ratee_id": taker_id, "stars_half": 10, "comment": "很好"},
        )
        assert ratings.status_code == 201

        taker_records = client.get(f"/api/users/{taker_id}/records").json()
        assert taker_records["completed_taken"] == 1
        assert taker_records["completed_published"] == 0
        assert taker_records["taker_rating"]["count"] == 1
        assert taker_records["first_completed_at"] is not None
        assert taker_records["top_categories"][0]["category"] == "技术疑难"
        assert taker_records["level"] >= 1

        publisher_records = client.get(f"/api/users/{publisher_id}/records").json()
        assert publisher_records["completed_published"] == 1
        assert publisher_records["published_total"] == 1

        assert client.get("/api/users/999999/records").status_code == 404
