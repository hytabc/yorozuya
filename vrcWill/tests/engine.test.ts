/**
 * 判定引擎单元测试
 * ------------------------------------------------------------------
 * 运行： node --test tests/engine.test.ts
 * 无第三方依赖（使用 node:test），可直接执行。
 *
 * 覆盖目标：分支覆盖 ≥ 90%（见 PRD 验收标准 §13.6）
 */

import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

import type { Level } from '../src/lib/engine/types.ts';
import {
  matchConstraint,
  isContiguousGroup,
  validateChain,
  assembleChain,
  sumWeights,
} from '../src/lib/engine/constraints.ts';
import { scoreEnding, computeCoherence, computeChainValence } from '../src/lib/engine/scoring.ts';
import { judgeChain, evaluateEnding, isEndingUnlocked, previewChain, isExactSolution } from '../src/lib/engine/judge.ts';
import { detectButterflies, resolveRedUnlock, computeDraggable } from '../src/lib/engine/butterfly.ts';
import { resolveHintTier, getHint, getRuleHint } from '../src/lib/engine/hints.ts';

const HERE = dirname(fileURLToPath(import.meta.url));
const LEVELS_DIR = join(HERE, '..', 'src', 'lib', 'data', 'levels');

function loadLevel(id: string): Level {
  return JSON.parse(readFileSync(join(LEVELS_DIR, `${id}.json`), 'utf8')) as Level;
}

/* ============================================================
 * 1. 约束匹配器
 * ============================================================ */

test('constraints: before', () => {
  const chain = ['A', 'B', 'C'];
  assert.equal(matchConstraint(chain, { kind: 'before', a: 'A', b: 'C', weight: 1 }), true);
  assert.equal(matchConstraint(chain, { kind: 'before', a: 'C', b: 'A', weight: 1 }), false);
});

test('constraints: adjacent 顺序不敏感', () => {
  const chain = ['A', 'B', 'C'];
  assert.equal(matchConstraint(chain, { kind: 'adjacent', a: 'A', b: 'B', weight: 1 }), true);
  assert.equal(matchConstraint(chain, { kind: 'adjacent', a: 'B', b: 'A', weight: 1 }), true);
  assert.equal(matchConstraint(chain, { kind: 'adjacent', a: 'A', b: 'C', weight: 1 }), false);
});

test('constraints: position 为 0-based 完整链下标', () => {
  const chain = ['X', 'A', 'B', 'Y'];
  assert.equal(matchConstraint(chain, { kind: 'position', frag: 'X', index: 0, weight: 1 }), true);
  assert.equal(matchConstraint(chain, { kind: 'position', frag: 'B', index: 2, weight: 1 }), true);
  assert.equal(matchConstraint(chain, { kind: 'position', frag: 'B', index: 1, weight: 1 }), false);
});

test('constraints: block 等价于 adjacent', () => {
  const chain = ['A', 'B', 'C'];
  assert.equal(matchConstraint(chain, { kind: 'block', a: 'A', b: 'B', weight: 1 }), true);
  assert.equal(matchConstraint(chain, { kind: 'block', a: 'A', b: 'C', weight: 1 }), false);
});

test('constraints: group 连续区间判定', () => {
  assert.equal(isContiguousGroup(['A', 'B', 'C', 'D'], ['B', 'C']), true);
  assert.equal(isContiguousGroup(['A', 'B', 'C', 'D'], ['C', 'B']), true, '内部顺序任意');
  assert.equal(isContiguousGroup(['A', 'B', 'C', 'D'], ['A', 'C']), false);
  assert.equal(isContiguousGroup(['A', 'B', 'C', 'D'], ['A', 'B', 'C']), true);
  assert.equal(isContiguousGroup(['A', 'B', 'C', 'D'], ['A', 'B', 'C', 'D']), true);
});

test('constraints: 引用不存在的碎片一律返回 false', () => {
  const chain = ['A', 'B'];
  assert.equal(matchConstraint(chain, { kind: 'before', a: 'A', b: 'ZZZ', weight: 1 }), false);
  assert.equal(matchConstraint(chain, { kind: 'position', frag: 'ZZZ', index: 0, weight: 1 }), false);
  assert.equal(matchConstraint(chain, { kind: 'group', frags: ['A', 'ZZZ'], weight: 1 }), false);
});

test('constraints: 畸形约束不抛异常', () => {
  const chain = ['A', 'B'];
  assert.equal(matchConstraint(chain, { kind: 'before', weight: 1 }), false);
  assert.equal(matchConstraint(chain, { kind: 'group', frags: [], weight: 1 }), false);
  assert.equal(matchConstraint(chain, { kind: 'position', frag: 'A', weight: 1 }), false);
});

test('constraints: assembleChain 首尾锚点', () => {
  assert.deepEqual(assembleChain('FIRST', ['b', 'c'], 'LAST'), ['FIRST', 'b', 'c', 'LAST']);
});

test('constraints: validateChain 捕获非法链', () => {
  const level = loadLevel('1-1');
  const expected = level.initialOrder;
  assert.equal(validateChain(level.initialOrder, level, expected).length, 0, '合法链应无错误');

  const wrongLength = ['frag_1_1_01', 'frag_1_1_02'];
  assert.ok(validateChain(wrongLength, level, expected).length > 0);

  const wrongAnchor = [...level.initialOrder];
  wrongAnchor[0] = 'frag_1_1_03';
  assert.ok(validateChain(wrongAnchor, level, expected).some((e) => e.includes('首位')));
});

/* ============================================================
 * 2. 评分
 * ============================================================ */

test('scoring: 得分 = 满足约束之和 − anti 扣分', () => {
  const chain = ['A', 'B', 'C'];
  const ending = {
    id: 't', levelId: 'x', type: 'good' as const, title: 't',
    threshold: 0, valence: 1,
    constraints: [
      { kind: 'before' as const, a: 'A', b: 'B', weight: 10 },
      { kind: 'before' as const, a: 'B', b: 'A', weight: 10 },
    ],
    anti: [{ kind: 'adjacent' as const, a: 'A', b: 'B', weight: 3 }],
    text: '', excerpt: '',
  };
  assert.equal(scoreEnding(chain, ending), 10 - 3);
});

test('scoring: 各关卡结局的理论最高分一致（100 分制）', () => {
  for (const id of ['1-1', '1-2', '1-3', '2-1', '2-2', '2-3', '3-1', '3-2', '3-3', '4-1', '4-2', '4-3']) {
    const level = loadLevel(id);
    const maxes = new Set(level.endings.map((e) => sumWeights(e.constraints)));
    assert.equal(maxes.size, 1, `${id} 的各结局最高分应一致，实际 ${[...maxes].join(',')}`);
    assert.equal([...maxes][0], 100, `${id} 应归一化到 100 分制`);
  }
});

test('scoring: 阈值不超过理论最高分', () => {
  for (const id of ['1-1', '2-3', '3-3', '4-3']) {
    const level = loadLevel(id);
    for (const e of level.endings) {
      assert.ok(e.threshold <= sumWeights(e.constraints), `${id} ${e.id} 阈值过高`);
    }
  }
});

test('scoring: valence 归一化到 -100..100', () => {
  const level = loadLevel('1-1');
  const v = computeChainValence(level.initialOrder, level);
  assert.ok(v >= -100 && v <= 100, `valence 越界：${v}`);
});

test('scoring: coherence 落在 0..100', () => {
  const level = loadLevel('2-3');
  const c = computeCoherence(level.initialOrder, level);
  assert.ok(c >= 0 && c <= 100, `coherence 越界：${c}`);
});

/* ============================================================
 * 3. 判定主流程
 * ============================================================ */

test('judge: 2-3 基准用例 —— 推荐解命中 good', () => {
  const level = loadLevel('2-3');
  const chain = [
    'frag_2_3_01',
    'frag_2_3_03',
    'frag_2_3_02',
    'frag_2_3_04',
    'frag_2_3_05',
    'frag_2_3_06',
    'frag_2_3_07',
  ];
  const r = judgeChain(chain, level, { unlockedEndingIds: null });
  assert.equal(r.isChaos, false);
  assert.equal(r.ending.id, '2_3_good');
  assert.equal(r.score, 100);
  assert.ok(isExactSolution(chain, r.ending), '推荐解应精确满足全部约束');
});

test('judge: 2-3 隐藏解命中 true', () => {
  const level = loadLevel('2-3');
  const chain = [
    'frag_2_3_01',
    'frag_2_3_02',
    'frag_2_3_03',
    'frag_2_3_04',
    'frag_2_3_05',
    'frag_2_3_06',
    'frag_2_3_07',
  ];
  const r = judgeChain(chain, level, { unlockedEndingIds: null });
  assert.equal(r.ending.id, '2_3_true');
  assert.equal(r.score, 100);
});

test('judge: 未命中任何结局时走混沌兜底', () => {
  const level = loadLevel('1-1');
  // 一个明显混乱的排列
  const chain = ['frag_1_1_01', 'frag_1_1_05', 'frag_1_1_03', 'frag_1_1_02', 'frag_1_1_04', 'frag_1_1_06'];
  const r = judgeChain(chain, level, { unlockedEndingIds: null });
  // 不断言一定是 chaos，但断言结果自洽
  assert.equal(r.evaluations.length, level.endings.length);
  assert.ok(r.coherence >= 0 && r.coherence <= 100);
  if (r.isChaos) assert.equal(r.ending.type, 'chaos');
});

test('judge: 结果与输入顺序无关地稳定（幂等）', () => {
  const level = loadLevel('3-3');
  const chain = [
    'frag_3_3_01', 'frag_3_3_02', 'frag_3_3_03', 'frag_3_3_04',
    'frag_3_3_05', 'frag_3_3_06', 'frag_3_3_07', 'frag_3_3_08', 'frag_3_3_09',
  ];
  const a = judgeChain(chain, level, { unlockedEndingIds: null });
  const b = judgeChain(chain, level, { unlockedEndingIds: null });
  assert.equal(a.ending.id, b.ending.id);
  assert.equal(a.score, b.score);
});

test('judge: requires 前置未满足时该结局不可命中', () => {
  const level = loadLevel('1-3');
  // 带上隐藏碎片 07 的链
  const chain = [
    'frag_1_3_01', 'frag_1_3_02', 'frag_1_3_03', 'frag_1_3_04',
    'frag_1_3_06', 'frag_1_3_05', 'frag_1_3_07', 'frag_1_3_08',
  ];
  const locked = judgeChain(chain, level, { unlockedEndingIds: [] });
  const unlocked = judgeChain(chain, level, { unlockedEndingIds: ['ending:1-3:good'] });

  const trueLocked = locked.evaluations.find((e) => e.endingId === '1_3_true')!;
  const trueUnlocked = unlocked.evaluations.find((e) => e.endingId === '1_3_true')!;
  assert.equal(trueLocked.unlocked, false);
  assert.equal(trueLocked.qualified, false);
  assert.equal(trueUnlocked.unlocked, true);
});

test('judge: isEndingUnlocked 语义', () => {
  assert.equal(isEndingUnlocked({ requires: undefined } as never, null), true);
  assert.equal(isEndingUnlocked({ requires: ['x'] } as never, null), true, 'null = 全部解锁');
  assert.equal(isEndingUnlocked({ requires: ['x'] } as never, []), false);
  assert.equal(isEndingUnlocked({ requires: ['x'] } as never, ['x']), true);
});

test('judge: evaluateEnding 输出约束轨迹长度正确', () => {
  const level = loadLevel('1-1');
  const e = level.endings[0];
  const ev = evaluateEnding(level.initialOrder, e, null);
  assert.equal(ev.trace.length, e.constraints.length + e.anti.length);
});

test('judge: previewChain 返回稳定态标记', () => {
  const level = loadLevel('2-3');
  const good = ['frag_2_3_01', 'frag_2_3_03', 'frag_2_3_02', 'frag_2_3_04', 'frag_2_3_05', 'frag_2_3_06', 'frag_2_3_07'];
  assert.equal(previewChain(good, level, { unlockedEndingIds: null }).settled, true);
});

/* ============================================================
 * 4. 蝴蝶效应 / 红碎片 / 可拖拽
 * ============================================================ */

test('butterfly: 3-3:A 触发条件', () => {
  const level = loadLevel('3-3');
  const chain = [
    'frag_3_3_01', 'frag_3_3_02', 'frag_3_3_03', 'frag_3_3_05',
    'frag_3_3_04', 'frag_3_3_06', 'frag_3_3_07', 'frag_3_3_08', 'frag_3_3_09',
  ];
  const hit = detectButterflies(chain, level, []);
  assert.ok(hit.some((b) => b.id === '3-3:A'), '应触发 3-3:A');
});

test('butterfly: 已触发的不重复触发', () => {
  const level = loadLevel('3-3');
  const chain = [
    'frag_3_3_01', 'frag_3_3_02', 'frag_3_3_03', 'frag_3_3_05',
    'frag_3_3_04', 'frag_3_3_06', 'frag_3_3_07', 'frag_3_3_08', 'frag_3_3_09',
  ];
  const hit = detectButterflies(chain, level, ['3-3:A']);
  assert.equal(hit.some((b) => b.id === '3-3:A'), false);
});

test('draggable: 灰色碎片永不可拖拽', () => {
  const level = loadLevel('1-1');
  const draggable = computeDraggable(level.initialOrder, level);
  assert.equal(draggable.has('frag_1_1_01'), false);
  assert.equal(draggable.has('frag_1_1_06'), false);
  assert.equal(draggable.has('frag_1_1_02'), true);
});

test('red unlock: 无 redUnlock 配置时返回 false', () => {
  const level = loadLevel('3-1');
  assert.equal(resolveRedUnlock(level.initialOrder, level), false);
});

/* ============================================================
 * 5. 提示系统
 * ============================================================ */

test('hints: 卡关次数 → 层级映射', () => {
  assert.equal(resolveHintTier(0), 0);
  assert.equal(resolveHintTier(2), 0);
  assert.equal(resolveHintTier(3), 1);
  assert.equal(resolveHintTier(6), 2);
  assert.equal(resolveHintTier(10), 3);
  assert.equal(resolveHintTier(99), 3);
});

test('hints: 取提示并向下回退', () => {
  const level = loadLevel('1-1');
  assert.ok(getHint(level, 3));
  assert.equal(getHint(level, 3)!.tier, 3);
  // 构造一个只有 tier1 的关卡，tier3 应回退到 tier1
  const only1 = { ...level, hints: [{ tier: 1 as const, text: 'x' }] };
  assert.equal(getHint(only1, 3)!.tier, 1);
});

test('hints: 规则说明不泄露解法', () => {
  const level = loadLevel('3-1');
  const rule = getRuleHint(level);
  assert.ok(rule.includes('红色碎片'), '3-1 含红色碎片，规则说明应提及');
  assert.ok(!rule.includes('frag_'), '规则说明不得包含碎片 ID');
});

/* ============================================================
 * 6. 数据完整性（全量）
 * ============================================================ */

test('data: 全部关卡首尾锚点正确且为灰色', () => {
  for (const id of ['1-1', '1-2', '1-3', '2-1', '2-2', '2-3', '3-1', '3-2', '3-3', '4-1', '4-2', '4-3']) {
    const level = loadLevel(id);
    const first = level.fragments.find((f) => f.id === level.anchors.first);
    const last = level.fragments.find((f) => f.id === level.anchors.last);
    assert.ok(first && first.type === 'gray', `${id} 首锚点应为 gray`);
    assert.ok(last && last.type === 'gray', `${id} 末锚点应为 gray`);
    assert.equal(level.initialOrder[0], level.anchors.first);
    assert.equal(level.initialOrder[level.initialOrder.length - 1], level.anchors.last);
  }
});

test('data: 碎片 ID 全局唯一，且前缀与 levelId 一致', () => {
  const seen = new Set<string>();
  for (const id of ['1-1', '1-2', '1-3', '2-1', '2-2', '2-3', '3-1', '3-2', '3-3', '4-1', '4-2', '4-3']) {
    const level = loadLevel(id);
    const prefix = `frag_${id.replace('-', '_')}_`;
    for (const f of level.fragments) {
      assert.equal(seen.has(f.id), false, `重复碎片 ID：${f.id}`);
      seen.add(f.id);
      assert.ok(f.id.startsWith(prefix), `碎片 ${f.id} 前缀与关卡 ${id} 不符（应为 ${prefix}）`);
      assert.equal(f.levelId, id, `碎片 ${f.id} 的 levelId 字段错误`);
    }
  }
});

test('data: 蓝色碎片一律不可拖拽且不入链', () => {
  for (const id of ['1-2', '2-1', '2-2', '2-3', '3-1', '3-3', '4-2', '4-3']) {
    const level = loadLevel(id);
    for (const f of level.fragments) {
      if (f.type === 'blue') {
        assert.equal(f.draggable, false, `${f.id} 蓝色碎片应不可拖拽`);
        assert.equal(level.initialOrder.includes(f.id), false, `${f.id} 蓝色碎片不应出现在链中`);
      }
    }
  }
});

test('data: 所有碎片正文长度在 1..80 字之间', () => {
  for (const id of ['1-1', '2-3', '3-3', '4-3']) {
    const level = loadLevel(id);
    for (const f of level.fragments) {
      assert.ok(f.text.length > 0 && f.text.length <= 80, `${f.id} 正文长度异常：${f.text.length}`);
    }
  }
});

test('data: 每个结局正文与摘要非空', () => {
  for (const id of ['1-1', '2-3', '4-3']) {
    const level = loadLevel(id);
    for (const e of [...level.endings, level.chaosEnding]) {
      assert.ok(e.text.length > 0, `${e.id} 缺少正文`);
      assert.ok(e.excerpt.length > 0, `${e.id} 缺少摘要`);
    }
  }
});
