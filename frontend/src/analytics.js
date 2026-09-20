import { api } from './api'
import { getTokenSync } from './authStorage'
import { createDwellTracker } from './analyticsDwell'

const SESSION_KEY = 'wsw_analytics_session'
// 同一事件在极短时间内的重复上报（连点、重复 emit）直接忽略，避免灌水。
const DEDUPE_MS = 800
const API_BASE = import.meta.env.VITE_API_BASE || '/api'

let currentPage = null
let lastEventKey = ''
let lastEventAt = 0
const dwell = createDwellTracker()

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

// 由 router.afterEach 调用：结算上一页的曝光时长，再开始为新页面计时；
// 同时记录当前页面 key，供后续点击事件 track() 归类到页面。
export function setCurrentPage(pageKey) {
  const left = dwell.enter(pageKey)
  currentPage = pageKey || null
  if (left) sendDwell(left.page, left.seconds, false)
  // 在后台发生的路由切换（例如登录后的跳转）不要开始计时，等回到前台再恢复。
  if (currentPage && typeof document !== 'undefined' && document.visibilityState === 'hidden') {
    dwell.pause()
  }
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

// 曝光时长上报。离页/卸载场景用 fetch keepalive：axios(XHR) 请求会被浏览器取消，
// 且必须在请求里带上令牌，否则登录用户会被后端记成匿名访客。
function sendDwell(pageKey, seconds, keepalive) {
  const body = { page_key: pageKey, seconds, session_id: analyticsSessionId() }
  if (!keepalive) {
    api.post('/analytics/page-dwell', body).catch(() => {})
    return
  }
  const headers = { 'Content-Type': 'application/json' }
  const token = getTokenSync()
  if (token) headers.Authorization = `Bearer ${token}`
  try {
    fetch(`${API_BASE}/analytics/page-dwell`, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
      keepalive: true,
    }).catch(() => {})
  } catch {
    /* 埋点失败不影响用户 */
  }
}

if (typeof document !== 'undefined') {
  // 切后台：结算当前页并暂停计时，后台停留不计入曝光时长。
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') {
      const left = dwell.pause()
      if (left) sendDwell(left.page, left.seconds, true)
    } else {
      dwell.resume()
    }
  })
  // 关标签/刷新：pagehide 在现代浏览器更可靠，beforeunload 兜底；
  // 第一次结算后 tracker 已清空，第二次调用是安全的空操作。
  const stop = () => {
    const left = dwell.finish()
    if (left) sendDwell(left.page, left.seconds, true)
  }
  window.addEventListener('pagehide', stop)
  window.addEventListener('beforeunload', stop)
}
