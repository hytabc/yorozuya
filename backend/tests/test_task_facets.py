"""委托模块化标签：白名单、上限、筛选与旧委托兼容。"""
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app

import test_api as api_tests
from test_api import auth, create_task, set_qq


def setup_function():
    # 多个测试模块共用 app 与 test_api 的内存库，必须每次重新指向覆盖。
    api_tests.setup_function()
    app.dependency_overrides[get_db] = api_tests.override_db


def publish(client, headers, title, facets, **extra):
    if not client.get("/api/auth/me", headers=headers).json().get("qq"):
        set_qq(client, headers, "1000000000")
    payload = {
        "title": title,
        "description": "用于验证委托模块化标签的正文内容，长度满足限制。",
        "category": "技术疑难",
        "expires_in_days": 2,
        "facets": facets,
        **extra,
    }
    return client.post("/api/tasks", headers=headers, json=payload)


def facet_pairs(task):
    return {(item["facet_type"], item["value"]) for item in task["facets"]}


def test_create_task_stores_and_returns_facets():
    with TestClient(app) as client:
        publisher = auth(client, "facet_pub")
        created = publish(
            client,
            publisher,
            "带标签的委托",
            [
                {"facet_type": "skill", "value": "Blender"},
                {"facet_type": "skill", "value": "Unity"},
                # 重复标签会被静默去重，避免唯一约束报错。
                {"facet_type": "skill", "value": "Blender"},
                {"facet_type": "platform", "value": "PCVR"},
                {"facet_type": "atmosphere", "value": "语音沟通"},
                {"facet_type": "world", "value": "示例世界"},
            ],
        )
        assert created.status_code == 201, created.text
        task = created.json()
        assert facet_pairs(task) == {
            ("skill", "Blender"),
            ("skill", "Unity"),
            ("platform", "PCVR"),
            ("atmosphere", "语音沟通"),
            ("world", "示例世界"),
        }
        assert [item["value"] for item in task["facets"]][:2] == ["Blender", "Unity"]

        listed = client.get("/api/tasks").json()
        assert facet_pairs(listed[0]) == facet_pairs(task)
        detail = client.get(f"/api/tasks/{task['id']}").json()
        assert facet_pairs(detail) == facet_pairs(task)


def test_invalid_facets_are_rejected():
    with TestClient(app) as client:
        publisher = auth(client, "facet_bad")

        unknown_skill = publish(
            client, publisher, "未知技能", [{"facet_type": "skill", "value": "不存在的技能"}]
        )
        assert unknown_skill.status_code == 422
        assert "技能标签不在允许范围内" in unknown_skill.json()["detail"]

        too_many_skills = publish(
            client,
            publisher,
            "技能超量",
            [
                {"facet_type": "skill", "value": "Blender"},
                {"facet_type": "skill", "value": "Unity"},
                {"facet_type": "skill", "value": "PhysBones"},
                {"facet_type": "skill", "value": "lilToon"},
                {"facet_type": "skill", "value": "Udon"},
                {"facet_type": "skill", "value": "VRChat SDK"},
                {"facet_type": "skill", "value": "灯光"},
            ],
        )
        assert too_many_skills.status_code == 422
        assert "技能最多选择 6 个" in too_many_skills.json()["detail"]

        long_world = publish(
            client,
            publisher,
            "World 名称过长",
            [{"facet_type": "world", "value": "世" * 61}],
        )
        assert long_world.status_code == 422
        assert "60 个字符" in long_world.json()["detail"]

        # 类型不在 Literal 白名单内，由 Pydantic 直接拦下。
        bad_type = publish(
            client, publisher, "未知类型", [{"facet_type": "color", "value": "红色"}]
        )
        assert bad_type.status_code == 422

        # 校验失败不会留下半成品委托。
        assert client.get("/api/tasks").json() == []


def test_facet_filters_and_legacy_tasks():
    with TestClient(app) as client:
        publisher = auth(client, "facet_filter")

        blender = publish(
            client,
            publisher,
            "Blender 委托",
            [
                {"facet_type": "skill", "value": "Blender"},
                {"facet_type": "platform", "value": "PCVR"},
                {"facet_type": "atmosphere", "value": "可录屏"},
            ],
        ).json()
        unity = publish(
            client,
            publisher,
            "Unity 委托",
            [
                {"facet_type": "skill", "value": "Unity"},
                {"facet_type": "platform", "value": "Quest"},
            ],
        ).json()
        # 旧委托：不带 facets 字段也应正常创建并返回空数组。
        legacy = create_task(client, publisher, required=None, title="没有标签的委托")
        assert legacy["facets"] == []

        assert [item["id"] for item in client.get("/api/tasks", params={"skill": "Blender"}).json()] == [blender["id"]]
        assert [item["id"] for item in client.get("/api/tasks", params={"platform": "Quest"}).json()] == [unity["id"]]
        assert [
            item["id"] for item in client.get("/api/tasks", params={"atmosphere": "可录屏"}).json()
        ] == [blender["id"]]
        # 多个筛选条件之间是「且」，不匹配时结果为空。
        assert client.get("/api/tasks", params={"skill": "Unity", "platform": "PCVR"}).json() == []
        assert len(client.get("/api/tasks").json()) == 3


def test_update_facets_permissions_and_started_window():
    with TestClient(app) as client:
        publisher = auth(client, "facet_edit_pub")
        other = auth(client, "facet_edit_other")
        taker = auth(client, "facet_edit_taker", role="volunteer")
        task = create_task(client, publisher, required=1)
        task_id = task["id"]

        replaced = client.patch(
            f"/api/tasks/{task_id}/facets",
            headers=publisher,
            json={"facets": [{"facet_type": "skill", "value": "世界优化"}]},
        )
        assert replaced.status_code == 200, replaced.text
        assert facet_pairs(replaced.json()) == {("skill", "世界优化")}

        assert client.patch(
            f"/api/tasks/{task_id}/facets",
            headers=other,
            json={"facets": [{"facet_type": "skill", "value": "音频"}]},
        ).status_code == 403

        assert client.post(
            f"/api/tasks/{task_id}/accept", headers=taker, json={"password": "facet-pw-1"}
        ).status_code == 200

        started = client.patch(
            f"/api/tasks/{task_id}/facets",
            headers=publisher,
            json={"facets": [{"facet_type": "skill", "value": "音频"}]},
        )
        assert started.status_code == 409
        assert "不能再修改标签" in started.json()["detail"]

        # 清空标签也是合法操作。
        task2 = create_task(client, publisher, required=2, title="待清空标签")
        client.patch(
            f"/api/tasks/{task2['id']}/facets",
            headers=publisher,
            json={"facets": [{"facet_type": "platform", "value": "Desktop"}]},
        )
        cleared = client.patch(
            f"/api/tasks/{task2['id']}/facets", headers=publisher, json={"facets": []}
        )
        assert cleared.status_code == 200
        assert cleared.json()["facets"] == []


def test_facet_catalog_counts_only_published_visible_tasks():
    with TestClient(app) as client:
        publisher = auth(client, "facet_catalog")
        publish(
            client,
            publisher,
            "目录计数甲",
            [{"facet_type": "skill", "value": "Blender"}, {"facet_type": "platform", "value": "PCVR"}],
        )
        publish(
            client,
            publisher,
            "目录计数乙",
            [{"facet_type": "skill", "value": "Blender"}],
        )
        catalog = client.get("/api/tasks/facets")
        assert catalog.status_code == 200
        data = catalog.json()
        skills = {item["value"]: item["count"] for item in data["skills"]}
        assert skills["Blender"] == 2
        assert skills["Unity"] == 0
        assert data["limits"] == {"skill": 6, "platform": 2, "world": 3, "atmosphere": 5}
        assert any(group["key"] == "contact" for group in data["atmospheres"])
        # 目录接口不能被 /api/tasks/{task_id} 吞掉。
        assert "skills" in data
