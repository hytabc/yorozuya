// 大厅星图的确定性布局：纯函数、无渲染依赖，node --test 直接覆盖。
// 同一批委托永远得到同一组坐标，避免筛选后卡片「乱跳」。
export const MAX_SPACE_NODES = 60

const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5))

// 分簇依据：优先主技能，其次分类；这样「同技能」的委托天然靠近。
export function clusterOf(task) {
  const skill = (task.facets || []).find((item) => item.facet_type === 'skill')
  return skill ? skill.value : task.category || '其他委托'
}

export function buildLayout(tasks, { radius = 13 } = {}) {
  const limited = (tasks || []).slice(0, MAX_SPACE_NODES)
  const groups = new Map()
  for (const task of limited) {
    const key = clusterOf(task)
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key).push(task)
  }

  const keys = [...groups.keys()]
  const nodes = []
  const clusters = []

  keys.forEach((key, clusterIndex) => {
    const members = groups.get(key)
    // 簇中心沿黄金角排布，数量变化时整体形状不塌缩成一条线。
    const angle = clusterIndex * GOLDEN_ANGLE
    const clusterRadius = keys.length === 1 ? 0 : Math.min(radius, 4 + Math.sqrt(clusterIndex + 1) * 2.6)
    const cx = Math.cos(angle) * clusterRadius
    const cy = Math.sin(angle) * clusterRadius
    clusters.push({ key, x: cx, y: cy, count: members.length })

    members.forEach((task, index) => {
      const local = index === 0 ? 0 : 1.2 + Math.sqrt(index) * 0.9
      const localAngle = index * GOLDEN_ANGLE
      nodes.push({
        id: task.id,
        task,
        cluster: key,
        // 单节点簇不偏移，避免所有节点挤在圆心。
        x: cx + Math.cos(localAngle) * local,
        y: cy + Math.sin(localAngle) * local,
        z: 0,
      })
    })
  })

  return { nodes, clusters, truncated: (tasks || []).length > MAX_SPACE_NODES }
}

// 同簇相邻节点连线：表达「同技能/同分类」，不暗示交易关系。
export function clusterLinks(nodes) {
  const byCluster = new Map()
  for (const node of nodes) {
    if (!byCluster.has(node.cluster)) byCluster.set(node.cluster, [])
    byCluster.get(node.cluster).push(node)
  }
  const links = []
  for (const members of byCluster.values()) {
    const sorted = [...members].sort((a, b) => a.id - b.id)
    for (let index = 1; index < sorted.length; index += 1) {
      links.push({ from: sorted[index - 1].id, to: sorted[index].id })
    }
  }
  return links
}

export const STATUS_COLORS = {
  published: '#2f7d5c',
  accepted: '#c79a2b',
  awaiting: '#c79a2b',
  completed: '#3b6f9e',
  cancelling: '#b23a3a',
  cancelled: '#89918d',
  expired: '#b23a3a',
}

export function nodeColor(task) {
  return STATUS_COLORS[task?.status] || STATUS_COLORS.published
}
