import test from 'node:test';
import assert from 'node:assert/strict';
import { match, tagsOk, flagsOk, INACTIVE_REL_STATES } from '../src/vrclife/engine/conditions.js';

function baseState(overrides = {}) {
  return {
    hours: 0, friends: 0, mood: 70, fame: 0, avatars: 1, assets: 0,
    sugarCount: 0, breakupCount: 0,
    skills: { modeling: 0, coding: 0, photo: 0, music: 0, dance: 0, language: 0, social: 0, meme: 0 },
    circles: [], tags: ['萌新'], flags: [], counters: {},
    relation: null, usedEvents: [], lastSeen: {}, scheduled: [],
    recentTags: [], lastEvents: [], negStreak: 0, posStreak: 0,
    milestones: new Set(), history: [], sugarPath: new Set(),
    illegal: 0, illegalDetail: {}, spawnBlockUntil: -1,
    sawLow: false, sawRecover: false, hints: {},
    ...overrides,
  };
}

function countingRng() {
  let n = 0;
  return {
    next() { n++; return 0.5; },
    count() { return n; },
  };
}


test('同时多段关系条件：minActiveRelations / minSugarRelations / anyRelation', () => {
  const relA = { id: 1, name: 'A', state: '朋友', intimacy: 10, trust: 10, freshness: 50, dependence: 0, realPressure: 0 };
  const relB = { id: 2, name: 'B', state: '砂糖', intimacy: 70, trust: 60, freshness: 60, dependence: 10, realPressure: 5 };
  const st = baseState({ relations: [relA, relB], relation: relA });

  assert.equal(match({ minActiveRelations: 2 }, st), true);
  assert.equal(match({ minActiveRelations: 3 }, st), false);
  assert.equal(match({ minSugarRelations: 1 }, st), true);
  assert.equal(match({ minSugarRelations: 2 }, st), false);

  // 默认看焦点（relA，intimacy 10）；anyRelation 时 relB 满足
  assert.equal(match({ minIntimacy: 50 }, st), false);
  assert.equal(match({ minIntimacy: 50, anyRelation: true }, st), true);
  assert.equal(match({ relationState: ['砂糖'] }, st), false);
  assert.equal(match({ relationState: ['砂糖'], anyRelation: true }, st), true);

  // 已结束的关系不计入活跃数
  const st2 = baseState({ relations: [relA, { ...relB, state: '结束' }], relation: relA });
  assert.equal(match({ minActiveRelations: 2 }, st2), false);
  assert.equal(match({ minSugarRelations: 1 }, st2), false);
});
test('空 condition 恒真', () => {
  assert.equal(match(null, baseState()), true);
  assert.equal(match({}, baseState()), true);
});

test('minHours/maxHours', () => {
  const st = baseState({ hours: 50 });
  assert.equal(match({ minHours: 50 }, st), true);
  assert.equal(match({ minHours: 51 }, st), false);
  assert.equal(match({ maxHours: 50 }, st), true);
  assert.equal(match({ maxHours: 49 }, st), false);
});

test('minMood/maxMood', () => {
  const st = baseState({ mood: 50 });
  assert.equal(match({ minMood: 50, maxMood: 50 }, st), true);
  assert.equal(match({ minMood: 51 }, st), false);
  assert.equal(match({ maxMood: 49 }, st), false);
});

test('minFame/minFriends/maxFriends/minAvatars/minAssets', () => {
  const st = baseState({ fame: 10, friends: 5, avatars: 2, assets: 100 });
  assert.equal(match({ minFame: 10 }, st), true);
  assert.equal(match({ minFame: 11 }, st), false);
  assert.equal(match({ minFriends: 5 }, st), true);
  assert.equal(match({ maxFriends: 4 }, st), false);
  assert.equal(match({ minAvatars: 3 }, st), false);
  assert.equal(match({ minAssets: 100 }, st), true);
});

test('minSugarCount/minBreakupCount', () => {
  const st = baseState({ sugarCount: 1, breakupCount: 2 });
  assert.equal(match({ minSugarCount: 1 }, st), true);
  assert.equal(match({ minSugarCount: 2 }, st), false);
  assert.equal(match({ minBreakupCount: 2 }, st), true);
  assert.equal(match({ minBreakupCount: 3 }, st), false);
});

test('tags/requireAnyTags/excludeTags', () => {
  const st = baseState({ tags: ['萌新', '社恐'] });
  assert.equal(match({ requireTags: ['萌新'] }, st), true);
  assert.equal(match({ requireTags: ['舞者'] }, st), false);
  assert.equal(match({ requireAnyTags: ['舞者', '社恐'] }, st), true);
  assert.equal(match({ requireAnyTags: ['舞者', '摄影师'] }, st), false);
  assert.equal(match({ excludeTags: ['舞者'] }, st), true);
  assert.equal(match({ excludeTags: ['社恐'] }, st), false);
});

test('flags/requireFlags/excludeFlags', () => {
  const st = baseState({ flags: ['a'] });
  assert.equal(match({ requireFlags: ['a'] }, st), true);
  assert.equal(match({ requireFlags: ['b'] }, st), false);
  assert.equal(match({ excludeFlags: ['b'] }, st), true);
  assert.equal(match({ excludeFlags: ['a'] }, st), false);
});

test('requireCircles', () => {
  const st = baseState({ circles: ['中文吧'] });
  assert.equal(match({ requireCircles: ['中文吧'] }, st), true);
  assert.equal(match({ requireCircles: ['跳舞圈'] }, st), false);
});

test('minSkills/maxSkills/all 特判', () => {
  const st = baseState({ skills: { modeling: 30, dance: 50, coding: 0, photo: 0, music: 0, language: 0, social: 0, meme: 0 } });
  assert.equal(match({ minSkills: { modeling: 30 } }, st), true);
  assert.equal(match({ minSkills: { modeling: 31 } }, st), false);
  assert.equal(match({ maxSkills: { modeling: 30 } }, st), true);
  assert.equal(match({ maxSkills: { modeling: 29 } }, st), false);
  assert.equal(match({ maxSkills: { all: 50 } }, st), true);
  assert.equal(match({ maxSkills: { all: 49 } }, st), false);
});

test('hasRelation 及 INACTIVE 语义', () => {
  assert.equal(match({ hasRelation: true }, baseState()), false);
  assert.equal(match({ hasRelation: false }, baseState()), true);

  const active = baseState({ relation: { state: '暧昧', intimacy: 10, dependence: 5, trust: 5, freshness: 50, realPressure: 30 } });
  assert.equal(match({ hasRelation: true }, active), true);
  assert.equal(match({ hasRelation: false }, active), false);

  for (const s of INACTIVE_REL_STATES) {
    const st = baseState({ relation: { state: s, intimacy: 0, dependence: 0, trust: 0, freshness: 0, realPressure: 0 } });
    assert.equal(match({ hasRelation: true }, st), false);
    assert.equal(match({ hasRelation: false }, st), true);
  }
});

test('relationState 不要求活跃（结束/低迷/恢复也能命中）', () => {
  const st = baseState({ relation: { state: '低迷', intimacy: 0, dependence: 0, trust: 0, freshness: 0, realPressure: 0 } });
  assert.equal(match({ relationState: ['低迷'] }, st), true);
  assert.equal(match({ relationState: ['暧昧'] }, st), false);
});

test('min 维度要求活跃', () => {
  const st = baseState({ relation: { state: '低迷', intimacy: 100, dependence: 100, trust: 100, freshness: 100, realPressure: 100 } });
  assert.equal(match({ minIntimacy: 5 }, st), false);
  assert.equal(match({ minDependence: 5 }, st), false);
  assert.equal(match({ minTrust: 5 }, st), false);
  assert.equal(match({ minFreshness: 5 }, st), false);
  assert.equal(match({ minRealPressure: 5 }, st), false);
});

test('maxRealPressure（not r 或 > 则 false）', () => {
  assert.equal(match({ maxRealPressure: 100 }, baseState()), false);
  const st = baseState({ relation: { state: '暧昧', intimacy: 0, dependence: 0, trust: 0, freshness: 0, realPressure: 30 } });
  assert.equal(match({ maxRealPressure: 30 }, st), true);
  assert.equal(match({ maxRealPressure: 29 }, st), false);
});

test('requiresEventDone/excludesEventDone', () => {
  const st = baseState({ usedEvents: ['intro_001'] });
  assert.equal(match({ requiresEventDone: ['intro_001'] }, st), true);
  assert.equal(match({ requiresEventDone: ['intro_002'] }, st), false);
  assert.equal(match({ excludesEventDone: ['intro_002'] }, st), true);
  assert.equal(match({ excludesEventDone: ['intro_001'] }, st), false);
});

test('probability 消耗 rng', () => {
  const rng = countingRng();
  assert.equal(match({ probability: 1.0 }, baseState(), rng), true);
  assert.equal(rng.count(), 1);
  const rng2 = countingRng();
  assert.equal(match({ probability: 0.0 }, baseState(), rng2), false);
  assert.equal(rng2.count(), 1);
});

test('无 probability 时不消耗 rng', () => {
  const rng = countingRng();
  match({ minHours: 0 }, baseState(), rng);
  assert.equal(rng.count(), 0);
});

test('tagsOk/flagsOk 单独可用', () => {
  assert.equal(tagsOk({ requireTags: ['萌新'] }, baseState()), true);
  assert.equal(flagsOk({ requireFlags: ['x'] }, baseState()), false);
});