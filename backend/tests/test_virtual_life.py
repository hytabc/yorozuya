import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.models import User
from app.security import create_access_token
from app.virtual_life import router


def state():
    ids = ['ache', 'xiaomi', 'maoyou', 'yu']
    return dict(schemaVersion=1, day=9, stats=dict(mood=72, energy=66, social=34, explore=28),
                currentWorld='beach', unlockedWorlds=8, currentNpcId='ache', tags=['test'],
                npcs=[dict(id=i, name=i, role='test', avatar='', status='', bond=12) for i in ids],
                conversations={i: [{'from': 'npc', 'text': 'persisted', 'day': 9, 'time': '18:20'}] for i in ids},
                diary=[dict(day=9, text='saved diary', mood='calm')], completed={'ache': True})


class SaveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.url = 'sqlite:///' + str(Path(self.temp.name) / 'test.db')
        self.start()
        Base.metadata.create_all(self.engine)
        with self.sessions() as db:
            for i in range(1, 4):
                db.add(User(id=i, username=f'u{i}', password_hash='unused', nickname=f'u{i}', is_admin=i != 3))
            db.commit()

    def start(self):
        self.engine = create_engine(self.url, connect_args={'check_same_thread': False})
        self.sessions = sessionmaker(bind=self.engine)
        app = FastAPI()
        app.include_router(router)
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
        self.assertEqual(loaded['state'], {**state(), 'actionLedger': {}, 'friendIds': [], 'interactedNpcIds': [], 'currentRoomId': None})
        newer = state()
        newer['day'] = 10
        self.assertEqual(self.client.put(url, json={'revision': loaded['revision'], 'state': newer}, headers=self.headers(1)).status_code, 200)
        self.assertEqual(self.client.put(url, json={'revision': 1, 'state': state()}, headers=self.headers(1)).status_code, 409)
        self.assertEqual(self.client.get(url, headers=self.headers(1)).json()['state']['day'], 10)
        invalid = state()
        invalid['currentNpcId'] = 'unknown'
        self.assertEqual(self.client.put(url, json={'revision': 2, 'state': invalid}, headers=self.headers(1)).status_code, 422)

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
        self.assertEqual(self.client.get(url, headers=headers).json()['state'], {**saved, 'friendIds': [], 'interactedNpcIds': [], 'currentRoomId': None})
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


if __name__ == '__main__':
    unittest.main()
