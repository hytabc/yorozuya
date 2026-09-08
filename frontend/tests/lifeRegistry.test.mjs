// 内容包注册表测试:注册、校验、活动 Pack、内容完整性与初始状态隔离。
// 运行: node --test --test-isolation=none tests/lifeRegistry.test.mjs
import test from 'node:test'
import assert from 'node:assert/strict'
import {
  registerLifePack, setActiveLifePack, getActiveLifePack, listLifePacks,
  portraitFor, validateLifePack, LifePackError, _resetLifeRegistry,
} from '../src/life/registry.js'
import { defaultLifePack } from '../src/life/content/defaultPack.js'

test('default pack registers and becomes the active pack', () => {
  _resetLifeRegistry()
  registerLifePack(defaultLifePack)
  assert.equal(getActiveLifePack().id, 'wsw-default-life')
  assert.deepEqual(listLifePacks(), [{ id: 'wsw-default-life', version: 1, active: true }])
})

test('default pack content is complete for every declared npc', () => {
  for (const id of defaultLifePack.npcIds) {
    assert.ok(defaultLifePack.npcs.some(npc => npc.id === id), 'npc def: ' + id)
    assert.ok(defaultLifePack.portraits[id].startsWith('/life-assets/'), 'portrait: ' + id)
    const script = defaultLifePack.dialogueScripts[id]
    assert.equal(script.npcLine.from, 'npc')
    assert.ok(script.choices.length >= 2, 'choices: ' + id)
    for (const choice of script.choices) {
      assert.equal(typeof choice.label, 'string')
      assert.equal(typeof choice.npcReply, 'string')
    }
  }
  assert.equal(portraitFor('ache'), defaultLifePack.portraits.ache)
})

test('createInitialState returns isolated deep copies', () => {
  const a = defaultLifePack.createInitialState()
  const b = defaultLifePack.createInitialState()
  a.stats.mood = 1
  a.conversations.ache.push({ from: 'player', text: 'x', day: 7, time: '18:20' })
  assert.equal(b.stats.mood, 72)
  assert.equal(b.conversations.ache.length, 1)
})

test('registry rejects incomplete or malformed packs', () => {
  _resetLifeRegistry()
  assert.throws(() => validateLifePack(null), LifePackError)
  assert.throws(() => validateLifePack({ id: 'x' }), LifePackError)
  const noPortrait = { ...defaultLifePack, id: 'bad-1', portraits: { ache: '/x.jpg', xiaomi: '/x.jpg', maoyou: '/x.jpg' } }
  assert.throws(() => validateLifePack(noPortrait), /立绘/)
  const noScript = { ...defaultLifePack, id: 'bad-2', dialogueScripts: { ache: defaultLifePack.dialogueScripts.ache } }
  assert.throws(() => validateLifePack(noScript), /剧本|选项/)
  const dupIds = { ...defaultLifePack, id: 'bad-3', npcIds: ['ache', 'ache', 'xiaomi', 'maoyou'] }
  assert.throws(() => validateLifePack(dupIds), /重复/)
})

test('unknown active pack id throws and registry reports emptiness', () => {
  _resetLifeRegistry()
  assert.throws(() => getActiveLifePack(), LifePackError)
  assert.throws(() => setActiveLifePack('missing'), LifePackError)
  registerLifePack(defaultLifePack, { active: false })
  assert.equal(getActiveLifePack().id, 'wsw-default-life')
  _resetLifeRegistry()
})
