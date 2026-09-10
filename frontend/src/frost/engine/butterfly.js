/**
 * 蝴蝶效应
 * 移植自 vrcWill/src/lib/engine/butterfly.ts。
 */

import { matchConstraint } from './constraints.js'

/** 检测当前链触发了哪些蝴蝶效应。 */
export function detectButterflies(chain, level, alreadyTriggered = []) {
  const list = level.butterflies ?? []
  const out = []
  for (const b of list) {
    if (alreadyTriggered.includes(b.id)) continue
    if (b.requires.length === 0) continue
    if (b.requires.every((c) => matchConstraint(chain, c))) {
      out.push(b)
    }
  }
  return out
}

/** 某只蝴蝶当前是否"差一点"触发（用于提示系统的方向性引导） */
export function butterflyProgress(chain, butterfly) {
  if (butterfly.requires.length === 0) return 0
  let hit = 0
  for (const c of butterfly.requires) {
    if (matchConstraint(chain, c)) hit++
  }
  return hit / butterfly.requires.length
}

/**
 * 计算"未解锁碎片"的可见性。
 * unlockedBy 语法：
 *   `ending:<levelId>:<type>`  —— 通关某关的某类型结局
 *   `endingType:<type>`        —— 任意关卡达成某类型结局
 *   `butterfly:<levelId>:<id>` —— 触发某关的某蝴蝶效应
 */
export function resolveHiddenFragments(level, state) {
  const out = []
  for (const f of level.fragments) {
    if (!f.hidden) continue
    if (isUnlocked(f.unlockedBy, state)) out.push(f.id)
  }
  return out
}

function isUnlocked(rule, state) {
  if (!rule) return false
  const parts = rule.split(':')
  if (parts[0] === 'ending' && parts.length === 3) {
    const [, levelId, type] = parts
    return state.seenEndings.some((e) => e.levelId === levelId && e.type === type)
  }
  if (parts[0] === 'endingType' && parts.length === 2) {
    const [, type] = parts
    return state.seenEndings.some((e) => e.type === type)
  }
  if (parts[0] === 'butterfly' && parts.length === 3) {
    const [, , id] = parts
    return state.triggeredButterflies.includes(id)
  }
  return false
}

/** 红色碎片解锁：金色碎片被放到指定位置后，红色碎片被"淡化"为可拖拽。 */
export function resolveRedUnlock(chain, level) {
  if (!level.redUnlock) return false
  return level.redUnlock.requires.every((c) => matchConstraint(chain, c))
}

/**
 * 计算当前链中所有可拖拽碎片（供 UI 渲染锁定态）。
 * 说明：原型对红碎片只在 redUnlock 命中时可拖拽，但 3-1 的红碎片数据为
 * draggable:true 且无 redUnlock，照搬会使该关不可解。这里以数据为准：
 * 红碎片在自身 draggable 为 true 或 redUnlock 命中时可拖拽。
 */
export function computeDraggable(chain, level) {
  const redUnlocked = resolveRedUnlock(chain, level)
  const set = new Set()
  for (const f of level.fragments) {
    if (f.type === 'red') {
      if (f.draggable || redUnlocked) set.add(f.id)
      continue
    }
    if (f.draggable) set.add(f.id)
  }
  return set
}
