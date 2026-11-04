import test from 'node:test'
import assert from 'node:assert/strict'

import {
  ATMOSPHERE_STORAGE_KEY,
  ATMOSPHERE_VERSION,
  needsAck,
  parseAckValue,
} from '../src/atmosphereRules.js'

test('礼仪版本与本地存储键稳定', () => {
  assert.equal(ATMOSPHERE_VERSION, 1)
  assert.equal(ATMOSPHERE_STORAGE_KEY, 'wsw_atmosphere_ack')
})

test('parseAckValue 只接受正整数版本', () => {
  assert.equal(parseAckValue('1'), 1)
  assert.equal(parseAckValue(3), 3)
  assert.equal(parseAckValue(null), 0)
  assert.equal(parseAckValue(''), 0)
  assert.equal(parseAckValue('abc'), 0)
  assert.equal(parseAckValue('0'), 0)
  assert.equal(parseAckValue('-2'), 0)
})

test('needsAck 在版本升级后重新触发', () => {
  assert.equal(needsAck(1, 0), true)
  assert.equal(needsAck(1, 1), false)
  assert.equal(needsAck(2, 1), true)
  // 未传参时按当前版本判断，避免调用方各自硬编码版本号。
  assert.equal(needsAck(undefined, 0), true)
  assert.equal(needsAck(undefined, ATMOSPHERE_VERSION), false)
})
