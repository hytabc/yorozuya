import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import {
  ONBOARDING_VERSION,
  needsOnboarding,
  onboardingStorageKey,
  onboardingSteps,
} from '../src/composables/onboardingSteps.js'
import { pickAnchor, spotlightRect } from '../src/composables/tourGeometry.js'

const srcDir = join(dirname(fileURLToPath(import.meta.url)), '..', 'src')

function walk(dir, files = []) {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name)
    if (statSync(path).isDirectory()) walk(path, files)
    else files.push(path)
  }
  return files
}

test('步骤表结构完整：id 唯一、5 步、文案与锚点齐全', () => {
  assert.ok(ONBOARDING_VERSION >= 1, '上线版本号必须 ≥ 1')
  assert.equal(onboardingSteps.length, 5)
  const ids = onboardingSteps.map((step) => step.id)
  assert.equal(new Set(ids).size, ids.length, 'id 不能重复')
  assert.deepEqual(ids, ['welcome', 'create', 'nav', 'notifications', 'profile'])
  for (const step of onboardingSteps) {
    assert.ok(step.title && step.title.length > 0, `${step.id} 缺少标题`)
    assert.ok(step.text && step.text.length > 0, `${step.id} 缺少正文`)
    assert.ok(Array.isArray(step.targets) && step.targets.length > 0, `${step.id} 缺少锚点`)
  }
})

test('一次性判定：0 表示从未看过，达到版本后不再展示，版本 0 等于关停', () => {
  assert.equal(needsOnboarding(0), true)
  assert.equal(needsOnboarding(undefined), true)
  assert.equal(needsOnboarding(null), true)
  assert.equal(needsOnboarding(ONBOARDING_VERSION), false)
  assert.equal(needsOnboarding(ONBOARDING_VERSION + 1), false)
  assert.equal(needsOnboarding('1'), false, '字符串形式的历史值也要能比较')
  // ONBOARDING_VERSION = 0 是线上关停开关
  assert.equal(needsOnboarding(0, 0), false)
  assert.equal(needsOnboarding(5, 0), false)
})

test('本地缓存键按账号与版本隔离', () => {
  const key = onboardingStorageKey(7)
  assert.match(key, new RegExp(`^wsw:onboarding:v${ONBOARDING_VERSION}:user:7$`))
  assert.notEqual(onboardingStorageKey(1), onboardingStorageKey(2))
  for (const id of [null, undefined, 0, '', -1, 'token-secret']) {
    assert.equal(onboardingStorageKey(id), null)
  }
})

test('pickAnchor 取第一个"真正可见"的候选锚点', () => {
  const visible = (width = 40, height = 20) => ({
    getClientRects: () => [{ width, height }],
    getBoundingClientRect: () => ({ left: 0, top: 0, right: width, bottom: height, width, height }),
  })
  const hidden = () => ({ getClientRects: () => [], getBoundingClientRect: () => ({ width: 0, height: 0 }) })
  const step = { targets: ['[data-tour="desktop"]', '[data-tour="mobile"]'] }
  const root = (map) => ({ querySelector: (selector) => map[selector] ?? null })

  // 桌面端：第二个候选（移动菜单）不可见也不影响
  assert.ok(pickAnchor(step, root({ '[data-tour="desktop"]': visible() })))
  // 移动端：第一个候选被 display:none 时顺延到第二个
  assert.ok(pickAnchor(step, root({ '[data-tour="desktop"]': hidden(), '[data-tour="mobile"]': visible() })))
  // 全部不可见时返回 null，由引导跳过该步
  assert.equal(pickAnchor(step, root({ '[data-tour="desktop"]': hidden() })), null)
  assert.equal(pickAnchor(step, root({})), null)
  assert.equal(pickAnchor(step, null), null)
})

test('spotlightRect 仍然只裁剪可见区域（虚拟人生指引依赖它）', () => {
  assert.deepEqual(spotlightRect({ left: -10, top: 10, right: 30, bottom: 50, width: 40, height: 40 }, 100, 100), {
    left: 0,
    top: 4,
    width: 36,
    height: 52,
  })
  assert.equal(spotlightRect(null, 100, 100), null)
})

test('步骤表里的 data-tour 锚点在源码中真实存在', () => {
  const sources = walk(srcDir)
    .filter((file) => file.endsWith('.vue'))
    .map((file) => readFileSync(file, 'utf8'))
    .join('\n')
  const declared = new Set([...sources.matchAll(/data-tour="([^"]+)"/g)].map((match) => match[1]))
  for (const step of onboardingSteps) {
    for (const selector of step.targets) {
      const match = selector.match(/^\[data-tour="([^"]+)"\]$/)
      if (!match) continue // 类名兜底锚点不在这里校验
      assert.ok(declared.has(match[1]), `步骤 ${step.id} 指向的 data-tour="${match[1]}" 在源码里不存在`)
    }
  }
})
