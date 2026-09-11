import test from 'node:test';
import assert from 'node:assert/strict';
import { applyEffects, deriveTags } from '../src/vrclife/engine/effects.js';

function baseState(overrides = {}) {
  return {
    hours: 0, friends: 0, mood: 70, fame: 0, avatars: 1, assets: 0,
    sugarCount: 0, breakupCount: 0,
    skills: { modeling: 0, coding: 0, photo: 0, music: 0, dance: 0, language: 0, social: 0, meme: 0 },
    circles: [], tags: [], flags: [], counters: {},
    relation: null, usedEvents: [], lastSeen: {}, scheduled: [],
    recentTags: [], lastEvents: [], negStreak: 0, posStreak: 0,
    milestones: new Set(), history: [], sugarPath: new Set(),
    illegal: 0, illegalDetail: {}, spawnBlockUntil: -1,
    sawLow: false, sawRecover: false, hints: {},
    ...overrides,
  };
}

test('mood 软上限：mood=90 时 +10 的实际增量 = 10×(10/30)', () => {
  const st = baseState({ mood: 90 });
  applyEffects(st, { mood: 10 });
  const expected = 90 + 10 * (10 / 30);
  assert.ok(Math.abs(st.mood - expected) < 1e-9, `${st.mood} != ${expected}`);
});

test('mood 负增量 -50 截断为 -20', () => {
  const st = baseState({ mood: 70 });
  applyEffects(st, { mood: -50 });
  assert.equal(st.mood, 50);
});

test('mood 夹取到 [0,100]', () => {
  const st = baseState({ mood: 5 });
  applyEffects(st, { mood: -100 });
  assert.equal(st.mood, 0);
  const st2 = baseState({ mood: 99 });
  applyEffects(st2, { mood: 100 }); // 软上限之后不会到 100
  assert.ok(st2.mood <= 100 && st2.mood > 99);
});

test('friends [0,999]，fame [0,100]，avatars≥0，assets 可负', () => {
  const st = baseState({ friends: 5, fame: 50, avatars: 2, assets: 100 });
  applyEffects(st, { friends: -100, fame: 100, avatars: -100, assets: -500 });
  assert.equal(st.friends, 0);
  assert.equal(st.fame, 100);
  assert.equal(st.avatars, 0);
  assert.equal(st.assets, -400);
});

test('sugarCount/breakupCount/hoursBonus 累加', () => {
  const st = baseState();
  applyEffects(st, { sugarCount: 2, breakupCount: 3, hoursBonus: 10 });
  assert.equal(st.sugarCount, 2);
  assert.equal(st.breakupCount, 3);
  assert.equal(st.hours, 10);
});

test('skills 夹取到 [0,100]', () => {
  const st = baseState();
  applyEffects(st, { skills: { modeling: 200, dance: -5 } });
  assert.equal(st.skills.modeling, 100);
  assert.equal(st.skills.dance, 0);
});

test('tags/circles/flags 增删幂等', () => {
  const st = baseState();
  applyEffects(st, { tags: { add: ['a', 'a'] }, circles: { add: ['c', 'c'] }, flags: { add: ['f', 'f'] } });
  assert.deepEqual(st.tags.filter((x) => x === 'a'), ['a']);
  assert.deepEqual(st.circles, ['c']);
  assert.deepEqual(st.flags, ['f']);
  applyEffects(st, { tags: { remove: ['a', 'nope'] }, circles: { remove: ['c', 'nope'] }, flags: { remove: ['f', 'nope'] } });
  assert.ok(!st.tags.includes('a'));
  assert.ok(!st.circles.includes('c'));
  assert.ok(!st.flags.includes('f'));
});

test('counters 累加', () => {
  const st = baseState();
  applyEffects(st, { counters: { photos: 1 } });
  applyEffects(st, { counters: { photos: 2 } });
  assert.equal(st.counters.photos, 3);
});

test('derive_tags: hours≥50 移除萌新', () => {
  const st = baseState({ hours: 50, tags: ['萌新'] });
  deriveTags(st);
  assert.ok(!st.tags.includes('萌新'));
  const st2 = baseState({ hours: 49, tags: ['萌新'] });
  deriveTags(st2);
  assert.ok(st2.tags.includes('萌新'));
});

test('derive_tags: friends<5 且 hours>100 加独行侠', () => {
  const st = baseState({ hours: 101, friends: 4 });
  deriveTags(st);
  assert.ok(st.tags.includes('独行侠'));
  const st2 = baseState({ hours: 100, friends: 4 });
  deriveTags(st2);
  assert.ok(!st2.tags.includes('独行侠'));
  const st3 = baseState({ hours: 101, friends: 5 });
  deriveTags(st3);
  assert.ok(!st3.tags.includes('独行侠'));
});

test('derive_tags: 退坑边缘规则（≤14 加；15-29 保持；≥30 移除）', () => {
  const low = baseState({ mood: 14, tags: [] });
  deriveTags(low);
  assert.ok(low.tags.includes('退坑边缘'));

  const mid = baseState({ mood: 20, tags: ['退坑边缘'] });
  deriveTags(mid);
  assert.ok(mid.tags.includes('退坑边缘')); // 保持现状

  const high = baseState({ mood: 30, tags: ['退坑边缘'] });
  deriveTags(high);
  assert.ok(!high.tags.includes('退坑边缘'));
});