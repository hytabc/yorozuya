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
from app.virtual_life_packs import router as packs_router, seed_virtual_life_packs

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
        'dialogue': {i: [{'start': 'n1', 'nodes': {'n1': {'line': '你好', 'choices': [
            {'label': '你好', 'effects': {}, 'reply': '嗯', 'next': None}]}}}] for i in npc_ids},
        'initialState': {'day': 1, 'stats': {'mood': 50, 'energy': 50, 'social': 50, 'explore': 50},
                         'tags': [], 'currentWorld': '世界一', 'unlockedWorlds': 1,
                         'conversations': {i: [] for i in npc_ids}, 'diary': []},
    }


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
        self.assertEqual(days[0]['nodes']['n1']['line'], '你好')
        # 迁移后的包通过校验,可以激活。
        self.assertEqual(self.client.post('/api/virtual-life/packs/legacy-pack/activate', headers=self.headers(1)).status_code, 200)

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


if __name__ == '__main__':
    unittest.main()
