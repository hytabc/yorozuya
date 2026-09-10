/**
 * 判定主流程
 * 移植自 vrcWill/src/lib/engine/judge.ts。
 */

import { evaluateConstraints, matchConstraint } from './constraints.js'
import { computeChainValence, computeCoherence, endingMaxScore, scoreEnding } from './scoring.js'

/**
 * 主判定函数。
 *  1. 逐一评估每个结局的得分；
 *  2. 可命中 = (score >= threshold) 且 (requires 前置全部满足)；
 *  3. 在可命中集合中取 score 最高者；
 *  4. score 并列时，取约束条数更少者；
 *  5. 若无任何结局可命中 → 返回混沌兜底结局。
 */
export function judgeChain(chain, level, ctx = {}) {
  const unlocked = ctx.unlockedEndingIds ?? null

  const evaluations = level.endings.map((e) => evaluateEnding(chain, e, unlocked))

  const qualified = evaluations.filter((e) => e.qualified)

  qualified.sort((a, b) => {
    if (b.score !== a.score) return b.score - a.score
    const ea = findEnding(level, a.endingId)
    const eb = findEnding(level, b.endingId)
    const ca = ea ? ea.constraints.length : 0
    const cb = eb ? eb.constraints.length : 0
    if (ca !== cb) return ca - cb
    return a.endingId.localeCompare(b.endingId)
  })

  const valence = computeChainValence(chain, level)

  if (qualified.length === 0) {
    return {
      ending: level.chaosEnding,
      isChaos: true,
      score: 0,
      coherence: computeCoherence(chain, level),
      valence,
      evaluations,
      runnerUp: strongestRejected(evaluations),
    }
  }

  const winner = qualified[0]
  const winnerEnding = findEnding(level, winner.endingId)

  return {
    ending: winnerEnding,
    isChaos: false,
    score: winner.score,
    coherence: computeCoherence(chain, level),
    valence,
    evaluations,
    runnerUp: qualified[1] ?? strongestRejected(evaluations),
  }
}

/** 评估单个结局 */
export function evaluateEnding(chain, ending, unlockedEndingIds) {
  const pos = evaluateConstraints(chain, ending.constraints, 1)
  const neg = evaluateConstraints(chain, ending.anti, -1)
  const score = pos.score + neg.score
  const trace = [...pos.trace, ...neg.trace]

  const unlocked = isEndingUnlocked(ending, unlockedEndingIds)

  return {
    endingId: ending.id,
    title: ending.title,
    type: ending.type,
    score,
    threshold: ending.threshold,
    qualified: unlocked && score >= ending.threshold,
    unlocked,
    trace,
  }
}

/** 前置条件判断。`unlockedEndingIds === null` 时一律视为已解锁。 */
export function isEndingUnlocked(ending, unlockedEndingIds) {
  if (!ending.requires || ending.requires.length === 0) return true
  if (unlockedEndingIds === null) return true
  return ending.requires.every((r) => unlockedEndingIds.includes(r))
}

/** 预判（不提交）：返回当前链最可能命中的结局与实时指标。 */
export function previewChain(chain, level, ctx = {}) {
  const result = judgeChain(chain, level, ctx)
  const ev = result.evaluations.find((e) => e.endingId === result.ending.id)
  const max = ev ? endingMaxScore(findEnding(level, ev.endingId)) : 0
  const rate = max > 0 ? result.score / max : 0
  return { result, settled: result.isChaos ? false : rate >= 0.75 }
}

/** 返回"最接近命中"的未达成结局，用于引导玩家。 */
export function nearestEnding(chain, level) {
  let best
  let bestRate = -1
  for (const e of level.endings) {
    const ev = evaluateEnding(chain, e, null)
    const max = endingMaxScore(e)
    const rate = max > 0 ? ev.score / max : 0
    if (rate > bestRate) {
      bestRate = rate
      best = ev
    }
  }
  return best
}

/** 判断一条链是否"精确命中"某结局的推荐解。 */
export function isExactSolution(chain, ending) {
  return ending.constraints.every((c) => matchConstraint(chain, c))
}

function findEnding(level, id) {
  if (level.chaosEnding.id === id) return level.chaosEnding
  return level.endings.find((e) => e.id === id)
}

/** 在所有未命中的结局里，取匹配率最高者 */
function strongestRejected(evals) {
  const rejected = evals.filter((e) => !e.qualified)
  if (rejected.length === 0) return undefined
  let best = rejected[0]
  let bestRate = rejected[0].threshold > 0 ? rejected[0].score / rejected[0].threshold : 0
  for (const e of rejected) {
    const rate = e.threshold > 0 ? e.score / e.threshold : 0
    if (rate > bestRate) {
      bestRate = rate
      best = e
    }
  }
  return best
}

export { scoreEnding }
