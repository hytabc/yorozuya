// 节点图对话规则测试:节点回退、选项推进、消息组(多句+图片)展开、完成判定、进度清洗。
// 运行: node --test --test-isolation=none tests/lifeDialogue.test.mjs
import test from 'node:test'
import assert from 'node:assert/strict'
import { scriptForDay, nodeFor, startMessages, groupMessages, resolveDialogueChoice, sanitizeDialogueNodes } from '../src/composables/lifeDialogue.js'
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
