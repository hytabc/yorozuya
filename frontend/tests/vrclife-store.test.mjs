/**
 * vrclife store 单元测试（node:test）。
 * 验证 Pinia store 的数据加载、开局、推进、存档、恢复与结局结算逻辑。
 */
import { test, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { createPinia, setActivePinia } from 'pinia';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { useVrclifeStore } from '../src/vrclife/store/vrclifeStore.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const dataDir = path.resolve(__dirname, '../../vrclife/data');

/** 构造内存存储后端 */
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
    /** 仅供测试：直接读取原始内容 */
    _raw(key) {
      return map.has(key) ? map.get(key) : null;
    },
  };
}

/** 从数据目录加载并组装测试用数据包 */
function loadTestData() {
  const files = fs.readdirSync(dataDir).filter((f) => f.endsWith('.json'));
  const data = {
    events: [],
    byId: {},
    vocab: null,
    endings: [],
    endingsRaw: [],
    archetypes: [],
  };

  for (const file of files) {
    const filePath = path.join(dataDir, file);
    let obj;
    try {
      obj = JSON.parse(fs.readFileSync(filePath, 'utf8'));
    } catch (_e) {
      continue;
    }
    const lower = file.toLowerCase();

    if (lower.includes('event')) {
      data.events = Array.isArray(obj) ? obj : (obj.events || []);
    } else if (lower.includes('ending')) {
      data.endings = Array.isArray(obj) ? obj : (obj.endings || []);
      data.endingsRaw = data.endings;
    } else if (lower.includes('vocab')) {
      data.vocab = obj;
    } else if (lower.includes('archetype')) {
      data.archetypes = Array.isArray(obj) ? obj : (obj.archetypes || []);
    }
  }

  // 若按文件名未识别成功，尝试按内容特征识别
  if (data.events.length === 0) {
    for (const file of files) {
      const obj = JSON.parse(fs.readFileSync(path.join(dataDir, file), 'utf8'));
      if (Array.isArray(obj) && obj.length > 0 && obj[0].options) {
        data.events = obj;
        break;
      }
    }
  }
  if (data.archetypes.length === 0) {
    for (const file of files) {
      const obj = JSON.parse(fs.readFileSync(path.join(dataDir, file), 'utf8'));
      if (Array.isArray(obj) && obj.length > 0 && obj[0].startText) {
        data.archetypes = obj;
        break;
      }
    }
  }
  if (data.endings.length === 0) {
    for (const file of files) {
      const obj = JSON.parse(fs.readFileSync(path.join(dataDir, file), 'utf8'));
      if (Array.isArray(obj) && obj.length > 0 && obj[0].id && obj[0].name && !obj[0].options) {
        data.endings = obj;
        data.endingsRaw = obj;
        break;
      }
    }
  }

  data.byId = Object.fromEntries(data.events.map((e) => [e.id, e]));
  return data;
}

// 模块加载时一次性读取测试数据
const testData = loadTestData();
assert.ok(testData.events.length > 0, 'events 数据应存在');
assert.ok(testData.archetypes.length > 0, 'archetypes 数据应存在');
assert.ok(testData.endings.length > 0, 'endings 数据应存在');
assert.ok(testData.vocab, 'vocab 数据应存在');

let originalLocalStorage;
let backend;
let store;

beforeEach(() => {
  // 每个测试使用独立的 Pinia 实例
  setActivePinia(createPinia());

  // 替换 globalThis.localStorage 为内存实现
  originalLocalStorage = globalThis.localStorage;
  backend = createMemoryBackend();
  globalThis.localStorage = backend;

  // 创建 store 并注入内存存储与测试数据
  store = useVrclifeStore();
  store.initWithStorage(backend);
  store.initWithData(testData);
});

afterEach(() => {
  // 恢复原始 localStorage，避免影响其他测试文件
  if (originalLocalStorage === undefined) {
    delete globalThis.localStorage;
  } else {
    globalThis.localStorage = originalLocalStorage;
  }
});

test('newGame 后进入开场阶段，begin 后进入 playing', () => {
  const archetypeId = testData.archetypes[0].id;
  const game = store.newGame({ seed: '123456', archetypeId });

  assert.equal(store.phase, 'opening');
  assert.ok(store.startArch, '应记录本局出生 archetype');
  assert.ok(store.startText, '应记录出生 startText');
  assert.equal(store.game, game, 'game 实例应被保存');

  store.begin();
  assert.equal(store.phase, 'playing');
});

test('choose 后存档被写入且 history 增长', () => {
  const archetypeId = testData.archetypes[0].id;
  store.newGame({ seed: '123456', archetypeId });
  store.begin();

  const beforeHistory = store.gameState.history.length;
  const current = store.currentEvent;
  assert.ok(current, '应存在当前事件');
  assert.ok(current.options && current.options.length > 0, '当前事件应有可用选项');

  const optionId = current.options.find((o) => o.available).id;
  const res = store.choose(optionId);

  assert.ok(res, 'choose 应返回结果');
  assert.ok(store.gameState.history.length > beforeHistory, 'history 应增长');

  // 检查存档是否落盘
  const raw = backend._raw('vrclife.save.v1');
  assert.ok(raw, '进行中存档应被写入');
  const save = JSON.parse(raw);
  assert.equal(save.version, '1.0');
  assert.ok(save.state.history.length > beforeHistory, '存档中的 history 应同步增长');
});

test('serialize → 写回存档 → continueGame 恢复后 hours 一致', () => {
  const archetypeId = testData.archetypes[0].id;
  store.newGame({ seed: '123456', archetypeId });
  store.begin();

  // 推进几步，确保有非初始状态
  let steps = 0;
  while (store.phase === 'playing' && steps < 5) {
    const current = store.currentEvent;
    if (!current || !current.options || current.options.length === 0) break;
    const opt = current.options.find((o) => o.available);
    if (!opt) break;
    store.choose(opt.id);
    steps++;
  }

  const originalHours = store.gameState.hours;
  // 手动持久化当前状态
  store.persistSave();

  // 创建一个全新的 store 实例来模拟重新打开页面
  setActivePinia(createPinia());
  const newStore = useVrclifeStore();
  newStore.initWithStorage(backend);
  newStore.initWithData(testData);

  const ok = newStore.continueGame();
  assert.equal(ok, true, 'continueGame 应成功');
  assert.equal(newStore.phase, 'playing');
  assert.equal(newStore.gameState.hours, originalHours, '恢复后 hours 应一致');
});

test('固定 seed 总选第一个可用选项跑到结局，结算正确', () => {
  const archetypeId = testData.archetypes[0].id;
  store.newGame({ seed: '123456', archetypeId });
  store.begin();

  let steps = 0;
  const MAX_STEPS = 1000;
  while (store.phase === 'playing' && steps < MAX_STEPS) {
    const current = store.currentEvent;
    if (!current || !current.options || current.options.length === 0) {
      break;
    }
    // 锁定的选项（available=false）引擎会拒选，必须选第一个可用项
    const opt = current.options.find((o) => o.available);
    if (!opt) break;
    store.choose(opt.id);
    steps++;
  }

  assert.equal(store.phase, 'ended', `应在 ${MAX_STEPS} 步内到达结局（实际 ${steps} 步）`);
  assert.equal(store.meta.playCount, 1, 'playCount 应累加为 1');
  assert.ok(store.ending, '应产生结局');
  assert.ok(
    store.meta.unlockedEndings.includes(store.ending.id),
    'unlockedEndings 应包含本局结局 id',
  );

  // 进行中存档应被清除
  assert.equal(backend._raw('vrclife.save.v1'), null, '结局后进行中存档应被清除');
});