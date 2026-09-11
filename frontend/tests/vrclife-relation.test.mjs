import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { applyRelationOp, driftRelation } from '../src/vrclife/engine/relation.js';
import { INACTIVE_REL_STATES } from '../src/vrclife/engine/conditions.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const dataDir = join(__dirname, '../../vrclife/data');

function loadVocab() {
  return JSON.parse(readFileSync(join(dataDir, 'vocab.json'), 'utf8'));
}

function makeRng(overrides = {}) {
  return {
    next: () => 0.5,
    pick: (arr) => (arr && arr.length ? arr[0] : undefined),
    randInt: (lo, _hi) => lo,
    randint: (lo, _hi) => lo,
    weightedPick: (items, _weights) => (items && items.length ? items[0] : undefined),
    getState: () => 0,
    setState: () => {},
    ...overrides,
  };
}

function makeSt(overrides = {}) {
  return {
    hours: 100,
    relation: null,
    spawnBlockUntil: -1,
    sawLow: false,
    sawRecover: false,
    illegal: 0,
    illegalDetail: {},
    recentTags: [],
    sugarPath: new Set(),
    ...overrides,
  };
}

test('spawn 冷却抑制与 force 豁免', () => {
  const vocab = loadVocab();
  const st = makeSt({ hours: 100, spawnBlockUntil: 200, relation: null });
  const rng = makeRng();

  // 无 force，应被抑制
  applyRelationOp(st, { type: 'spawn' }, rng, vocab);
  assert.equal(st.relation, null, '冷却期内 spawn 应被抑制');

  // force 豁免
  applyRelationOp(st, { type: 'spawn', force: true }, rng, vocab);
  assert.ok(st.relation, 'force 应豁免冷却');
  assert.equal(st.relation.state, '认识');
});

test('end 忽略数值键且置 spawnBlockUntil = hours+120', () => {
  const vocab = loadVocab();
  const st = makeSt({
    hours: 500,
    relation: {
      state: '稳定',
      intimacy: 50,
      trust: 50,
      freshness: 90,
      dependence: 0,
      realPressure: 0,
    },
  });
  const rng = makeRng();
  const eventsLog = [];

  applyRelationOp(st, { type: 'end', intimacy: -10 }, rng, vocab, eventsLog);

  assert.equal(st.relation.state, '结束');
  assert.equal(st.spawnBlockUntil, 500 + 120);
  assert.equal(st.relation.intimacy, 50, '数值键应被忽略');
  assert.deepEqual(eventsLog, [['state', '结束']]);
});

test('setState 合法转移：状态更新且数值生效', () => {
  const vocab = loadVocab();
  const st = makeSt({
    relation: {
      state: '认识',
      intimacy: 10,
      trust: 0,
      freshness: 90,
      dependence: 0,
      realPressure: 0,
    },
  });
  const rng = makeRng();
  const legalTargets = vocab.relationStateFlow['认识'] || [];
  assert.ok(legalTargets.length > 0, '认识应有合法转移目标');
  const target = legalTargets[0];

  applyRelationOp(st, { type: 'setState', state: target, intimacy: 5 }, rng, vocab);

  assert.equal(st.relation.state, target);
  assert.equal(st.relation.intimacy, 15);
  assert.equal(st.illegal, 0);
});

test('setState 非法转移：illegal 计数且状态不变但数值生效', () => {
  const vocab = loadVocab();
  const st = makeSt({
    relation: {
      state: '认识',
      intimacy: 10,
      trust: 0,
      freshness: 90,
      dependence: 0,
      realPressure: 0,
    },
  });
  const rng = makeRng();
  const legalTargets = vocab.relationStateFlow['认识'] || [];
  const allStates = vocab.relationStates || [];
  const illegalTarget = allStates.find((s) => s !== '认识' && !legalTargets.includes(s));
  assert.ok(illegalTarget, '应存在非法目标状态');

  applyRelationOp(st, { type: 'setState', state: illegalTarget, intimacy: 5 }, rng, vocab);

  assert.equal(st.relation.state, '认识', '非法转移状态应不变');
  assert.equal(st.relation.intimacy, 15, '数值仍应生效');
  assert.equal(st.illegal, 1);
  assert.equal(st.illegalDetail[`认识->${illegalTarget}`], 1);
});

test('INACTIVE → 活跃 setState 走 spawn 语义', () => {
  const vocab = loadVocab();
  const inactiveState = INACTIVE_REL_STATES[0];
  assert.ok(inactiveState, '应有非活跃状态');

  const st = makeSt({
    hours: 100,
    spawnBlockUntil: -1,
    relation: {
      state: inactiveState,
      name: '旧名',
      intimacy: 0,
      trust: 0,
      freshness: 0,
      dependence: 0,
      realPressure: 0,
    },
  });
  const rng = makeRng({ pick: () => '新名' });
  const activeTarget = (vocab.relationStates || []).find(
    (s) => !INACTIVE_REL_STATES.includes(s)
  );
  assert.ok(activeTarget, '应有活跃状态');

  applyRelationOp(st, { type: 'setState', state: activeTarget }, rng, vocab);

  assert.notEqual(st.relation.name, '旧名', '应创建新关系');
  assert.equal(st.relation.name, '新名');
  assert.equal(st.relation.state, activeTarget);
});

test('init* 先于裸增量', () => {
  const vocab = loadVocab();
  const st = makeSt({
    relation: {
      state: '认识',
      intimacy: 10,
      trust: 0,
      freshness: 90,
      dependence: 0,
      realPressure: 0,
    },
  });
  const rng = makeRng();
  const legalTargets = vocab.relationStateFlow['认识'] || [];
  const target = legalTargets[0] || '认识';

  applyRelationOp(
    st,
    { type: 'setState', state: target, initIntimacy: 50, intimacy: 10 },
    rng,
    vocab
  );

  // init 先赋值为 50，再加 10 => 60
  assert.equal(st.relation.intimacy, 60);
});

test('无关系时数值键静默忽略', () => {
  const vocab = loadVocab();
  const st = makeSt({ relation: null });
  const rng = makeRng();

  applyRelationOp(st, { type: 'renew', intimacy: 10, trust: 10 }, rng, vocab);

  assert.equal(st.relation, null);
});

test('driftRelation 仅在关系活跃时执行', () => {
  const inactiveState = INACTIVE_REL_STATES[0];
  assert.ok(inactiveState, '应有非活跃状态');

  const st = makeSt({
    relation: {
      state: inactiveState,
      intimacy: 50,
      freshness: 50,
      trust: 0,
      dependence: 0,
      realPressure: 0,
    },
  });
  const rng = makeRng();
  const scheduled = [];

  driftRelation(st, rng, scheduled);

  assert.equal(st.relation.freshness, 50, '非活跃关系不应漂移');
  assert.equal(scheduled.length, 0, '不应排入连锁事件');
});