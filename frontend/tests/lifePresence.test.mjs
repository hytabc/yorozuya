import test from 'node:test'
import assert from 'node:assert/strict'
import { roomFor, roomDecision, joinDecision, planJoin, canInteract, sceneRoster, migrateSocialState, friendshipDecision } from '../src/composables/lifePresence.js'

test('rooms reject private empty full while non-green is only a follow restriction', () => {
  for (const id of ['cafe-private', 'beach-empty', 'hall-full', 'unknown']) assert.equal(roomDecision(roomFor(id)).allowed, false)
  assert.equal(roomDecision(roomFor('beach-2086')).allowed, true)
  assert.equal(planJoin('maoyou').allowed, false)
  assert.equal(canInteract('maoyou', 'beach-2086'), true)
  assert.equal(joinDecision({status: 'green', roomId: 'cafe-private'}).allowed, false)
  for (const status of ['orange', 'red', 'offline']) assert.equal(joinDecision({status, roomId: 'beach-1024'}).allowed, false)
})
test('same map different room cannot interact and travel never opens dialogue', () => {
  const npcs = ['ache', 'xiaomi', 'maoyou', 'yu'].map(id => ({id}))
  assert.deepEqual(sceneRoster(npcs, 'beach-1024'), [{id:'ache'}])
  assert.deepEqual(sceneRoster(npcs, 'beach-2086'), [{id:'maoyou'}])
  assert.equal(canInteract('ache', 'beach-2086'), false)
  assert.equal(planJoin('xiaomi').dialogueVisible, false)
  assert.equal(planJoin('xiaomi').roomId, 'cafe-1101')
})
test('friend eligibility requires interaction plus 10 and explicit addition', () => {
  assert.equal(friendshipDecision('ache', 12, [], []).allowed, false)
  assert.equal(friendshipDecision('ache', 9, ['ache'], []).allowed, false)
  assert.equal(friendshipDecision('ache', 10, ['ache'], []).allowed, true)
  assert.equal(friendshipDecision('ache', 12, ['ache'], ['ache']).allowed, false)
})
test('old saves infer actual player interaction not friendship or opening greetings', () => {
  const old = {currentWorld:'潮汐之后 · 黄昏', conversations:{ache:[{from:'npc'}], xiaomi:[{from:'player'}]}}
  assert.deepEqual(migrateSocialState(old), {currentRoomId:'beach-1024',friendIds:[],interactedNpcIds:['xiaomi']})
  const saved = {...old, currentRoomId:'beach-2086', friendIds:['xiaomi'], interactedNpcIds:['xiaomi']}
  assert.deepEqual(migrateSocialState(JSON.parse(JSON.stringify(saved))), {currentRoomId:'beach-2086',friendIds:['xiaomi'],interactedNpcIds:['xiaomi']})
  assert.equal(migrateSocialState({currentWorld:'unknown'}).currentRoomId, 'beach-1024')
})
