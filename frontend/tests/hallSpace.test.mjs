import test from 'node:test'
import assert from 'node:assert/strict'

import {
  MAX_SPACE_NODES,
  STATUS_COLORS,
  buildLayout,
  clusterLinks,
  clusterOf,
  nodeColor,
} from '../src/hall/space/layout.js'

function task(id, { skill = null, category = '其他委托', status = 'published' } = {}) {
  return {
    id,
    title: `委托 ${id}`,
    category,
    status,
    facets: skill ? [{ facet_type: 'skill', value: skill }] : [],
  }
}

test('分簇优先取主技能，缺省回落到分类', () => {
  assert.equal(clusterOf(task(1, { skill: 'Blender' })), 'Blender')
  assert.equal(clusterOf(task(2, { category: '技术疑难' })), '技术疑难')
  assert.equal(clusterOf({ id: 3 }), '其他委托')
})

test('布局是确定性的：同一输入产生完全相同的坐标', () => {
  const tasks = [task(1, { skill: 'Blender' }), task(2, { skill: 'Unity' }), task(3)]
  const first = buildLayout(tasks)
  const second = buildLayout(tasks)
  assert.deepEqual(first, second)
  // 与输入顺序无关的分簇键集合（节点顺序保持输入顺序）。
  assert.deepEqual(first.nodes.map((node) => node.id), [1, 2, 3])
})

test('节点数量按上限截断并标记，避免一次渲染过多', () => {
  const tasks = Array.from({ length: MAX_SPACE_NODES + 12 }, (_, index) => task(index + 1))
  const layout = buildLayout(tasks)
  assert.equal(layout.nodes.length, MAX_SPACE_NODES)
  assert.equal(layout.truncated, true)
  assert.equal(buildLayout(tasks.slice(0, 5)).truncated, false)
  assert.deepEqual(buildLayout([]), { nodes: [], clusters: [], truncated: false })
})

test('每个节点只属于一个簇，簇计数与节点数一致', () => {
  const layout = buildLayout([
    task(1, { skill: 'Blender' }),
    task(2, { skill: 'Blender' }),
    task(3, { skill: 'Unity' }),
  ])
  const counts = {}
  for (const node of layout.nodes) counts[node.cluster] = (counts[node.cluster] || 0) + 1
  for (const cluster of layout.clusters) assert.equal(counts[cluster.key], cluster.count)
  assert.equal(layout.clusters.length, 2)
})

test('坐标保持在合理范围内，不会因为簇变多而无限外扩', () => {
  const tasks = Array.from({ length: 60 }, (_, index) =>
    task(index + 1, { skill: `技能${index % 12}` }),
  )
  const layout = buildLayout(tasks, { radius: 13 })
  for (const node of layout.nodes) {
    assert.ok(Math.abs(node.x) <= 40, `x 越界: ${node.x}`)
    assert.ok(Math.abs(node.y) <= 40, `y 越界: ${node.y}`)
    assert.equal(node.z, 0)
  }
})

test('连线只发生在同簇相邻节点之间', () => {
  const layout = buildLayout([
    task(3, { skill: 'Blender' }),
    task(1, { skill: 'Blender' }),
    task(2, { skill: 'Unity' }),
  ])
  const links = clusterLinks(layout.nodes)
  // Blender 两个节点（id 1、3）连一条；Unity 单节点不连。
  assert.deepEqual(links, [{ from: 1, to: 3 }])
})

test('节点颜色按状态取，未知状态回落到招募中', () => {
  assert.equal(nodeColor({ status: 'completed' }), STATUS_COLORS.completed)
  assert.equal(nodeColor({ status: '不存在的状态' }), STATUS_COLORS.published)
  assert.equal(nodeColor(null), STATUS_COLORS.published)
})
