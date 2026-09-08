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
//     events: [{id,roomId,title,icon,scripts}], // 每个事件恰好 7 天,含消息组与选项点
//     presence: {npcId: {status,roomId,intro}},
//     actions: [{id,label,reward,threshold,reply}],
//     dialogue: {npcId: [dayScript, ...]},  // 1-7 天,超出天数沿用最后一天(不循环)
//       dayScript = {start, nodes:{nodeId:{lines:[...], image, choices:[{label,effects,replies:[...],replyImage,next}]}}}
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

// 事件与后端校验保持一致:消息组和选项点互斥,回复禁止嵌套选项点。
function isEventObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function validateEventMessage(message, npcIds, where) {
  if (!isEventObject(message)) fail(`${where} 消息组必须是对象`)
  if (Object.hasOwn(message, 'choice')) fail(`${where} 消息组禁止嵌套选项点 choice`)
  const speaker = message.speaker
  if (!isEventObject(speaker) || Object.hasOwn(speaker, 'npcId') === Object.hasOwn(speaker, 'name')) fail(`${where} speaker 必须恰好指定 npcId 或 name`)
  if (Object.keys(speaker).some(key => !['npcId', 'name', 'avatar'].includes(key))) fail(`${where} speaker 包含未知字段`)
  if (Object.hasOwn(speaker, 'npcId') && (typeof speaker.npcId !== 'string' || !npcIds.has(speaker.npcId))) fail(`${where} speaker 指向未知 NPC`)
  if (Object.hasOwn(speaker, 'name') && (typeof speaker.name !== 'string' || !speaker.name)) fail(`${where} speaker 缺少名字`)
  // 后端 avatar 仅限制类型,不限制路径或要求非空。
  if (Object.hasOwn(speaker, 'avatar') && typeof speaker.avatar !== 'string') fail(`${where} speaker avatar 必须是字符串`)
  if (!Array.isArray(message.lines) || !message.lines.length || message.lines.some(line => typeof line !== 'string' || !line)) fail(`${where} 台词必须是非空句子数组`)
  if (message.image != null && (typeof message.image !== 'string' || !message.image.startsWith('/uploads/'))) fail(`${where} 图片必须是 /uploads/ 站内路径`)
}

function validateEvents(events, roomIds, npcIds) {
  if (!Array.isArray(events)) fail('events 必须是数组')
  const eventIds = new Set()
  for (const event of events) {
    if (!isEventObject(event)) fail('event 必须是对象')
    if (typeof event.id !== 'string' || !event.id || eventIds.has(event.id)) fail('event id 缺失或重复')
    eventIds.add(event.id)
    if (typeof event.roomId !== 'string' || !roomIds.has(event.roomId)) fail(`事件 ${event.id} 指向未知房间`)
    for (const key of ['title', 'icon']) {
      if (typeof event[key] !== 'string' || !event[key]) fail(`事件 ${event.id} 的 ${key} 必须是非空字符串`)
    }
    if (!Array.isArray(event.scripts) || event.scripts.length !== 7) fail(`事件 ${event.id} 的 scripts 必须恰好 7 份`)
    for (let d = 0; d < event.scripts.length; d++) {
      const script = event.scripts[d]
      const where = `事件 ${event.id}/第${d + 1}天`
      if (!isEventObject(script) || !Array.isArray(script.messages) || !script.messages.length) fail(`${where} messages 必须是非空数组`)
      for (const message of script.messages) {
        if (!isEventObject(message) || !Object.hasOwn(message, 'choice')) {
          validateEventMessage(message, npcIds, where)
          continue
        }
        if (Object.keys(message).length !== 1) fail(`${where} 选项点与消息组必须二选一`)
        const choice = message.choice
        if (!isEventObject(choice) || !Array.isArray(choice.options) || !choice.options.length) fail(`${where} options 必须是非空数组`)
        for (const option of choice.options) {
          if (!isEventObject(option) || typeof option.label !== 'string' || !option.label) fail(`${where} 存在无文案选项`)
          const effects = Object.hasOwn(option, 'effects') ? option.effects : {}
          if (!isEventObject(effects)) fail(`${where} 选项 effects 必须是对象`)
          if (Object.keys(effects).some(key => !['stats', 'bond'].includes(key))) fail(`${where} 选项 effects 只允许 stats,bond,禁止其他键`)
          const stats = Object.hasOwn(effects, 'stats') ? effects.stats : {}
          if (!isEventObject(stats) || Object.keys(stats).some(key => !Object.hasOwn(LIFE_STAT_LABELS, key))) fail(`${where} 选项包含未知属性`)
          if (Object.values(stats).some(value => !Number.isInteger(value) || value < -100 || value > 100)) fail(`${where} 选项属性变化无效`)
          if (Object.hasOwn(effects, 'bond')) {
            const bond = effects.bond
            if (!isEventObject(bond) || Object.keys(bond).length !== 2 || !Object.hasOwn(bond, 'npcId') || !Object.hasOwn(bond, 'value')) fail(`${where} 选项 bond 必须是恰好包含 npcId,value 的对象`)
            if (typeof bond.npcId !== 'string' || !npcIds.has(bond.npcId)) fail(`${where} 选项 bond 指向未知 NPC`)
            if (!Number.isInteger(bond.value) || bond.value < -100 || bond.value > 100) fail(`${where} 选项 bond value 必须是 -100..100 的整数`)
          }
          if (!Array.isArray(option.reply) || !option.reply.length) fail(`${where} reply 必须是非空消息组数组`)
          for (const replyMessage of option.reply) validateEventMessage(replyMessage, npcIds, `${where}/回复`)
        }
      }
    }
  }
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
  // 旧内容包缺省事件视为空数组,显式 null 仍是非法结构。
  validateEvents(pack.events === undefined ? [] : pack.events, roomIds, ids)
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
    const days = pack.dialogue[id]
    if (!Array.isArray(days) || !days.length || days.length > 7) fail('NPC 剧本必须是 1-7 天的数组: ' + id)
    for (let d = 0; d < days.length; d++) {
      const script = days[d]
      const where = `${id}/第${d + 1}天`
      if (!script || !script.nodes || typeof script.nodes !== 'object' || !Object.keys(script.nodes).length) fail('剧本没有节点: ' + where)
      if (!script.nodes[script.start]) fail('剧本起点无效: ' + where)
      for (const [nodeId, node] of Object.entries(script.nodes)) {
        if (!Array.isArray(node.lines) || !node.lines.length || node.lines.some(l => typeof l !== 'string' || !l)) fail(`节点台词必须是句子数组: ${where}/${nodeId}`)
        if (node.image != null && (typeof node.image !== 'string' || !node.image.startsWith('/uploads/'))) fail(`节点图片必须是站内路径: ${where}/${nodeId}`)
        if (!Array.isArray(node.choices) || !node.choices.length) fail(`节点缺少选项: ${where}/${nodeId}`)
        for (const choice of node.choices) {
          if (typeof choice.label !== 'string' || !choice.label) fail(`节点存在无文案选项: ${where}/${nodeId}`)
          if (!Array.isArray(choice.replies) || !choice.replies.length || choice.replies.some(r => typeof r !== 'string' || !r)) fail(`节点存在无回复选项: ${where}/${nodeId}`)
          if (choice.replyImage != null && (typeof choice.replyImage !== 'string' || !choice.replyImage.startsWith('/uploads/'))) fail(`回复图片必须是站内路径: ${where}/${nodeId}`)
          if (choice.next != null && !script.nodes[choice.next]) fail(`选项跳转到未知节点: ${where}/${nodeId}`)
        }
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
    events: content.events || [],
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
