// 虚拟人生内容包注册表（阶段 2）。
// 游戏引擎(useLifeGame)不再直接 import 内容文件，一律经本注册表消费。
// 内容包(Pack)结构:
//   {
//     id: string,                // 唯一标识,如 'wsw-default-life'
//     version: integer >= 1,     // 内容版本,用于存档兼容与迁移
//     npcIds: string[],          // NPC 顺序(唯一)
//     npcs: [{id,name,role,avatar,status,bond}],  // 与 npcIds 一一对应
//     portraits: {npcId: 图片路径},
//     dialogueScripts: {npcId: {npcLine, choices[]}},
//     createInitialState(): object,  // 返回全新深拷贝的初始人生数据
//   }
// A 方案:内容由站长配置,全站共享同一活动 Pack;当前仅内置默认 Pack。

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
    const script = pack.dialogueScripts && pack.dialogueScripts[id]
    if (!script || !script.npcLine || typeof script.npcLine.text !== 'string') fail('NPC 缺少剧本开场白: ' + id)
    if (!Array.isArray(script.choices) || !script.choices.length) fail('NPC 缺少对话选项: ' + id)
  }
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

// 仅供测试隔离使用。
export function _resetLifeRegistry() {
  packs.clear()
  activeId = null
}
