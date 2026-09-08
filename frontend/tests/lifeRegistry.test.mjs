// 内容包注册表测试:注册、校验、活动 Pack、内容完整性、初始状态隔离、
// 工厂派生视图,以及与后端种子 JSON 的一致性。
// 运行: node --test --test-isolation=none tests/lifeRegistry.test.mjs
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import {
  registerLifePack, setActiveLifePack, getActiveLifePack, listLifePacks,
  portraitFor, validateLifePack, createLifePackFromContent, effectText,
  LifePackError, _resetLifeRegistry,
} from '../src/life/registry.js'
import { defaultLifePack, defaultLifePackContent } from '../src/life/content/defaultPack.js'

test('default pack registers and becomes the active pack', () => {
  _resetLifeRegistry()
  registerLifePack(defaultLifePack)
  assert.equal(getActiveLifePack().id, 'wsw-default-life')
  assert.deepEqual(listLifePacks(), [{ id: 'wsw-default-life', version: 1, active: true }])
})

test('builtin content matches the backend seed JSON exactly', () => {
  const seedPath = fileURLToPath(new URL('../../backend/app/life_packs/wsw-default-life.json', import.meta.url))
  const seed = JSON.parse(readFileSync(seedPath, 'utf8'))
  assert.deepEqual(defaultLifePackContent, seed)
})

test('default pack content is complete for every declared npc', () => {
  for (const id of defaultLifePack.npcIds) {
    assert.ok(defaultLifePack.npcs.some(npc => npc.id === id), 'npc def: ' + id)
    assert.ok(defaultLifePack.portraits[id].startsWith('/life-assets/'), 'portrait: ' + id)
    assert.ok(defaultLifePack.presence[id], 'presence: ' + id)
    const script = defaultLifePack.dialogue[id]
    const start = script.nodes[script.start]
    assert.ok(start, 'dialogue start: ' + id)
    assert.equal(typeof start.line, 'string')
    assert.ok(start.choices.length >= 2, 'choices: ' + id)
    for (const choice of start.choices) {
      assert.equal(typeof choice.label, 'string')
      assert.equal(typeof choice.reply, 'string')
    }
  }
  assert.ok(defaultLifePack.worlds.length >= 1)
  assert.ok(defaultLifePack.rooms.length >= 1)
  assert.ok(defaultLifePack.actions.length >= 1)
  assert.equal(portraitFor('ache'), defaultLifePack.portraits.ache)
})

test('effectText renders node-graph choice effects as display text', () => {
  assert.equal(effectText({ bond: 2, stats: { social: 2, mood: 2 } }), '好感 +2 · 社交 +2 · 心情 +2')
  assert.equal(effectText({ stats: { energy: -4 } }), '精力 -4')
  assert.equal(effectText({}), '')
  assert.equal(effectText(), '')
  const pack = createLifePackFromContent({ id: 'copy-pack', version: 3, content: defaultLifePackContent })
  assert.equal(pack.id, 'copy-pack')
  assert.equal(pack.version, 3)
  assert.equal(pack.dialogue.yu.nodes.n1.line, defaultLifePackContent.dialogue.yu.nodes.n1.line)
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
  const noScript = { ...defaultLifePack, id: 'bad-2', dialogue: { ache: defaultLifePack.dialogue.ache } }
  assert.throws(() => validateLifePack(noScript), /剧本/)
  const dupIds = { ...defaultLifePack, id: 'bad-3', npcIds: ['ache', 'ache', 'xiaomi', 'maoyou'] }
  assert.throws(() => validateLifePack(dupIds), /重复/)
  const noWorlds = { ...defaultLifePack, id: 'bad-4', worlds: [] }
  assert.throws(() => validateLifePack(noWorlds), /worlds/)
  const badRoom = { ...defaultLifePack, id: 'bad-5', rooms: [{ id: 'r1', worldId: 'nowhere', label: '#1', private: false, capacity: 4, occupants: 1 }] }
  assert.throws(() => validateLifePack(badRoom), /未知世界/)
  const badNext = JSON.parse(JSON.stringify(defaultLifePack))
  badNext.id = 'bad-6'
  badNext.dialogue.ache.nodes.n1.choices[0].next = 'missing-node'
  assert.throws(() => validateLifePack(badNext), /未知节点/)
  const noActions = { ...defaultLifePack, id: 'bad-7', actions: [] }
  assert.throws(() => validateLifePack(noActions), /actions/)
})

test('unknown active pack id throws and registry reports emptiness', () => {
  _resetLifeRegistry()
  assert.throws(() => getActiveLifePack(), LifePackError)
  assert.throws(() => setActiveLifePack('missing'), LifePackError)
  registerLifePack(defaultLifePack, { active: false })
  assert.equal(getActiveLifePack().id, 'wsw-default-life')
  _resetLifeRegistry()
})
