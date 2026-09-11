/**
 * DLC1 好感度（favor）系统单测。
 *
 * 语义事实源：vrclife/DLC1/scripts/simulate_dlc1.py
 * 全部使用最小假数据，不依赖真数据文件。
 */
import test from 'node:test';
import assert from 'node:assert/strict';

import { createGame } from '../src/vrclife/engine/engine.js';
import { applyEffects, deriveTags } from '../src/vrclife/engine/effects.js';
import { evalScore, evaluateEnding } from '../src/vrclife/engine/ending.js';
import { score } from '../src/vrclife/engine/pool.js';

/* ------------------------------------------------------------------ 假数据 */

function baseState(overrides = {}) {
  return {
    hours: 0, friends: 0, mood: 70, fame: 0, avatars: 1, assets: 0,
    sugarCount: 0, breakupCount: 0, favor: 50,
    skills: { coding: 0 },
    circles: [], tags: [], flags: [], counters: {},
    relation: null, usedEvents: [], lastSeen: {}, scheduled: [],
    recentTags: [], lastEvents: [], negStreak: 0, posStreak: 0,
    milestones: new Set(), history: [], sugarPath: new Set(),
    illegal: 0, illegalDetail: {}, spawnBlockUntil: -1,
    sawLow: false, sawRecover: false, hints: {},
    ...overrides,
  };
}

const TEST_VOCAB = {
  skills: [{ key: 'coding', name: '编程' }],
  stages: [{ key: '萌新期', minHours: 0, maxHours: 5000 }],
  hourStepByStage: { 萌新期: [1, 1] },
  worldPool: ['世界'],
  coreTags: [],
  favorTiers: [
    { key: '生分', min: 0, max: 19 },
    { key: '客套', min: 20, max: 39 },
    { key: '聊得来', min: 40, max: 59 },
    { key: '交心', min: 60, max: 79 },
    { key: '挚友', min: 80, max: 100 },
  ],
};

function makeEvent(id, opts = {}) {
  const options = opts.options || [
    {
      id: 'a',
      text: '选项A',
      condition: null,
      outcomes: [
        { weight: 1, tier: 'normal', text: '结果', effects: opts.effects || {} },
      ],
    },
  ];
  return {
    id,
    title: opts.title || id,
    text: opts.text === undefined ? '测试事件文本' : opts.text,
    category: opts.category || 'event',
    weight: opts.weight === undefined ? 10 : opts.weight,
    tags: opts.tags || [],
    hoursRange: opts.hoursRange || [0, 100000],
    condition: opts.condition || null,
    options,
    once: !!opts.once,
    cooldown: opts.cooldown || 0,
  };
}

function makeData(events, opts = {}) {
  const byId = {};
  for (const e of events) byId[e.id] = e;
  return {
    events,
    byId,
    vocab: TEST_VOCAB,
    archetypes: [
      {
        id: 'test',
        name: '测试出生',
        weight: 1,
        init: opts.init || {},
        skills: {},
        tags: ['萌新'],
        flags: {},
      },
    ],
    endings: opts.endings || [
      { id: 'end_default', title: '普通玩家', condition: {}, score: '0', summaryTemplate: '' },
    ],
  };
}

function newGame(events, opts = {}) {
  return createGame({
    data: makeData(events, opts),
    seed: opts.seed === undefined ? 1 : opts.seed,
    archetypeId: 'test',
  });
}

/* ------------------------------------------------------------ 1. 初始与覆盖 */

test('favor 初始为 50（FAVOR_START）', () => {
  const game = newGame([makeEvent('e1')]);
  assert.equal(game.state.favor, 50);
});

test('archetype.init 的 favor 覆盖默认值', () => {
  const game = newGame([makeEvent('e1')], { init: { favor: 80 } });
  assert.equal(game.state.favor, 80);
  const game2 = newGame([makeEvent('e1')], { init: { favor: 0 } });
  assert.equal(game2.state.favor, 0);
});

/* --------------------------------------------------------------- 2. 自然漂移 */

test('每回合末尾自然漂移 -0.35', () => {
  const game = newGame([makeEvent('e1')]);
  assert.equal(game.state.favor, 50);
  game.choose('a');
  assert.ok(Math.abs(game.state.favor - 49.65) < 1e-9, `favor=${game.state.favor}`);
});

test('漂移在回合末发生（事件 fx 先结算、再漂移）', () => {
  const game = newGame([makeEvent('rise', { effects: { favor: 30 } })]);
  game.choose('a');
  // 50 + 30 = 80，再 -0.35
  assert.ok(Math.abs(game.state.favor - 79.65) < 1e-9, `favor=${game.state.favor}`);
});

/* ------------------------------------------------------------ 3. 下界夹取 */

test('favor 漂移在 0 处夹取，不为负', () => {
  const game = newGame([makeEvent('e1')]);
  game.state.favor = 0.2;
  game.choose('a');
  assert.equal(game.state.favor, 0);
});

/* ------------------------------------------------- 4. fx.favor 增减与上界夹取 */

test('fx.favor 增减与 [0,100] 夹取', () => {
  const st = baseState({ favor: 50 });
  applyEffects(st, { favor: 30 });
  assert.ok(Math.abs(st.favor - 80) < 1e-9, `favor=${st.favor}`);

  applyEffects(st, { favor: -100 });
  assert.equal(st.favor, 0);

  const st2 = baseState({ favor: 95 });
  applyEffects(st2, { favor: 30 });
  assert.equal(st2.favor, 100);

  // 没有 favor 字段时不改动
  const st3 = baseState({ favor: 42 });
  applyEffects(st3, { mood: 5 });
  assert.equal(st3.favor, 42);
});

/* --------------------------------------------------------- 5. 挚友标签规则 */

test('挚友标签：favor≥80 加上', () => {
  const st = baseState({ favor: 80 });
  deriveTags(st);
  assert.ok(st.tags.includes('挚友'));

  const st2 = baseState({ favor: 100 });
  deriveTags(st2);
  assert.ok(st2.tags.includes('挚友'));
});

test('挚友标签：favor<60 移除', () => {
  const st = baseState({ favor: 59.99, tags: ['挚友'] });
  deriveTags(st);
  assert.ok(!st.tags.includes('挚友'), JSON.stringify(st.tags));
});

test('挚友标签：60 ≤ favor < 80 保持现状（elif 关系）', () => {
  const keepA = baseState({ favor: 60, tags: ['挚友'] });
  deriveTags(keepA);
  assert.ok(keepA.tags.includes('挚友'));

  const keepB = baseState({ favor: 79.99, tags: ['挚友'] });
  deriveTags(keepB);
  assert.ok(keepB.tags.includes('挚友'));

  // 本来没有就不会凭空加上
  const none = baseState({ favor: 79.99, tags: [] });
  deriveTags(none);
  assert.ok(!none.tags.includes('挚友'));
});

/* ----------------------------------------------------------- 6. 圈子浪人 */

test('圈子浪人：circles≥5 加上，且无移除规则', () => {
  const five = baseState({ circles: ['a', 'b', 'c', 'd', 'e'] });
  deriveTags(five);
  assert.ok(five.tags.includes('圈子浪人'));

  const four = baseState({ circles: ['a', 'b', 'c', 'd'] });
  deriveTags(four);
  assert.ok(!four.tags.includes('圈子浪人'));

  five.circles.pop(); // 掉回 4 个也保留
  deriveTags(five);
  assert.ok(five.tags.includes('圈子浪人'));
});

/* ----------------------------------------------------- 7. conditions 门控 */

test('conditions：minFavor / maxFavor 门控事件可用性', () => {
  const high = makeEvent('need_favor', { condition: { minFavor: 60 } });
  const low = makeEvent('cap_favor', { condition: { maxFavor: 40 } });

  // favor=80：只有 need_favor 可用
  const gHigh = newGame([high, low], { init: { favor: 80 }, seed: 21 });
  assert.equal(gHigh.phase, 'playing');
  assert.equal(gHigh.current.event.id, 'need_favor');

  // favor=20：只有 cap_favor 可用
  const gLow = newGame([high, low], { init: { favor: 20 }, seed: 21 });
  assert.equal(gLow.phase, 'playing');
  assert.equal(gLow.current.event.id, 'cap_favor');

  // favor=50：两条都被门掉 → 空池
  const gMid = newGame([high, low], { init: { favor: 50 }, seed: 21 });
  assert.equal(gMid.phase, 'ended');
  assert.equal(gMid.error, 'EMPTY_POOL');
});

/* --------------------------------------------------------- 8. ending 条件 */

test('ending：minFavor / maxFavor / minCircles 条件', () => {
  const endings = [
    { id: 'end_favor', title: '高好感', condition: { minFavor: 80 }, score: 'favor * 2', summaryTemplate: '' },
    { id: 'end_circles', title: '圈子', condition: { minCircles: 5 }, score: 'circle.count * 10', summaryTemplate: '' },
    { id: 'end_default', title: '普通玩家', condition: {}, score: '0', summaryTemplate: '' },
  ];

  assert.equal(evaluateEnding(baseState({ favor: 90 }), TEST_VOCAB, endings), 'end_favor');
  assert.equal(
    evaluateEnding(baseState({ favor: 50, circles: ['a', 'b', 'c', 'd', 'e'] }), TEST_VOCAB, endings),
    'end_circles',
  );
  assert.equal(evaluateEnding(baseState({ favor: 50 }), TEST_VOCAB, endings), 'end_default');

  const maxEndings = [
    { id: 'end_cold', title: '生分', condition: { maxFavor: 30 }, score: '100 - favor', summaryTemplate: '' },
    { id: 'end_default', title: '普通玩家', condition: {}, score: '0', summaryTemplate: '' },
  ];
  assert.equal(evaluateEnding(baseState({ favor: 20 }), TEST_VOCAB, maxEndings), 'end_cold');
  assert.equal(evaluateEnding(baseState({ favor: 31 }), TEST_VOCAB, maxEndings), 'end_default');
  assert.equal(evaluateEnding(baseState({ favor: 30 }), TEST_VOCAB, maxEndings), 'end_cold');
});

test('ending：score 表达式里 favor 变量可用', () => {
  assert.equal(evalScore('favor', baseState({ favor: 73.5 }), TEST_VOCAB), 73.5);
  assert.equal(evalScore('favor >= 80 ? 1 : 0', baseState({ favor: 85 }), TEST_VOCAB), 1);
  assert.equal(evalScore('favor >= 80 ? 1 : 0', baseState({ favor: 79 }), TEST_VOCAB), 0);
  assert.equal(evalScore('favor * 2 + circle.count', baseState({ favor: 10, circles: ['a', 'b'] }), TEST_VOCAB), 22);
});

/* ------------------------------------------------------------- 9. 序列化 */

test('序列化往返保留 favor', () => {
  const data = makeData([makeEvent('e1')]);
  const game = createGame({ data, seed: 31, archetypeId: 'test' });
  game.state.favor = 77.5;

  const save = game.serialize();
  assert.equal(save.favor, 77.5);

  const restored = createGame.fromSave(save, data);
  assert.equal(restored.state.favor, 77.5);
});

test('旧存档（无 favor 字段）恢复为 50', () => {
  const data = makeData([makeEvent('e1')]);
  const game = createGame({ data, seed: 31, archetypeId: 'test' });
  game.state.favor = 12;

  const save = game.serialize();
  delete save.favor;

  const restored = createGame.fromSave(save, data);
  assert.equal(restored.state.favor, 50);
});

/* --------------------------------------------------------- 10. 权重修正 */

test('权重修正：favor<30 时带「友情」的事件 ×1.3', () => {
  const vocab = { stages: [{ key: 's1', minHours: 0, maxHours: 1000 }] };
  const ev = { id: 'friend', weight: 10, tags: ['友情'], stage: 's1' };
  const rng = { next: () => 0.5 }; // 抖动系数 0.8 + 0.5*0.4 = 1.0

  const wHigh = score(ev, baseState({ favor: 50 }), rng, vocab);
  const wLow = score(ev, baseState({ favor: 29 }), rng, vocab);
  const wEdge = score(ev, baseState({ favor: 30 }), rng, vocab);

  assert.ok(Math.abs(wLow - wHigh * 1.3) < 1e-9, `${wLow} vs ${wHigh}`);
  assert.ok(Math.abs(wEdge - wHigh) < 1e-9);

  // 不带「友情」的事件不受 favor 影响
  const other = { id: 'plain', weight: 10, tags: ['日常'], stage: 's1' };
  const pLow = score(other, baseState({ favor: 5 }), rng, vocab);
  const pHigh = score(other, baseState({ favor: 80 }), rng, vocab);
  assert.ok(Math.abs(pLow - pHigh) < 1e-9);
});

test('权重修正：设备党 ×1.5、挚友+友情+正面 ×1.4', () => {
  const vocab = { stages: [{ key: 's1', minHours: 0, maxHours: 1000 }] };
  const rng = { next: () => 0.5 };

  const devEv = { id: 'dev', weight: 10, tags: ['设备'], stage: 's1' };
  const devPlain = score(devEv, baseState(), rng, vocab);
  const devBoost = score(devEv, baseState({ tags: ['Quest党'] }), rng, vocab);
  assert.ok(Math.abs(devBoost - devPlain * 1.5) < 1e-9, `${devBoost} vs ${devPlain}`);

  const friendEv = { id: 'f', weight: 10, tags: ['友情', '正面'], stage: 's1' };
  const fPlain = score(friendEv, baseState(), rng, vocab);
  const fBoost = score(friendEv, baseState({ tags: ['挚友'] }), rng, vocab);
  assert.ok(Math.abs(fBoost - fPlain * 1.4) < 1e-9, `${fBoost} vs ${fPlain}`);
});