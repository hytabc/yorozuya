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
from app.virtual_life import router as save_router
from app.virtual_life_packs import router as packs_router, seed_virtual_life_packs, \
    validate_pack_content, migrate_pack_content, derive_save_rules, PackContentError

SEED = json.loads((Path(__file__).resolve().parent.parent / 'app' / 'life_packs' / 'wsw-default-life.json').read_text(encoding='utf-8'))


def state():
    ids = ['ache', 'xiaomi', 'maoyou', 'yu']
    return dict(schemaVersion=2, packId='wsw-default-life', day=9,
                stats=dict(mood=72, energy=66, social=34, explore=28),
                currentWorld='beach', unlockedWorlds=8, currentNpcId='ache', tags=[],
                npcs=[dict(id=i, name=i, role='r', avatar='', status='', bond=12) for i in ids],
                conversations={i: [] for i in ids}, diary=[], completed={})


def mini_pack(npc_ids):
    """Smallest valid pack content with custom NPC ids, one world/room/action."""
    return {
        'npcIds': npc_ids,
        'npcs': [{'id': i, 'name': i, 'role': 'r', 'avatar': '', 'status': '', 'bond': 12} for i in npc_ids],
        'portraits': {i: '/p.jpg' for i in npc_ids},
        'worlds': [{'id': 'w1', 'name': '世界一', 'vibe': '', 'color': '#000', 'bg': ''}],
        'rooms': [{'id': 'w1-1', 'worldId': 'w1', 'label': '#1', 'private': False, 'capacity': 8, 'occupants': 1}],
        'presence': {i: {'status': 'green', 'roomId': 'w1-1', 'intro': ''} for i in npc_ids},
        'actions': [{'id': 'wave', 'label': '挥手', 'reward': 1, 'threshold': 0, 'reply': '笑了笑'}],
        'dialogue': {i: [{'start': 'n1', 'nodes': {'n1': {'lines': ['你好'], 'image': None, 'choices': [
            {'label': '你好', 'effects': {}, 'replies': ['嗯'], 'replyImage': None, 'next': None}]}}}] for i in npc_ids},
        'initialState': {'day': 1, 'stats': {'mood': 50, 'energy': 50, 'social': 50, 'explore': 50},
                         'tags': [], 'currentWorld': '世界一', 'unlockedWorlds': 1,
                         'conversations': {i: [] for i in npc_ids}, 'diary': []},
    }


def event_pack(npc_ids):
    content = mini_pack(npc_ids)
    content['events'] = [{
        'id': 'greeting', 'roomId': 'w1-1', 'title': '房间招呼', 'icon': '👋',
        'scripts': [{'messages': [
            {'speaker': {'npcId': npc_ids[0]}, 'lines': ['你好', '欢迎'], 'image': None},
            {'choice': {'options': [{
                'label': '回应', 'effects': {'stats': {'mood': 100, 'energy': -100, 'social': 1, 'explore': 0}},
                'reply': [{'speaker': {'name': '路人', 'avatar': '/uploads/avatar.png'},
                           'lines': ['很高兴见到你'], 'image': '/uploads/life/hello.png'}],
            }]}},
        ]} for _ in range(7)],
    }]
    return content


class PackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.url = 'sqlite:///' + str(Path(self.temp.name) / 'test.db')
        self.engine = create_engine(self.url, connect_args={'check_same_thread': False})
        self.sessions = sessionmaker(bind=self.engine)
        app = FastAPI()
        app.include_router(save_router)
        app.include_router(packs_router)
        def database():
            with self.sessions() as db:
                yield db
        app.dependency_overrides[get_db] = database
        self.client = TestClient(app)
        Base.metadata.create_all(self.engine)
        with self.sessions() as db:
            db.add(User(id=1, username='boss', password_hash='unused', nickname='boss', is_admin=True, role=UserRole.USER))
            db.add(User(id=2, username='staff', password_hash='unused', nickname='staff', is_admin=False, role=UserRole.STAFF))
            db.add(User(id=3, username='plain', password_hash='unused', nickname='plain', is_admin=False, role=UserRole.USER))
            db.commit()
            seed_virtual_life_packs(db)

    def tearDown(self):
        self.client.close()
        self.engine.dispose()
        self.temp.cleanup()

    def headers(self, uid):
        return {'Authorization': 'Bearer ' + create_access_token(uid)}

    def test_seed_and_active_pack(self):
        packs = self.client.get('/api/virtual-life/packs', headers=self.headers(1)).json()
        self.assertEqual([p['id'] for p in packs], ['wsw-default-life'])
        self.assertTrue(packs[0]['active'])
        active = self.client.get('/api/virtual-life/pack', headers=self.headers(1)).json()
        self.assertEqual(active['id'], 'wsw-default-life')
        self.assertEqual(active['content']['npcIds'], ['ache', 'xiaomi', 'maoyou', 'yu'])
        self.assertIn('dialogue', active['content'])
        self.assertIn('worlds', active['content'])
        # Seeding is idempotent.
        with self.sessions() as db:
            seed_virtual_life_packs(db)
        self.assertEqual(len(self.client.get('/api/virtual-life/packs', headers=self.headers(1)).json()), 1)

    def test_permission_gates(self):
        for uid, status in ((None, 401), (3, 403)):
            headers = self.headers(uid) if uid else {}
            self.assertEqual(self.client.get('/api/virtual-life/pack', headers=headers).status_code, status)
            self.assertEqual(self.client.get('/api/virtual-life/packs', headers=headers).status_code, status)
            self.assertEqual(self.client.post('/api/virtual-life/packs', json={'id': 'x', 'name': 'x', 'content': {}}, headers=headers).status_code, status)
        # Staff administrators may manage packs too.
        self.assertEqual(self.client.get('/api/virtual-life/packs', headers=self.headers(2)).status_code, 200)

    def test_create_validate_activate_duplicate_delete(self):
        h = self.headers(1)
        # Invalid content is rejected with a Chinese reason.
        bad = self.client.post('/api/virtual-life/packs', json={'id': 'bad', 'name': '坏包', 'content': {'npcIds': []}}, headers=h)
        self.assertEqual(bad.status_code, 422)
        # Invalid jump reference is rejected.
        broken = mini_pack(['neo'])
        broken['dialogue']['neo'][0]['nodes']['n1']['choices'][0]['next'] = 'nowhere'
        self.assertEqual(self.client.post('/api/virtual-life/packs', json={'id': 'broken', 'name': '断链', 'content': broken}, headers=h).status_code, 422)
        # Create, list, duplicate, activate.
        created = self.client.post('/api/virtual-life/packs', json={'id': 'neo-pack', 'name': '新人物包', 'content': mini_pack(['neo'])}, headers=h)
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(self.client.post('/api/virtual-life/packs', json={'id': 'neo-pack', 'name': 'x', 'content': mini_pack(['neo'])}, headers=h).status_code, 409)
        self.assertEqual(self.client.post('/api/virtual-life/packs', json={'id': 'BAD ID', 'name': 'x', 'content': mini_pack(['neo'])}, headers=h).status_code, 422)
        dup = self.client.post('/api/virtual-life/packs/neo-pack/duplicate', json={'id': 'neo-copy', 'name': '副本'}, headers=h)
        self.assertEqual(dup.status_code, 201)
        self.assertFalse(dup.json()['active'])
        self.assertEqual(self.client.post('/api/virtual-life/packs/neo-pack/activate', headers=h).status_code, 200)
        active = self.client.get('/api/virtual-life/pack', headers=h).json()
        self.assertEqual(active['id'], 'neo-pack')
        # Active pack cannot be deleted; inactive can.
        self.assertEqual(self.client.delete('/api/virtual-life/packs/neo-pack', headers=h).status_code, 409)
        self.assertEqual(self.client.delete('/api/virtual-life/packs/neo-copy', headers=h).status_code, 204)
        self.assertEqual(self.client.get('/api/virtual-life/packs/neo-copy', headers=h).status_code, 404)

    def test_save_validation_follows_active_pack(self):
        h = self.headers(1)
        # Default pack active: default npcs pass, custom npcs fail.
        self.assertEqual(self.client.put('/api/virtual-life/save', json={'revision': 0, 'state': state()}, headers=h).status_code, 200)
        custom = state()
        custom['npcs'] = [{'id': 'neo', 'name': 'neo', 'role': 'r', 'avatar': '', 'status': '', 'bond': 12}]
        custom['currentNpcId'] = 'neo'
        custom['conversations'] = {'neo': []}
        self.assertEqual(self.client.put('/api/virtual-life/save', json={'revision': 1, 'state': custom}, headers=h).status_code, 422)
        # Activate a pack whose NPC is 'neo': now the custom save passes with its packId.
        self.client.post('/api/virtual-life/packs', json={'id': 'neo-pack', 'name': '新人物包', 'content': mini_pack(['neo'])}, headers=h)
        self.client.post('/api/virtual-life/packs/neo-pack/activate', headers=h)
        custom['packId'] = 'neo-pack'
        response = self.client.put('/api/virtual-life/save', json={'revision': 1, 'state': custom}, headers=h)
        self.assertEqual(response.status_code, 200, response.text)
        # The old pack's id is now rejected.
        old = state()
        old['packId'] = 'wsw-default-life'
        self.assertEqual(self.client.put('/api/virtual-life/save', json={'revision': 2, 'state': old}, headers=h).status_code, 422)

    def test_update_pack_bumps_version(self):
        h = self.headers(1)
        self.client.post('/api/virtual-life/packs', json={'id': 'neo-pack', 'name': '新人物包', 'content': mini_pack(['neo'])}, headers=h)
        content = mini_pack(['neo'])
        content['npcs'][0]['name'] = '尼欧'
        updated = self.client.put('/api/virtual-life/packs/neo-pack', json={'content': content, 'name': '改过的包'}, headers=h)
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()['version'], 2)
        self.assertEqual(updated.json()['name'], '改过的包')
        self.assertEqual(updated.json()['content']['npcs'][0]['name'], '尼欧')
        # Updating with broken content keeps the stored version.
        content['actions'] = []
        self.assertEqual(self.client.put('/api/virtual-life/packs/neo-pack', json={'content': content}, headers=h).status_code, 422)
        self.assertEqual(self.client.get('/api/virtual-life/packs/neo-pack', headers=h).json()['version'], 2)

    def test_startup_migrates_legacy_single_script_dialogue(self):
        from app.virtual_life_packs import VirtualLifePack
        legacy = mini_pack(['neo'])
        legacy['dialogue'] = {'neo': legacy['dialogue']['neo'][0]}  # 每日数组之前的旧形状
        with self.sessions() as db:
            db.add(VirtualLifePack(id='legacy-pack', name='旧包', version=1,
                                   content_json=json.dumps(legacy, ensure_ascii=False),
                                   is_active=False, updated_at='2026-01-01T00:00:00+00:00'))
            db.commit()
            seed_virtual_life_packs(db)  # 启动播种:幂等 + 就地迁移旧形状
        migrated = self.client.get('/api/virtual-life/packs/legacy-pack', headers=self.headers(1)).json()
        days = migrated['content']['dialogue']['neo']
        self.assertIsInstance(days, list)
        self.assertEqual(days[0]['nodes']['n1']['lines'], ['你好'])
        self.assertIsNone(days[0]['nodes']['n1']['image'])
        # 迁移后的包通过校验,可以激活。
        self.assertEqual(self.client.post('/api/virtual-life/packs/legacy-pack/activate', headers=self.headers(1)).status_code, 200)

    def test_migrate_upgrades_single_line_shape_idempotent(self):
        content = mini_pack(['ache'])
        node = content['dialogue']['ache'][0]['nodes']['n1']
        node['line'] = node.pop('lines')[0]
        node.pop('image')
        node['choices'][0]['reply'] = node['choices'][0].pop('replies')[0]
        node['choices'][0].pop('replyImage')
        self.assertIs(migrate_pack_content(content), True)
        self.assertEqual(node['lines'], ['你好'])
        self.assertIsNone(node['image'])
        self.assertEqual(node['choices'][0]['replies'], ['嗯'])
        self.assertIsNone(node['choices'][0]['replyImage'])
        self.assertIs(migrate_pack_content(content), False)  # 幂等
        validate_pack_content(content)  # 迁移后必须通过校验

    def test_validate_rejects_external_image_and_empty_lines(self):
        content = mini_pack(['ache'])
        content['dialogue']['ache'][0]['nodes']['n1']['image'] = 'https://evil.com/x.png'
        with self.assertRaises(PackContentError):
            validate_pack_content(content)
        content = mini_pack(['ache'])
        content['dialogue']['ache'][0]['nodes']['n1']['lines'] = []
        with self.assertRaises(PackContentError):
            validate_pack_content(content)

    def test_activation_migrates_compatible_saves(self):
        h = self.headers(1)
        # Save under the default pack.
        self.assertEqual(self.client.put('/api/virtual-life/save', json={'revision': 0, 'state': state()}, headers=h).status_code, 200)
        # An incompatible pack (different NPCs): migration skips the save, untouched.
        self.client.post('/api/virtual-life/packs', json={'id': 'neo-pack', 'name': '新人物包', 'content': mini_pack(['neo'])}, headers=h)
        resp = self.client.post('/api/virtual-life/packs/neo-pack/activate', headers=h)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['saveMigration'], {'migrated': 0, 'skipped': 1})
        saved = self.client.get('/api/virtual-life/save', headers=h).json()
        self.assertEqual(saved['state']['packId'], 'wsw-default-life')
        # A compatible pack (same NPC ids): the save is repointed and keeps working.
        self.client.post('/api/virtual-life/packs', json={'id': 'clone-pack', 'name': '同人包',
                                                          'content': mini_pack(['ache', 'xiaomi', 'maoyou', 'yu'])}, headers=h)
        resp = self.client.post('/api/virtual-life/packs/clone-pack/activate', headers=h)
        self.assertEqual(resp.json()['saveMigration'], {'migrated': 1, 'skipped': 0})
        saved = self.client.get('/api/virtual-life/save', headers=h).json()
        self.assertEqual(saved['state']['packId'], 'clone-pack')
        migrated_state = state()
        migrated_state['packId'] = 'clone-pack'
        response = self.client.put('/api/virtual-life/save', json={'revision': saved['revision'], 'state': migrated_state}, headers=h)
        self.assertEqual(response.status_code, 200, response.text)
        # Re-activating the same pack is a no-op for already-migrated saves.
        resp = self.client.post('/api/virtual-life/packs/clone-pack/activate', headers=h)
        self.assertEqual(resp.json()['saveMigration'], {'migrated': 0, 'skipped': 0})

    def test_events_valid_and_save_rules(self):
        content = event_pack(['ache'])
        self.assertIs(validate_pack_content(content), content)
        self.assertEqual(derive_save_rules(content)['eventIds'], ['greeting'])
        legacy = mini_pack(['ache'])
        self.assertIs(validate_pack_content(legacy), legacy)
        self.assertNotIn('events', legacy)  # 校验不改变旧包内容。
        self.assertEqual(derive_save_rules(legacy)['eventIds'], [])

    def test_events_reject_nested_choice(self):
        content = event_pack(['ache'])
        choice = content['events'][0]['scripts'][0]['messages'][1]
        choice['choice']['options'][0]['reply'] = [{'choice': {'options': []}}]
        with self.assertRaisesRegex(PackContentError, '嵌套'):
            validate_pack_content(content)

    def test_events_reject_scalar_bond(self):
        content = event_pack(['ache'])
        content['events'][0]['scripts'][0]['messages'][1]['choice']['options'][0]['effects']['bond'] = 0
        with self.assertRaisesRegex(PackContentError, 'bond 必须是恰好包含 npcId,value 的对象'):
            validate_pack_content(content)

    def test_events_accept_bond_boundaries(self):
        for npc_id in ('ache', 'neo'):
            for value in (-100, -1, 0, 1, 100):
                for with_stats in (False, True):
                    with self.subTest(npc_id=npc_id, value=value, with_stats=with_stats):
                        content = event_pack(['ache', 'neo'])
                        option = content['events'][0]['scripts'][0]['messages'][1]['choice']['options'][0]
                        if not with_stats:
                            option['effects'] = {}
                        option['effects']['bond'] = {'npcId': npc_id, 'value': value}
                        self.assertIs(validate_pack_content(content), content)

    def test_events_reject_bond_unknown_npc(self):
        for npc_id in ('unknown', '', None, True, 1, [], {}):
            with self.subTest(npc_id=npc_id):
                content = event_pack(['ache'])
                content['events'][0]['scripts'][0]['messages'][1]['choice']['options'][0]['effects']['bond'] = {
                    'npcId': npc_id, 'value': 1,
                }
                with self.assertRaisesRegex(PackContentError, '^事件 greeting/第1天 选项 bond 指向未知 NPC$'):
                    validate_pack_content(content)

    def test_events_reject_invalid_bond_value(self):
        for value in (-101, 101, True, False, 0.5, -1.5, '1', None, [], {}):
            with self.subTest(value=value):
                content = event_pack(['ache'])
                content['events'][0]['scripts'][0]['messages'][1]['choice']['options'][0]['effects']['bond'] = {
                    'npcId': 'ache', 'value': value,
                }
                with self.assertRaisesRegex(PackContentError, r'^事件 greeting/第1天 选项 bond value 必须是 -100\.\.100 的整数$'):
                    validate_pack_content(content)

    def test_events_reject_invalid_bond_shape(self):
        for bond in ({}, {'npcId': 'ache'}, {'value': 1},
                     {'npcId': 'ache', 'value': 1, 'extra': 0},
                     {'npcId': 'ache', 'other': 1}, None, [],
                     [{'npcId': 'ache', 'value': 1}], 0, 'bond', True):
            with self.subTest(bond=bond):
                content = event_pack(['ache'])
                content['events'][0]['scripts'][0]['messages'][1]['choice']['options'][0]['effects']['bond'] = bond
                with self.assertRaisesRegex(PackContentError, '^事件 greeting/第1天 选项 bond 必须是恰好包含 npcId,value 的对象$'):
                    validate_pack_content(content)

    def test_events_reject_unknown_room(self):
        content = event_pack(['ache'])
        content['events'][0]['roomId'] = 'unknown'
        with self.assertRaisesRegex(PackContentError, '未知房间'):
            validate_pack_content(content)

    def test_events_require_seven_scripts(self):
        for count in (0, 1, 6, 8):
            with self.subTest(count=count):
                content = event_pack(['ache'])
                scripts = content['events'][0]['scripts']
                content['events'][0]['scripts'] = [scripts[0] for _ in range(count)]
                with self.assertRaisesRegex(PackContentError, '7'):
                    validate_pack_content(content)

    def test_events_require_exclusive_speaker(self):
        for speaker in ({'npcId': 'ache', 'name': '路人'}, {}, {'avatar': '/uploads/a.png'}):
            with self.subTest(speaker=speaker):
                content = event_pack(['ache'])
                content['events'][0]['scripts'][0]['messages'][0]['speaker'] = speaker
                with self.assertRaisesRegex(PackContentError, 'speaker'):
                    validate_pack_content(content)

    def test_events_reject_invalid_message_groups(self):
        for patch in ({'speaker': {'npcId': 'unknown'}}, {'speaker': {'name': ''}},
                      {'speaker': {'name': '路人', 'avatar': None}}, {'lines': []},
                      {'lines': ['']}, {'lines': [1]}, {'image': 'https://example.com/a.png'}):
            for in_reply in (False, True):
                with self.subTest(patch=patch, in_reply=in_reply):
                    content = event_pack(['ache'])
                    messages = content['events'][0]['scripts'][0]['messages']
                    message = messages[1]['choice']['options'][0]['reply'][0] if in_reply else messages[0]
                    message.update(patch)
                    with self.assertRaises(PackContentError):
                        validate_pack_content(content)

    def test_events_reject_invalid_options(self):
        for patch in ({'label': ''}, {'effects': {'other': 1}}, {'effects': []},
                      {'effects': {'stats': {'bond': 1}}}, {'effects': {'stats': {'mood': 101}}},
                      {'effects': {'stats': {'mood': -101}}}, {'effects': {'stats': {'mood': True}}},
                      {'effects': {'stats': {'mood': 1.5}}}, {'reply': []}):
            with self.subTest(patch=patch):
                content = event_pack(['ache'])
                content['events'][0]['scripts'][0]['messages'][1]['choice']['options'][0].update(patch)
                with self.assertRaises(PackContentError):
                    validate_pack_content(content)

    def test_events_reject_invalid_structure(self):
        for patch in ({'id': ''}, {'title': ''}, {'icon': ''}, {'scripts': [{'messages': []}] * 7},
                      {'scripts': [{'messages': [{'choice': {'options': []}}]}] * 7},
                      {'scripts': [{'messages': [{'choice': {'options': []}, 'speaker': {'name': '路人'}}]}] * 7}):
            with self.subTest(patch=patch):
                content = event_pack(['ache'])
                content['events'][0].update(patch)
                with self.assertRaises(PackContentError):
                    validate_pack_content(content)
        content = event_pack(['ache'])
        content['events'].append(content['events'][0])
        with self.assertRaisesRegex(PackContentError, '重复'):
            validate_pack_content(content)
        for events in (None, {}, [None]):
            with self.subTest(events=events):
                content = mini_pack(['ache'])
                content['events'] = events
                with self.assertRaises(PackContentError):
                    validate_pack_content(content)

    def test_start_room_and_endings_validation(self):
        # 合法:初始房间 + 条件结局 + 无条件兜底结局。
        content = mini_pack(['ache'])
        content['startRoomId'] = 'w1-1'
        content['endings'] = [
            {'id': 'warm', 'name': '温暖的日常', 'text': '……',
             'conditions': {'stats': {'mood': 60}, 'bonds': {'ache': 50}}},
            {'id': 'plain', 'name': '平凡收官', 'text': '……', 'conditions': {}},
        ]
        validate_pack_content(content)
        # 初始房间必须指向已有房间。
        for bad in ('nowhere', 1, []):
            with self.subTest(startRoomId=bad):
                content = mini_pack(['ache'])
                content['startRoomId'] = bad
                with self.assertRaises(PackContentError):
                    validate_pack_content(content)
        # 结局字段与条件校验。
        for patch in ({'id': ''}, {'name': ''}, {'text': ''}, {'conditions': []},
                      {'conditions': {'stats': {'bond': 1}}},
                      {'conditions': {'stats': {'mood': 101}}},
                      {'conditions': {'bonds': {'ghost': 10}}},
                      {'conditions': {'bonds': {'ache': -1}}}):
            with self.subTest(patch=patch):
                content = mini_pack(['ache'])
                content['endings'] = [dict({'id': 'e1', 'name': '结局', 'text': '……'}, **patch)]
                with self.assertRaises(PackContentError):
                    validate_pack_content(content)
        content = mini_pack(['ache'])
        content['endings'] = [{'id': 'e1', 'name': 'a', 'text': 'x'}, {'id': 'e1', 'name': 'b', 'text': 'y'}]
        with self.assertRaisesRegex(PackContentError, '重复'):
            validate_pack_content(content)
        # 结局图片:允许留空或站内 /uploads/ 路径,拒绝外链与非法值。
        for bad_image in ('https://example.com/a.png', 'relative.png', 1):
            with self.subTest(image=bad_image):
                content = mini_pack(['ache'])
                content['endings'] = [{'id': 'e1', 'name': 'a', 'text': 'x', 'image': bad_image}]
                with self.assertRaises(PackContentError):
                    validate_pack_content(content)
        content = mini_pack(['ache'])
        content['endings'] = [{'id': 'e1', 'name': 'a', 'text': 'x', 'image': '/uploads/life/end.png'}]
        validate_pack_content(content)

    def test_migrate_adds_events_idempotently(self):
        for content in (mini_pack(['ache']), {}):
            self.assertTrue(migrate_pack_content(content))
            self.assertEqual(content['events'], [])
            self.assertFalse(migrate_pack_content(content))
        content = event_pack(['ache'])
        content['npcs'][0]['fallbackReplies'] = []
        original = json.loads(json.dumps(content, ensure_ascii=False))
        self.assertFalse(migrate_pack_content(content))
        self.assertEqual(content, original)

    def test_asset_upload(self):
        from unittest.mock import patch
        import app.virtual_life_packs as vlp

        class FakeSettings:
            sugar_upload_path = Path(self.temp.name) / 'uploads'

        png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
        with patch.object(vlp, 'settings', FakeSettings):
            ok = self.client.post('/api/virtual-life/assets', files={'file': ('bg.png', png, 'image/png')}, headers=self.headers(1))
            self.assertEqual(ok.status_code, 201, ok.text)
            url = ok.json()['url']
            self.assertTrue(url.startswith('/uploads/life/'), url)
            stored = Path(self.temp.name) / 'uploads' / url.removeprefix('/uploads/')
            self.assertTrue(stored.exists())
            bad = self.client.post('/api/virtual-life/assets', files={'file': ('x.txt', b'not an image', 'text/plain')}, headers=self.headers(1))
            self.assertEqual(bad.status_code, 422)
            empty = self.client.post('/api/virtual-life/assets', files={'file': ('x.png', b'', 'image/png')}, headers=self.headers(1))
            self.assertEqual(empty.status_code, 422)
        # Permission gates mirror the pack API.
        self.assertEqual(self.client.post('/api/virtual-life/assets', files={'file': ('bg.png', png, 'image/png')}).status_code, 401)
        self.assertEqual(self.client.post('/api/virtual-life/assets', files={'file': ('bg.png', png, 'image/png')}, headers=self.headers(3)).status_code, 403)


class FallbackReplyTests(unittest.TestCase):
    def test_accepts_valid_and_default_fallback_replies(self) -> None:
        for patch in ({}, {'fallbackReplies': []},
                      {'fallbackReplies': [{'text': '你好'}]},
                      {'fallbackReplies': [{'text': '你好', 'minBond': 0}]},
                      {'fallbackReplies': [{'text': '你好', 'minBond': 1}]},
                      {'fallbackReplies': [{'text': '你好', 'minBond': 100}]},
                      {'fallbackReplies': [{'text': '默认回复'}, {'text': '亲密回复', 'minBond': 80}]}):
            with self.subTest(patch=patch):
                content = mini_pack(['ache'])
                content['npcs'][0].update(patch)
                original = json.loads(json.dumps(content, ensure_ascii=False))
                self.assertIs(validate_pack_content(content), content)
                self.assertEqual(content, original)  # 缺省值用于校验,不改写内容。

    def test_rejects_non_array_fallback_replies(self) -> None:
        for replies in (None, {}, '', 'reply', 0, 1, True, False, ()):
            with self.subTest(replies=replies):
                content = mini_pack(['ache'])
                content['npcs'][0]['fallbackReplies'] = replies
                with self.assertRaisesRegex(PackContentError, '^NPC ache 的 fallbackReplies 必须是数组$'):
                    validate_pack_content(content)

    def test_rejects_non_object_fallback_reply(self) -> None:
        for reply in (None, [], 'reply', 0, True, False, 1.5, ()):
            with self.subTest(reply=reply):
                content = mini_pack(['ache'])
                content['npcs'][0]['fallbackReplies'] = [{'text': '合法首条'}, reply]
                with self.assertRaisesRegex(PackContentError, '^NPC ache 的 fallbackReplies/第2条 必须是对象$'):
                    validate_pack_content(content)

    def test_rejects_missing_empty_or_non_string_text(self) -> None:
        for reply in ({}, {'minBond': 0}, {'text': ''}, {'text': None}, {'text': False},
                      {'text': 0}, {'text': 1.5}, {'text': []}, {'text': {}}):
            with self.subTest(reply=reply):
                content = mini_pack(['ache'])
                content['npcs'][0]['fallbackReplies'] = [reply]
                with self.assertRaisesRegex(PackContentError, '^NPC ache 的 fallbackReplies/第1条 的 text 必须是非空字符串$'):
                    validate_pack_content(content)

    def test_rejects_invalid_min_bond_type_and_range(self) -> None:
        for min_bond in (-1, 101, True, False, None, 0.0, 100.0, 0.5, '0', [], {}):
            with self.subTest(min_bond=min_bond):
                content = mini_pack(['ache', 'neo'])
                content['npcs'][1]['fallbackReplies'] = [{'text': '你好', 'minBond': min_bond}]
                with self.assertRaisesRegex(PackContentError, r'^NPC neo 的 fallbackReplies/第1条 的 minBond 必须是 0\.\.100 的整数$'):
                    validate_pack_content(content)

    def test_rejects_unknown_fallback_reply_keys(self) -> None:
        for reply in ({'text': '你好', 'extra': 1},
                      {'text': '你好', 'minBond': 0, 'bond': 1},
                      {'text': '你好', 'minbond': 0}):
            with self.subTest(reply=reply):
                content = mini_pack(['ache'])
                content['npcs'][0]['fallbackReplies'] = [reply]
                with self.assertRaisesRegex(PackContentError, '^NPC ache 的 fallbackReplies/第1条 包含未知字段$'):
                    validate_pack_content(content)

    def test_migration_adds_independent_defaults_idempotently(self) -> None:
        for dialogue_shape in ('valid', 'missing', 'null'):
            with self.subTest(dialogue_shape=dialogue_shape):
                content = mini_pack(['ache', 'neo'])
                content['events'] = []
                if dialogue_shape == 'missing':
                    content.pop('dialogue')
                elif dialogue_shape == 'null':
                    content['dialogue'] = None
                self.assertTrue(migrate_pack_content(content))
                for npc in content['npcs']:
                    self.assertEqual(npc['fallbackReplies'], [])
                self.assertIsNot(content['npcs'][0]['fallbackReplies'], content['npcs'][1]['fallbackReplies'])
                original = json.loads(json.dumps(content, ensure_ascii=False))
                self.assertFalse(migrate_pack_content(content))
                self.assertEqual(content, original)
                if dialogue_shape == 'valid':
                    self.assertIs(validate_pack_content(content), content)

    def test_migration_preserves_existing_configuration(self) -> None:
        for replies in ([], [{'text': '默认回复'}, {'text': '亲密回复', 'minBond': 100}], None, {}, 'invalid'):
            for missing_sibling in (False, True):
                with self.subTest(replies=replies, missing_sibling=missing_sibling):
                    content = mini_pack(['ache', 'neo'])
                    content['events'] = []
                    content['npcs'][0]['fallbackReplies'] = replies
                    if not missing_sibling:
                        content['npcs'][1]['fallbackReplies'] = []
                    original_replies = json.loads(json.dumps(replies, ensure_ascii=False))
                    self.assertIs(migrate_pack_content(content), missing_sibling)
                    self.assertIs(content['npcs'][0]['fallbackReplies'], replies)
                    self.assertEqual(content['npcs'][0]['fallbackReplies'], original_replies)
                    self.assertEqual(content['npcs'][1]['fallbackReplies'], [])
                    original = json.loads(json.dumps(content, ensure_ascii=False))
                    self.assertFalse(migrate_pack_content(content))
                    self.assertEqual(content, original)


if __name__ == '__main__':
    unittest.main()
