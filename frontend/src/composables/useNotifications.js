// 站内通知：轮询（默认 30s），不做 WebSocket/SSE，避免长连接与代理运维成本。
import { reactive } from 'vue'
import { api } from '../api'
import { getTokenSync } from '../authStorage'

export const notifications = reactive({
  unread: 0,
  items: [],
  total: 0,
  page: 1,
  loading: false,
  loaded: false,
})

let timer = 0

export function resetNotifications() {
  notifications.unread = 0
  notifications.items = []
  notifications.total = 0
  notifications.page = 1
  notifications.loaded = false
}

export async function loadNotifications(page = 1) {
  if (!getTokenSync()) {
    resetNotifications()
    return
  }
  notifications.loading = true
  try {
    const { data } = await api.get('/events', { params: { page, page_size: 20 } })
    notifications.items = data.items
    notifications.total = data.total
    notifications.unread = data.unread
    notifications.page = data.page
    notifications.loaded = true
  } catch {
    // 通知加载失败不影响任何主流程；下一次轮询会自然重试。
  } finally {
    notifications.loading = false
  }
}

export async function loadNotificationSummary() {
  if (!getTokenSync()) return
  try {
    notifications.unread = (await api.get('/events/summary')).data.unread
  } catch {
    /* 静默降级 */
  }
}

export async function markAllRead() {
  if (!getTokenSync() || !notifications.unread) return
  try {
    await api.post('/events/read', { ids: [] })
    notifications.unread = 0
    notifications.items = notifications.items.map((item) => ({ ...item, read: true }))
  } catch {
    /* 失败保留未读状态，下次打开再试 */
  }
}

export function startNotificationPolling() {
  stopNotificationPolling()
  if (!getTokenSync()) return
  loadNotificationSummary()
  timer = window.setInterval(() => {
    // 页面不可见时不轮询，避免后台标签页持续打接口。
    if (!document.hidden) loadNotificationSummary()
  }, 30000)
}

export function stopNotificationPolling() {
  if (timer) window.clearInterval(timer)
  timer = 0
}
