import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { evalScore, evaluateEnding, canonicalHint } from '../src/vrclife/engine/ending.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const dataDir = join(__dirname, '../../vrclife/data');

function loadEndings() {
  return JSON.parse(readFileSync(join(dataDir, 'endings.json'), 'utf8')).endings;
}

function loadVocab() {
  return JSON.parse(readFileSync(join(dataDir, 'vocab.json'), 'utf8'));
}

function makeSt(overrides = {}) {
  return {
    hours: 100,
    friends: 5,
    mood: 60,
    fame: 20,
    avatars: 2,
    assets: 1000,
    sugarCount: 1,
    breakupCount: 0,
    skills: { modeling: 36, singing: 10 },
    circles: ['a', 'b'],
    tags: ['萌新', 'sugar'],
    flags: ['flag1'],
    hints: {},
    ...overrides,
  };
}

test('evalScore 四则运算', () => {
  const st = makeSt();
  const vocab = {};
  assert.equal(evalScore('1 + 2 * 3', st, vocab), 7);
  assert.equal(evalScore('(1 + 2) * 3', st, vocab), 9);
});

test('evalScore 比较运算', () => {
  const st = makeSt({ mood: 60 });
  const vocab = {};
  assert.equal(evalScore('mood > 50', st, vocab), 1);
  assert.equal(evalScore('mood < 50', st, vocab), 0);
  assert.equal(evalScore('mood == 60', st, vocab), 1);
  assert.equal(evalScore('mood != 60', st, vocab), 0);
  assert.equal(evalScore('mood >= 60', st, vocab), 1);
  assert.equal(evalScore('mood <= 60', st, vocab), 1);
});

test('evalScore 三元与逻辑运算', () => {
  const st = makeSt({ mood: 60, fame: 20 });
  const vocab = {};
  assert.equal(evalScore('mood > 50 ? 10 : 20', st, vocab), 10);
  // NOTE: 解析器把 &&/|| 与比较放在同一优先级左结合（与 simulate.py 一致），
  // 因此逻辑运算两端必须加括号；endings.json 的 score 表达式从不混用这两者。
  assert.equal(evalScore('(mood > 50) && (fame > 10)', st, vocab), 1);
  assert.equal(evalScore('(mood > 50) || (fame > 100)', st, vocab), 1);
  assert.equal(evalScore('(mood > 50) && (fame > 100)', st, vocab), 0);
});

test('evalScore 除零返回 0', () => {
  const st = makeSt();
  const vocab = {};
  assert.equal(evalScore('1 / 0', st, vocab), 0);
  assert.equal(evalScore('10 / 2', st, vocab), 5);
});

test('evalScore skill.* / hint.* / hasFlag.*', () => {
  const st = makeSt({
    skills: { modeling: 36 },
    hints: { end_creator: 2 },
    flags: ['flag1'],
  });
  const vocab = { endingPathAliases: { creator: 'end_creator' } };

  assert.equal(evalScore('skill.modeling', st, vocab), 36);
  assert.equal(evalScore('skill.unknown', st, vocab), 0);
  assert.equal(evalScore('hint.creator', st, vocab), 2);
  assert.equal(evalScore('hint.unknown', st, vocab), 0);
  assert.equal(evalScore('hasFlag.flag1', st, vocab), 1);
  assert.equal(evalScore('hasFlag.flag2', st, vocab), 0);
});

test('canonicalHint 别名链', () => {
  const vocab = { endingPathAliases: { a: 'b', b: 'c', c: 'd' } };
  assert.equal(canonicalHint('a', vocab), 'd');
  assert.equal(canonicalHint('b', vocab), 'd');
  assert.equal(canonicalHint('x', vocab), 'x');

  // 循环别名应停止并返回当前节点
  const vocab2 = { endingPathAliases: { a: 'b', b: 'a' } };
  assert.equal(canonicalHint('a', vocab2), 'a');
});

test('lock 结局 end_burnout（maxMood:0）必中', () => {
  const endings = loadEndings();
  const vocab = loadVocab();
  const burnout = endings.find((e) => e.id === 'end_burnout');
  assert.ok(burnout, '应有 end_burnout 结局');
  assert.ok(burnout.lock, 'end_burnout 应为 lock');

  const st = makeSt({ mood: 0 });
  const result = evaluateEnding(st, vocab, endings);
  assert.equal(result, 'end_burnout');
});

test('构造状态命中特定结局 end_creator', () => {
  const allEndings = loadEndings();
  const vocab = loadVocab();
  const creator = allEndings.find((e) => e.id === 'end_creator');
  assert.ok(creator, '应有 end_creator 结局');

  const st = makeSt({
    hours: 300,
    skills: { modeling: 36 },
    mood: 60,
    fame: 20,
    friends: 5,
  });

  // 只保留 end_creator 和 end_default 以避免其他结局干扰
  const endDefault = allEndings.find((e) => e.id === 'end_default');
  const endings = [creator, endDefault].filter(Boolean);

  const result = evaluateEnding(st, vocab, endings);
  assert.equal(result, 'end_creator');
});

test('priority 平局加权和兜底 end_default', () => {
  const vocab = {};
  const endings = [
    { id: 'a', condition: {}, score: '1', priority: 1 },
    { id: 'b', condition: {}, score: '1', priority: 2 },
    { id: 'end_default', condition: {}, score: '0' },
  ];
  const st = makeSt();
  assert.equal(evaluateEnding(st, vocab, endings), 'b');

  // 兜底：所有条件不满足
  const endings2 = [
    { id: 'a', condition: { minHours: 9999 }, score: '1' },
    { id: 'end_default', condition: {}, score: '0' },
  ];
  assert.equal(evaluateEnding(st, vocab, endings2), 'end_default');
});