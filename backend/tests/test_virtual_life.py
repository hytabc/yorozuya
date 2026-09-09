import json
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.models import User, UserRole
from app.security import create_access_token
from app.virtual_life import GameState, router
from app.virtual_life_packs import get_active_pack, router as packs_router, seed_virtual_life_packs, validate_pack_content


def state():
    ids = ['ache', 'xiaomi', 'maoyou', 'yu']
    return dict(schemaVersion=1, day=9, stats=dict(mood=72, energy=66, social=34, explore=28),
                currentWorld='beach', unlockedWorlds=8, currentNpcId='ache', tags=['test'],
                npcs=[dict(id=i, name=i, role='test', avatar='', status='', bond=12) for i in ids],
                conversations={i: [{'from': 'npc', 'text': 'persisted', 'day': 9, 'time': '18:20', 'image': None}] for i in ids},
                diary=[dict(day=9, text='saved diary', mood='calm')], completed={'ache': True})


# Legacy v1 writes are upgraded on save: schemaVersion 2 + active pack id.
V2 = {'schemaVersion': 2, 'packId': 'wsw-default-life'}


class SaveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.url = 'sqlite:///' + str(Path(self.temp.name) / 'test.db')
        self.start()
        Base.metadata.create_all(self.engine)
        with self.sessions() as db:
            roles = {1: UserRole.USER, 2: UserRole.USER, 3: UserRole.USER,
                     4: UserRole.STAFF, 5: UserRole.VOLUNTEER, 6: UserRole.STAFF}
            for i, role in roles.items():
                db.add(User(id=i, username=f'u{i}', password_hash='unused', nickname=f'u{i}',
                            is_admin=i in (1, 2), role=role))
            db.commit()
            seed_virtual_life_packs(db)

    def start(self):
        self.engine = create_engine(self.url, connect_args={'check_same_thread': False})
        self.sessions = sessionmaker(bind=self.engine)
        app = FastAPI()
        app.include_router(router)
        app.include_router(packs_router)
        def database():
            with self.sessions() as db:
                yield db
        app.dependency_overrides[get_db] = database
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.engine.dispose()
        self.temp.cleanup()

    def headers(self, uid):
        return {'Authorization': 'Bearer ' + create_access_token(uid)}

    def test_isolation_revision_and_restart(self):
        url = '/api/virtual-life/save'
        self.assertEqual(self.client.get(url).status_code, 401)
        self.assertEqual(self.client.get(url, headers=self.headers(3)).status_code, 403)
        self.assertEqual(self.client.put(url, json={'revision': 0, 'state': state()}, headers=self.headers(3)).status_code, 403)
        self.assertEqual(self.client.put(url, json={'revision': 0, 'state': state(), 'user_id': 2}, headers=self.headers(1)).status_code, 422)
        response = self.client.put(url, json={'revision': 0, 'state': state()}, headers=self.headers(1))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.client.get(url, headers=self.headers(2)).json()['state'], None)
        self.assertEqual(self.client.put(url, json={'revision': 0, 'state': state()}, headers=self.headers(1)).status_code, 409)
        self.assertEqual(self.client.put(url, json={'revision': 1, 'state': state()}, headers=self.headers(2)).status_code, 409)
        self.client.close()
        self.engine.dispose()
        self.start()  # new app/engine against same file; no in-memory state survives
        loaded = self.client.get(url, headers=self.headers(1)).json()
        self.assertEqual(loaded['state'], {**state(), **V2, 'actionLedger': {}, 'dialogueNodes': {}, 'friendIds': [], 'interactedNpcIds': [], 'currentRoomId': None, 'eventProgress': {'day': 1, 'done': []}})
        newer = state()
        newer['day'] = 10
        self.assertEqual(self.client.put(url, json={'revision': loaded['revision'], 'state': newer}, headers=self.headers(1)).status_code, 200)
        self.assertEqual(self.client.put(url, json={'revision': 1, 'state': state()}, headers=self.headers(1)).status_code, 409)
        self.assertEqual(self.client.get(url, headers=self.headers(1)).json()['state']['day'], 10)

    def add_event(self):
        # 使用真实活动包规则,而非模拟白名单。
        with self.sessions() as db:
            pack = get_active_pack(db)
            content = json.loads(pack.content_json)
            content['events'] = [{
                'id': 'greeting', 'roomId': content['rooms'][0]['id'], 'title': '招呼', 'icon': '👋',
                'scripts': [{'messages': [{'speaker': {'npcId': 'ache'}, 'lines': ['你好'], 'image': None}]}
                            for _ in range(7)],
            }]
            validate_pack_content(content)
            pack.content_json = json.dumps(content, ensure_ascii=False)
            db.commit()

    def test_event_progress_roundtrip(self):
        self.add_event()
        saved = {**state(), 'eventProgress': {'day': 9, 'done': ['greeting']}}
        response = self.client.put('/api/virtual-life/save', json={'revision': 0, 'state': saved}, headers=self.headers(1))
        self.assertEqual(response.status_code, 200, response.text)
        self.client.close()
        self.engine.dispose()
        self.start()
        loaded = self.client.get('/api/virtual-life/save', headers=self.headers(1)).json()['state']
        self.assertEqual(loaded['eventProgress'], saved['eventProgress'])

    def test_event_progress_defaults_for_legacy_save(self):
        parsed = GameState.model_validate(state())
        self.assertEqual(parsed.eventProgress.model_dump(), {'day': 1, 'done': []})
        parsed.eventProgress.done.append('greeting')
        self.assertEqual(GameState.model_validate(state()).eventProgress.done, [])
        response = self.client.put('/api/virtual-life/save', json={'revision': 0, 'state': state()}, headers=self.headers(1))
        self.assertEqual(response.status_code, 200, response.text)
        loaded = self.client.get('/api/virtual-life/save', headers=self.headers(1)).json()['state']
        self.assertEqual(loaded['eventProgress'], {'day': 1, 'done': []})

    def test_event_progress_filters_unknown_event_ids(self):
        self.add_event()
        saved = {**state(), 'eventProgress': {'day': 8, 'done': ['removed', 'greeting', 'unknown']}}
        response = self.client.put('/api/virtual-life/save', json={'revision': 0, 'state': saved}, headers=self.headers(1))
        self.assertEqual(response.status_code, 200, response.text)
        loaded = self.client.get('/api/virtual-life/save', headers=self.headers(1)).json()['state']
        self.assertEqual(loaded['eventProgress'], {'day': 8, 'done': ['greeting']})
        # 包中事件被删除后,再次写入也应平滑清理。
        with self.sessions() as db:
            pack = get_active_pack(db)
            content = json.loads(pack.content_json)
            content.pop('events')
            pack.content_json = json.dumps(content, ensure_ascii=False)
            db.commit()
        response = self.client.put('/api/virtual-life/save', json={'revision': 1, 'state': loaded}, headers=self.headers(1))
        self.assertEqual(response.status_code, 200, response.text)
        loaded = self.client.get('/api/virtual-life/save', headers=self.headers(1)).json()['state']
        self.assertEqual(loaded['eventProgress'], {'day': 8, 'done': []})

    def test_event_progress_rejects_invalid_structure(self):
        for progress in ({'day': 0, 'done': []}, {'day': 1.5, 'done': []},
                         {'day': 1, 'done': [123]}, {'day': 1, 'done': 'greeting'},
                         {'day': 1, 'done': [], 'extra': True}, {'day': 1}, {'done': []}):
            with self.subTest(progress=progress):
                saved = {**state(), 'eventProgress': progress}
                response = self.client.put('/api/virtual-life/save', json={'revision': 0, 'state': saved}, headers=self.headers(1))
                self.assertEqual(response.status_code, 422, response.text)

    def test_save_message_with_image_roundtrip(self):
        url = '/api/virtual-life/save'
        s = state()
        s['conversations']['ache'].append(
            {'from': 'npc', 'text': '看这张', 'day': 9, 'time': '18:20', 'image': '/uploads/life/a.png'})
        r = self.client.put(url, json={'revision': 0, 'state': s}, headers=self.headers(1))
        self.assertEqual(r.status_code, 200, r.text)
        got = self.client.get(url, headers=self.headers(1)).json()
        self.assertEqual(got['state']['conversations']['ache'][-1]['image'], '/uploads/life/a.png')
        # 不带图片的消息序列化为 image: None,不丢字段也不炸校验。
        self.assertIsNone(got['state']['conversations']['ache'][0]['image'])
        invalid = state()
        invalid['currentNpcId'] = 'unknown'
        self.assertEqual(self.client.put(url, json={'revision': 2, 'state': invalid}, headers=self.headers(1)).status_code, 422)

    def test_staff_access_is_private_and_other_roles_are_forbidden(self):
        url = '/api/virtual-life/save'
        payload = {'revision': 0, 'state': state()}
        for uid, status in ((None, 401), (3, 403), (5, 403)):
            headers = self.headers(uid) if uid else {}
            self.assertEqual(self.client.get(url, headers=headers).status_code, status)
            self.assertEqual(self.client.put(url, json=payload, headers=headers).status_code, status)
        for uid in (1, 4, 6):  # super administrator and two regular administrators
            response = self.client.get(url, headers=self.headers(uid))
            self.assertEqual(response.status_code, 200)
            self.assertIsNone(response.json()['state'])
            own_state = {**state(), 'day': 10 + uid}
            response = self.client.put(url, json={'revision': 0, 'state': own_state}, headers=self.headers(uid))
            self.assertEqual(response.status_code, 200, response.text)
        for uid in (1, 4, 6):
            saved = self.client.get(url, headers=self.headers(uid)).json()
            self.assertEqual(saved['state']['day'], 10 + uid)
            self.assertEqual(saved['revision'], 1)
        self.assertEqual(self.client.put(url, json={**payload, 'user_id': 1}, headers=self.headers(4)).status_code, 422)
        self.assertIsNone(self.client.get(url, headers=self.headers(2)).json()['state'])

    def test_beta_user_can_save_and_read_active_pack_then_loses_access(self):
        headers = self.headers(3)
        with self.sessions() as db:
            db.get(User, 3).is_beta_tester = True
            db.commit()
        response = self.client.get('/api/virtual-life/pack', headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['id'], V2['packId'])
        url = '/api/virtual-life/save'
        self.assertIsNone(self.client.get(url, headers=headers).json()['state'])
        response = self.client.put(url, json={'revision': 0, 'state': state()}, headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        loaded = self.client.get(url, headers=headers).json()
        self.assertEqual(loaded['revision'], 1)
        self.assertEqual(loaded['state']['day'], 9)
        self.assertIsNone(self.client.get(url, headers=self.headers(1)).json()['state'])
        response = self.client.put(url, json={'revision': 1, 'state': {**state(), 'day': 10}}, headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        with self.sessions() as db:
            user = db.get(User, 3)
            self.assertEqual(user.role, UserRole.USER)
            user.is_beta_tester = False
            db.commit()
        for method, path, kwargs in (
            ('get', url, {}),
            ('put', url, {'json': {'revision': 2, 'state': state()}}),
            ('get', '/api/virtual-life/pack', {}),
        ):
            response = self.client.request(method, path, headers=headers, **kwargs)
            self.assertEqual(response.status_code, 403, response.text)
            self.assertEqual(response.json()['detail'], '需要内测资格')

    def test_beta_user_cannot_manage_any_pack_endpoint_or_upload_assets(self):
        with self.sessions() as db:
            db.get(User, 3).is_beta_tester = True
            content = json.loads(get_active_pack(db).content_json)
            db.commit()
        base = '/api/virtual-life/packs'
        pack = base + '/' + V2['packId']
        for method, path, kwargs in (
            ('get', base, {}),
            ('post', base, {'json': {'id': 'beta-created', 'name': 'Beta', 'content': content}}),
            ('get', pack, {}),
            ('put', pack, {'json': {'name': 'Beta rename'}}),
            ('post', pack + '/activate', {}),
            ('post', pack + '/duplicate', {'json': {'id': 'beta-copy', 'name': 'Copy'}}),
            ('delete', pack, {}),
            ('post', '/api/virtual-life/assets', {'files': {'file': ('test.png', b'\x89PNG\r\n\x1a\n', 'image/png')}}),
        ):
            with self.subTest(method=method, path=path):
                response = self.client.request(method, path, headers=self.headers(3), **kwargs)
                self.assertEqual(response.status_code, 403, response.text)
                self.assertEqual(response.json()['detail'], '需要管理员权限')

    def test_action_ledger_compatibility_and_roundtrip(self):
        url = '/api/virtual-life/save'
        headers = self.headers(1)
        old = state()  # Old v1 clients omit the new field.
        self.assertEqual(self.client.put(url, json={'revision': 0, 'state': old}, headers=headers).status_code, 200)
        self.assertEqual(self.client.get(url, headers=headers).json()['state']['actionLedger'], {})
        saved = state()
        saved['actionLedger'] = {'9': {'ache': {'headpat': True, 'kiss': True}, 'yu': {'poke': True}}}
        saved['npcs'][0]['bond'] = 35
        response = self.client.put(url, json={'revision': 1, 'state': saved}, headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        self.client.close()
        self.engine.dispose()
        self.start()
        self.assertEqual(self.client.get(url, headers=headers).json()['state'], {**saved, **V2, 'dialogueNodes': {}, 'friendIds': [], 'interactedNpcIds': [], 'currentRoomId': None, 'eventProgress': {'day': 1, 'done': []}})
        self.assertIsNone(self.client.get(url, headers=self.headers(2)).json()['state'])
        for invalid in ({'10': {'ache': {'headpat': True}}}, {'9': {'unknown': {'poke': True}}}, {'9': {'ache': {'invalid': True}}}):
            bad = {**saved, 'actionLedger': invalid}
            self.assertEqual(self.client.put(url, json={'revision': 2, 'state': bad}, headers=headers).status_code, 422)

    def test_friendship_rooms_and_legacy_migration(self):
        url = '/api/virtual-life/save'
        headers = self.headers(1)
        old = state()
        old['conversations']['ache'].append({'from': 'player', 'text': 'hello', 'day': 9, 'time': '18:20'})
        self.assertEqual(self.client.put(url, json={'revision': 0, 'state': old}, headers=headers).status_code, 200)
        saved = self.client.get(url, headers=headers).json()['state']
        self.assertEqual(saved['friendIds'], [])
        self.assertEqual(saved['interactedNpcIds'], ['ache'])
        saved.update(currentWorld='潮汐之后', currentRoomId='beach-2086', friendIds=['ache'])
        self.assertEqual(self.client.put(url, json={'revision': 1, 'state': saved}, headers=headers).status_code, 200)
        self.client.close()
        self.engine.dispose()
        self.start()
        self.assertEqual(self.client.get(url, headers=headers).json()['state'], saved)
        self.assertIsNone(self.client.get(url, headers=self.headers(2)).json()['state'])
        for patch in ({'friendIds': ['yu']}, {'currentRoomId': 'cafe-private'}, {'currentRoomId': 'hall-full'}, {'currentRoomId': 'beach-empty'}, {'currentWorld': '小小咖啡馆'}, {'friendIds': ['ache', 'ache']}):
            self.assertEqual(self.client.put(url, json={'revision': 2, 'state': {**saved, **patch}}, headers=headers).status_code, 422)
        saved['npcs'][0]['bond'] = 9
        self.assertEqual(self.client.put(url, json={'revision': 2, 'state': saved}, headers=headers).status_code, 422)
    def test_dialogue_nodes_roundtrip_and_validation(self):
        url = '/api/virtual-life/save'
        headers = self.headers(1)
        saved = state()
        saved['dialogueNodes'] = {'ache': 'n1'}
        self.assertEqual(self.client.put(url, json={'revision': 0, 'state': saved}, headers=headers).status_code, 200)
        loaded = self.client.get(url, headers=headers).json()['state']
        self.assertEqual(loaded['dialogueNodes'], {'ache': 'n1'})
        for bad in ({'ghost': 'n1'}, {'ache': 'gone'}):
            payload = {**state(), 'dialogueNodes': bad}
            self.assertEqual(self.client.put(url, json={'revision': 1, 'state': payload}, headers=headers).status_code, 422, str(bad))

    def test_pack_schema_v2_and_pack_id_rules(self):
        url = '/api/virtual-life/save'
        headers = self.headers(1)
        # v2 saves must declare the site's active pack.
        good = {**state(), **V2}
        self.assertEqual(self.client.put(url, json={'revision': 0, 'state': good}, headers=headers).status_code, 200)
        self.assertEqual(self.client.get(url, headers=headers).json()['state']['packId'], 'wsw-default-life')
        for bad in ({**state(), 'schemaVersion': 2},  # v2 without packId
                    {**state(), 'schemaVersion': 2, 'packId': 'other-pack'},
                    {**state(), 'schemaVersion': 1, 'packId': 'wsw-default-life'},  # legacy cannot declare
                    {**state(), 'schemaVersion': 3, 'packId': 'wsw-default-life'}):
            self.assertEqual(self.client.put(url, json={'revision': 1, 'state': bad}, headers=headers).status_code, 422, str(bad.get('packId')))
        # Whitelists now come from the pack manifest, still enforced.
        bad_npc = {**state(), **V2}
        bad_npc['friendIds'] = ['stranger']
        self.assertEqual(self.client.put(url, json={'revision': 1, 'state': bad_npc}, headers=headers).status_code, 422)
        bad_action = {**state(), **V2, 'actionLedger': {'9': {'ache': {'fly': True}}}}
        self.assertEqual(self.client.put(url, json={'revision': 1, 'state': bad_action}, headers=headers).status_code, 422)


if __name__ == '__main__':
    unittest.main()
