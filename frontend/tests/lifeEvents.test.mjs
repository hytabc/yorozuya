// 房间事件纯规则测试：七日钳制、房间过滤、属性结算与存档进度迁移。
// 运行: node --test --test-isolation=none tests/lifeEvents.test.mjs
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import { defaultLifePack } from '../src/life/content/defaultPack.js'
import { effectText } from '../src/life/registry.js'
import { scriptForDay, startMessages, sanitizeDialogueNodes } from '../src/composables/lifeDialogue.js'
import test from 'node:test'
import assert from 'node:assert/strict'
import { eventScriptForDay, eventsForRoom, isEventDone, applyEventChoice, eventEffectsOf, mergeEventChoices, normalizeEventProgress } from '../src/composables/lifeEvents.js'

const event = { id: 'tea', roomId: 'room-a', scripts: Array.from({ length: 7 }, (_, i) => ({ messages: [`第${i + 1}天`] })) }

test('eventScriptForDay clamps to days one through seven without cycling', () => {
  for (let day = 1; day <= 7; day++) assert.equal(eventScriptForDay(event, day), event.scripts[day - 1])
  for (const day of [8, 14, 100]) assert.equal(eventScriptForDay(event, day), event.scripts[6])
  for (const day of [0, -1]) assert.equal(eventScriptForDay(event, day), event.scripts[0])
  assert.equal(eventScriptForDay({}, 1), null)
  assert.equal(eventScriptForDay({ scripts: [] }, 1), null)
})

test('eventsForRoom preserves room event order and supports legacy packs', () => {
  const other = { ...event, id: 'other', roomId: 'room-b' }
  const second = { ...event, id: 'second' }
  const events = [event, other, second]
  assert.deepEqual(eventsForRoom(events, 'room-a'), [event, second])
  assert.deepEqual(eventsForRoom(events, 'missing'), [])
  assert.deepEqual(eventsForRoom(undefined, 'room-a'), [])
  assert.equal(events.length, 3)
})

test('isEventDone only recognizes completion on the current day', () => {
  const progress = { day: 3, done: ['tea'] }
  assert.equal(isEventDone(progress, 3, 'tea'), true)
  assert.equal(isEventDone(progress, 4, 'tea'), false)
  assert.equal(isEventDone(progress, 3, 'other'), false)
  assert.equal(isEventDone(undefined, 1, 'tea'), false)
  assert.equal(isEventDone({ day: 1 }, 1, 'tea'), false)
})

test('applyEventChoice adds only stat deltas and clamps without mutating inputs', () => {
  const stats = { mood: 98, energy: 3, social: 40, explore: 20 }
  const effects = { mood: 8, energy: -9, social: 2, bond: 100, unknown: 9 }
  assert.deepEqual(applyEventChoice(stats, effects), { mood: 100, energy: 0, social: 42, explore: 20 })
  assert.deepEqual(stats, { mood: 98, energy: 3, social: 40, explore: 20 })
  assert.equal(effects.mood, 8)
  assert.deepEqual(applyEventChoice(stats), stats)
  assert.notEqual(applyEventChoice(stats), stats)
})

test('eventEffectsOf passes through stats only and defaults to an empty object', () => {
  const stats = { mood: 2 }
  assert.equal(eventEffectsOf({ effects: { stats, bond: 99 } }), stats)
  for (const option of [undefined, null, {}, { effects: {} }]) assert.deepEqual(eventEffectsOf(option), {})
})

test('normalizeEventProgress resets missing and malformed saves', () => {
  for (const saved of [undefined, null, [], 'bad', {}, { day: 0, done: [] }, { day: 1.5, done: [] },
    { day: '1', done: [] }, { day: 1, done: null }, { day: 1, done: 'tea' },
    { day: 1, done: [1] }, { day: 1, done: [''] }]) {
    assert.deepEqual(normalizeEventProgress(saved, 1), { day: 1, done: [] })
  }
})

test('normalizeEventProgress resets stale progress to the new day', () => {
  const saved = { day: 7, done: ['tea'] }
  assert.deepEqual(normalizeEventProgress(saved, 8), { day: 8, done: [] })
  assert.deepEqual(saved, { day: 7, done: ['tea'] })
})

test('normalizeEventProgress preserves current progress in an independent array', () => {
  const saved = { day: 2, done: ['tea', 'tea', 'other'] }
  const progress = normalizeEventProgress(saved, 2)
  assert.deepEqual(progress, { day: 2, done: ['tea', 'other'] })
  progress.done.push('new')
  assert.deepEqual(saved.done, ['tea', 'tea', 'other'])
})

test('mergeEventChoices handles empty and multiple empty effects', () => {
  for (const choices of [undefined, [], [{}, {}, { stats: {} }]]) {
    assert.deepEqual(mergeEventChoices(choices), { stats: {}, bonds: {} })
  }
})

test('mergeEventChoices sums stats without clamping or mutating choices', () => {
  const choices = [{ stats: { mood: 100, energy: -2 } }, { stats: { mood: 10, energy: 2, social: 0 } }]
  const before = structuredClone(choices)
  assert.deepEqual(mergeEventChoices(choices), { stats: { mood: 110, energy: 0, social: 0 }, bonds: {} })
  assert.deepEqual(choices, before)
})

test('mergeEventChoices groups bonds by NPC and accumulates repeated NPC choices', () => {
  const choices = [
    { bond: { npcId: 'ache', value: 100 }, stats: { explore: 3 } },
    {}, { bond: { npcId: 'yu', value: -5 } },
    { bond: { npcId: 'ache', value: 10 } },
    { bond: { npcId: 'yu', value: 5 } },
    { bond: { npcId: '__proto__', value: -3 } },
  ]
  const before = structuredClone(choices)
  assert.deepEqual(mergeEventChoices(choices), {
    stats: { explore: 3 }, bonds: { ache: 110, yu: 0, ['__proto__']: -3 },
  })
  assert.deepEqual(choices, before)
})

// 按现有存档测试方式隔离 Vue 与浏览器副作用，验证真实引擎接线。
test('game wires event guards, completion, snapshots, hydration and next day', () => {
  const room = defaultLifePack.rooms[0]
  const pack = { ...defaultLifePack, events: [{ ...event, roomId: room.id }] }
  let changes = 0
  const context = vm.createContext({
    ref: value => ({ value }), computed: get => ({ get value() { return get() } }),
    onMounted() {}, onBeforeUnmount() {}, setTimeout: () => 1, clearTimeout() {},
    getActiveLifePack: () => pack, portraitFor: id => pack.portraits[id],
    useLifeSave: () => ({ ready: { value: true }, conflict: { value: false }, changed: () => { changes++ } }),
    createLifePlayback: () => ({ stop() {} }),
    eventScriptForDay, eventsForRoom, isEventDone, applyEventChoice, normalizeEventProgress,
    effectText, scriptForDay, startMessages, sanitizeDialogueNodes,
    roomFor: id => pack.rooms.find(item => item.id === id),
    worldFor: id => pack.worlds.find(item => item.id === id),
    migrateSocialState: state => state,
  })
  const source = readFileSync(new URL('../src/life/useLifeGame.js', import.meta.url), 'utf8')
    .replace(/^import .*$/gm, '').replace('export function', 'function')
  vm.runInContext(source + '\nglobalThis.game = useLifeGame()', context)
  const game = context.game
  game.currentRoomId.value = room.id
  assert.deepEqual(game.eventProgress.value, { day: game.day.value, done: [] })
  game.saveReady.value = false
  game.openEvent('tea')
  assert.equal(game.activeEvent.value, null)
  game.saveReady.value = true
  game.saveConflict.value = true
  game.openEvent('tea')
  assert.equal(game.activeEvent.value, null)
  game.saveConflict.value = false
  game.openEvent('unknown')
  assert.equal(game.activeEvent.value, null)
  game.openEvent('tea')
  assert.equal(game.activeEvent.value.script, event.scripts[game.day.value - 1])
  game.closeEvent()
  assert.equal(game.roomEvents.value[0].done, false)
  assert.equal(changes, 0)
  game.openEvent('tea')
  game.stats.value.mood = 99
  const [firstNpc, secondNpc] = game.npcs.value
  firstNpc.bond = 99
  secondNpc.bond = 2
  game.finishEvent({ stats: { mood: 5 }, bonds: { [firstNpc.id]: 5, [secondNpc.id]: -10, missing: 10 } })
  assert.equal(firstNpc.bond, 100)
  assert.equal(secondNpc.bond, 0)
  assert.equal(game.stats.value.mood, 100)
  assert.equal(game.activeEvent.value, null)
  assert.equal(game.roomEvents.value[0].done, true)
  assert.equal(game.toast.value, `✦ 心情 +5 · ${firstNpc.name} 好感 +5 · ${secondNpc.name} 好感 -10`)
  assert.equal(changes, 1)
  game.finishEvent({ stats: { mood: -100 }, bonds: { [firstNpc.id]: -100 } })
  assert.equal(firstNpc.bond, 100)
  assert.equal(secondNpc.bond, 0)
  game.openEvent('tea')
  assert.equal(game.activeEvent.value, null)
  assert.equal(changes, 1)
  const saved = game.snapshot()
  assert.equal(saved.eventProgress.done[0], 'tea')
  assert.equal(game.day.value, 7)
  game.nextDay()
  assert.equal(game.day.value, 7)
  assert.equal(game.eventProgress.value.day, game.day.value)
  assert.equal(game.eventProgress.value.done.includes('tea'), true)
  assert.equal(game.roomEvents.value[0].done, true)
  game.completed.value = { [firstNpc.id]: true }
  game.pending.value = { [firstNpc.id]: true }
  game.dialogueNodes.value = { [firstNpc.id]: 'test-node' }
  game.actionLedger.value = { test: 1 }
  const beforeReset = game.snapshot()
  const changesBeforeReset = changes
  // 存档未就绪或有冲突时，测试重置也不能修改状态。
  game.saveReady.value = false
  game.resetToday()
  assert.deepEqual(game.snapshot(), beforeReset)
  game.saveReady.value = true
  game.saveConflict.value = true
  game.resetToday()
  assert.deepEqual(game.snapshot(), beforeReset)
  assert.equal(changes, changesBeforeReset)
  game.saveConflict.value = false
  game.resetToday()
  assert.equal(game.day.value, 7)
  // VM 内创建的对象原型不同，转为本侧普通对象后比较完整内容。
  assert.deepEqual(JSON.parse(JSON.stringify(game.eventProgress.value)), { day: 7, done: [] })
  assert.equal(game.roomEvents.value[0].done, false)
  for (const field of ['completed', 'pending', 'dialogueNodes', 'actionLedger']) {
    assert.deepEqual(Object.keys(game[field].value), [])
  }
  assert.equal(game.activeEvent.value, null)
  assert.equal(game.dialogueVisible.value, false)
  const afterReset = game.snapshot()
  for (const field of ['stats', 'npcs', 'friendIds', 'interactedNpcIds', 'diary', 'tags', 'unlockedWorlds']) {
    assert.deepEqual(afterReset[field], beforeReset[field])
  }
  const fresh = pack.createInitialState()
  for (const npc of game.npcs.value) {
    const greeting = fresh.conversations[npc.id]?.[0]
    assert.deepEqual(JSON.parse(JSON.stringify(afterReset.conversations[npc.id])), [
      ...(greeting ? [{ ...greeting, day: 7 }] : []),
      ...startMessages(scriptForDay(pack.dialogue[npc.id], 7), 7),
    ])
  }
  assert.equal(game.toast.value, '↺ 已重置今天：对话、事件与动作奖励都可重玩')
  assert.equal(changes, changesBeforeReset + 1)
  game.openEvent('tea')
  assert.notEqual(game.activeEvent.value, null)
  game.hydrate(saved)
  assert.equal(game.activeEvent.value, null)
  assert.equal(game.roomEvents.value[0].done, true)
  delete saved.eventProgress
  game.hydrate(saved)
  assert.equal(game.eventProgress.value.done.length, 0)
  saved.eventProgress = { day: saved.day + 1, done: ['tea'] }
  game.hydrate(saved)
  assert.equal(game.eventProgress.value.done.length, 0)
})
