/**
 * 指标计算：因果连贯度 Coherence / 情感走向 Valence
 * 移植自 vrcWill/src/lib/engine/scoring.ts。
 */

import { matchConstraint, sumWeights } from './constraints.js'

/**
 * 计算单个结局在给定链上的得分。
 * score = Σ(满足的正向约束权重) − Σ(满足的 anti 权重)
 */
export function scoreEnding(chain, ending) {
  let s = 0
  for (const c of ending.constraints) {
    if (matchConstraint(chain, c)) s += c.weight
  }
  for (const a of ending.anti) {
    if (matchConstraint(chain, a)) s -= a.weight
  }
  return s
}

/** 该结局的理论最高分（正向约束权重之和） */
export function endingMaxScore(ending) {
  return sumWeights(ending.constraints)
}

/** 匹配率 0..1：得分 / 理论最高分。 */
export function matchRate(chain, ending) {
  const max = endingMaxScore(ending)
  if (max <= 0) return 0
  return clamp01(scoreEnding(chain, ending) / max)
}

/** 实时连贯度 0..100。 */
export function computeCoherence(chain, level) {
  let best = 0
  for (const e of level.endings) {
    const r = matchRate(chain, e)
    if (r > best) best = r
  }
  return Math.round(best * 100)
}

/** 链的情感走向 -100..+100。 */
export function computeChainValence(chain, level) {
  const map = new Map(level.fragments.map((f) => [f.id, f]))
  let total = 0
  let count = 0
  for (const id of chain) {
    const f = map.get(id)
    if (!f) continue
    total += f.valence
    count++
  }
  if (count === 0) return 0
  const raw = (total / (count * 2)) * 100
  return Math.round(clamp(raw, -100, 100))
}

/** 结局的评价色调。 */
export function valenceBand(v) {
  if (v > 0.2) return 'warm'
  if (v < -0.2) return 'cold'
  return 'neutral'
}

function clamp01(n) {
  if (!Number.isFinite(n)) return 0
  if (n < 0) return 0
  if (n > 1) return 1
  return n
}

function clamp(n, lo, hi) {
  if (!Number.isFinite(n)) return lo
  return Math.min(hi, Math.max(lo, n))
}
