// 节点图对话规则（阶段 4c）。纯函数，不依赖 vue，供 useLifeGame 与测试消费。
// 剧本结构: {start, nodes: {nodeId: {line, choices: [{label, effects, reply, next}]}}}
// 语义: 每天每个 NPC 一条链，从 start 开始;选项的 next 非空则当天推进到下一节点,
// next 为空(或指向失效节点)则当天对话完成;nextDay 重置回 start。

export function nodeFor(script, nodeId) {
  return (nodeId && script.nodes[nodeId]) ? script.nodes[nodeId] : script.nodes[script.start]
}

// 开场/每日重置台词(来自 start 节点)。
export function startLine(script, day = 1) {
  return { from: 'npc', text: script.nodes[script.start].line, day, time: '18:20' }
}

// 选中选项后的推进结果(纯计算;effects 落账与消息写入由 useLifeGame 完成)。
export function resolveDialogueChoice(script, choice) {
  const effects = choice.effects || {}
  const next = choice.next && script.nodes[choice.next] ? choice.next : null
  return {
    bond: effects.bond || 0,
    stats: { ...(effects.stats || {}) },
    reply: choice.reply,
    nextNodeId: next,
    nextLine: next ? script.nodes[next].line : null,
    done: !next,
  }
}

// 载入存档时丢弃指向已不存在节点/NPC 的进度(包内容可能已变更)。
export function sanitizeDialogueNodes(dialogue, saved) {
  const out = {}
  for (const [npcId, nodeId] of Object.entries(saved || {})) {
    if (dialogue[npcId]?.nodes?.[nodeId]) out[npcId] = nodeId
  }
  return out
}
