// 虚拟人生内容管理（/life-admin，阶段 4d）数据层。
// 模块级单例状态:外壳与五个编辑区块共享同一份可编辑 content;
// 保存时整体 PUT,后端 validate_pack_content 把关引用一致性。
import { reactive, watch, nextTick } from 'vue'
import axios from 'axios'

const ownerToken = localStorage.getItem('wsw_token')
const api = axios.create({
  baseURL: '/api', timeout: 20000,
  headers: { Authorization: `Bearer ${ownerToken}` },
})

export const adminState = reactive({
  packs: [],        // 摘要列表 [{id,name,version,active,updatedAt}]
  selectedId: '',
  detail: null,     // 当前编辑包 {id,name,version,active,updatedAt}
  content: null,    // 可编辑内容(直接双向绑定)
  dirty: false,
  saving: false,
  loading: false,
  error: '',
  toast: '',
  section: 'npcs',
})

let toastTimer
export function showAdminToast(msg) {
  adminState.toast = msg
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => { adminState.toast = '' }, 2500)
}

watch(() => adminState.content, () => { adminState.dirty = true }, { deep: true })

function errText(e) {
  const detail = e.response?.data?.detail
  return (typeof detail === 'string' ? detail : null) || e.message
}

export async function loadPacks({ keepSelection = true } = {}) {
  adminState.loading = true
  adminState.error = ''
  try {
    const { data } = await api.get('/virtual-life/packs')
    adminState.packs = data
    const current = keepSelection && data.find(p => p.id === adminState.selectedId)
    await selectPack((current || data.find(p => p.active) || data[0])?.id || '')
  } catch (e) {
    adminState.error = '读取内容包列表失败：' + errText(e)
  } finally {
    adminState.loading = false
  }
}

export async function selectPack(id) {
  if (!id) { adminState.selectedId = ''; adminState.detail = null; adminState.content = null; return }
  adminState.error = ''
  try {
    const { data } = await api.get(`/virtual-life/packs/${id}`)
    adminState.selectedId = data.id
    adminState.detail = { id: data.id, name: data.name, version: data.version, active: data.active, updatedAt: data.updatedAt }
    adminState.content = normalizeContent(data.content)
    // 赋值本身会触发 dirty 侦听器(pre-flush 在下一 tick 才执行),等它跑完再复位。
    await nextTick()
    adminState.dirty = false
  } catch (e) {
    adminState.error = '读取内容包失败：' + errText(e)
  }
}

// 补齐可选字段(effects/stats),并把剧本统一成 7 天数组(不足复制最后一天),
// 让编辑表单可以直接双向绑定;兼容旧单剧本形状。
export const LIFE_DIALOGUE_DAYS = 7

function normalizeContent(content) {
  for (const [npcId, days] of Object.entries(content.dialogue || {})) {
    const list = (Array.isArray(days) ? days : [days]).filter(Boolean)
    if (!list.length) list.push({ start: 'n1', nodes: { n1: { line: '……', choices: [{ label: '你好', effects: {}, reply: '你好呀。', next: null }] } } })
    while (list.length < LIFE_DIALOGUE_DAYS) list.push(JSON.parse(JSON.stringify(list[list.length - 1])))
    content.dialogue[npcId] = list.slice(0, LIFE_DIALOGUE_DAYS)
    for (const script of content.dialogue[npcId]) {
      for (const node of Object.values(script.nodes || {})) {
        for (const choice of node.choices || []) {
          if (!choice.effects || typeof choice.effects !== 'object') choice.effects = {}
          if (!choice.effects.stats || typeof choice.effects.stats !== 'object') choice.effects.stats = {}
          if (choice.next === undefined) choice.next = null
        }
      }
    }
  }
  return content
}

export async function savePack() {
  if (!adminState.detail || adminState.saving) return false
  adminState.saving = true
  adminState.error = ''
  try {
    const { data } = await api.put(`/virtual-life/packs/${adminState.detail.id}`, {
      name: adminState.detail.name,
      content: adminState.content,
    })
    adminState.detail = { id: data.id, name: data.name, version: data.version, active: data.active, updatedAt: data.updatedAt }
    adminState.content = data.content
    await nextTick()
    adminState.dirty = false
    const summary = adminState.packs.find(p => p.id === data.id)
    if (summary) { summary.name = data.name; summary.version = data.version; summary.updatedAt = data.updatedAt }
    showAdminToast(`已保存 · 版本 ${data.version}${data.active ? ' · 玩家端立即生效' : ''}`)
    return true
  } catch (e) {
    adminState.error = '保存失败：' + errText(e)
    return false
  } finally {
    adminState.saving = false
  }
}

export async function activatePack(id) {
  adminState.error = ''
  try {
    await api.post(`/virtual-life/packs/${id}/activate`)
    await loadPacks()
    showAdminToast('已激活为全站内容包，玩家端与存档校验立即生效')
  } catch (e) {
    adminState.error = '激活失败：' + errText(e)
  }
}

export async function duplicatePack(id) {
  const source = adminState.packs.find(p => p.id === id)
  const newId = window.prompt('新内容包 id（小写字母/数字/连字符）：', `${id}-copy`)
  if (!newId) return
  const newName = window.prompt('新内容包名称：', `${source?.name || id} 副本`)
  if (!newName) return
  adminState.error = ''
  try {
    const { data } = await api.post(`/virtual-life/packs/${id}/duplicate`, { id: newId.trim(), name: newName.trim() })
    await loadPacks()
    await selectPack(data.id)
    showAdminToast('已创建副本，正在编辑副本内容')
  } catch (e) {
    adminState.error = '复制失败：' + errText(e)
  }
}

export async function deletePack(id) {
  if (!window.confirm(`确定删除内容包「${id}」？此操作不可恢复。`)) return
  adminState.error = ''
  try {
    await api.delete(`/virtual-life/packs/${id}`)
    if (adminState.selectedId === id) adminState.selectedId = ''
    await loadPacks({ keepSelection: false })
    showAdminToast('内容包已删除')
  } catch (e) {
    adminState.error = '删除失败：' + errText(e)
  }
}

// 上传一张图片(世界背景/立绘),返回可写入包内容的 URL。
export async function uploadAsset(file) {
  const form = new FormData()
  form.append('file', file)
  const { data } = await api.post('/virtual-life/assets', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data.url
}

// ==== 内容编辑辅助(各区块共用) ====

export function npcById(id) {
  return adminState.content?.npcs.find(n => n.id === id)
}

// 新增 NPC:同步补齐 portraits/presence/dialogue(7 天)/initialState.conversations。
export function addNpc(id, name) {
  const c = adminState.content
  if (!c || !id || c.npcIds.includes(id)) return 'id 为空或已存在'
  const defaultScript = () => ({ start: 'n1', nodes: { n1: { line: '……', choices: [{ label: '你好', effects: { stats: {} }, reply: '你好呀。', next: null }] } } })
  c.npcIds.push(id)
  c.npcs.push({ id, name: name || id, role: '', avatar: '✨', status: '', bond: 0 })
  c.portraits[id] = ''
  c.presence[id] = { status: 'offline', roomId: null, intro: '' }
  c.dialogue[id] = Array.from({ length: LIFE_DIALOGUE_DAYS }, defaultScript)
  c.initialState.conversations[id] = [{ from: 'npc', text: '……', day: c.initialState.day, time: '18:20' }]
  return ''
}

// 删除 NPC:清理全部引用;至少保留一个。
export function removeNpc(id) {
  const c = adminState.content
  if (!c || c.npcIds.length <= 1) return '至少保留一个人物'
  c.npcIds = c.npcIds.filter(x => x !== id)
  c.npcs = c.npcs.filter(n => n.id !== id)
  delete c.portraits[id]
  delete c.presence[id]
  delete c.dialogue[id]
  delete c.initialState.conversations[id]
  return ''
}

export function addWorld(id, name) {
  const c = adminState.content
  if (!c || !id || c.worlds.some(w => w.id === id)) return 'id 为空或已存在'
  c.worlds.push({ id, name: name || id, vibe: '', color: '#3f7777', bg: '' })
  return ''
}

// 删除世界:级联删除其房间,指向这些房间的在场状态置为离线。
export function removeWorld(id) {
  const c = adminState.content
  if (!c || c.worlds.length <= 1) return '至少保留一个世界'
  const roomIds = new Set(c.rooms.filter(r => r.worldId === id).map(r => r.id))
  c.worlds = c.worlds.filter(w => w.id !== id)
  c.rooms = c.rooms.filter(r => !roomIds.has(r.id))
  for (const p of Object.values(c.presence)) {
    if (roomIds.has(p.roomId)) { p.roomId = null; p.status = 'offline' }
  }
  return ''
}

export function addRoom(id, worldId, label) {
  const c = adminState.content
  if (!c || !id || c.rooms.some(r => r.id === id)) return 'id 为空或已存在'
  c.rooms.push({ id, worldId, label: label || id, private: false, capacity: 16, occupants: 1 })
  return ''
}

export function removeRoom(id) {
  const c = adminState.content
  if (!c) return ''
  c.rooms = c.rooms.filter(r => r.id !== id)
  for (const p of Object.values(c.presence)) {
    if (p.roomId === id) { p.roomId = null; p.status = 'offline' }
  }
  return ''
}

// 剧本节点操作(作用于传入的某天剧本)
// 注意:新建节点的 effects 必须带 stats: {},否则编辑表单的 v-model 绑定会在渲染时炸掉。
export function addDialogueNode(script) {
  if (!script) return ''
  let i = Object.keys(script.nodes).length + 1
  while (script.nodes[`n${i}`]) i += 1
  script.nodes[`n${i}`] = { line: '……', choices: [{ label: '继续', effects: { stats: {} }, reply: '……', next: null }] }
  return `n${i}`
}

// 删除节点:指向它的选项改为当天结束;删的是起点则把起点让给剩余的第一个节点;
// 只剩最后一个节点时不允许删(当天剧本至少要有一句台词)。
export function removeDialogueNode(script, nodeId) {
  if (!script || !script.nodes[nodeId]) return '节点不存在'
  const remaining = Object.keys(script.nodes).filter(id => id !== nodeId)
  if (!remaining.length) return '至少保留一个节点'
  delete script.nodes[nodeId]
  if (script.start === nodeId) script.start = remaining[0]
  for (const node of Object.values(script.nodes)) {
    for (const choice of node.choices) {
      if (choice.next === nodeId) choice.next = null
    }
  }
  return ''
}
