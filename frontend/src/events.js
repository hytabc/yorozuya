// 站内事件流的展示规则：kind 白名单与后端 backend/app/events.py 的 EVENT_KINDS 同步。
export const EVENT_LABELS = {
  designated: '指定委托',
  accepted: '有人接取',
  started: '委托开始',
  awaiting: '等待确认',
  completed: '委托完成',
  cancel_requested: '取消请求',
  cancelled: '委托取消',
  hidden: '内容隐藏',
}

export function eventLabel(kind) {
  return EVENT_LABELS[kind] || '委托动态'
}

export function unreadBadge(unread) {
  const value = Number(unread) || 0
  if (value <= 0) return ''
  return value > 99 ? '99+' : String(value)
}

// 相对时间只用于通知列表；超过 7 天直接显示日期，避免「1 个月前」这类模糊表述。
export function relativeTime(iso, now = Date.now()) {
  if (!iso) return ''
  const time = new Date(iso).getTime()
  if (Number.isNaN(time)) return ''
  const diff = Math.max(0, now - time)
  const minutes = Math.floor(diff / 60000)
  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes} 分钟前`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} 小时前`
  const days = Math.floor(hours / 24)
  if (days < 7) return `${days} 天前`
  return new Intl.DateTimeFormat('zh-CN', { month: 'short', day: 'numeric' }).format(new Date(time))
}

// 点击事件回到大厅并带上 task 参数：不新增独立详情路由，复用 TaskDialog。
export function eventTarget(event) {
  return event?.task_id ? { path: '/', query: { task: String(event.task_id) } } : { path: '/' }
}
