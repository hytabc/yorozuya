import test from 'node:test'
import assert from 'node:assert/strict'

import {
  DISCLOSURE_DEFAULT,
  TRUST_DISCLOSURE,
  disclosureCount,
  disclosurePatch,
  platformLabel,
  trustSummary,
} from '../src/trust.js'

test('披露项与后端 DISCLOSURE_KEYS 一致，默认全关', () => {
  assert.deepEqual(
    TRUST_DISCLOSURE.map((item) => item.key),
    ['identity', 'trust_rank', 'account_age', 'platform', 'common_friends', 'common_groups', 'worlds'],
  )
  assert.deepEqual(Object.keys(DISCLOSURE_DEFAULT).sort(), TRUST_DISCLOSURE.map((item) => item.key).sort())
  assert.equal(disclosureCount(DISCLOSURE_DEFAULT), 0)
  // 已验证可用的四项；共同好友/社群/World 仍等待后续接入。
  assert.deepEqual(
    TRUST_DISCLOSURE.filter((item) => item.available).map((item) => item.key),
    ['identity', 'trust_rank', 'account_age', 'platform'],
  )
})

test('trustSummary 不伪造 Trust Rank 或账号年龄', () => {
  assert.equal(trustSummary(null), null)
  assert.equal(trustSummary({ bound: false }), null)

  const named = trustSummary({ bound: true, display_name: 'ColdRain' })
  assert.equal(named.text, 'ColdRain · 未验证')
  assert.equal(named.level, '未验证')
  assert.ok(named.source.includes('未验证'))

  // 未披露显示名时也不能编造内容，只说明「已绑定」。
  const hidden = trustSummary({ bound: true })
  assert.equal(hidden.text, '已绑定 VRChat · 未验证')

  // 已验证时展示真实 Trust Rank / 账号年龄 / 平台。
  const verified = trustSummary({
    bound: true,
    verified: true,
    display_name: 'ColdRain',
    trust_rank: 'known_user',
    account_age_label: '5 年 2 个月',
    platform: 'standalonewindows',
    stale: false,
  })
  assert.equal(verified.level, '熟识用户')
  assert.equal(verified.text, 'ColdRain · 熟识用户 · 账号 5 年 2 个月 · PC')
  assert.ok(verified.source.includes('简介验证码'))
  assert.equal(platformLabel('android'), 'Quest / Android')
})

test('disclosurePatch 只发送白名单布尔值', () => {
  const patch = disclosurePatch({ identity: true, trust_rank: 1, unknown: 'x' })
  assert.deepEqual(patch, {
    identity: true,
    trust_rank: true,
    account_age: false,
    platform: false,
    common_friends: false,
    common_groups: false,
    worlds: false,
  })
  assert.deepEqual(disclosurePatch(null), DISCLOSURE_DEFAULT)
})

test('disclosureCount 只统计开启项', () => {
  assert.equal(disclosureCount({ identity: true, worlds: true }), 2)
  assert.equal(disclosureCount(null), 0)
})
