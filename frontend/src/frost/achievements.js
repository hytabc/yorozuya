/**
 * 成就判定：由存档进度派生（不单独存储）。
 * 触发语法见 data/achievements.json 的 trigger 字段。
 */
import {
  ACHIEVEMENTS,
  ALL_BLUE_FRAGMENT_IDS,
  ALL_BUTTERFLY_IDS,
  ALL_DESIGN_ENDING_IDS,
  ENDING_META,
  LEVELS,
  LEVELS_BY_CHAPTER,
} from './levels.js'
import { resolveHiddenFragments } from './engine/butterfly.js'

/** 把结局 ID 列表转换为 resolveHiddenFragments 需要的 seenEndings 结构。 */
export function endingEntries(endingsSeen) {
  return endingsSeen.map((id) => ENDING_META[id]).filter(Boolean)
}

/** 当前已解锁的蓝色独白数量。 */
export function unlockedBlueCount(progress) {
  const state = {
    seenEndings: endingEntries(progress.endingsSeen),
    triggeredButterflies: progress.butterfliesSeen,
  }
  let count = 0
  for (const level of LEVELS) {
    const visible = resolveHiddenFragments(level, state)
    count += level.fragments.filter((f) => f.type === 'blue' && visible.includes(f.id)).length
  }
  return count
}

/** 返回 { [achievementId]: boolean }。 */
export function evaluateAchievements(progress) {
  const ctx = {
    seen: new Set(progress.endingsSeen),
    cleared: new Set(progress.cleared),
    butterflies: new Set(progress.butterfliesSeen),
    blueUnlocked: unlockedBlueCount(progress),
    hintsUsed: progress.hintsUsed || {},
    attempts: progress.attempts || {},
    chaosCount: progress.chaosCount || 0,
  }
  const result = {}
  for (const achievement of ACHIEVEMENTS) {
    result[achievement.id] = checkTrigger(achievement.trigger, ctx)
  }
  return result
}

/** 已解锁成就的总点数。 */
export function achievementPoints(unlocked) {
  let points = 0
  for (const achievement of ACHIEVEMENTS) {
    if (unlocked[achievement.id]) points += achievement.points
  }
  return points
}

function checkTrigger(trigger, ctx) {
  const { seen, cleared, butterflies, blueUnlocked, hintsUsed, attempts, chaosCount } = ctx
  const kind = trigger.split(':')[0]
  const rest = trigger.slice(kind.length + 1)

  switch (kind) {
    case 'level_clear':
      return cleared.has(rest)
    case 'ending':
      return seen.has(rest)
    case 'chaos_count':
      return chaosCount >= Number(rest)
    case 'butterflies_all':
      return ALL_BUTTERFLY_IDS.every((id) => butterflies.has(id))
    case 'blue_all':
      return blueUnlocked >= ALL_BLUE_FRAGMENT_IDS.length
    case 'endings_all':
      return ALL_DESIGN_ENDING_IDS.every((id) => seen.has(id))
    case 'chapter_clear_no_hint': {
      const chapter = LEVELS_BY_CHAPTER.find((c) => String(c.id) === rest)
      if (!chapter) return false
      return chapter.levels.every((level) => cleared.has(level.id) && !hintsUsed[level.id])
    }
    case 'hints_all':
      return LEVELS.every((level) => (hintsUsed[level.id] || 0) >= 3)
    case 'first_try': {
      const [levelId, type] = rest.split(':')
      const endingId = `${levelId.replace('-', '_')}_${type}`
      return attempts[levelId] === 1 && seen.has(endingId)
    }
    default:
      return false
  }
}
