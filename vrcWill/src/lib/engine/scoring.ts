/**
 * 指标计算：因果连贯度 Coherence / 情感走向 Valence
 * ------------------------------------------------------------------
 * 这两个指标是玩家在关卡中唯一能看到的"反馈信号"，
 * 它们必须：
 *   1. 连续（不能只在提交时才跳变）
 *   2. 单调（排列越接近某个结局，指标越接近该结局的语义）
 *   3. 可解释（玩家能凭直觉把指标变化与自己的操作对应起来）
 */

import type { Ending, Level } from './types.ts';
import { matchConstraint, sumWeights } from './constraints.ts';

/**
 * 计算单个结局在给定链上的得分。
 * score = Σ(满足的正向约束权重) − Σ(满足的 anti 权重)
 */
export function scoreEnding(chain: string[], ending: Ending): number {
  let s = 0;
  for (const c of ending.constraints) {
    if (matchConstraint(chain, c)) s += c.weight;
  }
  for (const a of ending.anti) {
    if (matchConstraint(chain, a)) s -= a.weight;
  }
  return s;
}

/** 该结局的理论最高分（正向约束权重之和） */
export function endingMaxScore(ending: Ending): number {
  return sumWeights(ending.constraints);
}

/**
 * 匹配率 0..1：得分 / 理论最高分。
 * 用于归一化比较不同结局（各结局的总权重可能不同）。
 */
export function matchRate(chain: string[], ending: Ending): number {
  const max = endingMaxScore(ending);
  if (max <= 0) return 0;
  return clamp01(scoreEnding(chain, ending) / max);
}

/**
 * 实时连贯度 0..100。
 * 取所有结局中"匹配率最高者"，映射到百分制。
 * 这样玩家每拖一次，指标都会平滑变化。
 */
export function computeCoherence(chain: string[], level: Level): number {
  let best = 0;
  for (const e of level.endings) {
    const r = matchRate(chain, e);
    if (r > best) best = r;
  }
  return Math.round(best * 100);
}

/**
 * 链的情感走向 -100..+100。
 * 由链中所有碎片的 valence（-2..+2）归一化而来。
 * 正值偏"靠近"，负值偏"疏离"。
 */
export function computeChainValence(chain: string[], level: Level): number {
  const map = new Map(level.fragments.map((f) => [f.id, f]));
  let total = 0;
  let count = 0;
  for (const id of chain) {
    const f = map.get(id);
    if (!f) continue;
    total += f.valence;
    count++;
  }
  if (count === 0) return 0;
  const raw = (total / (count * 2)) * 100;
  return Math.round(clamp(raw, -100, 100));
}

/**
 * 结局的评价色调：把 ending.valence（-1..1）映射为色彩区间标签，
 * 供 UI 选择渐变背景。
 */
export function valenceBand(v: number): 'warm' | 'neutral' | 'cold' {
  if (v > 0.2) return 'warm';
  if (v < -0.2) return 'cold';
  return 'neutral';
}

/* ------------------------- 内部工具 ------------------------- */

function clamp01(n: number): number {
  if (!Number.isFinite(n)) return 0;
  if (n < 0) return 0;
  if (n > 1) return 1;
  return n;
}

function clamp(n: number, lo: number, hi: number): number {
  if (!Number.isFinite(n)) return lo;
  return Math.min(hi, Math.max(lo, n));
}
