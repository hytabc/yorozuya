/**
 * vrclife storage 单元测试（node:test）。
 * 通过注入内存假 backend 来验证 createStorage 的读写、版本校验与默认回落行为。
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  createStorage,
  defaultMeta,
  SAVE_KEY,
  META_KEY,
  SAVE_VERSION,
} from '../src/vrclife/utils/storage.js';

/** 构造一个内存存储后端（行为与浏览器 localStorage 的最小子集一致） */
function createMemoryBackend() {
  const map = new Map();
  return {
    getItem(key) {
      return map.has(key) ? map.get(key) : null;
    },
    setItem(key, value) {
      map.set(key, String(value));
    },
    removeItem(key) {
      map.delete(key);
    },
    /** 仅供测试：直接窥视原始内容 */
    _raw(key) {
      return map.has(key) ? map.get(key) : null;
    },
  };
}

test('createStorage 使用注入的内存后端', () => {
  const backend = createMemoryBackend();
  const storage = createStorage(backend);
  assert.equal(storage.backend, backend);
});

test('writeSave / loadSave 往返一致', () => {
  const backend = createMemoryBackend();
  const storage = createStorage(backend);

  const state = {
    seed: '123456',
    hours: 42,
    mood: 66,
    skills: { talk: 3, dance: 1 },
    history: [{ turn: 0, eventId: 'ev_a' }],
  };
  const meta = { ...defaultMeta(), playCount: 2 };
  const savedAt = 1700000000000;

  const ok = storage.writeSave({ state, meta, savedAt });
  assert.equal(ok, true);

  const loaded = storage.loadSave();
  assert.ok(loaded, 'loadSave 应返回对象');
  assert.equal(loaded.version, SAVE_VERSION);
  assert.equal(loaded.savedAt, savedAt);
  assert.deepEqual(loaded.state, state);
  assert.deepEqual(loaded.meta, meta);
});

test('writeSave 缺少 state 时返回 false 且不写入', () => {
  const backend = createMemoryBackend();
  const storage = createStorage(backend);

  assert.equal(storage.writeSave(null), false);
  assert.equal(storage.writeSave({}), false);
  assert.equal(storage.writeSave({ state: null }), false);
  assert.equal(storage.writeSave({ state: 'oops' }), false);

  assert.equal(backend._raw(SAVE_KEY), null);
  assert.equal(storage.loadSave(), null);
});

test('writeSave 未传 savedAt 时自动填充', () => {
  const backend = createMemoryBackend();
  const storage = createStorage(backend);
  storage.writeSave({ state: { hours: 1 } });

  const loaded = storage.loadSave();
  assert.ok(loaded);
  assert.equal(typeof loaded.savedAt, 'number');
  assert.ok(loaded.savedAt > 0);
});

test('版本不符时 loadSave 返回 null', () => {
  const backend = createMemoryBackend();
  backend.setItem(
    SAVE_KEY,
    JSON.stringify({ version: '0.9', savedAt: 1, state: { hours: 1 }, meta: {} }),
  );

  const storage = createStorage(backend);
  assert.equal(storage.loadSave(), null);
});

test('缺少 state 字段时 loadSave 返回 null', () => {
  const backend = createMemoryBackend();
  backend.setItem(SAVE_KEY, JSON.stringify({ version: SAVE_VERSION, savedAt: 1 }));

  const storage = createStorage(backend);
  assert.equal(storage.loadSave(), null);
});

test('JSON 损坏时 loadSave 返回 null（不抛异常）', () => {
  const backend = createMemoryBackend();
  backend.setItem(SAVE_KEY, '{not valid json');

  const storage = createStorage(backend);
  assert.equal(storage.loadSave(), null);
});

test('clearSave 移除存档', () => {
  const backend = createMemoryBackend();
  const storage = createStorage(backend);

  storage.writeSave({ state: { hours: 5 } });
  assert.ok(storage.loadSave());

  assert.equal(storage.clearSave(), true);
  assert.equal(storage.loadSave(), null);
  assert.equal(backend._raw(SAVE_KEY), null);
});

test('loadMeta 缺省时返回默认值', () => {
  const backend = createMemoryBackend();
  const storage = createStorage(backend);

  assert.deepEqual(storage.loadMeta(), {
    playCount: 0,
    unlockedEndings: [],
    unlockedArchetypes: [],
    seenEvents: [],
  });
});

test('loadMeta / writeMeta 往返一致', () => {
  const backend = createMemoryBackend();
  const storage = createStorage(backend);

  const meta = {
    playCount: 7,
    unlockedEndings: ['end_a', 'end_b'],
    unlockedArchetypes: ['arch_x'],
    seenEvents: ['ev_1'],
  };

  assert.equal(storage.writeMeta(meta), true);
  assert.deepEqual(storage.loadMeta(), meta);
});

test('loadMeta 在数据损坏时回落默认值', () => {
  const backend = createMemoryBackend();
  backend.setItem(META_KEY, 'not json at all');

  const storage = createStorage(backend);
  assert.deepEqual(storage.loadMeta(), {
    playCount: 0,
    unlockedEndings: [],
    unlockedArchetypes: [],
    seenEvents: [],
  });
});

test('loadMeta 对非法字段做清洗（负数 / 非数组）', () => {
  const backend = createMemoryBackend();
  backend.setItem(
    META_KEY,
    JSON.stringify({
      playCount: -12.7,
      unlockedEndings: 'not-an-array',
      unlockedArchetypes: null,
      seenEvents: { a: 1 },
    }),
  );

  const storage = createStorage(backend);
  assert.deepEqual(storage.loadMeta(), {
    playCount: 0,
    unlockedEndings: [],
    unlockedArchetypes: [],
    seenEvents: [],
  });
});

test('defaultMeta 每次返回新对象（互不共享引用）', () => {
  const a = defaultMeta();
  const b = defaultMeta();
  assert.notEqual(a, b);
  a.unlockedEndings.push('end_x');
  assert.equal(b.unlockedEndings.length, 0);
  assert.equal(a.playCount, 0);
});
