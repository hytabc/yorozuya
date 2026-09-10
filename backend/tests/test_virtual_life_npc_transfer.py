import base64
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.models import User, UserRole
from app.security import create_access_token
from app.virtual_life import router as save_router
from app.virtual_life_packs import router as packs_router, seed_virtual_life_packs
import app.virtual_life_packs as vlp


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def day_script():
    return {
        'start': 'n1',
        'nodes': {
            'n1': {
                'lines': ['你好'],
                'image': None,
                'choices': [
                    {'label': '你好', 'effects': {}, 'replies': ['嗯'], 'replyImage': None, 'next': None}
                ]
            }
        }
    }


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
        'dialogue': {i: [deepcopy(day_script()) for _ in range(7)] for i in npc_ids},
        'initialState': {
            'day': 1,
            'stats': {'mood': 50, 'energy': 50, 'social': 50, 'explore': 50},
            'tags': [],
            'currentWorld': '世界一',
            'unlockedWorlds': 1,
            'conversations': {i: [] for i in npc_ids},
            'diary': [],
        },
    }


class NpcTransferTests(unittest.TestCase):
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

    def upload_settings(self):
        class FakeSettings:
            sugar_upload_path = Path(self.temp.name) / 'uploads'

        return patch.object(vlp, 'settings', FakeSettings)

    def create_pack(self, pack_id, content, name='测试包'):
        response = self.client.post(
            '/api/virtual-life/packs',
            json={'id': pack_id, 'name': name, 'content': content},
            headers=self.headers(1),
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def write_upload(self, url, content=PNG):
        path = Path(self.temp.name) / 'uploads' / url.removeprefix('/uploads/')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def test_export_embeds_life_images(self):
        pack_id = 'wsw-npc-export'
        content = mini_pack(['mimi'])
        content['portraits']['mimi'] = '/uploads/life/mimi.png'
        content['dialogue']['mimi'][0]['nodes']['n1']['image'] = '/uploads/life/node.png'
        content['dialogue']['mimi'][0]['nodes']['n1']['choices'][0]['replyImage'] = '/uploads/life/reply.png'
        self.create_pack(pack_id, content)
        self.write_upload('/uploads/life/mimi.png', PNG)
        self.write_upload('/uploads/life/node.png', PNG + b'node')
        self.write_upload('/uploads/life/reply.png', PNG + b'reply')

        with self.upload_settings():
            response = self.client.get(
                f'/api/virtual-life/packs/{pack_id}/npcs/mimi/export',
                headers=self.headers(1),
            )

        self.assertEqual(response.status_code, 200, response.text)
        bundle = response.json()
        self.assertEqual(bundle['format'], 'wsw-life-npc')
        self.assertEqual(bundle['formatVersion'], 1)
        self.assertEqual(bundle['npcId'], 'mimi')
        self.assertEqual(bundle['data']['npc']['id'], 'mimi')
        self.assertEqual(bundle['data']['portrait'], '/uploads/life/mimi.png')
        self.assertEqual(bundle['data']['presence']['status'], 'green')
        self.assertEqual(len(bundle['data']['dialogue']), 7)
        self.assertEqual(bundle['data']['initialConversation'], [])
        self.assertEqual(base64.b64decode(bundle['images']['/uploads/life/mimi.png']), PNG)
        self.assertIn('/uploads/life/node.png', bundle['images'])
        self.assertIn('/uploads/life/reply.png', bundle['images'])
        self.assertEqual(bundle['missingImages'], [])

    def test_export_import_round_trip_restores_slice(self):
        pack_id = 'wsw-npc-roundtrip'
        content = mini_pack(['mimi', 'bob'])
        content['portraits']['mimi'] = '/uploads/life/mimi.png'
        content['dialogue']['mimi'][0]['nodes']['n1']['image'] = '/uploads/life/node.png'
        content['dialogue']['mimi'][0]['nodes']['n1']['choices'][0]['replyImage'] = '/uploads/life/reply.png'
        self.create_pack(pack_id, content)
        self.write_upload('/uploads/life/mimi.png', PNG)
        self.write_upload('/uploads/life/node.png', PNG + b'node')
        self.write_upload('/uploads/life/reply.png', PNG + b'reply')

        with self.upload_settings():
            export = self.client.get(
                f'/api/virtual-life/packs/{pack_id}/npcs/mimi/export',
                headers=self.headers(1),
            ).json()

            without = deepcopy(content)
            without['npcIds'] = [i for i in without['npcIds'] if i != 'mimi']
            without['npcs'] = [n for n in without['npcs'] if n['id'] != 'mimi']
            without['portraits'].pop('mimi', None)
            without['presence'].pop('mimi', None)
            without['dialogue'].pop('mimi', None)
            without['initialState']['conversations'].pop('mimi', None)
            put = self.client.put(
                f'/api/virtual-life/packs/{pack_id}',
                json={'content': without},
                headers=self.headers(1),
            )
            self.assertEqual(put.status_code, 200, put.text)

            imported = self.client.post(
                f'/api/virtual-life/packs/{pack_id}/npcs/import',
                json={'bundle': export},
                headers=self.headers(1),
            )
            self.assertEqual(imported.status_code, 200, imported.text)

        detail = self.client.get(
            f'/api/virtual-life/packs/{pack_id}',
            headers=self.headers(1),
        ).json()['content']
        self.assertIn('mimi', detail['npcIds'])
        self.assertEqual(next(n for n in detail['npcs'] if n['id'] == 'mimi')['name'], 'mimi')
        self.assertTrue(detail['portraits']['mimi'].startswith('/uploads/life/'))
        self.assertNotEqual(detail['portraits']['mimi'], '/uploads/life/mimi.png')
        stored = Path(self.temp.name) / 'uploads' / detail['portraits']['mimi'].removeprefix('/uploads/')
        self.assertTrue(stored.exists())
        self.assertEqual(detail['presence']['mimi']['status'], 'green')
        self.assertEqual(len(detail['dialogue']['mimi']), 7)
        self.assertEqual(detail['initialState']['conversations']['mimi'], [])

    def test_import_does_not_touch_other_slices(self):
        pack_id = 'wsw-npc-isolated'
        content = mini_pack(['mimi', 'bob'])
        content['portraits']['mimi'] = '/uploads/life/mimi.png'
        content['events'] = [{
            'id': 'greeting',
            'roomId': 'w1-1',
            'title': '房间招呼',
            'icon': '👋',
            'scripts': [
                {'messages': [{'speaker': {'npcId': 'mimi'}, 'lines': ['你好'], 'image': None}]}
                for _ in range(7)
            ],
        }]
        content['endings'] = [{'id': 'end', 'name': '结局', 'text': '完', 'image': None, 'conditions': {}}]
        self.create_pack(pack_id, content)
        self.write_upload('/uploads/life/mimi.png', PNG)

        with self.upload_settings():
            export = self.client.get(
                f'/api/virtual-life/packs/{pack_id}/npcs/mimi/export',
                headers=self.headers(1),
            ).json()
            before = self.client.get(
                f'/api/virtual-life/packs/{pack_id}',
                headers=self.headers(1),
            ).json()['content']
            imported = self.client.post(
                f'/api/virtual-life/packs/{pack_id}/npcs/import',
                json={'bundle': export},
                headers=self.headers(1),
            )
            self.assertEqual(imported.status_code, 200, imported.text)
            after = self.client.get(
                f'/api/virtual-life/packs/{pack_id}',
                headers=self.headers(1),
            ).json()['content']

        for key in ('worlds', 'rooms', 'actions', 'events', 'endings'):
            self.assertEqual(after[key], before[key], key)
        self.assertEqual(after['npcIds'], before['npcIds'])
        self.assertEqual(next(n for n in after['npcs'] if n['id'] == 'bob'),
                         next(n for n in before['npcs'] if n['id'] == 'bob'))
        self.assertEqual(after['portraits']['bob'], before['portraits']['bob'])
        self.assertEqual(after['presence']['bob'], before['presence']['bob'])
        self.assertEqual(after['dialogue']['bob'], before['dialogue']['bob'])
        self.assertEqual(after['initialState']['conversations']['bob'],
                         before['initialState']['conversations']['bob'])

    def test_bad_bundle_rolls_back(self):
        pack_id = 'wsw-npc-bad'
        content = mini_pack(['mimi', 'bob'])
        self.create_pack(pack_id, content)

        with self.upload_settings():
            export = self.client.get(
                f'/api/virtual-life/packs/{pack_id}/npcs/mimi/export',
                headers=self.headers(1),
            ).json()

        before = self.client.get(
            f'/api/virtual-life/packs/{pack_id}',
            headers=self.headers(1),
        ).json()['content']
        before_packs = {p['id'] for p in self.client.get('/api/virtual-life/packs', headers=self.headers(1)).json()}

        bad_format = deepcopy(export)
        bad_format['format'] = 'bad'
        bad_npc_id = deepcopy(export)
        bad_npc_id['npcId'] = 'Bad ID'
        bad_npc_id['data']['npc']['id'] = 'Bad ID'
        bad_image = deepcopy(export)
        bad_image['images'] = {'/uploads/life/x.png': base64.b64encode(b'not image').decode('ascii')}

        with self.upload_settings():
            for bundle in (bad_format, bad_npc_id, bad_image):
                response = self.client.post(
                    f'/api/virtual-life/packs/{pack_id}/npcs/import',
                    json={'bundle': bundle},
                    headers=self.headers(1),
                )
                self.assertEqual(response.status_code, 422, response.text)
                self.assertEqual(
                    self.client.get(f'/api/virtual-life/packs/{pack_id}', headers=self.headers(1)).json()['content'],
                    before,
                )
                packs = self.client.get('/api/virtual-life/packs', headers=self.headers(1)).json()
                self.assertFalse(any('-bak-' in p['id'] for p in packs))
                self.assertEqual({p['id'] for p in packs}, before_packs)

    def test_import_creates_backup(self):
        pack_id = 'wsw-npc-backup'
        content = mini_pack(['mimi'])
        self.create_pack(pack_id, content)

        with self.upload_settings():
            export = self.client.get(
                f'/api/virtual-life/packs/{pack_id}/npcs/mimi/export',
                headers=self.headers(1),
            ).json()
            before = self.client.get(
                f'/api/virtual-life/packs/{pack_id}',
                headers=self.headers(1),
            ).json()['content']
            imported = self.client.post(
                f'/api/virtual-life/packs/{pack_id}/npcs/import',
                json={'bundle': export},
                headers=self.headers(1),
            )
            self.assertEqual(imported.status_code, 200, imported.text)

        backup_id = imported.json()['npcImport']['backupId']
        self.assertIn('-bak-', backup_id)
        packs = self.client.get('/api/virtual-life/packs', headers=self.headers(1)).json()
        self.assertIn(backup_id, [p['id'] for p in packs])
        backup = self.client.get(f'/api/virtual-life/packs/{backup_id}', headers=self.headers(1)).json()
        self.assertEqual(backup['content'], before)
        self.assertFalse(backup['active'])
        self.assertIn('自动备份', backup['name'])

    def test_plain_user_forbidden(self):
        pack_id = 'wsw-npc-auth'
        content = mini_pack(['mimi'])
        self.create_pack(pack_id, content)

        with self.upload_settings():
            export = self.client.get(
                f'/api/virtual-life/packs/{pack_id}/npcs/mimi/export',
                headers=self.headers(1),
            ).json()

        self.assertEqual(
            self.client.get(
                f'/api/virtual-life/packs/{pack_id}/npcs/mimi/export',
                headers=self.headers(3),
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                f'/api/virtual-life/packs/{pack_id}/npcs/import',
                json={'bundle': export},
                headers=self.headers(3),
            ).status_code,
            403,
        )


if __name__ == '__main__':
    unittest.main()