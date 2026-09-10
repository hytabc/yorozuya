// 条件结局与初始房间规则(纯函数,不依赖 Vue)。
// 结局:列表顺序即优先级,第一个满足全部条件(属性≥阈值 且 好感≥阈值)的结局生效;
// 条件为空的结局恒成立,排在最后充当兜底;都不匹配时退回内置默认结局。

const BUILTIN_DEFAULT_ENDING = {
  id: 'builtin-default',
  name: '七日的旅程',
  text: '晚风轻轻翻过手记，又一个七天落下帷幕。那些平凡的问候、偶然的相遇，已悄悄成为心底温暖的光。不必急着为这段时光寻找答案，你认真走过的每一步，都值得被温柔收藏。',
}

export function resolveEnding(pack, state) {
  for (const ending of pack.endings || []) {
    const conditions = ending.conditions || {}
    const statsOk = Object.entries(conditions.stats || {})
      .every(([key, min]) => (state.stats?.[key] ?? 0) >= min)
    const bondsOk = Object.entries(conditions.bonds || {})
      .every(([npcId, min]) => (state.npcs?.find(n => n.id === npcId)?.bond ?? 0) >= min)
    if (statsOk && bondsOk) return ending
  }
  return BUILTIN_DEFAULT_ENDING
}

// 初始房间:优先用包内配置的 startRoomId(必须仍存在),否则挑第一个有人、未满的非私密房间,
// 再兜底第一个房间,保证玩家永远有处可去。
export function startRoomIdOf(pack) {
  if (pack.startRoomId && pack.rooms.some(r => r.id === pack.startRoomId)) return pack.startRoomId
  const room = pack.rooms.find(r => !r.private && r.occupants > 0 && r.occupants < r.capacity)
  return (room || pack.rooms[0]).id
}
