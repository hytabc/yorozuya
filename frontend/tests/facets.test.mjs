import test from 'node:test'
import assert from 'node:assert/strict'

import {
  ATMOSPHERE_GROUPS,
  ATMOSPHERE_TAGS,
  FACET_LIMITS,
  TASK_PLATFORMS,
  TASK_SKILLS,
} from '../src/constants.js'
import {
  buildFacets,
  cardFacets,
  facetGroups,
  facetQueryParams,
  facetsOfType,
  pickSingle,
  toggleFacet,
} from '../src/facets.js'

test('标签词表与后端白名单的数量上限一致', () => {
  assert.deepEqual(FACET_LIMITS, { skill: 6, platform: 2, world: 3, atmosphere: 5 })
  assert.equal(TASK_SKILLS.length, 10)
  assert.equal(TASK_PLATFORMS.length, 4)
  // 氛围各维度的取值不允许重复，否则单选分组会互相干扰。
  assert.equal(new Set(ATMOSPHERE_TAGS).size, ATMOSPHERE_TAGS.length)
  assert.equal(ATMOSPHERE_GROUPS.length, 4)
  assert.equal(ATMOSPHERE_TAGS.length, 13)
})

test('toggleFacet 追加、移除并遵守上限', () => {
  assert.deepEqual(toggleFacet([], 'Blender', 6), ['Blender'])
  assert.deepEqual(toggleFacet(['Blender'], 'Blender', 6), [])
  assert.deepEqual(toggleFacet(['Blender', 'Unity'], 'Blender', 6), ['Unity'])
  // 达到上限后不再追加，但已选项仍可取消。
  assert.deepEqual(toggleFacet(['a', 'b'], 'c', 2), ['a', 'b'])
  assert.deepEqual(toggleFacet(['a', 'b'], 'a', 2), ['b'])
})

test('pickSingle 按维度互斥', () => {
  assert.deepEqual(pickSingle([], '语音沟通'), ['语音沟通'])
  assert.deepEqual(pickSingle(['文字为主'], '语音沟通'), ['语音沟通'])
  assert.deepEqual(pickSingle(['语音沟通'], '语音沟通'), [])
})

test('facetsOfType 忽略空值与未知类型', () => {
  const facets = [
    { facet_type: 'skill', value: 'Blender' },
    { facet_type: 'skill', value: 'Unity' },
    { facet_type: 'platform', value: 'PCVR' },
  ]
  assert.deepEqual(facetsOfType(facets, 'skill'), ['Blender', 'Unity'])
  assert.deepEqual(facetsOfType(facets, 'world'), [])
  assert.deepEqual(facetsOfType(null, 'skill'), [])
})

test('facetQueryParams 只保留非空条件', () => {
  assert.deepEqual(
    facetQueryParams({ skill: 'Blender', platform: '', world: '', atmosphere: '可录屏', search: 'x' }),
    { skill: 'Blender', atmosphere: '可录屏' },
  )
  assert.deepEqual(facetQueryParams({}), {})
  assert.deepEqual(facetQueryParams(null), {})
})

test('facetGroups 按固定顺序分组并跳过空组', () => {
  const groups = facetGroups([
    { facet_type: 'world', value: '示例世界' },
    { facet_type: 'skill', value: 'Blender' },
    { facet_type: 'atmosphere', value: '可录屏' },
  ])
  assert.deepEqual(groups.map((group) => group.key), ['skill', 'world', 'atmosphere'])
  assert.deepEqual(groups[0], { key: 'skill', label: '技能', values: ['Blender'] })
  assert.deepEqual(facetGroups([]), [])
})

test('cardFacets 只取 3 个技能与 1 个平台', () => {
  const cards = cardFacets([
    { facet_type: 'platform', value: 'PCVR' },
    { facet_type: 'platform', value: 'Quest' },
    { facet_type: 'skill', value: 'Blender' },
    { facet_type: 'skill', value: 'Unity' },
    { facet_type: 'skill', value: 'Udon' },
    { facet_type: 'skill', value: '音频' },
  ])
  assert.equal(cards.platform, 'PCVR')
  assert.deepEqual(cards.skills, ['Blender', 'Unity', 'Udon'])
  assert.equal(cards.moreSkills, 1)
})

test('buildFacets 产出后端要求的 facet_type/value 结构', () => {
  const facets = buildFacets({
    skills: ['Blender'],
    platforms: ['PCVR'],
    atmosphere: ['可录屏'],
    worlds: ['示例世界'],
  })
  assert.deepEqual(facets, [
    { facet_type: 'skill', value: 'Blender' },
    { facet_type: 'platform', value: 'PCVR' },
    { facet_type: 'atmosphere', value: '可录屏' },
    { facet_type: 'world', value: '示例世界' },
  ])
  assert.deepEqual(buildFacets({}), [])
})
