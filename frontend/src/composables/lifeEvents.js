// 房间事件规则：纯函数，不依赖 vue；第七天之后沿用第七天剧本。
export function eventScriptForDay(event, day) {
  if (!Array.isArray(event?.scripts) || !event.scripts.length) return null
  return event.scripts[Math.min(Math.max(1, day), 7) - 1] || null
}

export function eventsForRoom(events, roomId) {
  return (events || []).filter(event => event.roomId === roomId)
}

export function isEventDone(eventProgress, day, eventId) {
  return eventProgress?.day === day && Array.isArray(eventProgress.done) && eventProgress.done.includes(eventId)
}

// effects 为已选选项的属性变化表，不接收 bond；与对话一致逐属性加算并钳制。
export function applyEventChoice(stats, effects = {}) {
  const next = { ...stats }
  for (const key of ['mood', 'energy', 'social', 'explore']) {
    if (Object.hasOwn(effects, key) && Number.isFinite(effects[key]) && Number.isFinite(next[key])) {
      next[key] = Math.max(0, Math.min(100, next[key] + effects[key]))
    }
  }
  return next
}

// 保留只提取属性的兼容接口；完整事件效果使用 mergeEventChoices 合并。
export function eventEffectsOf(option) {
  return option?.effects?.stats || {}
}

// 合并已校验的选项效果；先求和，完整看完事件后再统一钳制结算。
export function mergeEventChoices(choices = []) {
  const stats = new Map()
  const bonds = new Map()
  for (const effects of choices) {
    for (const [key, value] of Object.entries(effects?.stats || {})) {
      stats.set(key, (stats.get(key) || 0) + value)
    }
    if (effects?.bond) {
      const { npcId, value } = effects.bond
      bonds.set(npcId, (bonds.get(npcId) || 0) + value)
    }
  }
  return { stats: Object.fromEntries(stats), bonds: Object.fromEntries(bonds) }
}

// 旧存档、损坏形状或跨日进度都重置；返回独立数组，避免结算修改原存档。
export function normalizeEventProgress(saved, day) {
  if (!saved || typeof saved !== 'object' || Array.isArray(saved) ||
      !Number.isInteger(saved.day) || saved.day < 1 || saved.day !== day ||
      !Array.isArray(saved.done) || saved.done.some(id => typeof id !== 'string' || !id)) {
    return { day, done: [] }
  }
  return { day, done: [...new Set(saved.done)] }
}
