import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { renderTemplate } from '../src/vrclife/engine/template.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const dataDir = join(__dirname, '../../vrclife/data');

function loadVocab() {
  const vocab = JSON.parse(readFileSync(join(dataDir, 'vocab.json'), 'utf8'));
  if (!vocab.worldPool) vocab.worldPool = ['世界1', '世界2'];
  // 覆盖为自定义技能表：{技能} 变量的「最高技能」断言依赖它
  vocab.skills = [
    { key: 'a', name: '技能A' },
    { key: 'b', name: '技能B' },
  ];
  return vocab;
}

function makeRng(overrides = {}) {
  return {
    next: () => 0.5,
    pick: (arr) => (arr && arr.length ? arr[0] : undefined),
    randInt: (_lo, _hi) => 42,
    randint: (_lo, _hi) => 42,
    weightedPick: (items, _weights) => (items && items.length ? items[0] : undefined),
    getState: () => 0,
    setState: () => {},
    ...overrides,
  };
}

function makeSt(overrides = {}) {
  return {
    playerName: '我',
    relation: null,
    circles: [],
    skills: {},
    ...overrides,
  };
}

test('随机组消耗 rng 且结果在组内', () => {
  const vocab = loadVocab();
  const st = makeSt();
  let calls = 0;
  const rng = makeRng({
    next: () => {
      calls++;
      return 0.5;
    },
  });

  const result = renderTemplate('{A|B|C}', st, rng, vocab);

  assert.equal(calls, 1, '应消耗一次 rng');
  assert.ok(['A', 'B', 'C'].includes(result), '结果应在组内');
});

test('七个变量各自替换', () => {
  const vocab = loadVocab();
  const st = makeSt({
    playerName: '玩家',
    relation: { name: '小明' },
    circles: ['圈子1'],
    skills: { a: 10, b: 20 },
  });
  const rng = makeRng({
    pick: (arr) => arr[0],
    randint: () => 42,
    randInt: () => 42,
  });

  assert.equal(renderTemplate('{ta}', st, rng, vocab), '小明');
  assert.equal(renderTemplate('{我}', st, rng, vocab), '玩家');
  assert.equal(renderTemplate('{世界}', st, rng, vocab), vocab.worldPool[0]);
  assert.equal(renderTemplate('{中文吧}', st, rng, vocab), '中文吧');
  assert.equal(renderTemplate('{圈子}', st, rng, vocab), '圈子1');
  assert.equal(renderTemplate('{技能}', st, rng, vocab), '技能B');
  assert.equal(renderTemplate('{N}', st, rng, vocab), '42');
});

test('无关系时 {ta} 为「那个陌生人」', () => {
  const vocab = loadVocab();
  const st = makeSt({ relation: null });
  const rng = makeRng();

  assert.equal(renderTemplate('{ta}', st, rng, vocab), '那个陌生人');
});

test('{圈子} 空数组回退「这里」', () => {
  const vocab = loadVocab();
  const st = makeSt({ circles: [] });
  const rng = makeRng();

  assert.equal(renderTemplate('{圈子}', st, rng, vocab), '这里');
});