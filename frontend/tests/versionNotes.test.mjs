import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

import {
  currentVersion,
  currentVersionEntry,
  loadVersionNotes,
  missedVersionCount,
  normalizeVersion,
  resetVersionNotesCache,
  shouldPromptVersion,
  versionIndex,
} from '../src/versionNotes.js'
import {
  claimPrompt,
  promptOwner,
  readAckedVersion,
  releasePrompt,
  resetPromptSession,
  resetVersionDecision,
  settleVersionDecision,
  versionDecisionSettled,
  writeAckedVersion,
} from '../src/composables/versionPrompt.js'

const NOTES = {
  entries: [
    { version: 'V1.1', summary: ['新版本'] },
    { version: 'V1.0', summary: ['旧版本'] },
    { version: 'V0.9', summary: ['更旧'] },
  ],
}

function memoryStorage(initial = {}) {
  const data = new Map(Object.entries(initial))
  return {
    getItem: (key) => (data.has(key) ? data.get(key) : null),
    setItem: (key, value) => data.set(key, String(value)),
    dump: () => Object.fromEntries(data),
  }
}

test('当前版本取 entries 第一项', () => {
  assert.equal(currentVersion(NOTES), 'V1.1')
  assert.equal(currentVersion({ entries: [] }), '')
  assert.equal(currentVersion(null), '')
  assert.equal(currentVersionEntry(NOTES).version, 'V1.1')
  assert.equal(normalizeVersion('  V1.1 '), 'V1.1')
})

test('只有版本号变化才提示；同一版本改文案不提示', () => {
  assert.equal(shouldPromptVersion(NOTES, ''), true)
  assert.equal(shouldPromptVersion(NOTES, 'V1.0'), true)
  assert.equal(shouldPromptVersion(NOTES, 'V1.1'), false)
  assert.equal(shouldPromptVersion(NOTES, ' V1.1 '), false)
  assert.equal(shouldPromptVersion({ entries: [] }, ''), false)
})

test('错过的版本数按已确认版本的位置计算', () => {
  assert.equal(missedVersionCount(NOTES, ''), 0)
  assert.equal(missedVersionCount(NOTES, 'V1.1'), 0)
  assert.equal(missedVersionCount(NOTES, 'V1.0'), 1)
  assert.equal(missedVersionCount(NOTES, 'V0.9'), 2)
  // 已确认版本不在列表里：按"除了最新版都错过了"算
  assert.equal(missedVersionCount(NOTES, 'V0.1'), 2)
  assert.equal(versionIndex(NOTES, 'V1.0'), 1)
  assert.equal(versionIndex(NOTES, 'nope'), -1)
})

test('游客标记读写与损坏存储的降级', () => {
  const storage = memoryStorage()
  assert.equal(readAckedVersion(storage), '')
  assert.equal(writeAckedVersion('V1.1', storage), true)
  assert.equal(readAckedVersion(storage), 'V1.1')
  assert.equal(writeAckedVersion('   ', storage), false)

  const broken = { getItem() { throw new Error('denied') }, setItem() { throw new Error('denied') } }
  assert.equal(readAckedVersion(broken), '')
  assert.equal(writeAckedVersion('V1.1', broken), false)
})

test('每次进入只有一个浮层位置，优先级由谁先抢到决定', () => {
  resetPromptSession()
  assert.equal(promptOwner(), null)
  assert.equal(claimPrompt('version'), true)
  assert.equal(claimPrompt('announcement'), false)
  assert.equal(claimPrompt('atmosphere'), false)
  assert.equal(promptOwner(), 'version')
  releasePrompt('announcement')
  assert.equal(promptOwner(), 'version')
  releasePrompt('version')
  assert.equal(claimPrompt('announcement'), true)
  resetPromptSession()
  assert.equal(promptOwner(), null)
})

test('版本判定完成后公告才能继续', async () => {
  resetVersionDecision()
  let done = false
  versionDecisionSettled().then(() => { done = true })
  await Promise.resolve()
  assert.equal(done, false)
  settleVersionDecision()
  await versionDecisionSettled()
  assert.equal(done, true)
})

test('加载失败不缓存，下一次可以重试', async () => {
  resetVersionNotesCache()
  const failing = async () => ({ ok: false })
  assert.equal(await loadVersionNotes(failing), null)
  const ok = async () => ({ ok: true, json: async () => NOTES })
  assert.equal((await loadVersionNotes(ok)).entries.length, 3)
  resetVersionNotesCache()
})

test('versions.json 结构：从新到旧、有摘要、版本号唯一', () => {
  const raw = readFileSync(new URL('../public/versions/versions.json', import.meta.url), 'utf8')
  const notes = JSON.parse(raw)
  assert.ok(Array.isArray(notes.entries) && notes.entries.length > 0)
  const versions = notes.entries.map((entry) => entry.version)
  assert.equal(new Set(versions).size, versions.length)
  for (const entry of notes.entries) {
    assert.ok(entry.version, '版本号不能为空')
    assert.ok(entry.date, `${entry.version} 缺少日期`)
    assert.ok(Array.isArray(entry.summary) && entry.summary.length > 0, `${entry.version} 缺少摘要`)
    assert.ok(Array.isArray(entry.sections), `${entry.version} 的 sections 必须是数组`)
  }
  // 版本号按数字段从新到旧
  const keys = versions.map((v) => v.match(/\d+/g).map(Number))
  const compare = (a, b) => {
    for (let i = 0; i < Math.max(a.length, b.length); i++) {
      const diff = (a[i] || 0) - (b[i] || 0)
      if (diff) return diff
    }
    return 0
  }
  for (let i = 1; i < keys.length; i++) {
    assert.ok(
      compare(keys[i - 1], keys[i]) > 0,
      `${versions[i - 1]} 应排在新于 ${versions[i]} 的位置`,
    )
  }
})
