<script setup>
// 剧本文块:每个 NPC 的对话节点图编辑器(思维导图 + 点选编辑),按天编排(第 1~7 天,超出沿用第 7 天)。
// 导图从起点节点沿选项跳转铺开:起点在左,不同选项导向的分支向右散开,连线标注选项文案;
// 点击节点卡片,下方编辑面板只显示该节点的台词与选项。
import { computed, ref, watch } from 'vue'
import { adminState, npcById, addDialogueNode, removeDialogueNode, LIFE_DIALOGUE_DAYS } from './useLifeAdmin'

const content = computed(() => adminState.content)
const activeNpc = ref('')
const activeDay = ref(1)
const npcId = computed(() => activeNpc.value || content.value?.npcIds[0])
const days = computed(() => (npcId.value ? content.value.dialogue[npcId.value] : []) || [])
const script = computed(() => days.value[activeDay.value - 1] || null)
const nodeIds = computed(() => Object.keys(script.value?.nodes || {}))
const dayTabs = Array.from({ length: LIFE_DIALOGUE_DAYS }, (_, i) => i + 1)

const selectedNode = ref('')
watch(script, s => { selectedNode.value = s?.start || '' }, { immediate: true })
const node = computed(() => script.value?.nodes[selectedNode.value] || null)

// ==== 思维导图布局(左→右分层,父节点垂直居中于其子分支) ====
const NODE_W = 168
const NODE_H = 64
const COL_GAP = 96
const ROW_GAP = 20
const PAD = 16

const mindmap = computed(() => {
  const s = script.value
  if (!s) return { cards: [], edges: [], width: 0, height: 0 }
  const entries = new Map()
  let leaf = 0
  let maxDepth = 0
  // 放置:沿选项跳转递归;已放置的节点不再重复占位(交叉/回连边仍画出)。
  const place = (nid, depth, parent) => {
    if (entries.has(nid) || !s.nodes[nid]) return null
    maxDepth = Math.max(maxDepth, depth)
    const entry = { nid, depth, parent, children: [], slot: 0 }
    entries.set(nid, entry)
    const kids = []
    for (const c of s.nodes[nid].choices || []) {
      if (c.next && s.nodes[c.next] && !entries.has(c.next) && !kids.includes(c.next)) kids.push(c.next)
    }
    for (const k of kids) {
      const child = place(k, depth + 1, nid)
      if (child) entry.children.push(child)
    }
    entry.slot = entry.children.length
      ? entry.children.reduce((sum, c) => sum + c.slot, 0) / entry.children.length
      : leaf++
    return entry
  }
  place(s.start, 0, null)
  // 从起点不可达的节点(改跳转/删节点可能产生)放到最右一列,标为未连接。
  for (const nid of nodeIds.value) {
    if (!entries.has(nid)) entries.set(nid, { nid, depth: maxDepth + 1, parent: null, children: [], slot: leaf++, orphan: true })
  }
  const xy = e => ({ x: PAD + e.depth * (NODE_W + COL_GAP), y: PAD + e.slot * (NODE_H + ROW_GAP) })
  const cards = [...entries.values()].map(e => ({ ...e, ...xy(e) }))
  const edges = []
  for (const e of entries.values()) {
    if (e.orphan) continue
    const from = xy(e)
    for (const c of s.nodes[e.nid].choices || []) {
      const target = entries.get(c.next)
      if (!c.next || !target) continue
      const to = xy(target)
      edges.push({
        key: `${e.nid}-${c.next}-${edges.length}`,
        label: c.label,
        back: target.parent !== e.nid,
        from: e.nid, to: c.next,
        x1: from.x + NODE_W, y1: from.y + NODE_H / 2,
        x2: to.x, y2: to.y + NODE_H / 2,
      })
    }
  }
  return {
    cards, edges,
    width: PAD * 2 + (maxDepth + 2) * (NODE_W + COL_GAP),
    height: Math.max(1, leaf) * (NODE_H + ROW_GAP) + PAD * 2,
  }
})

function previewOf(nid) {
  const line = script.value?.nodes[nid]?.line || ''
  return line.length > 30 ? line.slice(0, 30) + '…' : line
}
function edgePath(e) {
  const bend = Math.max(36, (e.x2 - e.x1) / 2)
  return `M ${e.x1} ${e.y1} C ${e.x1 + bend} ${e.y1} ${e.x2 - bend} ${e.y2} ${e.x2} ${e.y2}`
}

function addChoice(target) {
  target.choices.push({ label: '……', effects: { stats: {} }, reply: '……', next: null })
}
function removeChoice(target, index) {
  if (target.choices.length <= 1) return
  target.choices.splice(index, 1)
}
function addNodeAndSelect() {
  const id = addDialogueNode(script.value)
  if (id) selectedNode.value = id
}
// 选项跳转下拉:普通选项 = 已有节点/当天结束;「＋ 新建节点…」直接建一个节点并跳过去。
function onNextChange(choice, event) {
  const raw = event.target.selectedOptions[0]._value
  if (raw === '__new__') {
    const id = addDialogueNode(script.value)
    if (id) { choice.next = id; selectedNode.value = id }
  } else {
    choice.next = raw ?? null
  }
}
function submitRemoveNode(nodeId) {
  const count = Object.keys(script.value?.nodes || {}).length
  if (count <= 1) { window.alert('当天剧本至少保留一个节点'); return }
  const isStart = script.value.start === nodeId
  if (!window.confirm(`删除节点 ${nodeId}？指向它的选项会改为当天结束。${isStart ? '它是起点，删除后起点将移交给剩余的第一个节点。' : ''}`)) return
  removeDialogueNode(script.value, nodeId)
  if (selectedNode.value === nodeId) selectedNode.value = script.value.start
}
</script>

<template>
  <section class="la-section" v-if="script">
    <h2>剧本</h2>
    <p>剧本按天编排：第 1~7 天各一条对话链，内容到第 7 天为止；第 8 天起沿用第 7 天的剧本。下方导图从起点展开整条对话树：不同选项导向不同分支，点击节点卡片即可在编辑面板里改它的台词与选项；选项跳转「→ 节点」则玩家选择后当天进入下一节点，「当天结束」则完成当日对话。</p>

    <nav class="la-npc-tabs">
      <button v-for="id in content.npcIds" :key="id"
              :class="{ active: id === npcId }"
              @click="activeNpc = id">{{ npcById(id)?.name || id }}</button>
    </nav>
    <nav class="la-npc-tabs">
      <button v-for="d in dayTabs" :key="d"
              :class="{ active: d === activeDay }"
              @click="activeDay = d">第 {{ d }} 天</button>
    </nav>

    <!-- 思维导图:起点在左,分支沿选项向右散开,连线标注选项文案 -->
    <div class="la-map-scroll">
      <div class="la-map" :style="{ width: mindmap.width + 'px', height: mindmap.height + 'px' }">
        <svg class="la-map-edges" :width="mindmap.width" :height="mindmap.height">
          <g v-for="e in mindmap.edges" :key="e.key">
            <path :d="edgePath(e)" fill="none"
                  :stroke="e.back ? '#c9a86a' : '#b9c9be'"
                  :stroke-width="e.to === selectedNode || e.from === selectedNode ? 2 : 1.5"
                  :stroke-dasharray="e.back ? '5 4' : 'none'" />
            <text :x="(e.x1 + e.x2) / 2" :y="(e.y1 + e.y2) / 2 - 6"
                  text-anchor="middle" class="la-map-label">{{ e.label }}</text>
          </g>
        </svg>
        <div v-for="card in mindmap.cards" :key="card.nid"
             class="la-map-node"
             :class="{ selected: card.nid === selectedNode, orphan: card.orphan }"
             :style="{ left: card.x + 'px', top: card.y + 'px', width: NODE_W + 'px', height: NODE_H + 'px' }"
             @click="selectedNode = card.nid">
          <div class="la-map-node-head">
            <code>{{ card.nid }}</code>
            <span v-if="script.start === card.nid" class="la-active-tag">起点</span>
            <span v-if="card.orphan" class="la-map-orphan">未连接</span>
          </div>
          <div class="la-map-node-line">{{ previewOf(card.nid) }}</div>
        </div>
      </div>
    </div>

    <!-- 选中节点的编辑面板 -->
    <div v-if="node" class="la-node">
      <div class="la-node-head">
        <code>{{ selectedNode }}</code>
        <span v-if="script.start === selectedNode" class="la-active-tag">起点</span>
        <button v-if="script.start !== selectedNode" class="la-mini" @click="script.start = selectedNode">设为起点</button>
        <button class="la-mini" style="margin-left:auto" @click="addNodeAndSelect">+ 新增节点</button>
        <button class="la-mini la-danger" :disabled="nodeIds.length <= 1" @click="submitRemoveNode(selectedNode)">删除节点</button>
      </div>
      <textarea v-model="node.line" placeholder="NPC 台词"></textarea>

      <div class="la-choice la-choice-head">
        <span>选项文案</span><span>NPC 回复</span><span>好感</span><span>心情</span><span>精力</span><span>社交</span><span>探索</span><span>跳转</span><span></span>
      </div>
      <div v-for="(choice, ci) in node.choices" :key="ci" class="la-choice">
        <input v-model="choice.label" type="text" placeholder="玩家选项" />
        <input v-model="choice.reply" type="text" placeholder="NPC 回复" />
        <input v-model.number="choice.effects.bond" type="number" min="0" max="100" placeholder="0" />
        <input v-model.number="choice.effects.stats.mood" type="number" min="-100" max="100" placeholder="0" />
        <input v-model.number="choice.effects.stats.energy" type="number" min="-100" max="100" placeholder="0" />
        <input v-model.number="choice.effects.stats.social" type="number" min="-100" max="100" placeholder="0" />
        <input v-model.number="choice.effects.stats.explore" type="number" min="-100" max="100" placeholder="0" />
        <select :value="choice.next" @change="onNextChange(choice, $event)">
          <option :value="null">当天结束</option>
          <option v-for="target in nodeIds" :key="target" :value="target">→ {{ target }}</option>
          <option value="__new__">＋ 新建节点…</option>
        </select>
        <button class="la-mini la-danger" :disabled="node.choices.length <= 1" @click="removeChoice(node, ci)">删</button>
      </div>
      <button class="la-mini" @click="addChoice(node)">+ 新增选项</button>
    </div>
  </section>
</template>

<style>
.la-map-scroll { border: 1px solid #e7ebe5; border-radius: 8px; margin-bottom: 14px; max-height: 380px; overflow: auto; background: #fbfdfc; }
.la-map { position: relative; }
.la-map-edges { position: absolute; inset: 0; pointer-events: none; }
.la-map-label { font-size: 10px; fill: #69736e; paint-order: stroke; stroke: #fbfdfc; stroke-width: 3px; }
.la-map-node { position: absolute; box-sizing: border-box; background: #fff; border: 1.5px solid #d9dedb; border-radius: 10px; padding: 7px 10px; cursor: pointer; overflow: hidden; transition: border-color .15s, box-shadow .15s; }
.la-map-node:hover { border-color: #8fb8a3; }
.la-map-node.selected { border-color: #237a57; box-shadow: 0 0 0 3px rgba(35, 122, 87, .15); }
.la-map-node.orphan { border-style: dashed; background: #fdf8f2; }
.la-map-node-head { display: flex; align-items: center; gap: 6px; margin-bottom: 2px; }
.la-map-node-head code { color: #237a57; font-weight: 600; font-size: 12px; }
.la-map-node-line { font-size: 11px; color: #69736e; line-height: 1.35; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.la-map-orphan { background: #fdf0e5; color: #b26a21; font-size: 10px; padding: 1px 6px; border-radius: 999px; }
</style>
