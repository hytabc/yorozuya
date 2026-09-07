import test from 'node:test'
import assert from 'node:assert/strict'
import { createLifePlayback } from '../src/composables/lifePlayback.js'
function fixture(reduced = false) {
  let state, id = 0
  const tasks = new Map()
  const player = createLifePlayback(s => { state = s }, {
    schedule: f => { tasks.set(++id, f); return id }, cancel: n => tasks.delete(n), reducedMotion: () => reduced,
  })
  return { player, get state() { return state }, step() { const [key, fn] = tasks.entries().next().value; tasks.delete(key); fn() }, get size() { return tasks.size } }
}
test('types Unicode code points and alternates single participant', () => {
  const f = fixture()
  f.player.play([{ from: 'player', text: '白😀' }, { from: 'npc', text: '你好' }])
  f.step(); assert.equal(f.state.text, '白')
  f.step(); assert.equal(f.state.text, '白😀'); assert.equal(f.state.from, 'player')
  assert.equal(f.state.playing, true)
  f.step(); assert.equal(f.state.from, 'npc'); assert.equal(f.state.text, '')
  f.player.complete(); assert.equal(f.state.text, '你好'); assert.equal(f.state.playing, false)
})
test('switch/cancel removes old presentation without touching input history', () => {
  const f = fixture(), input = [{ from: 'player', text: 'old' }, { from: 'npc', text: 'wrong NPC' }]
  const before = JSON.stringify(input)
  f.player.play(input); f.player.play([{ from: 'npc', text: 'new' }]); f.player.complete()
  assert.equal(f.state.text, 'new'); assert.equal(f.size, 0)
  f.player.stop(); assert.equal(f.state.playing, false); assert.equal(f.state.text, '')
  assert.equal(JSON.stringify(input), before)
})
test('reduced motion displays whole lines but preserves turn order', () => {
  const f = fixture(true)
  f.player.play([{ from: 'player', text: 'first' }, { from: 'npc', text: 'second' }])
  assert.equal(f.state.text, 'first'); assert.equal(f.state.typing, false)
  f.step(); assert.equal(f.state.text, 'second'); assert.equal(f.state.playing, false)
})
