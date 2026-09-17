import { api } from './api'

const SESSION_KEY = 'wsw_analytics_session'
// 同一事件在极短时间内的重复上报（连点、重复 emit）直接忽略，避免灌水。
const DEDUPE_MS = 800

let currentPage = null
let lastEventKey = ''
let lastEventAt = 0

// 匿名访客会话 ID：本地持久化，后端据此对未登录访客去重。
export function analyticsSessionId() {
  let value = localStorage.getItem(SESSION_KEY)
  if (!value) {
    value = globalThis.crypto?.randomUUID?.().replaceAll('-', '')
      || `${Date.now()}_${Math.random().toString(36).slice(2)}`
    localStorage.setItem(SESSION_KEY, value)
  }
  return value
}

// 由 router.afterEach 调用，记录当前页面 key（事件按页面聚合）。
export function setCurrentPage(pageKey) {
  currentPage = pageKey || null
}

// 关键行为事件：fire-and-forget，失败静默丢弃，绝不阻塞或影响用户操作。
export function track(eventKey) {
  const now = Date.now()
  if (eventKey === lastEventKey && now - lastEventAt < DEDUPE_MS) return
  lastEventKey = eventKey
  lastEventAt = now
  api.post('/analytics/event', {
    event_key: eventKey,
    page_key: currentPage,
    session_id: analyticsSessionId(),
  }).catch(() => {})
}
