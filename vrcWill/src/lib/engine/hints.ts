/**
 * 分级提示系统
 * ------------------------------------------------------------------
 * 设计原则：首次卡关时给出"方向性引导"，而非直接答案。
 * 提示分三级，随卡关次数逐级解锁，且使用次数计入"完美通关"评价。
 */

import type { Hint, Level } from './types.ts';

/** 触发各层级提示所需的"未通关提交次数"阈值 */
export const HINT_THRESHOLDS: { tier: 1 | 2 | 3; failCount: number }[] = [
  { tier: 1, failCount: 3 },
  { tier: 2, failCount: 6 },
  { tier: 3, failCount: 10 },
];

/**
 * 根据卡关次数返回应当展示的提示层级。
 * 返回 0 表示"暂不提供提示"。
 */
export function resolveHintTier(failCount: number): 0 | 1 | 2 | 3 {
  let tier: 0 | 1 | 2 | 3 = 0;
  for (const t of HINT_THRESHOLDS) {
    if (failCount >= t.failCount) tier = t.tier;
  }
  return tier;
}

/**
 * 取指定层级的提示。
 * 若该关未配置对应层级，则向下回退到更低的层级。
 */
export function getHint(level: Level, tier: 1 | 2 | 3): Hint | null {
  const hints = level.hints ?? [];
  if (hints.length === 0) return null;
  let t: 1 | 2 | 3 = tier;
  while (t >= 1) {
    const found = hints.find((h) => h.tier === t);
    if (found) return found;
    t = (t - 1) as 1 | 2 | 3;
  }
  return null;
}

/**
 * 玩家主动点击"?"时展示的规则说明（不涉及具体解法）。
 */
export function getRuleHint(level: Level): string {
  const hasRed = level.fragments.some((f) => f.type === 'red');
  const hasGold = level.fragments.some((f) => f.type === 'gold');
  const hasGray = level.fragments.some((f) => f.type === 'gray');

  const parts: string[] = ['把碎片按你认为正确的顺序排好，然后让因果稳定。'];
  if (hasGray) parts.push('灰色碎片是固定的起点与终点，无法移动。');
  if (hasGold) parts.push('金色碎片是关键事件，放下它时会改变相邻碎片的关系。');
  if (hasRed) parts.push('红色碎片是负面事件，把它排到合适的位置，它会慢慢淡下去。');
  parts.push('同一个故事有很多种走法，没有"错误"的排列，只有不同的结局。');
  return parts.join('');
}

/**
 * 从"最接近的结局"反推一句方向性提示，用于 tier 1 兜底。
 * 不暴露具体碎片，只描述因果方向。
 */
export function directionalHint(level: Level, nearestEndingId: string): string {
  const e = level.endings.find((x) => x.id === nearestEndingId);
  if (!e) return '试试改变两句话的先后顺序，因果会不一样。';
  switch (e.type) {
    case 'good':
      return '你已经很接近一个好的走向了——注意"先关心，再看见"的顺序。';
    case 'bittersweet':
      return '这条线能走通，但它通向的不是和解。想想哪两句话的因果反了。';
    case 'bad':
      return '这个排列会让事情变糟。也许该把某句解释，挪到质问之前。';
    case 'true':
      return '有一条隐藏的路。它需要把两段本该分开的回忆，放到一起。';
    default:
      return '目前的因果还不太稳定，试着让有因果关系的两句话挨在一起。';
  }
}
