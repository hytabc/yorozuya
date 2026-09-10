// 节点图对话规则（阶段 4c/5/8a）。纯函数，不依赖 vue，供 useLifeGame 与测试消费。
// 剧本结构: pack.dialogue[npcId] = [dayScript, ...] (1-7 天),
//   dayScript = {start, nodes: {nodeId: {lines: [...], image, choices: [{label, effects, replies: [...], replyImage, next}]}}}
// 语义: 每天每个 NPC 一条链,第 1~7 天各用各的剧本;超过剧本天数后一直沿用最后一天
//   (剧本内容到第 7 天为止,不循环)。每天从 start 开始;
// 选项的 next 非空则当天推进到下一节点,next 为空(或指向失效节点)则当天对话完成;
// nextDay 重置回当天的 start。
// 消息组(8a):节点台词 lines 与选项回复 replies 都是多句数组,逐句连播;
// `bg` 是整组持续的对话背景,挂在每一条消息上;`image` 仍只挂在最后一句(供历史抽屉缩略图记录)。

// 当天对话耗尽后,只从好感够得着的最高档随机取一句;不修改配置或产生效果。
export function pickFallbackReply(replies, bond, rng = Math.random) {
  const eligible = (replies || []).filter(reply => (reply.minBond ?? 0) <= bond)
  if (!eligible.length) return null
  const highest = Math.max(...eligible.map(reply => reply.minBond ?? 0))
  const tier = eligible.filter(reply => (reply.minBond ?? 0) === highest)
  return tier[Math.floor(rng() * tier.length)].text
}

// 取某一天的剧本(钳制:超出天数沿用最后一天;days 为 1-7 天数组)。
export function scriptForDay(days, day) {
  if (!Array.isArray(days) || !days.length) return null
  const index = Math.min(Math.max(1, day), days.length) - 1
  return days[index]
}

export function nodeFor(script, nodeId) {
  return (nodeId && script.nodes[nodeId]) ? script.nodes[nodeId] : script.nodes[script.start]
}

// 消息组展开:多句台词逐条成消息;`bg` 是整组持续的对话背景,挂在每一条上;
// `image` 仍只挂在最后一句(供历史抽屉缩略图记录)。
export function groupMessages(texts, image, day, from = 'npc') {
  return texts.map((text, i) => ({
    from, text, day, time: '18:20',
    image: i === texts.length - 1 ? (image || null) : null,
    bg: image || null,
  }))
}

// 开场/每日重置消息组(来自 start 节点)。
export function startMessages(script, day = 1) {
  const node = script.nodes[script.start]
  return groupMessages(node.lines, node.image, day)
}

// 选中选项后的推进结果(纯计算;effects 落账与消息写入由 useLifeGame 完成)。
export function resolveDialogueChoice(script, choice) {
  const effects = choice.effects || {}
  const next = choice.next && script.nodes[choice.next] ? choice.next : null
  const nextNode = next ? script.nodes[next] : null
  return {
    bond: effects.bond || 0,
    stats: { ...(effects.stats || {}) },
    replies: [...choice.replies],
    replyImage: choice.replyImage || null,
    nextNodeId: next,
    nextLines: nextNode ? [...nextNode.lines] : null,
    nextImage: nextNode ? (nextNode.image || null) : null,
    done: !next,
  }
}

// 载入存档时丢弃指向已不存在节点/NPC 的进度(包内容可能已变更;
// 节点 id 在任一一天剧本中存在即视为有效)。
export function sanitizeDialogueNodes(dialogue, saved) {
  const out = {}
  for (const [npcId, nodeId] of Object.entries(saved || {})) {
    const days = dialogue[npcId]
    if (Array.isArray(days) && days.some(script => script.nodes?.[nodeId])) out[npcId] = nodeId
  }
  return out
}
