// 委托模块化标签的纯逻辑：组件与测试共用，不依赖 Vue。
import { FACET_LIMITS, FACET_LABELS } from './constants.js'

export { FACET_LIMITS, FACET_LABELS }

const FILTER_KEYS = ['skill', 'platform', 'world', 'atmosphere']

export function facetsOfType(facets, type) {
  return (facets || [])
    .filter((item) => item && item.facet_type === type)
    .map((item) => item.value)
}

// 多选切换：已在列表里则移除；达到上限时不再追加，而不是静默替换。
export function toggleFacet(list, value, max) {
  const current = Array.isArray(list) ? [...list] : []
  const index = current.indexOf(value)
  if (index >= 0) {
    current.splice(index, 1)
    return current
  }
  if (max != null && current.length >= max) return current
  current.push(value)
  return current
}

// 单选切换（氛围按维度互斥）：点已选中的项即清空该维度。
export function pickSingle(list, value) {
  const current = Array.isArray(list) ? list : []
  return current.includes(value) ? [] : [value]
}

// 只把非空的标签条件放进查询参数，避免出现 skill= 之类的空筛选。
export function facetQueryParams(filters) {
  const params = {}
  for (const key of FILTER_KEYS) {
    const value = filters?.[key]
    if (typeof value === 'string' && value) params[key] = value
  }
  return params
}

// 详情页按类型分组展示；空组不渲染。
export function facetGroups(facets) {
  const groups = []
  for (const key of FILTER_KEYS) {
    const values = facetsOfType(facets, key)
    if (values.length) groups.push({ key, label: FACET_LABELS[key], values })
  }
  return groups
}

// 卡片只展示 3 个技能与 1 个平台，其余折叠为 “+N”。
export function cardFacets(facets) {
  const skills = facetsOfType(facets, 'skill')
  const platforms = facetsOfType(facets, 'platform')
  return {
    platform: platforms[0] || '',
    skills: skills.slice(0, 3),
    moreSkills: Math.max(0, skills.length - 3),
  }
}

// 创建/编辑时把各类型的选中值拼成后端需要的 facets 数组。
export function buildFacets({ skills = [], platforms = [], worlds = [], atmosphere = [] }) {
  return [
    ...skills.map((value) => ({ facet_type: 'skill', value })),
    ...platforms.map((value) => ({ facet_type: 'platform', value })),
    ...atmosphere.map((value) => ({ facet_type: 'atmosphere', value })),
    ...worlds.map((value) => ({ facet_type: 'world', value })),
  ]
}
