/**
 * 小时推进 —— step_hours 移植（含里程碑保护）。
 */
import { stageOf } from './pool.js';

const MILESTONES = [10, 50, 200, 500, 1000, 5000];

/**
 * @param {object} st
 * @param {object} rng
 * @param {object} vocab
 * @returns {number}
 */
export function stepHours(st, rng, vocab) {
  const s = stageOf(st.hours, vocab);
  const range = (vocab.hourStepByStage || {})[s] || [1, 20];
  const lo = range[0];
  const hi = range[1];
  let step = rng.randint(lo, hi);
  // mood ≤ 14 时加速推进（int() 截断对应 Math.floor）
  if (st.mood <= 14) step = Math.floor(step * 1.5);
  step = Math.max(1, step);
  // 里程碑保护
  for (const m of MILESTONES) {
    if (st.hours < m && m <= st.hours + step && !st.milestones.has(m)) {
      st.milestones.add(m);
      return m - st.hours;
    }
  }
  return step;
}