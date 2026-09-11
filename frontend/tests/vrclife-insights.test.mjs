/**
 * 结局洞察（情感分析 / 成就）单测。
 * 纯函数，不依赖浏览器与数据文件。
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildInsights, buildSeries, evaluateAchievements } from '../src/vrclife/engine/insights.js';
import { IN_RUN_ACHIEVEMENTS, CROSS_RUN_ACHIEVEMENTS } from '../src/vrclife/data/achievements.js';

function entry(over = {}) {
  return {
    turn: 0,
    hoursAfter: 10,
    eventTitle: '事件',
    optionText: '选项',
    outcomeText: '结果',
    deltas: [],
    relationSnapshot: null,
    ...over,
  };
}

function state(over = {}) {
  return {
    hours: 300,
    friends: 20,
    mood: 60,
    fame: 50,
    avatars: 3,
    assets: 5000,
    favor: 70,
    sugarCount: 1,
    breakupCount: 0,
    skills: { modeling: 40, coding: 10 },
    circles: ['中文吧'],
    tags: ['萌新'],
    flags: [],
    counters: {},
    hints: { best_friend: 4.5 },
    relation: null,
    history: [],
    ...over,
  };
}

function meta(over = {}) {
  return {
    playCount: 0,
    unlockedEndings: [],
    unlockedArchetypes: [],
    seenEvents: [],
    ...over,
  };
}

const data = {
  endings: new Array(23).fill({}),
  events: new Array(355).fill({}),
  archetypes: new Array(14).fill({}),
};

test('buildSeries 用终局值 + 增量反向重建', () => {
  const history = [
    entry({ deltas: [{ label: '好感度', diff: 4 }] }),
    entry({ turn: 1, hoursAfter: 30, deltas: [{ label: '好感度', diff: -2 }] }),
  ];
  const pts = buildSeries(history, 60, '好感度');
  assert.equal(pts.length, 3);
  assert.equal(pts[0].y, 58); // 60 - (4 - 2)
  assert.equal(pts[1].y, 62);
  assert.equal(pts[2].y, 60);
  assert.equal(pts[2].x, 30);
});

test('buildSeries 空历史 / 缺 deltas 不崩', () => {
  assert.equal(buildSeries([], 42, '好感度').length, 1);
  assert.equal(buildSeries([], 42, '好感度')[0].y, 42);
  const legacy = buildSeries([entry({ deltas: undefined }), entry({ deltas: null })], 33, '心态');
  assert.equal(legacy.length, 3);
  assert.equal(legacy[2].y, 33);
});

test('buildInsights 产出峰值 / 高光 / 低谷 / 文案', () => {
  const history = [
    entry({ turn: 0, hoursAfter: 20, eventTitle: '第一次上台', optionText: '开麦', deltas: [{ label: '心态', diff: 12 }, { label: '好感度', diff: 6 }] }),
    entry({ turn: 1, hoursAfter: 60, eventTitle: '被放了鸽子', optionText: '等', deltas: [{ label: '心态', diff: -18 }] }),
    entry({ turn: 2, hoursAfter: 100, eventTitle: '有人陪你', optionText: '一起', deltas: [{ label: '心态', diff: 5 }, { label: '好感度', diff: 3 }], relationSnapshot: { name: '小满', state: '朋友', intimacy: 60 } }),
  ];
  const st = state({ mood: 59, favor: 79, history });
  const ins = buildInsights(st, {}, data);
  assert.equal(ins.turns, 3);
  assert.equal(ins.mood.start, 60); // 59 - (12 - 18 + 5)
  assert.equal(ins.mood.max.value, 72); // 60 + 12
  assert.equal(ins.mood.min.value, 54); // 72 - 18
  assert.equal(ins.highs[0].eventTitle, '第一次上台');
  assert.equal(ins.lows[0].eventTitle, '被放了鸽子');
  assert.equal(ins.favor.max.value, 79);
  assert.equal(ins.paths[0].key, 'best_friend');
  assert.ok(ins.summary.length > 0);
  assert.ok(ins.summary.includes('好感度'));
});

test('buildInsights 无关系时给出独行文案', () => {
  const ins = buildInsights(state({ history: [entry()] }), {}, data);
  assert.equal(ins.relation.final, null);
  assert.ok(ins.summary.includes('没有哪个名字'));
});

test('evaluateAchievements 本局判定', () => {
  const st = state({ favor: 82, friends: 51, circles: ['a', 'b', 'c', 'd', 'e'] });
  const ins = buildInsights(st, {}, data);
  const res = evaluateAchievements({ st, ending: { id: 'end_best_friend', rarity: 'rare' }, insights: ins, vocab: {}, data, meta: meta() });
  const earned = new Set(res.earnedIds);
  assert.ok(earned.has('favor_80'));
  assert.ok(!earned.has('favor_95'));
  assert.ok(earned.has('friends_50'));
  assert.ok(earned.has('circles_5'));
  assert.ok(earned.has('rare_ending'));
  assert.equal(res.inRun.length, IN_RUN_ACHIEVEMENTS.length);

  const common = evaluateAchievements({ st, ending: { id: 'end_default', rarity: 'common' }, insights: ins, vocab: {}, data, meta: meta() });
  assert.ok(!new Set(common.earnedIds).has('rare_ending'));
  assert.ok(!new Set(common.earnedIds).has('burnout_ending'));
  const burnt = evaluateAchievements({ st, ending: { id: 'end_burnout', rarity: 'special' }, insights: ins, vocab: {}, data, meta: meta() });
  assert.ok(new Set(burnt.earnedIds).has('burnout_ending'));
});

test('evaluateAchievements 跨局进度与解锁', () => {
  const res = evaluateAchievements({
    st: state(),
    ending: { id: 'end_default' },
    insights: buildInsights(state(), {}, data),
    data,
    meta: meta({ playCount: 1, unlockedEndings: ['a', 'b'], seenEvents: new Array(120).fill('x') }),
  });
  const byId = {};
  for (const a of res.crossRun) byId[a.def.id] = a;
  assert.equal(byId.first_run.earned, true);
  assert.equal(byId.runs_10.earned, false);
  assert.equal(byId.endings_5.value, 2);
  assert.equal(byId.endings_5.target, 5);
  assert.equal(byId.events_100.earned, true);
  assert.equal(byId.events_all.target, 355);
  assert.ok(byId['endings_5'].ratio > 0 && byId['endings_5'].ratio < 1);
});

test('evaluateAchievements 空上下文不抛错', () => {
  const res = evaluateAchievements();
  assert.equal(res.earnedIds.length, 0);
  assert.equal(res.inRun.length, IN_RUN_ACHIEVEMENTS.length);
  assert.equal(res.crossRun.length, CROSS_RUN_ACHIEVEMENTS.length);
});

test('成就 id 唯一', () => {
  const ids = [...IN_RUN_ACHIEVEMENTS, ...CROSS_RUN_ACHIEVEMENTS].map((a) => a.id);
  assert.equal(new Set(ids).size, ids.length);
});
