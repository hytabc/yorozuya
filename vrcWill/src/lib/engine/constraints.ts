/**
 * 约束匹配器
 * ------------------------------------------------------------------
 * 提供 5 种因果约束的判定，以及批量打分。
 * 全部为纯函数，不依赖任何外部状态。
 */

import type { Constraint, Level } from './types.ts';

/** 取碎片在链中的下标；不存在返回 -1 */
export function indexOfFragment(chain: string[], id: string): number {
  return chain.indexOf(id);
}

/** 链中是否包含该碎片 */
export function hasFragment(chain: string[], id: string): boolean {
  return chain.indexOf(id) >= 0;
}

/**
 * 判断一组碎片是否占据"连续区间"（内部顺序任意）。
 * 例：chain = [A,B,C,D]，frags = [B,C] → true；frags = [A,C] → false
 */
export function isContiguousGroup(chain: string[], frags: string[]): boolean {
  if (frags.length === 0) return false;
  if (frags.length === 1) return hasFragment(chain, frags[0]);
  const idxs: number[] = [];
  for (const f of frags) {
    const i = chain.indexOf(f);
    if (i < 0) return false;
    idxs.push(i);
  }
  const min = Math.min(...idxs);
  const max = Math.max(...idxs);
  return max - min + 1 === frags.length;
}

/**
 * 单条约束是否被满足。
 * 注意：任何涉及"链中不存在的碎片"的约束一律返回 false
 * （这保证了隐藏碎片未解锁时不会误命中）。
 */
export function matchConstraint(chain: string[], c: Constraint): boolean {
  switch (c.kind) {
    case 'before': {
      if (!c.a || !c.b) return false;
      const ia = chain.indexOf(c.a);
      const ib = chain.indexOf(c.b);
      if (ia < 0 || ib < 0) return false;
      return ia < ib;
    }
    case 'adjacent': {
      if (!c.a || !c.b) return false;
      const ia = chain.indexOf(c.a);
      const ib = chain.indexOf(c.b);
      if (ia < 0 || ib < 0) return false;
      return Math.abs(ia - ib) === 1;
    }
    case 'position': {
      if (!c.frag || typeof c.index !== 'number') return false;
      const i = chain.indexOf(c.frag);
      if (i < 0) return false;
      return i === c.index;
    }
    case 'block': {
      // 语义与 adjacent 相同，单独保留是为了让数据自解释：
      // 出现在 anti 中表示"这两件事不该挨在一起"。
      if (!c.a || !c.b) return false;
      const ia = chain.indexOf(c.a);
      const ib = chain.indexOf(c.b);
      if (ia < 0 || ib < 0) return false;
      return Math.abs(ia - ib) === 1;
    }
    case 'group': {
      if (!c.frags || c.frags.length === 0) return false;
      return isContiguousGroup(chain, c.frags);
    }
    default:
      return false;
  }
}

/** 一组约束的总权重（用于归一化） */
export function sumWeights(constraints: Constraint[]): number {
  let s = 0;
  for (const c of constraints) s += c.weight;
  return s;
}

/**
 * 批量评估约束，返回总分与逐条轨迹。
 * @param sign 正向约束传 +1，anti 约束传 -1
 */
export function evaluateConstraints(
  chain: string[],
  constraints: Constraint[],
  sign: 1 | -1,
): { score: number; trace: { constraint: Constraint; matched: boolean; delta: number }[] } {
  let score = 0;
  const trace: { constraint: Constraint; matched: boolean; delta: number }[] = [];
  for (const c of constraints) {
    const matched = matchConstraint(chain, c);
    const delta = matched ? sign * c.weight : 0;
    score += delta;
    trace.push({ constraint: c, matched, delta });
  }
  return { score, trace };
}

/**
 * 校验一条链是否"结构合法"：
 *  - 长度与关卡参与判定的碎片数一致
 *  - 首尾与锚点一致
 *  - 无重复、无缺失
 * 用于开发期断言与存档容错。
 */
export function validateChain(chain: string[], level: Level, expectedIds: string[]): string[] {
  const errors: string[] = [];
  if (chain.length !== expectedIds.length) {
    errors.push(`链长度 ${chain.length} ≠ 期望 ${expectedIds.length}`);
  }
  const set = new Set(chain);
  if (set.size !== chain.length) errors.push('链中存在重复碎片');
  for (const id of expectedIds) {
    if (!set.has(id)) errors.push(`缺少碎片 ${id}`);
  }
  for (const id of chain) {
    if (!expectedIds.includes(id)) errors.push(`出现未知碎片 ${id}`);
  }
  if (chain[0] !== level.anchors.first) {
    errors.push(`首位应为锚点 ${level.anchors.first}，实际 ${chain[0]}`);
  }
  if (chain[chain.length - 1] !== level.anchors.last) {
    errors.push(`末位应为锚点 ${level.anchors.last}，实际 ${chain[chain.length - 1]}`);
  }
  return errors;
}

/** 由"锚点 + 可动碎片顺序"装配出完整链 */
export function assembleChain(first: string, movable: string[], last: string): string[] {
  return [first, ...movable, last];
}
