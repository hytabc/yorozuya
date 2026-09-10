/**
 * 《糖霜世界》关卡数据穷举校验器（移植自 vrcWill/tools/verify-levels.ts）
 * 用法：node frontend/scripts/verify-frost.mjs [关卡ID...]
 *
 * 穷举每关全部合法排列，断言：
 *   - 数据自洽（ID 唯一、锚点 gray、约束引用存在、阈值不超上限、各结局满分一致）
 *   - 每个设计结局至少被一种排列命中（可达性）
 * 退出码：0 = 全部通过；1 = 存在错误。
 */
import { readFileSync, readdirSync, existsSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

import { judgeChain } from '../src/frost/engine/judge.js'
import { sumWeights } from '../src/frost/engine/constraints.js'

const HERE = dirname(fileURLToPath(import.meta.url))
const LEVELS_DIR = join(HERE, '..', 'src', 'frost', 'data', 'levels')

function permutations(arr) {
  if (arr.length <= 1) return [arr.slice()]
  const out = []
  for (let i = 0; i < arr.length; i++) {
    const rest = arr.slice(0, i).concat(arr.slice(i + 1))
    for (const p of permutations(rest)) out.push([arr[i], ...p])
  }
  return out
}

function validateLevel(level) {
  const errors = []
  const ids = level.fragments.map((f) => f.id)

  if (new Set(ids).size !== ids.length) errors.push('存在重复的碎片 ID')

  for (const key of ['first', 'last']) {
    const id = level.anchors[key]
    const frag = level.fragments.find((f) => f.id === id)
    if (!frag) errors.push(`锚点 ${key}=${id} 不存在`)
    else if (frag.type !== 'gray') errors.push(`锚点 ${id} 的类型应为 gray，实际为 ${frag.type}`)
  }

  const order = level.initialOrder
  if (order[0] !== level.anchors.first) errors.push('initialOrder 首位不是 anchors.first')
  if (order[order.length - 1] !== level.anchors.last) errors.push('initialOrder 末位不是 anchors.last')
  if (new Set(order).size !== order.length) errors.push('initialOrder 存在重复')
  for (const id of order) if (!ids.includes(id)) errors.push(`initialOrder 含未知碎片 ${id}`)

  const allEndings = [...level.endings, level.chaosEnding]
  for (const e of allEndings) {
    for (const c of [...e.constraints, ...e.anti]) {
      const refs = [c.a, c.b, c.frag, ...(c.frags ?? [])].filter(Boolean)
      if (refs.length === 0) errors.push(`结局 ${e.id} 存在空约束`)
      for (const r of refs) {
        if (!ids.includes(r)) errors.push(`结局 ${e.id} 引用了不存在的碎片 ${r}`)
      }
      if (c.kind === 'position' && typeof c.index !== 'number') {
        errors.push(`结局 ${e.id} 的 position 约束缺少 index`)
      }
    }
    if (e.type !== 'chaos' && e.threshold > sumWeights(e.constraints)) {
      errors.push(`结局 ${e.id} 阈值 ${e.threshold} 超过理论上限 ${sumWeights(e.constraints)}`)
    }
  }

  const maxes = level.endings.map((e) => sumWeights(e.constraints))
  if (maxes.length > 0 && new Set(maxes).size > 1) {
    errors.push(`各结局的理论最高分不一致：[${level.endings.map((e) => `${e.id}=${sumWeights(e.constraints)}`).join(', ')}]`)
  }
  if (maxes.length > 0 && maxes[0] !== 100) {
    errors.push(`结局满分应为 100，实际 ${maxes[0]}`)
  }

  return errors
}

function verifyLevel(level) {
  const errors = validateLevel(level)
  const baseMovable = level.initialOrder.slice(1, -1)
  const baseSet = new Set(level.initialOrder)
  const hiddenChainFrags = level.fragments
    .filter((f) => f.hidden && f.type !== 'blue' && !baseSet.has(f.id))
    .map((f) => f.id)

  const configs = [{ label: '基础配置', movable: baseMovable }]
  if (hiddenChainFrags.length > 0) {
    configs.push({ label: `解锁配置(+${hiddenChainFrags.length})`, movable: [...baseMovable, ...hiddenChainFrags] })
  }

  const stats = new Map()
  for (const e of level.endings) stats.set(e.id, { reachable: false, error: false })

  let chaosCount = 0
  let permCount = 0
  for (const cfg of configs) {
    const perms = permutations(cfg.movable)
    permCount = perms.length
    const chainSet = new Set([level.anchors.first, ...cfg.movable, level.anchors.last])
    for (const perm of perms) {
      const chain = [level.anchors.first, ...perm, level.anchors.last]
      const result = judgeChain(chain, level, { unlockedEndingIds: null })
      if (result.isChaos) {
        chaosCount++
        continue
      }
      const st = stats.get(result.ending.id)
      if (!st) continue
      const e = level.endings.find((x) => x.id === result.ending.id)
      const refs = [...e.constraints, ...e.anti].flatMap((c) => [c.a, c.b, c.frag, ...(c.frags ?? [])]).filter(Boolean)
      if (refs.every((r) => chainSet.has(r))) st.reachable = true
    }
  }

  for (const [id, st] of stats) {
    if (!st.reachable) errors.push(`结局 ${id} 不可达`)
  }
  return { errors, chaosCount, permCount }
}

function loadLevels(filter) {
  if (!existsSync(LEVELS_DIR)) {
    console.error(`找不到关卡目录：${LEVELS_DIR}`)
    process.exit(1)
  }
  const files = readdirSync(LEVELS_DIR).filter((f) => f.endsWith('.json') && f !== 'index.json')
  const levels = []
  for (const f of files) {
    const level = JSON.parse(readFileSync(join(LEVELS_DIR, f), 'utf8'))
    if (filter.length > 0 && !filter.includes(level.id)) continue
    levels.push(level)
  }
  levels.sort((a, b) => a.chapter - b.chapter || a.order - b.order)
  return levels
}

const filter = process.argv.slice(2).filter((a) => !a.startsWith('-'))
const levels = loadLevels(filter)
if (levels.length === 0) {
  console.error('没有匹配的关卡。')
  process.exit(1)
}

let hasError = false
for (const level of levels) {
  const { errors, chaosCount, permCount } = verifyLevel(level)
  console.log(`\n━━ ${level.id} ${level.title} ━━`)
  if (errors.length > 0) {
    hasError = true
    for (const e of errors) console.log(`  ✗ ${e}`)
  } else {
    console.log(`  数据自检通过｜排列 ${permCount}｜混沌 ${chaosCount} (${((chaosCount / permCount) * 100).toFixed(1)}%)`)
  }
}

if (hasError) {
  console.log('\n校验未通过。')
  process.exit(1)
}
console.log(`\n全部 ${levels.length} 关校验通过。`)
