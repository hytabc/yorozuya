// 节点图对话规则测试:节点回退、选项推进、链式台词、完成判定、进度清洗。
// 运行: node --test --test-isolation=none tests/lifeDialogue.test.mjs
import test from 'node:test'
import assert from 'node:assert/strict'
import { nodeFor, startLine, resolveDialogueChoice, sanitizeDialogueNodes } from '../src/composables/lifeDialogue.js'
import { defaultLifePackContent } from '../src/life/content/defaultPack.js'

const chainScript = {
  start: 'n1',
  nodes: {
    n1: {
      line: '第一句',
      choices: [
        { label: '继续', effects: { bond: 2, stats: { mood: 1 } }, reply: '回复一', next: 'n2' },
        { label: '结束', effects: {}, reply: '回复终', next: null },
      ],
    },
    n2: {
      line: '第二句',
      choices: [
        { label: '收尾', effects: { stats: { social: 3 } }, reply: '回复二', next: null },
      ],
    },
  },
}

test('nodeFor falls back to the start node for missing positions', () => {
  assert.equal(nodeFor(chainScript, 'n2').line, '第二句')
  assert.equal(nodeFor(chainScript, 'gone').line, '第一句')
  assert.equal(nodeFor(chainScript, null).line, '第一句')
  assert.equal(nodeFor(chainScript, undefined).line, '第一句')
})

test('startLine renders the start node as an npc message', () => {
  const line = startLine(chainScript, 9)
  assert.deepEqual(line, { from: 'npc', text: '第一句', day: 9, time: '18:20' })
})

test('resolveDialogueChoice advances chains and defers completion', () => {
  const cont = resolveDialogueChoice(chainScript, chainScript.nodes.n1.choices[0])
  assert.equal(cont.done, false)
  assert.equal(cont.nextNodeId, 'n2')
  assert.equal(cont.nextLine, '第二句')
  assert.equal(cont.bond, 2)
  assert.deepEqual(cont.stats, { mood: 1 })
  assert.equal(cont.reply, '回复一')

  const end = resolveDialogueChoice(chainScript, chainScript.nodes.n2.choices[0])
  assert.equal(end.done, true)
  assert.equal(end.nextNodeId, null)
  assert.equal(end.nextLine, null)
  assert.equal(end.bond, 0)
  assert.deepEqual(end.stats, { social: 3 })

  const terminal = resolveDialogueChoice(chainScript, chainScript.nodes.n1.choices[1])
  assert.equal(terminal.done, true)
})

test('resolveDialogueChoice treats a dangling next as terminal (defensive)', () => {
  const broken = { label: 'x', effects: {}, reply: 'r', next: 'missing' }
  const result = resolveDialogueChoice(chainScript, broken)
  assert.equal(result.done, true)
  assert.equal(result.nextNodeId, null)
})

test('sanitizeDialogueNodes drops unknown npcs and nodes', () => {
  const dialogue = defaultLifePackContent.dialogue
  assert.deepEqual(sanitizeDialogueNodes(dialogue, { ache: 'n1', ghost: 'n1', xiaomi: 'gone' }), { ache: 'n1' })
  assert.deepEqual(sanitizeDialogueNodes(dialogue, null), {})
  assert.deepEqual(sanitizeDialogueNodes(dialogue, undefined), {})
})
