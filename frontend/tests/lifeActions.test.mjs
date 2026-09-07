import test from 'node:test'
import assert from 'node:assert/strict'
import { resolveLifeAction } from '../src/composables/lifeActions.js'
const run = (overrides = {}) => resolveLifeAction({ day: 7, npcId: 'ache', bond: 12, actionId: 'headpat', ...overrides })
test('first reward per day per NPC per action, ledger survives JSON reload', () => {
  const first = run()
  assert.equal(first.reward, 2)
  const ledger = JSON.parse(JSON.stringify(first.ledger))
  const repeat = run({ ledger, bond: first.bond })
  assert.equal(repeat.allowed, true)
  assert.equal(repeat.repeated, true)
  assert.equal(repeat.reward, 0)
  assert.equal(repeat.action.reply.length > 0, true)
  assert.equal(run({ ledger, npcId: 'xiaomi' }).reward, 2)
  assert.equal(run({ ledger, actionId: 'poke' }).reward, 1)
  assert.equal(run({ ledger, day: 8 }).reward, 2)
  assert.deepEqual(ledger, first.ledger)
})
test('kiss threshold 29 blocked, 30 accepted, correct reward and cap', () => {
  assert.equal(run({ actionId: 'kiss', bond: 29 }).allowed, false)
  assert.equal(run({ actionId: 'kiss', bond: 30 }).reward, 3)
  const capped = run({ actionId: 'kiss', bond: 99 })
  assert.equal(capped.bond, 100)
  assert.equal(capped.reward, 1)
  const full = run({ bond: 100 })
  assert.equal(full.reward, 0)
  assert.equal(run({ ledger: full.ledger, bond: 100 }).repeated, true)
})
test('old save absent ledger accepted; invalid actions rejected without changes', () => {
  assert.equal(run({ ledger: undefined }).reward, 2)
  assert.equal(run({ actionId: 'unknown' }).allowed, false)
  assert.equal(run({ day: 0 }).allowed, false)
})
