import test from 'node:test'
import assert from 'node:assert/strict'

import {
  EVENT_LABELS,
  eventLabel,
  eventTarget,
  relativeTime,
  unreadBadge,
} from '../src/events.js'

test('事件类型与后端 EVENT_KINDS 一致', () => {
  assert.deepEqual(
    Object.keys(EVENT_LABELS).sort(),
    ['accepted', 'awaiting', 'cancel_requested', 'cancelled', 'completed', 'designated', 'hidden', 'started'],
  )
  assert.equal(eventLabel('completed'), '委托完成')
  assert.equal(eventLabel('未知类型'), '委托动态')
})

test('未读角标超过 99 折叠为 99+', () => {
  assert.equal(unreadBadge(0), '')
  assert.equal(unreadBadge(null), '')
  assert.equal(unreadBadge(3), '3')
  assert.equal(unreadBadge(99), '99')
  assert.equal(unreadBadge(120), '99+')
  assert.equal(unreadBadge(-1), '')
})

test('相对时间按分钟 / 小时 / 天 / 日期分档', () => {
  const now = Date.parse('2026-11-04T12:00:00Z')
  assert.equal(relativeTime('2026-11-04T11:59:30Z', now), '刚刚')
  assert.equal(relativeTime('2026-11-04T11:35:00Z', now), '25 分钟前')
  assert.equal(relativeTime('2026-11-04T09:00:00Z', now), '3 小时前')
  assert.equal(relativeTime('2026-11-01T12:00:00Z', now), '3 天前')
  assert.equal(relativeTime('2026-09-01T12:00:00Z', now), '9月1日')
  assert.equal(relativeTime('不是时间', now), '')
  assert.equal(relativeTime(null, now), '')
})

test('点击事件跳回大厅并带上 task 参数', () => {
  assert.deepEqual(eventTarget({ task_id: 7 }), { path: '/', query: { task: '7' } })
  assert.deepEqual(eventTarget({}), { path: '/' })
  assert.deepEqual(eventTarget(null), { path: '/' })
})
