// Logical coordinates: x/y on the floor; z is height. No rendering dependencies.
export const clone = (value) => JSON.parse(JSON.stringify(value))
export const blankRoom = () => ({ schemaVersion: 1, name: '我的小屋', placements: [], floor: { color: '#eee5d5', textureId: null, mode: 'repeat' }, wall: { color: '#f2eee5', textureId: null, mode: 'repeat' } })

export function normalizedVoxels(data, rotation = 0) {
  const points = data.voxels.map(([x, y, z, c]) => rotation === 90 ? [-y, x, z, c] : rotation === 180 ? [-x, -y, z, c] : rotation === 270 ? [y, -x, z, c] : [x, y, z, c])
  if (!points.length) return []
  const low = [Infinity, Infinity, Infinity]
  for (const p of points) for (let a = 0; a < 3; a++) low[a] = Math.min(low[a], p[a])
  return points.map(([x, y, z, c]) => [x - low[0], y - low[1], z - low[2], c])
}

export function bounds(data, rotation = 0) {
  const size = [0, 0, 0]
  for (const p of normalizedVoxels(data, rotation)) for (let a = 0; a < 3; a++) size[a] = Math.max(size[a], p[a] + 1)
  return size
}

export function placementError(room, assets) {
  if (room.placements.length > 128) return '最多放置128件家具'
  const occupied = new Set(), ids = new Set()
  let count = 0
  for (const p of room.placements) {
    if (ids.has(p.id)) return '家具编号重复'
    ids.add(p.id)
    const data = assets[p.versionId]?.data
    if (!data) return '家具版本尚未加载'
    if (![0, 90, 180, 270].includes(p.rotation)) return '朝向无效'
    if (![p.position.x, p.position.y, p.position.z].every(Number.isInteger)) return '位置必须是整数'
    count += data.voxels.length
    if (count > 1000000) return '房间累计体素超过100万'
    for (const [x, y, z] of normalizedVoxels(data, p.rotation)) {
      const q = [x + p.position.x, y + p.position.y, z + p.position.z]
      if (q.some((a, i) => a < 0 || a >= [256, 256, 128][i])) return '家具超出房间边界'
      const key = q.join(',')
      if (occupied.has(key)) return '家具之间不能重叠'
      occupied.add(key)
    }
  }
  return ''
}

export function validateVoxelData(data) {
  if (!data || ![16, 32, 64].includes(data.gridSize)) throw new Error('网格尺寸应为16、32或64')
  if (!['floor', 'surface', 'wall', 'ceiling'].includes(data.mount)) throw new Error('摆放方式无效')
  if (!Array.isArray(data.palette) || !data.palette.length || data.palette.length > 256) throw new Error('色板无效')
  const keys = new Set()
  for (const slot of data.palette) {
    if (!/^[a-z][a-z0-9_-]{0,31}$/.test(slot.key) || keys.has(slot.key) || !/^#[\da-f]{6}$/i.test(slot.color) || typeof slot.editable !== 'boolean' || !slot.label || slot.label.length > 32) throw new Error('改色部位无效')
    keys.add(slot.key)
  }
  if (!Array.isArray(data.voxels) || data.voxels.length < 1 || data.voxels.length > data.gridSize ** 3) throw new Error('体素数量无效')
  const occupied = new Set()
  for (const p of data.voxels) {
    if (!Array.isArray(p) || p.length !== 4 || !p.every(Number.isInteger) || p.slice(0, 3).some((a) => a < 0 || a >= data.gridSize) || p[3] < 0 || p[3] >= data.palette.length) throw new Error('体素坐标或色板索引无效')
    const key = p.slice(0, 3).join(',')
    if (occupied.has(key)) throw new Error('体素坐标重复')
    occupied.add(key)
  }
  return data
}

export function editVoxels(data, point, mode, color, mirrors = []) {
  const copy = clone(data), cells = new Map(copy.voxels.map((p) => [p.slice(0, 3).join(','), p]))
  let points = [point.slice(0, 3)]
  for (const axis of mirrors) points = [...points, ...points.map((p) => p.map((n, i) => i === axis ? data.gridSize - 1 - n : n))]
  for (const p of points) {
    if (p.some((n) => n < 0 || n >= data.gridSize)) continue
    const key = p.join(',')
    if (mode === 'delete') cells.delete(key)
    else if (mode === 'add' || cells.has(key)) cells.set(key, [...p, color])
  }
  copy.voxels = [...cells.values()]
  return copy
}

export function recoloredData(data, overrides = {}) {
  const copy = clone(data)
  copy.palette = copy.palette.map((s) => ({ ...s, color: s.editable && overrides[s.key] || s.color }))
  return copy
}

export function anchorPosition(data, target, rotation = 0) {
  const size = bounds(data, rotation)
  const position = { x: Math.round(target.x - size[0] / 2), y: Math.round(target.y - size[1] / 2), z: Math.round(target.z || 0) }
  if (data.mount === 'ceiling') position.z = 128 - size[2]
  if (data.mount === 'wall') { position.y = 256 - size[1]; position.z = Math.min(128 - size[2], Math.max(28, position.z)) }
  for (const [i, a] of ['x', 'y', 'z'].entries()) position[a] = Math.max(0, Math.min([256, 256, 128][i] - size[i], position[a]))
  return position
}

export function createHistory(limit = 30, byteBudget = 24 * 1024 * 1024) {
  const past = [], future = []
  // Strings avoid retaining hundreds of thousands of nested arrays for each
  // undo step in a dense 64³ model. Keep the nearest undo/redo even if oversized.
  const encode = (state) => JSON.stringify(state)
  function trim() {
    const bytes = () => [...past, ...future].reduce((sum, item) => sum + item.length * 2, 0)
    while (bytes() > byteBudget && (past.length > 1 || future.length > 1)) {
      if (past.length > 1) past.shift(); else future.shift()
    }
  }
  return {
    push(state) { past.push(encode(state)); if (past.length > limit) past.shift(); future.length = 0; trim() },
    undo(state) { if (!past.length) return null; future.push(encode(state)); const next = JSON.parse(past.pop()); trim(); return next },
    redo(state) { if (!future.length) return null; past.push(encode(state)); const next = JSON.parse(future.pop()); trim(); return next },
    clear() { past.length = 0; future.length = 0 },
  }
}
