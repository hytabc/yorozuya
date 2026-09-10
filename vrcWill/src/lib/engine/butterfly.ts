/**
 * 蝴蝶效应
 * ------------------------------------------------------------------
 * 当玩家跨角色交换碎片，使两条时间线在某一时刻"相遇"时，
 * 触发隐藏剧情并解锁蓝色碎片。
 */

import type { Butterfly, Constraint, Level } from './types.ts';
import { matchConstraint } from './constraints.ts';

/**
 * 检测当前链触发了哪些蝴蝶效应。
 * @param alreadyTriggered 已触发过的蝴蝶效应 ID（不会重复触发）
 */
export function detectButterflies(
  chain: string[],
  level: Level,
  alreadyTriggered: string[] = [],
): Butterfly[] {
  const list = level.butterflies ?? [];
  const out: Butterfly[] = [];
  for (const b of list) {
    if (alreadyTriggered.includes(b.id)) continue;
    if (b.requires.length === 0) continue;
    if (b.requires.every((c: Constraint) => matchConstraint(chain, c))) {
      out.push(b);
    }
  }
  return out;
}

/** 某只蝴蝶当前是否"差一点"触发（用于提示系统的方向性引导） */
export function butterflyProgress(chain: string[], butterfly: Butterfly): number {
  if (butterfly.requires.length === 0) return 0;
  let hit = 0;
  for (const c of butterfly.requires) {
    if (matchConstraint(chain, c)) hit++;
  }
  return hit / butterfly.requires.length;
}

/**
 * 计算"未解锁碎片"的可见性。
 * 返回在当前存档状态下应当出现在碎片池中的隐藏碎片 ID。
 *
 * unlockedBy 语法：
 *   `ending:<levelId>:<type>`  —— 通关某关的某类型结局
 *   `endingType:<type>`        —— 任意关卡达成某类型结局
 *   `butterfly:<levelId>:<id>` —— 触发某关的某蝴蝶效应
 */
export function resolveHiddenFragments(
  level: Level,
  state: {
    seenEndings: { levelId: string; type: string }[];
    triggeredButterflies: string[];
  },
): string[] {
  const out: string[] = [];
  for (const f of level.fragments) {
    if (!f.hidden) continue;
    if (isUnlocked(f.unlockedBy, state)) out.push(f.id);
  }
  return out;
}

function isUnlocked(
  rule: string | null | undefined,
  state: { seenEndings: { levelId: string; type: string }[]; triggeredButterflies: string[] },
): boolean {
  if (!rule) return false;
  const parts = rule.split(':');
  if (parts[0] === 'ending' && parts.length === 3) {
    const [, levelId, type] = parts;
    return state.seenEndings.some((e) => e.levelId === levelId && e.type === type);
  }
  if (parts[0] === 'endingType' && parts.length === 2) {
    const [, type] = parts;
    return state.seenEndings.some((e) => e.type === type);
  }
  if (parts[0] === 'butterfly' && parts.length === 3) {
    const [, , id] = parts;
    return state.triggeredButterflies.includes(id);
  }
  return false;
}

/**
 * 红色碎片解锁：金色碎片被放到指定位置后，红色碎片被"淡化"为可拖拽。
 */
export function resolveRedUnlock(chain: string[], level: Level): boolean {
  if (!level.redUnlock) return false;
  return level.redUnlock.requires.every((c) => matchConstraint(chain, c));
}

/**
 * 计算当前链中所有可拖拽碎片（供 UI 渲染锁定态）。
 */
export function computeDraggable(chain: string[], level: Level): Set<string> {
  const redUnlocked = resolveRedUnlock(chain, level);
  const set = new Set<string>();
  for (const f of level.fragments) {
    if (f.type === 'red') {
      if (redUnlocked) set.add(f.id);
      continue;
    }
    if (f.draggable) set.add(f.id);
  }
  return set;
}
