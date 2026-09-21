// 夜间模式的纯逻辑：不依赖 Vue 与 DOM，便于单测（theme.js 负责响应式与落地）。
// 明暗（mode）与风格（theme）是两个正交维度：风格决定"长什么样"，
// 明暗决定"亮还是暗"，因此 <html> 上同时有 data-theme 与 data-mode。

// auto = 交给"跟随系统/按时间"判断，day/night = 用户在设置里手动固定。
export const MODE_SOURCES = [
  { id: 'auto', label: '根据时间切换', hint: '21:00 至次日 06:00 自动使用夜间模式' },
  { id: 'system', label: '跟随系统设置', hint: '跟随操作系统/浏览器的深色模式偏好' },
  { id: 'day', label: '保持日间', hint: '始终使用日间配色' },
  { id: 'night', label: '保持夜间', hint: '始终使用夜间配色' },
]

// 按时间切换的区间：21:00（含）至次日 06:00（不含）。
export const NIGHT_START_HOUR = 21
export const NIGHT_END_HOUR = 6

export function isNightTime(date = new Date()) {
  const hour = date.getHours()
  return hour >= NIGHT_START_HOUR || hour < NIGHT_END_HOUR
}

// 实际生效的明暗。auto 档按时间推导，system 档由调用方把系统偏好传进来，
// day/night 档直接就是用户选的那个。
export function resolveMode(source, { date = new Date(), systemPrefersDark = false } = {}) {
  if (source === 'day' || source === 'night') return source
  if (source === 'system') return systemPrefersDark ? 'night' : 'day'
  return isNightTime(date) ? 'night' : 'day'
}

export function isValidModeSource(id) {
  return MODE_SOURCES.some((item) => item.id === id)
}

// 距下一次昼夜边界（21:00 或 06:00）还有多少毫秒。
// 用"算准下一次切换点"代替"每分钟轮询"：只排一个定时器，切完再排下一个。
export function nextModeChangeIn(date = new Date()) {
  const next = new Date(date.getTime())
  next.setSeconds(0, 0)
  const hour = date.getHours()
  if (hour < NIGHT_END_HOUR) {
    next.setHours(NIGHT_END_HOUR, 0, 0, 0) // 当天 06:00 转日间
  } else if (hour < NIGHT_START_HOUR) {
    next.setHours(NIGHT_START_HOUR, 0, 0, 0) // 当天 21:00 转夜间
  } else {
    next.setDate(next.getDate() + 1) // 次日 06:00 转日间
    next.setHours(NIGHT_END_HOUR, 0, 0, 0)
  }
  return next.getTime() - date.getTime()
}

