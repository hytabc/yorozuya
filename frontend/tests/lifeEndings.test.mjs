// 条件结局纯规则测试:顺序优先级、条件判定、兜底,以及初始房间选择。
import test from 'node:test'
import assert from 'node:assert/strict'
import { resolveEnding, startRoomIdOf } from '../src/life/endings.js'

const pack = {
  endings: [
    { id: 'soulmate', name: '灵魂共鸣', text: '结局A', conditions: { stats: {}, bonds: { ache: 80 } } },
    { id: 'sunny', name: '晴朗收尾', text: '结局B', conditions: { stats: { mood: 60 }, bonds: {} } },
    { id: 'plain', name: '平凡落幕', text: '结局C', conditions: {} },
  ],
  rooms: [
    { id: 'plaza-1', worldId: 'w1', label: '#1', private: false, capacity: 8, occupants: 0 },
    { id: 'beach-2', worldId: 'w1', label: '#2', private: false, capacity: 8, occupants: 2 },
  ],
  startRoomId: 'beach-2',
}
const state = (mood, bond) => ({ stats: { mood }, npcs: [{ id: 'ache', bond }] })

test('resolveEnding picks the first ending whose conditions all pass', () => {
  assert.equal(resolveEnding(pack, state(70, 90)).id, 'soulmate')
  assert.equal(resolveEnding(pack, state(70, 10)).id, 'sunny')
  assert.equal(resolveEnding(pack, state(10, 10)).id, 'plain')
})

test('resolveEnding falls back to a built-in default when nothing matches', () => {
  const noFallback = { endings: [{ id: 'hard', name: '难', text: 'x', conditions: { stats: { mood: 99 } } }] }
  const ending = resolveEnding(noFallback, state(10, 0))
  assert.ok(ending.name && ending.text)
  assert.equal(ending.id, 'builtin-default')
})

test('resolveEnding treats missing conditions as always-true and empty pack as default', () => {
  assert.equal(resolveEnding({ endings: [{ id: 'e', name: 'n', text: 't' }] }, state(0, 0)).id, 'e')
  assert.equal(resolveEnding({}, state(0, 0)).id, 'builtin-default')
})

test('startRoomIdOf prefers the configured room, falls back to first enterable', () => {
  assert.equal(startRoomIdOf(pack), 'beach-2')
  assert.equal(startRoomIdOf({ ...pack, startRoomId: 'ghost' }), 'beach-2')
  assert.equal(startRoomIdOf({ ...pack, startRoomId: '' }), 'beach-2')
  // 无配置时挑第一个有人、未满的非私密房间;都没有则退回第一个房间。
  assert.equal(startRoomIdOf({ ...pack, startRoomId: null }), 'beach-2')
  const empty = { ...pack, startRoomId: null, rooms: pack.rooms.map(r => ({ ...r, occupants: 0 })) }
  assert.equal(startRoomIdOf(empty), 'plaza-1')
})
