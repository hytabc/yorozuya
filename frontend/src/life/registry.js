// 虚拟人生内容包注册表（阶段 2/4b）。
// 游戏引擎(useLifeGame)不再直接 import 内容文件，一律经本注册表消费。
// 运行时内容包(Pack)结构:
//   {
//     id: string,                // 唯一标识,如 'wsw-default-life'
//     version: integer >= 1,     // 内容版本,用于存档兼容与迁移
//     npcIds: string[],          // NPC 顺序(唯一)
//     npcs: [{id,name,role,avatar,status,bond}],  // 与 npcIds 一一对应
//     portraits: {npcId: 图片路径},
//     worlds: [{id,name,vibe,color,bg}],   // bg 为空字符串表示无背景图
//     rooms: [{id,worldId,label,private,capacity,occupants}],
//     presence: {npcId: {status,roomId,intro}},
//     actions: [{id,label,reward,threshold,reply}],
//     dialogue: {npcId: {start, nodes:{nodeId:{line, choices:[{label,effects,reply,next}]}}}},
//     initialState: object,      // 全新人生的初始数据(纯 JSON)
//     createInitialState(): object,  // 返回 initialState 的全新深拷贝
//   }
// A 方案:内容由站长配置,全站共享同一活动 Pack;API 拉取失败时回退内置 Pack。
// 对话引擎(4c)直接消费 dialogue 节点图;选项效果文案由 effectText 渲染。

const packs = new Map()
let activeId = null

export class LifePackError extends Error {
  constructor(message) {
    super(message)
    this.name = 'LifePackError'
  }
}

function fail(message) {
  throw new LifePackError('虚拟人生内容包无效: ' + message)
}

export function validateLifePack(pack) {
  if (!pack || typeof pack !== 'object' || Array.isArray(pack)) fail('内容包必须是对象')
  if (typeof pack.id !== 'string' || !pack.id.trim()) fail('缺少 id')
  if (!Number.isInteger(pack.version) || pack.version < 1) fail('version 必须是 >=1 的整数')
  if (!Array.isArray(pack.npcIds) || !pack.npcIds.length) fail('npcIds 不能为空')
  if (new Set(pack.npcIds).size !== pack.npcIds.length) fail('npcIds 存在重复')
  if (!Array.isArray(pack.npcs) || pack.npcs.length !== pack.npcIds.length) fail('npcs 与 npcIds 数量不一致')
  const ids = new Set(pack.npcIds)
  for (const npc of pack.npcs) {
    if (!npc || !ids.has(npc.id)) fail('npcs 包含未声明的 NPC id: ' + (npc && npc.id))
  }
  for (const id of pack.npcIds) {
    if (!pack.portraits || typeof pack.portraits[id] !== 'string') fail('NPC 缺少立绘: ' + id)
  }
  if (!Array.isArray(pack.worlds) || !pack.worlds.length) fail('worlds 不能为空')
  const worldIds = new Set()
  for (const world of pack.worlds) {
    if (!world || typeof world.id !== 'string' || !world.id || worldIds.has(world.id)) fail('world id 缺失或重复')
    worldIds.add(world.id)
    if (typeof world.name !== 'string' || !world.name) fail('世界缺少名称: ' + world.id)
  }
  if (!Array.isArray(pack.rooms) || !pack.rooms.length) fail('rooms 不能为空')
  const roomIds = new Set()
  for (const room of pack.rooms) {
    if (!room || typeof room.id !== 'string' || !room.id || roomIds.has(room.id)) fail('room id 缺失或重复')
    roomIds.add(room.id)
    if (!worldIds.has(room.worldId)) fail('房间指向未知世界: ' + room.id)
  }
  if (!pack.presence || typeof pack.presence !== 'object') fail('缺少 presence')
  for (const id of pack.npcIds) {
    const p = pack.presence[id]
    if (!p || typeof p.status !== 'string') fail('NPC 缺少在线状态: ' + id)
    if (p.roomId != null && !roomIds.has(p.roomId)) fail('NPC 指向未知房间: ' + id)
  }
  if (!Array.isArray(pack.actions) || !pack.actions.length) fail('actions 不能为空')
  const actionIds = new Set()
  for (const action of pack.actions) {
    if (!action || typeof action.id !== 'string' || !action.id || actionIds.has(action.id)) fail('action id 缺失或重复')
    actionIds.add(action.id)
    if (typeof action.label !== 'string' || !action.label) fail('动作缺少名称: ' + action.id)
  }
  if (!pack.dialogue || typeof pack.dialogue !== 'object') fail('缺少 dialogue')
  for (const id of pack.npcIds) {
    const script = pack.dialogue[id]
    if (!script || !script.nodes || typeof script.nodes !== 'object' || !Object.keys(script.nodes).length) fail('NPC 缺少剧本节点: ' + id)
    if (!script.nodes[script.start]) fail('NPC 剧本起点无效: ' + id)
    for (const [nodeId, node] of Object.entries(script.nodes)) {
      if (typeof node.line !== 'string' || !node.line) fail(`节点缺少台词: ${id}/${nodeId}`)
      if (!Array.isArray(node.choices) || !node.choices.length) fail(`节点缺少选项: ${id}/${nodeId}`)
      for (const choice of node.choices) {
        if (typeof choice.label !== 'string' || !choice.label) fail(`节点存在无文案选项: ${id}/${nodeId}`)
        if (typeof choice.reply !== 'string' || !choice.reply) fail(`节点存在无回复选项: ${id}/${nodeId}`)
        if (choice.next != null && !script.nodes[choice.next]) fail(`选项跳转到未知节点: ${id}/${nodeId}`)
      }
    }
  }
  if (!pack.initialState || typeof pack.initialState !== 'object') fail('缺少 initialState')
  if (!Number.isInteger(pack.initialState.day) || pack.initialState.day < 1) fail('initialState.day 无效')
  if (!pack.initialState.stats || typeof pack.initialState.stats !== 'object') fail('initialState.stats 缺失')
  if (typeof pack.createInitialState !== 'function') fail('缺少 createInitialState()')
  return true
}

export function registerLifePack(pack, { active = true } = {}) {
  validateLifePack(pack)
  packs.set(pack.id, pack)
  if (active || !activeId) activeId = pack.id
  return pack
}

export function setActiveLifePack(id) {
  if (!packs.has(id)) throw new LifePackError('未注册的虚拟人生内容包: ' + id)
  activeId = id
}

export function getActiveLifePack() {
  const pack = activeId && packs.get(activeId)
  if (!pack) throw new LifePackError('尚未注册任何虚拟人生内容包')
  return pack
}

export function listLifePacks() {
  return [...packs.values()].map(pack => ({ id: pack.id, version: pack.version, active: pack.id === activeId }))
}

export function portraitFor(npcId) {
  return getActiveLifePack().portraits[npcId]
}

// ==== 从原始 JSON 内容构建运行时 Pack(阶段 4b) ====
// content 与后端 validate_pack_content 同构;对话引擎直接消费节点图,
// createInitialState 深拷贝 initialState。

export const LIFE_STAT_LABELS = { mood: '心情', energy: '精力', social: '社交', explore: '探索' }

export function effectText(effects = {}) {
  const parts = []
  if (effects.bond) parts.push(`好感 +${effects.bond}`)
  for (const [key, value] of Object.entries(effects.stats || {})) {
    if (value) parts.push(`${LIFE_STAT_LABELS[key] || key} ${value > 0 ? '+' : ''}${value}`)
  }
  return parts.join(' · ')
}

export function createLifePackFromContent({ id, version, content }) {
  if (!content || typeof content !== 'object') fail('缺少 content')
  const initial = content.initialState
  const pack = {
    id,
    version,
    npcIds: content.npcIds,
    npcs: content.npcs,
    portraits: content.portraits,
    worlds: content.worlds,
    rooms: content.rooms,
    presence: content.presence,
    actions: content.actions,
    dialogue: content.dialogue,
    initialState: initial,
    createInitialState() {
      return JSON.parse(JSON.stringify(initial))
    },
  }
  validateLifePack(pack)
  return pack
}

// 仅供测试隔离使用。
export function _resetLifeRegistry() {
  packs.clear()
  activeId = null
}
