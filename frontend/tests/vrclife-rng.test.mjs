import test from 'node:test';
import assert from 'node:assert/strict';
import { createRng, hashSeed } from '../src/vrclife/engine/rng.js';

test('同 seed 两实例序列一致（连抽 1000 次）', () => {
  const a = createRng('test-seed');
  const b = createRng('test-seed');
  for (let i = 0; i < 1000; i++) {
    assert.equal(a.next(), b.next());
  }
});

test('hashSeed 对同一字符串稳定', () => {
  assert.equal(hashSeed('abc'), hashSeed('abc'));
  assert.notEqual(hashSeed('abc'), hashSeed('abd'));
  assert.ok(hashSeed('x') >= 0);
});

test('getState/setState 恢复后续抽序列一致', () => {
  const a = createRng('abc');
  for (let i = 0; i < 17; i++) a.next();
  const s = a.getState();
  const expected = [a.next(), a.next(), a.next()];
  const b = createRng('completely-different');
  b.setState(s);
  assert.equal(b.next(), expected[0]);
  assert.equal(b.next(), expected[1]);
  assert.equal(b.next(), expected[2]);
});

test('randInt 边界与分布粗检', () => {
  const rng = createRng(42);
  const counts = { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0 };
  for (let i = 0; i < 6000; i++) {
    const v = rng.randint(1, 6);
    assert.ok(v >= 1 && v <= 6 && Number.isInteger(v));
    counts[v]++;
  }
  for (let k = 1; k <= 6; k++) {
    assert.ok(counts[k] > 600, `side ${k}: ${counts[k]}`);
  }
});

test('weightedPick 权重为 0 的项永不命中', () => {
  const rng = createRng(7);
  for (let i = 0; i < 1000; i++) {
    const v = rng.weightedPick(['a', 'b', 'c'], [0, 1, 0]);
    assert.equal(v, 'b');
  }
});

test('weightedPick 全 0 兜底不抛', () => {
  const rng = createRng(7);
  const v = rng.weightedPick(['a', 'b'], [0, 0]);
  assert.ok(v === 'a' || v === 'b');
});