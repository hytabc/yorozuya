// 节点图对话规则测试:节点回退、选项推进、消息组(多句+图片)展开、完成判定、进度清洗。
// 运行: node --test --test-isolation=none tests/lifeDialogue.test.mjs
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { scriptForDay, nodeFor, startMessages, groupMessages, resolveDialogueChoice, sanitizeDialogueNodes, pickFallbackReply } from '../src/composables/lifeDialogue.js'
import { defaultLifePackContent } from '../src/life/content/defaultPack.js'

test('scriptForDay clamps to the 7-day schedule (no cycling)', () => {
  const days = defaultLifePackContent.dialogue.ache
  assert.equal(days.length, 7)
  assert.equal(scriptForDay(days, 1), days[0])
  assert.equal(scriptForDay(days, 7), days[6])
  assert.equal(scriptForDay(days, 8), days[6], '第 8 天起沿用第 7 天剧本,不循环')
  assert.equal(scriptForDay(days, 14), days[6])
  assert.equal(scriptForDay(days, 100), days[6])
  assert.equal(scriptForDay([], 3), null)
  const single = [days[0]]
  assert.equal(scriptForDay(single, 5), days[0], '单天剧本每天重复')
})

test('pickFallbackReply returns null without configured or eligible replies', () => {
  const unusedRng = () => { throw new Error('无候选不应调用随机数') }
  for (const replies of [undefined, null, [], [{ text: '熟悉之后', minBond: 30 }]]) {
    assert.equal(pickFallbackReply(replies, 0, unusedRng), null)
  }
})

test('pickFallbackReply selects the highest reachable tier including its boundary', () => {
  const replies = [{ text: '亲近', minBond: 70 }, { text: '你好', minBond: 0 }, { text: '熟悉', minBond: 30 }]
  for (const [bond, expected] of [[0, '你好'], [29, '你好'], [30, '熟悉'], [69, '熟悉'], [70, '亲近'], [100, '亲近']]) {
    assert.equal(pickFallbackReply(replies, bond, () => 0), expected)
  }
})

test('pickFallbackReply randomizes only within the highest eligible tier without mutation', () => {
  const replies = Object.freeze([
    Object.freeze({ text: '低档', minBond: 0 }),
    Object.freeze({ text: '第一句', minBond: 30 }),
    Object.freeze({ text: '高档', minBond: 70 }),
    Object.freeze({ text: '第二句', minBond: 30 }),
  ])
  assert.equal(pickFallbackReply(replies, 50, () => 0), '第一句')
  assert.equal(pickFallbackReply(replies, 50, () => 0.499), '第一句')
  assert.equal(pickFallbackReply(replies, 50, () => 0.5), '第二句')
  assert.equal(pickFallbackReply(replies, 50, () => 0.999), '第二句')
})

test('pickFallbackReply treats omitted minBond as zero', () => {
  const replies = [{ text: '默认' }, { text: '零档', minBond: 0 }, { text: '高档', minBond: 30 }]
  assert.equal(pickFallbackReply(replies, 0, () => 0), '默认')
  assert.equal(pickFallbackReply(replies, 0, () => 0.9), '零档')
  assert.equal(pickFallbackReply(replies, 30, () => 0), '高档')
})

// 抽取实际切换/快照函数,用轻量状态桩验证接线,不依赖浏览器或 Vue 挂载。
function fallbackGame(completedToday, replies, bond = 30) {
  const source = readFileSync(new URL('../src/life/useLifeGame.js', import.meta.url), 'utf8')
  const npc = { id: 'ache', name: '阿澈', role: '摄影', avatar: '📷', status: '', bond }
  const ref = value => ({ value })
  const context = {
    saveReady: ref(true), saveConflict: ref(false), canInteract: () => true,
    currentRoomId: ref('room'), currentNpcId: ref('other'), currentNpc: ref(npc),
    conversations: ref({ ache: [{ from: 'npc', text: '旧回复', day: 7, time: '18:20' }] }),
    completed: ref({ ache: completedToday }), actionFeedback: ref('旧反馈'), dialogueVisible: ref(false),
    pack: { id: 'test-pack', npcs: [{ ...npc, fallbackReplies: replies }], dialogue: { ache: [{ start: 'n1', nodes: { n1: { lines: ['开场'] } } }] } },
    day: ref(7), pickFallbackReply, startMessages, scriptForDay,
    playback: { play: messages => { context.played.push(messages) } },
    cancelPresentation: () => { context.cancelled++ }, markChanged: () => { context.changed++ },
    played: [], cancelled: 0, changed: 0,
    npcs: ref([{ ...npc, fallbackReplies: replies }]), stats: ref({}), tags: ref([]),
    currentWorld: ref('世界'), unlockedWorlds: ref(1), diaryHistory: ref([]),
    actionLedger: ref({}), dialogueNodes: ref({}), eventProgress: ref({ day: 7, done: [] }),
    friendIds: ref([]), interactedNpcIds: ref([]),
  }
  const bind = (start, end, name) => {
    const body = source.slice(source.indexOf(start), source.indexOf(end, source.indexOf(start)))
    return new Function(...Object.keys(context), `${body}; return ${name}`)(...Object.values(context))
  }
  context.switchNpc = bind('  function switchNpc(', '  function chooseOption(', 'switchNpc')
  context.snapshot = bind('  function snapshot(', '  function hydrate(', 'snapshot')
  return context
}

test('completed avatar clicks append and play a single fallback, persisted without content fields or effects', () => {
  const game = fallbackGame(true, [{ text: '坐一会儿吧', minBond: 30 }])
  game.switchNpc('ache')
  game.switchNpc('ache')
  assert.equal(game.currentNpcId.value, 'ache')
  assert.equal(game.cancelled, 2)
  assert.equal(game.changed, 2)
  assert.equal(game.conversations.value.ache.length, 3)
  assert.deepEqual(game.played, [[{ from: 'npc', text: '坐一会儿吧', day: 7, time: '18:20' }], [{ from: 'npc', text: '坐一会儿吧', day: 7, time: '18:20' }]])
  // 旧存档 NPC 没有配置字段也能从活动包取得台词。
  assert.equal(game.currentNpc.value.fallbackReplies, undefined)
  const saved = game.snapshot()
  assert.deepEqual(saved.conversations.ache, game.conversations.value.ache)
  assert.equal(Object.hasOwn(saved.npcs[0], 'fallbackReplies'), false)
  assert.equal(saved.npcs[0].bond, 30)
  assert.deepEqual(saved.actionLedger, {})
  assert.deepEqual(saved.diary, [])
})

test('completed avatar clicks without eligible fallback only switch and do not replay history', () => {
  for (const replies of [undefined, [], [{ text: '高档', minBond: 70 }]]) {
    const game = fallbackGame(true, replies)
    game.switchNpc('ache')
    assert.equal(game.currentNpcId.value, 'ache')
    assert.equal(game.dialogueVisible.value, true)
    assert.equal(game.conversations.value.ache.length, 1)
    assert.deepEqual(game.played, [])
    assert.equal(game.changed, 1)
  }
})

test('unfinished avatar clicks retain opening and replay behavior rather than fallback', () => {
  const game = fallbackGame(false, [{ text: '默认', minBond: 0 }])
  game.switchNpc('ache')
  game.switchNpc('ache')
  assert.deepEqual(game.conversations.value.ache.map(message => message.text), ['旧回复', '开场'])
  assert.deepEqual(game.played.map(messages => messages[0].text), ['开场', '开场'])
})

const chainScript = {
  start: 'n1',
  nodes: {
    n1: {
      lines: ['第一句'],
      image: null,
      choices: [
        { label: '继续', effects: { bond: 2, stats: { mood: 1 } }, replies: ['回复一'], replyImage: null, next: 'n2' },
        { label: '结束', effects: {}, replies: ['回复终'], replyImage: null, next: null },
      ],
    },
    n2: {
      lines: ['第二句', '第二句半'],
      image: '/uploads/life/n2.png',
      choices: [
        { label: '收尾', effects: { stats: { social: 3 } }, replies: ['回复二', '回复二续'], replyImage: '/uploads/life/r2.png', next: null },
      ],
    },
  },
}

test('nodeFor falls back to the start node for missing positions', () => {
  assert.deepEqual(nodeFor(chainScript, 'n2').lines, ['第二句', '第二句半'])
  assert.deepEqual(nodeFor(chainScript, 'gone').lines, ['第一句'])
  assert.deepEqual(nodeFor(chainScript, null).lines, ['第一句'])
  assert.deepEqual(nodeFor(chainScript, undefined).lines, ['第一句'])
})

test('groupMessages expands a message group with the image on the last line', () => {
  const msgs = groupMessages(['一', '二', '三'], '/uploads/life/x.png', 2)
  assert.deepEqual(msgs.map(m => m.text), ['一', '二', '三'])
  assert.deepEqual(msgs.map(m => m.image), [null, null, '/uploads/life/x.png'])
  assert.ok(msgs.every(m => m.from === 'npc' && m.day === 2 && m.time === '18:20'))
  const noImage = groupMessages(['单'], null, 1)
  assert.deepEqual(noImage, [{ from: 'npc', text: '单', day: 1, time: '18:20', image: null }])
})

test('startMessages expands the start node as npc messages', () => {
  assert.deepEqual(startMessages(chainScript, 9), [
    { from: 'npc', text: '第一句', day: 9, time: '18:20', image: null },
  ])
  const multi = startMessages({ start: 'n1', nodes: { n1: { lines: ['早', '吃了吗'], image: '/uploads/life/m.png', choices: [{ label: 'x', effects: {}, replies: ['y'], replyImage: null, next: null }] } } }, 3)
  assert.deepEqual(multi, [
    { from: 'npc', text: '早', day: 3, time: '18:20', image: null },
    { from: 'npc', text: '吃了吗', day: 3, time: '18:20', image: '/uploads/life/m.png' },
  ])
})

test('resolveDialogueChoice advances chains and defers completion', () => {
  const cont = resolveDialogueChoice(chainScript, chainScript.nodes.n1.choices[0])
  assert.equal(cont.done, false)
  assert.equal(cont.nextNodeId, 'n2')
  assert.deepEqual(cont.nextLines, ['第二句', '第二句半'])
  assert.equal(cont.nextImage, '/uploads/life/n2.png')
  assert.equal(cont.bond, 2)
  assert.deepEqual(cont.stats, { mood: 1 })
  assert.deepEqual(cont.replies, ['回复一'])
  assert.equal(cont.replyImage, null)

  const end = resolveDialogueChoice(chainScript, chainScript.nodes.n2.choices[0])
  assert.equal(end.done, true)
  assert.equal(end.nextNodeId, null)
  assert.equal(end.nextLines, null)
  assert.equal(end.bond, 0)
  assert.deepEqual(end.stats, { social: 3 })
  assert.deepEqual(end.replies, ['回复二', '回复二续'])
  assert.equal(end.replyImage, '/uploads/life/r2.png')

  const terminal = resolveDialogueChoice(chainScript, chainScript.nodes.n1.choices[1])
  assert.equal(terminal.done, true)
})

test('resolveDialogueChoice treats a dangling next as terminal (defensive)', () => {
  const broken = { label: 'x', effects: {}, replies: ['r'], replyImage: null, next: 'missing' }
  const result = resolveDialogueChoice(chainScript, broken)
  assert.equal(result.done, true)
  assert.equal(result.nextNodeId, null)
  assert.equal(result.nextLines, null)
})

test('sanitizeDialogueNodes drops unknown npcs and nodes', () => {
  const dialogue = defaultLifePackContent.dialogue
  assert.deepEqual(sanitizeDialogueNodes(dialogue, { ache: 'n1', ghost: 'n1', xiaomi: 'gone' }), { ache: 'n1' })
  assert.deepEqual(sanitizeDialogueNodes(dialogue, null), {})
  assert.deepEqual(sanitizeDialogueNodes(dialogue, undefined), {})
})
