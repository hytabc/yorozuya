import test from 'node:test'
import assert from 'node:assert/strict'

import {
  SERIAL_PATTERN,
  VISIBILITY_HINTS,
  VISIBILITY_LABELS,
  credentialMeta,
  formatIssued,
  isPublicCredential,
  isSerialValid,
  portfolioTagLabel,
  truncate,
} from '../src/credential.js'

const credential = {
  serial: 'WS-2026-000123',
  title: '为一个虚拟形象做材质与灯光',
  category: '技术疑难',
  skills: ['Blender', '灯光'],
  platforms: ['PCVR'],
  publisher: 'ColdRain',
  taker: '某位志愿者',
  completed_at: '2026-11-01T10:00:00Z',
  issued_at: '2026-11-01T10:05:00Z',
  visibility: 'link',
  revoked: false,
  verify_note: '本凭证基于本站的委托完成记录生成。',
}

test('凭证编号格式与服务端 WS-{年份}-{6 位序号} 一致', () => {
  assert.ok(SERIAL_PATTERN.test('WS-2026-000123'))
  assert.equal(isSerialValid('WS-2026-000123'), true)
  assert.equal(isSerialValid('WS-26-1'), false)
  assert.equal(isSerialValid('ws-2026-000123'), false)
  assert.equal(isSerialValid(''), false)
  assert.equal(isSerialValid(null), false)
})

test('truncate 按字符裁剪并补省略号', () => {
  assert.equal(truncate('短文本', 10), '短文本')
  assert.equal(truncate('一二三四五', 3), '一二…')
  assert.equal(truncate('', 3), '')
  assert.equal(truncate(null, 3), '')
  assert.equal(truncate('abc', 0), 'abc')
})

test('credentialMeta 按「技能 / 平台」插入并保持固定字段', () => {
  const rows = credentialMeta(credential)
  const labels = rows.map((row) => row.label)
  assert.deepEqual(labels, ['委托标题', '委托类型', '技能栈', '平台', '委托方', '接单人', '完成时间', '签发时间'])
  assert.equal(rows[2].value, 'Blender / 灯光')
  assert.equal(rows[3].value, 'PCVR')
  assert.deepEqual(credentialMeta(null), [])

  // 没有技能/平台时不会留下空行。
  const plain = credentialMeta({ title: '只有标题' })
  assert.deepEqual(plain.map((row) => row.label), ['委托标题', '委托类型', '委托方', '接单人', '完成时间', '签发时间'])
})

test('portfolioTagLabel 与公开凭证判定', () => {
  assert.equal(portfolioTagLabel({ value: 'Blender', count: 5 }), 'Blender · 5 次完成')
  assert.equal(isPublicCredential(credential), false)
  assert.equal(isPublicCredential({ ...credential, visibility: 'public' }), true)
  assert.equal(isPublicCredential({ ...credential, visibility: 'public', revoked: true }), false)
  assert.equal(isPublicCredential(null), false)
})

test('可见性文案覆盖三档', () => {
  assert.deepEqual(Object.keys(VISIBILITY_LABELS).sort(), ['link', 'private', 'public'])
  assert.deepEqual(Object.keys(VISIBILITY_HINTS).sort(), ['link', 'private', 'public'])
})

test('formatIssued 对非法时间返回空串', () => {
  assert.equal(formatIssued({ issued_at: 'not-a-date' }), '')
  assert.equal(formatIssued({}), '')
  assert.ok(formatIssued(credential).length > 0)
})
