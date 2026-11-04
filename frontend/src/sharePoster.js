// 委托分享海报的纯数据层：尺寸、文案与任务快照，便于 node:test 直接覆盖。
// 绘制在 ShareDialog.vue 的 Canvas 2D 中完成。

export const POSTER_FORMATS = {
  portrait: { key: 'portrait', label: '3:4', width: 1080, height: 1440 },
  story: { key: 'story', label: '9:16', width: 1080, height: 1920 },
}

const STATUS_LABELS = {
  published: '招募中',
  accepted: '处理中',
  awaiting: '待确认',
  cancelling: '取消确认中',
  completed: '已完成',
  expired: '已过期',
  cancelled: '已取消',
}

const SCALE_LABELS = {
  small: '小型',
  medium: '中型',
  large: '大型',
}

const LIVE_STATUSES = new Set(['published', 'accepted', 'awaiting', 'cancelling'])

export function statusLabel(value) {
  return STATUS_LABELS[value] || value || ''
}

export function scaleLabel(value) {
  return SCALE_LABELS[value] || value || ''
}

export function isEndedStatus(value) {
  return !LIVE_STATUSES.has(value)
}

export function truncate(text, max = 150) {
  const value = String(text || '').replace(/\s+/g, ' ').trim()
  if (value.length <= max) return value
  return `${value.slice(0, Math.max(0, max - 1))}…`
}

export function formatDeadline(value) {
  if (!value) return '未设置'
  try {
    return new Intl.DateTimeFormat('zh-CN', {
      month: 'long',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    }).format(new Date(value))
  } catch {
    return '未设置'
  }
}

export function pointsText(task) {
  const base = Number(task?.base_points || 0)
  const bounty = Number(task?.bounty_points || 0)
  if (!base && !bounty) return '积分待定'
  if (bounty) return `${base} 分 + 悬赏 ${bounty}`
  return `${base} 分`
}

export function publisherName(task) {
  if (task?.is_anonymous) return '匿名委托'
  if (task?.is_official) return '万事屋官方'
  return task?.publisher?.nickname || '万事屋用户'
}

export function posterModel(task, shareUrl = '') {
  const ended = isEndedStatus(task?.status)
  const anonymous = Boolean(task?.is_anonymous)
  const official = Boolean(task?.is_official)
  const publisher = publisherName(task)
  return {
    taskId: task?.id,
    title: task?.title || '未命名委托',
    category: task?.category || '其他委托',
    scale: scaleLabel(task?.scale),
    status: statusLabel(task?.status),
    ended,
    description: truncate(task?.description, 150),
    points: pointsText(task),
    required: task?.required_takers == null ? '人数不限' : `需要 ${task.required_takers} 人`,
    deadline: formatDeadline(task?.expires_at),
    publisher,
    publisherInitial: anonymous ? '匿' : official ? '官' : String(publisher).slice(0, 1),
    official,
    anonymous,
    copy: ended ? '扫码查看详情' : '扫码查看委托',
    shareUrl,
    shortLink: String(shareUrl || '').replace(/^https?:\/\//, '').replace(/\?.*$/, ''),
  }
}
