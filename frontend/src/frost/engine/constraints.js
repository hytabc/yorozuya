/**
 * 约束匹配器
 * 移植自 vrcWill/src/lib/engine/constraints.ts（纯函数，零依赖）。
 */

/** 取碎片在链中的下标；不存在返回 -1 */
export function indexOfFragment(chain, id) {
  return chain.indexOf(id)
}

/** 链中是否包含该碎片 */
export function hasFragment(chain, id) {
  return chain.indexOf(id) >= 0
}

/**
 * 判断一组碎片是否占据"连续区间"（内部顺序任意）。
 */
export function isContiguousGroup(chain, frags) {
  if (frags.length === 0) return false
  if (frags.length === 1) return hasFragment(chain, frags[0])
  const idxs = []
  for (const f of frags) {
    const i = chain.indexOf(f)
    if (i < 0) return false
    idxs.push(i)
  }
  const min = Math.min(...idxs)
  const max = Math.max(...idxs)
  return max - min + 1 === frags.length
}

/** 单条约束是否被满足。 */
export function matchConstraint(chain, c) {
  switch (c.kind) {
    case 'before': {
      if (!c.a || !c.b) return false
      const ia = chain.indexOf(c.a)
      const ib = chain.indexOf(c.b)
      if (ia < 0 || ib < 0) return false
      return ia < ib
    }
    case 'adjacent': {
      if (!c.a || !c.b) return false
      const ia = chain.indexOf(c.a)
      const ib = chain.indexOf(c.b)
      if (ia < 0 || ib < 0) return false
      return Math.abs(ia - ib) === 1
    }
    case 'position': {
      if (!c.frag || typeof c.index !== 'number') return false
      const i = chain.indexOf(c.frag)
      if (i < 0) return false
      return i === c.index
    }
    case 'block': {
      if (!c.a || !c.b) return false
      const ia = chain.indexOf(c.a)
      const ib = chain.indexOf(c.b)
      if (ia < 0 || ib < 0) return false
      return Math.abs(ia - ib) === 1
    }
    case 'group': {
      if (!c.frags || c.frags.length === 0) return false
      return isContiguousGroup(chain, c.frags)
    }
    default:
      return false
  }
}

/** 一组约束的总权重（用于归一化） */
export function sumWeights(constraints) {
  let s = 0
  for (const c of constraints) s += c.weight
  return s
}

/** 批量评估约束，返回总分与逐条轨迹。 */
export function evaluateConstraints(chain, constraints, sign) {
  let score = 0
  const trace = []
  for (const c of constraints) {
    const matched = matchConstraint(chain, c)
    const delta = matched ? sign * c.weight : 0
    score += delta
    trace.push({ constraint: c, matched, delta })
  }
  return { score, trace }
}

/** 校验一条链是否"结构合法"。 */
export function validateChain(chain, level, expectedIds) {
  const errors = []
  if (chain.length !== expectedIds.length) {
    errors.push(`链长度 ${chain.length} ≠ 期望 ${expectedIds.length}`)
  }
  const set = new Set(chain)
  if (set.size !== chain.length) errors.push('链中存在重复碎片')
  for (const id of expectedIds) {
    if (!set.has(id)) errors.push(`缺少碎片 ${id}`)
  }
  for (const id of chain) {
    if (!expectedIds.includes(id)) errors.push(`出现未知碎片 ${id}`)
  }
  if (chain[0] !== level.anchors.first) {
    errors.push(`首位应为锚点 ${level.anchors.first}，实际 ${chain[0]}`)
  }
  if (chain[chain.length - 1] !== level.anchors.last) {
    errors.push(`末位应为锚点 ${level.anchors.last}，实际 ${chain[chain.length - 1]}`)
  }
  return errors
}

/** 由"锚点 + 可动碎片顺序"装配出完整链 */
export function assembleChain(first, movable, last) {
  return [first, ...movable, last]
}
