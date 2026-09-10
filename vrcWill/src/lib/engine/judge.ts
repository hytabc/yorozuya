/**
 * 判定主流程
 * ------------------------------------------------------------------
 * judgeChain() 是整款游戏最核心的函数：
 *   输入：一条完整因果链 + 关卡定义 + 玩家存档状态
 *   输出：命中的结局 + 全部评估明细
 *
 * 算法见 docs/02-判定引擎规格.md。
 */

import type {
  Ending,
  EndingEvaluation,
  JudgeResult,
  Level,
  ConstraintTrace,
} from './types.ts';
import { evaluateConstraints, matchConstraint } from './constraints.ts';
import { computeChainValence, computeCoherence, endingMaxScore, scoreEnding } from './scoring.ts';

/** 判定所需的玩家状态（可裁剪子集，便于纯函数测试） */
export interface JudgeContext {
  /** 已解锁的结局 ID（用于 requires 前置判断）。null 表示"全部视为已解锁"（开发/调试用） */
  unlockedEndingIds?: string[] | null;
  /** 已触发的蝴蝶效应 ID */
  triggeredButterflies?: string[];
}

/**
 * 主判定函数。
 *
 * 规则（与 PRD §2.4.3 一致）：
 *  1. 逐一评估每个结局的得分；
 *  2. 可命中 = (score >= threshold) 且 (requires 前置全部满足)；
 *  3. 在可命中集合中取 score 最高者；
 *  4. score 并列时，取约束条数更少者（更"顺其自然"的解法）；
 *  5. 若无任何结局可命中 → 返回混沌兜底结局。
 */
export function judgeChain(chain: string[], level: Level, ctx: JudgeContext = {}): JudgeResult {
  const unlocked = ctx.unlockedEndingIds ?? null;

  const evaluations: EndingEvaluation[] = level.endings.map((e) =>
    evaluateEnding(chain, e, unlocked),
  );

  const qualified = evaluations.filter((e) => e.qualified);

  qualified.sort((a, b) => {
    if (b.score !== a.score) return b.score - a.score;
    const ea = findEnding(level, a.endingId);
    const eb = findEnding(level, b.endingId);
    const ca = ea ? ea.constraints.length : 0;
    const cb = eb ? eb.constraints.length : 0;
    if (ca !== cb) return ca - cb;
    return a.endingId.localeCompare(b.endingId);
  });

  const valence = computeChainValence(chain, level);

  if (qualified.length === 0) {
    return {
      ending: level.chaosEnding,
      isChaos: true,
      score: 0,
      coherence: computeCoherence(chain, level),
      valence,
      evaluations,
      runnerUp: strongestRejected(evaluations),
    };
  }

  const winner = qualified[0];
  const winnerEnding = findEnding(level, winner.endingId)!;

  return {
    ending: winnerEnding,
    isChaos: false,
    score: winner.score,
    coherence: computeCoherence(chain, level),
    valence,
    evaluations,
    runnerUp: qualified[1] ?? strongestRejected(evaluations),
  };
}

/** 评估单个结局 */
export function evaluateEnding(
  chain: string[],
  ending: Ending,
  unlockedEndingIds: string[] | null,
): EndingEvaluation {
  const pos = evaluateConstraints(chain, ending.constraints, 1);
  const neg = evaluateConstraints(chain, ending.anti, -1);
  const score = pos.score + neg.score;
  const trace: ConstraintTrace[] = [...pos.trace, ...neg.trace];

  const unlocked = isEndingUnlocked(ending, unlockedEndingIds);

  return {
    endingId: ending.id,
    title: ending.title,
    type: ending.type,
    score,
    threshold: ending.threshold,
    qualified: unlocked && score >= ending.threshold,
    unlocked,
    trace,
  };
}

/**
 * 前置条件判断。
 * `unlockedEndingIds === null` 时一律视为已解锁（用于穷举校验与调试）。
 */
export function isEndingUnlocked(ending: Ending, unlockedEndingIds: string[] | null): boolean {
  if (!ending.requires || ending.requires.length === 0) return true;
  if (unlockedEndingIds === null) return true;
  return ending.requires.every((r) => unlockedEndingIds.includes(r));
}

/**
 * 预判（不提交）：返回当前链最可能命中的结局与实时指标。
 * 用于拖拽结束后的 2 秒"因果稳定中……"过渡态。
 */
export function previewChain(
  chain: string[],
  level: Level,
  ctx: JudgeContext = {},
): { result: JudgeResult; settled: boolean } {
  const result = judgeChain(chain, level, ctx);
  // 归一化匹配率 ≥ 0.75 视为"已稳定"，UI 可直接预览而无需等待 2 秒
  const ev = result.evaluations.find((e) => e.endingId === result.ending.id);
  const max = ev ? endingMaxScore(findEnding(level, ev.endingId)!) : 0;
  const rate = max > 0 ? result.score / max : 0;
  return { result, settled: result.isChaos ? false : rate >= 0.75 };
}

/**
 * 返回"最接近命中"的未达成结局，用于引导玩家。
 * 判定依据：归一化匹配率最高。
 */
export function nearestEnding(chain: string[], level: Level): EndingEvaluation | undefined {
  let best: EndingEvaluation | undefined;
  let bestRate = -1;
  for (const e of level.endings) {
    const ev = evaluateEnding(chain, e, null);
    const max = endingMaxScore(e);
    const rate = max > 0 ? ev.score / max : 0;
    if (rate > bestRate) {
      bestRate = rate;
      best = ev;
    }
  }
  return best;
}

/**
 * 判断一条链是否"精确命中"某结局的推荐解。
 * 用于成就系统与"完美通关"判定。
 */
export function isExactSolution(chain: string[], ending: Ending): boolean {
  return ending.constraints.every((c) => matchConstraint(chain, c));
}

/* ------------------------- 内部工具 ------------------------- */

function findEnding(level: Level, id: string): Ending | undefined {
  if (level.chaosEnding.id === id) return level.chaosEnding;
  return level.endings.find((e) => e.id === id);
}

/** 在所有未命中的结局里，取匹配率最高者 */
function strongestRejected(evals: EndingEvaluation[]): EndingEvaluation | undefined {
  const rejected = evals.filter((e) => !e.qualified);
  if (rejected.length === 0) return undefined;
  let best = rejected[0];
  let bestRate = rejected[0].threshold > 0 ? rejected[0].score / rejected[0].threshold : 0;
  for (const e of rejected) {
    const rate = e.threshold > 0 ? e.score / e.threshold : 0;
    if (rate > bestRate) {
      bestRate = rate;
      best = e;
    }
  }
  return best;
}

/** 重算某结局在当前链上的得分（供测试与调试面板使用） */
export { scoreEnding };
