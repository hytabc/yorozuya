import test from 'node:test'
import assert from 'node:assert/strict'

import {
  POSTER_FORMATS,
  isEndedStatus,
  posterModel,
  scaleLabel,
  statusLabel,
  truncate,
} from '../src/sharePoster.js'

const task = {
  id: 7,
  title: '帮忙整理一份资料',
  description: '需要把十条记录整理成清晰的表格文件，方便后续交接。',
  category: '技术疑难',
  scale: 'small',
  status: 'published',
  base_points: 5,
  bounty_points: 0,
  required_takers: 1,
  expires_at: '2026-11-05T12:00:00Z',
  publisher: { nickname: 'ColdRain' },
  is_anonymous: false,
  is_official: false,
}

test('海报提供 3:4 与 9:16 两种尺寸', () => {
  assert.equal(POSTER_FORMATS.portrait.width, 1080)
  assert.equal(POSTER_FORMATS.portrait.height, 1440)
  assert.equal(POSTER_FORMATS.story.width, 1080)
  assert.equal(POSTER_FORMATS.story.height, 1920)
  assert.deepEqual(Object.values(POSTER_FORMATS).map((item) => item.label), ['3:4', '9:16'])
})

test('海报内容：普通委托展示发布者与扫码接取文案', () => {
  const model = posterModel(task, 'https://example.com/share/task/7?ref=ABC')
  assert.equal(model.publisher, 'ColdRain')
  assert.equal(model.publisherInitial, 'C')
  assert.equal(model.copy, '扫码查看委托')
  assert.equal(model.shortLink, 'example.com/share/task/7')
  assert.equal(model.points, '5 分')
  assert.equal(model.required, '需要 1 人')
  assert.equal(model.scale, '小型')
  assert.equal(model.status, '招募中')
  assert.equal(model.ended, false)
})

test('匿名/官方委托按规则裁剪，不冒充发布者', () => {
  const anonymous = posterModel({ ...task, is_anonymous: true })
  assert.equal(anonymous.publisher, '匿名委托')
  assert.equal(anonymous.publisherInitial, '匿')

  const official = posterModel({ ...task, is_official: true, publisher: { nickname: '__official__' } })
  assert.equal(official.publisher, '万事屋官方')
  assert.equal(official.publisherInitial, '官')
  assert.equal(official.official, true)
})

test('已结束委托加状态丝带并弱化接取文案', () => {
  const done = posterModel({ ...task, status: 'completed' })
  assert.equal(done.status, '已完成')
  assert.equal(done.ended, true)
  assert.equal(done.copy, '扫码查看详情')
  assert.equal(isEndedStatus('published'), false)
  assert.equal(isEndedStatus('cancelled'), true)
  assert.equal(statusLabel('expired'), '已过期')
  assert.equal(scaleLabel('large'), '大型')
})

test('悬赏、描述截断与截止时间', () => {
  const bounty = posterModel({ ...task, bounty_points: 10 })
  assert.equal(bounty.points, '5 分 + 悬赏 10')
  assert.equal(truncate('x'.repeat(200), 20).length, 20)
  assert.ok(truncate('x'.repeat(200), 20).endsWith('…'))
  assert.equal(posterModel({ ...task, expires_at: null }).deadline, '未设置')
  assert.equal(posterModel({ ...task, required_takers: null }).required, '人数不限')
})
