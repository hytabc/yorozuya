// Static mock worlds/rooms/presence; not real VRC or shared multiplayer state.
export const WORLDS = [
  { id: 'beach', name: '潮汐之后', vibe: '安静 · 海边拍照', color: '#3f7777' },
  { id: 'cafe', name: '小小咖啡馆', vibe: '轻松 · 咖啡闲聊', color: '#9a7563' },
  { id: 'hall', name: '夜间聚会大厅', vibe: '热闹 · 社交聚会', color: '#576c80' },
]
export const ROOMS = [
  { id: 'beach-1024', worldId: 'beach', label: '#1024', private: false, capacity: 16, occupants: 1 },
  { id: 'beach-2086', worldId: 'beach', label: '#2086', private: false, capacity: 16, occupants: 1 },
  { id: 'beach-empty', worldId: 'beach', label: '#3000', private: false, capacity: 16, occupants: 0 },
  { id: 'cafe-1101', worldId: 'cafe', label: '#1101', private: false, capacity: 12, occupants: 1 },
  { id: 'cafe-private', worldId: 'cafe', label: '#2202', private: true, capacity: 12, occupants: 2 },
  { id: 'hall-1001', worldId: 'hall', label: '#1001', private: false, capacity: 20, occupants: 2 },
  { id: 'hall-full', worldId: 'hall', label: '#2002', private: false, capacity: 4, occupants: 4 },
]
export const MOCK_PRESENCE = {
  ache: { status: 'green', roomId: 'beach-1024', intro: '喜欢记录日落，也喜欢和新朋友一起拍照。' },
  xiaomi: { status: 'green', roomId: 'cafe-1101', intro: '练舞结束后常去咖啡馆休息。' },
  maoyou: { status: 'orange', roomId: 'beach-2086', intro: '正在调试模型，暂时不接受跟随加入。' },
  yu: { status: 'green', roomId: 'hall-1001', intro: '喜欢探索没去过的世界。' },
}
export const STATUS_LABELS = { green: '在线 · 可加入', orange: '请勿加入', red: '忙碌', offline: '离线' }
export const roomFor = id => ROOMS.find(room => room.id === id)
export const worldFor = id => WORLDS.find(world => world.id === id)
export const presenceFor = id => MOCK_PRESENCE[id] || { status: 'offline', roomId: null, intro: '暂无资料' }
export const normalizeWorld = world => world === '潮汐之后 · 黄昏' ? '潮汐之后' : world
export function roomDecision(room) {
  if (!room) return { allowed: false, reason: '房间不可用' }
  if (room.private) return { allowed: false, reason: '私密房间不可加入' }
  if (room.occupants <= 0) return { allowed: false, reason: '空房间不可加入' }
  if (room.occupants >= room.capacity) return { allowed: false, reason: '房间已满' }
  return { allowed: true, roomId: room.id, world: worldFor(room.worldId)?.name, reason: '' }
}
export function joinDecision(presence) {
  if (presence?.status !== 'green') return { allowed: false, reason: ({ orange: '对方暂不接受跟随', red: '对方忙碌，无法跟随', offline: '对方已离线' })[presence?.status] || '当前状态不可加入' }
  return roomDecision(roomFor(presence.roomId))
}
export function planJoin(id) { return { ...joinDecision(presenceFor(id)), dialogueVisible: false } }
export function canInteract(id, roomId) {
  const p = presenceFor(id)
  return Boolean(roomFor(roomId)) && p.status !== 'offline' && p.roomId === roomId
}
export const sceneRoster = (npcs, roomId) => npcs.filter(npc => canInteract(npc.id, roomId))
export function migrateSocialState(state) {
  const legacyWorld = WORLDS.find(w => w.name === normalizeWorld(state.currentWorld))
  const fallback = ROOMS.find(r => r.worldId === legacyWorld?.id && roomDecision(r).allowed) || ROOMS[0]
  const currentRoomId = roomDecision(roomFor(state.currentRoomId)).allowed ? state.currentRoomId : fallback.id
  const interactedNpcIds = state.interactedNpcIds || Object.keys(MOCK_PRESENCE).filter(id => state.conversations?.[id]?.some(m => m.from === 'player'))
  return { currentRoomId, friendIds: state.friendIds || [], interactedNpcIds }
}
export function friendshipDecision(npcId, bond, interactedIds, friendIds) {
  if (friendIds.includes(npcId)) return { allowed: false, reason: '已是好友' }
  if (!interactedIds.includes(npcId)) return { allowed: false, reason: '至少完成一次对话或动作互动后才能添加' }
  if (bond < 10) return { allowed: false, reason: '需要好感达到 10（当前 ' + bond + '）' }
  return { allowed: true, reason: '发送申请后，模拟人物将立即接受' }
}
