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
    const days = defaultLifePack.dialogue[id]
    assert.ok(Array.isArray(days) && days.length === 7, 'daily scripts: ' + id)
    const start = days[0].nodes[days[0].start]
    assert.ok(start, 'dialogue start: ' + id)
    assert.ok(Array.isArray(start.lines) && start.lines.length >= 1, 'lines: ' + id)
    assert.ok(start.choices.length >= 2, 'choices: ' + id)
    assert.notEqual(days[0].nodes.n1.lines[0], days[1].nodes.n1.lines[0], '每天开场应不同: ' + id)
    for (const choice of start.choices) {
      assert.equal(typeof choice.label, 'string')
      assert.ok(Array.isArray(choice.replies) && choice.replies.length >= 1, 'replies: ' + id)
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
  assert.equal(pack.dialogue.yu[0].nodes.n1.line, defaultLifePackContent.dialogue.yu[0].nodes.n1.line)
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
  badNext.dialogue.ache[0].nodes.n1.choices[0].next = 'missing-node'
  assert.throws(() => validateLifePack(badNext), /未知节点/)
  const noActions = { ...defaultLifePack, id: 'bad-7', actions: [] }
  assert.throws(() => validateLifePack(noActions), /actions/)
})

// 每次新建七天事件,避免变异测试污染默认内容或其他用例。
function makeEvent() {
  return {
    id: 'room-event', roomId: defaultLifePack.rooms[0].id, title: '午后相遇', icon: '☕',
    scripts: Array.from({ length: 7 }, (_, day) => ({
      messages: [
        { speaker: { npcId: defaultLifePack.npcIds[0] }, lines: [`第${day + 1}天`, '你好'], image: '/uploads/event.png' },
        { speaker: { name: '路人', avatar: '/uploads/avatar.png' }, lines: ['一起坐坐吧'], image: null },
        { choice: { options: [
          { label: '加入', effects: { stats: { mood: 100, energy: -100, social: 0, explore: 1 } }, reply: [
            { speaker: { name: '店员' }, lines: ['欢迎'], image: '/uploads/reply.png' },
            { speaker: { npcId: defaultLifePack.npcIds[0] }, lines: ['请坐'] },
          ] },
          { label: '下次再来', reply: [{ speaker: { name: '路人' }, lines: ['再见'] }] },
        ] } },
      ],
    })),
  }
}

function validateEvents(events) {
  return validateLifePack({ ...defaultLifePack, events })
}

function eventOption(event) {
  return event.scripts[0].messages[2].choice.options[0]
}

function rejectsEvent(mutate, pattern) {
  const event = makeEvent()
  mutate(event)
  assert.throws(() => validateEvents([event]), error => error instanceof LifePackError && pattern.test(error.message))
}

test('events accept seven daily scripts with messages, choices and stat boundaries', () => {
  const events = [makeEvent(), { ...makeEvent(), id: 'another-event' }]
  assert.equal(validateEvents(events), true)
  const content = { ...defaultLifePackContent, events }
  const pack = createLifePackFromContent({ id: 'event-pack', version: 1, content })
  assert.equal(pack.events, events)
  assert.deepEqual(pack.events, content.events)
})

test('events default to empty while direct validation rejects explicit null', () => {
  const pack = { ...defaultLifePack }
  delete pack.events
  assert.equal(validateLifePack(pack), true)
  assert.equal(validateEvents(undefined), true)
  assert.equal(validateEvents([]), true)
  for (const events of [null, {}, 'events', 0, false]) {
    assert.throws(() => validateEvents(events), /events 必须是数组/)
  }
  const content = { ...defaultLifePackContent }
  delete content.events
  assert.deepEqual(createLifePackFromContent({ id: 'legacy-pack', version: 1, content }).events, [])
  for (const events of [undefined, null, false, 0, '']) {
    // 工厂按 content.events || [] 归一,与直接校验显式 null 的行为不同。
    assert.deepEqual(createLifePackFromContent({ id: 'empty-events', version: 1, content: { ...content, events } }).events, [])
  }
  assert.throws(() => createLifePackFromContent({ id: 'bad-events', version: 1, content: { ...content, events: {} } }), /events 必须是数组/)
})

test('events reject malformed entries, ids, room references and display fields', () => {
  for (const event of [null, [], 'event', 1, false]) {
    assert.throws(() => validateEvents([event]), /event 必须是对象/)
  }
  assert.throws(() => validateEvents([makeEvent(), makeEvent()]), /id 缺失或重复/)
  for (const id of [undefined, null, '', 1]) rejectsEvent(event => { event.id = id }, /id 缺失或重复/)
  for (const roomId of [undefined, null, '', 'missing-room', 1]) rejectsEvent(event => { event.roomId = roomId }, /未知房间/)
  for (const key of ['title', 'icon']) {
    for (const value of [undefined, null, '', 1, []]) rejectsEvent(event => { event[key] = value }, /非空字符串/)
  }
})

test('events require exactly seven nonempty daily message arrays', () => {
  for (const scripts of [undefined, null, {}, [], makeEvent().scripts.slice(0, 6), [...makeEvent().scripts, makeEvent().scripts[0]]]) {
    rejectsEvent(event => { event.scripts = scripts }, /scripts 必须恰好 7 份/)
  }
  for (const script of [null, [], 'script', {}, { messages: null }, { messages: {} }, { messages: [] }]) {
    rejectsEvent(event => { event.scripts[6] = script }, /第7天.*messages 必须是非空数组/)
  }
})

// 消息组和选项回复必须使用同一套 speaker、台词和图片约束。
for (const target of ['message', 'reply']) {
  const setMessage = (event, message) => {
    if (target === 'message') event.scripts[0].messages[0] = message
    else eventOption(event).reply[0] = message
  }
  test(`event ${target} rejects malformed groups and invalid speakers`, () => {
    for (const message of [null, [], 'message', 1]) rejectsEvent(event => setMessage(event, message), /消息组必须是对象/)
    const speakers = [
      [undefined, /恰好指定/], [null, /恰好指定/], [[], /恰好指定/], [{}, /恰好指定/],
      [{ npcId: defaultLifePack.npcIds[0], name: '双重身份' }, /恰好指定/],
      [{ npcId: 'missing' }, /未知 NPC/], [{ npcId: 1 }, /未知 NPC/], [{ npcId: null }, /未知 NPC/],
      [{ name: '' }, /缺少名字/], [{ name: 1 }, /缺少名字/], [{ name: null }, /缺少名字/],
      [{ name: '路人', extra: true }, /未知字段/],
      ...[undefined, null, 1, {}, []].map(avatar => [{ name: '路人', avatar }, /avatar 必须是字符串/]),
    ]
    for (const [speaker, pattern] of speakers) {
      rejectsEvent(event => setMessage(event, { speaker, lines: ['你好'] }), pattern)
    }
  })

  test(`event ${target} validates lines and upload images without restricting avatar paths`, () => {
    for (const lines of [undefined, null, {}, '你好', [], [''], ['你好', null], [1], [false]]) {
      rejectsEvent(event => setMessage(event, { speaker: { name: '路人' }, lines }), /台词必须是非空句子数组/)
    }
    for (const image of ['', '/life-assets/image.png', 'https://example.com/image.png', '/uploads-other/a.png', 1, false, {}]) {
      rejectsEvent(event => setMessage(event, { speaker: { name: '路人' }, lines: ['你好'], image }), /图片必须是 \/uploads\/ 站内路径/)
    }
    for (const image of [undefined, null, '/uploads/a.png']) {
      for (const avatar of ['', '/life-assets/a.png', 'https://example.com/avatar.png']) {
        const event = makeEvent()
        setMessage(event, { speaker: { name: '路人', avatar }, lines: ['你好'], image })
        assert.equal(validateEvents([event]), true)
      }
    }
  })
}

test('event choices reject mixed message groups and nested reply choices', () => {
  for (const key of ['speaker', 'lines', 'image', 'extra']) {
    rejectsEvent(event => { event.scripts[0].messages[2][key] = null }, /选项点与消息组必须二选一/)
  }
  rejectsEvent(event => { eventOption(event).reply = [event.scripts[0].messages[2]] }, /禁止嵌套选项点 choice/)
  rejectsEvent(event => { eventOption(event).reply[0].choice = null }, /禁止嵌套选项点 choice/)
  for (const choice of [undefined, null, [], {}, { options: null }, { options: {} }, { options: [] }]) {
    rejectsEvent(event => { event.scripts[0].messages[2].choice = choice }, /options 必须是非空数组/)
  }
  for (const option of [null, [], 'option', {}, { label: '' }, { label: 1 }]) {
    rejectsEvent(event => { event.scripts[0].messages[2].choice.options = [option] }, /无文案选项/)
  }
  for (const reply of [undefined, null, {}, 'reply', []]) {
    rejectsEvent(event => { eventOption(event).reply = reply }, /reply 必须是非空消息组数组/)
  }
})

test('event effects allow only stat objects and forbid bond or other keys', () => {
  for (const effects of [undefined, null, [], 1, false, 'effects']) {
    rejectsEvent(event => { eventOption(event).effects = effects }, /effects 必须是对象/)
  }
  for (const effects of [{ bond: 0 }, { bond: 1, stats: {} }, { unknown: 1 }]) {
    rejectsEvent(event => { eventOption(event).effects = effects }, /只允许 stats,禁止 bond 或其他键/)
  }
  for (const stats of [undefined, null, [], 1, false, 'stats', { unknown: 1 }, { bond: 1 }, { toString: 1 }]) {
    rejectsEvent(event => { eventOption(event).effects = { stats } }, /选项包含未知属性/)
  }
  for (const effects of [{}, { stats: {} }]) {
    const event = makeEvent()
    eventOption(event).effects = effects
    assert.equal(validateEvents([event]), true)
  }
})

test('event stat deltas require integers between minus and plus one hundred', () => {
  for (const value of [-101, 101, 0.5, NaN, Infinity, -Infinity, true, false, '1', null, undefined, [], {}]) {
    rejectsEvent(event => { eventOption(event).effects.stats = { mood: value } }, /选项属性变化无效/)
  }
  for (const key of ['mood', 'energy', 'social', 'explore']) {
    for (const value of [-100, -1, 0, 1, 100]) {
      const event = makeEvent()
      eventOption(event).effects.stats = { [key]: value }
      assert.equal(validateEvents([event]), true)
    }
  }
})

test('event validation checks later options, messages and reply groups', () => {
  rejectsEvent(event => { event.scripts[6].messages[1].speaker = { npcId: 'missing' } }, /第7天.*未知 NPC/)
  rejectsEvent(event => { event.scripts[0].messages[2].choice.options[1].label = '' }, /无文案选项/)
  rejectsEvent(event => { eventOption(event).reply[1].lines = [] }, /回复.*台词/)
})

test('unknown active pack id throws and registry reports emptiness', () => {
  _resetLifeRegistry()
  assert.throws(() => getActiveLifePack(), LifePackError)
  assert.throws(() => setActiveLifePack('missing'), LifePackError)
  registerLifePack(defaultLifePack, { active: false })
  assert.equal(getActiveLifePack().id, 'wsw-default-life')
  _resetLifeRegistry()
})
