<script setup>
// 剧本文块:每个 NPC 的对话节点图编辑器(树状总览 + 点选编辑),按天编排(第 1~7 天,超出沿用第 7 天)。
// 上方树从起点节点沿选项跳转递归展开;点击某个节点,下方编辑面板只显示该节点的台词与选项。
// 节点 = 一段 NPC 台词 + 若干玩家选项;选项的 next 指向下一节点(空 = 当天结束)。
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

// 从起点沿选项跳转递归展开为带缩进的行;已展示的节点以引用行呈现(防环);
// 从起点不可达的节点(改跳转/删节点可能产生)单列在最后,方便找回。
const treeRows = computed(() => {
  const s = script.value
  if (!s) return []
  const rows = []
  const visited = new Set()
  let seq = 0
  const walk = (nid, depth, via) => {
    if (!s.nodes[nid]) return
    if (visited.has(nid)) { rows.push({ key: `r${seq++}`, nid, depth, via, ref: true }) ; return }
    visited.add(nid)
    rows.push({ key: `r${seq++}`, nid, depth, via, ref: false })
    for (const c of s.nodes[nid].choices) {
      if (c.next) walk(c.next, depth + 1, c.label)
    }
  }
  walk(s.start, 0, null)
  for (const nid of nodeIds.value) {
    if (!visited.has(nid)) rows.push({ key: `r${seq++}`, nid, depth: 0, via: null, ref: false, orphan: true })
  }
  return rows
})

function previewOf(nid) {
  const line = script.value?.nodes[nid]?.line || ''
  return line.length > 24 ? line.slice(0, 24) + '…' : line
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
    <p>剧本按天编排：第 1~7 天各一条对话链，内容到第 7 天为止；第 8 天起沿用第 7 天的剧本。下方树从起点展开整条链：点击节点即可在编辑面板里改它的台词与选项；选项跳转「→ 节点」则玩家选择后当天进入下一节点，「当天结束」则完成当日对话。</p>

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

    <!-- 树状总览:从起点沿选项跳转展开,缩进表示层级 -->
    <div class="la-tree">
      <div v-for="row in treeRows" :key="row.key"
           class="la-tree-row"
           :class="{ selected: row.nid === selectedNode && !row.ref, ref: row.ref, orphan: row.orphan }"
           :style="{ paddingLeft: (row.depth * 26 + 8) + 'px' }"
           @click="selectedNode = row.nid">
        <span v-if="row.via" class="la-tree-via" :title="row.via">↳ {{ row.via }}</span>
        <code>{{ row.nid }}</code>
        <span v-if="script.start === row.nid" class="la-active-tag">起点</span>
        <span v-if="row.orphan" class="la-tree-orphan">未连接</span>
        <span class="la-tree-line">{{ row.ref ? '（上方已展示，点击选中）' : previewOf(row.nid) }}</span>
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
.la-tree { border: 1px solid #e7ebe5; border-radius: 8px; margin-bottom: 14px; max-height: 260px; overflow-y: auto; background: #fbfdfc; }
.la-tree-row { display: flex; align-items: center; gap: 8px; padding: 6px 10px; font-size: 12px; cursor: pointer; border-bottom: 1px solid #f0f2f0; }
.la-tree-row:last-child { border-bottom: 0; }
.la-tree-row:hover { background: #f0f7f2; }
.la-tree-row.selected { background: #e5f3eb; box-shadow: inset 2px 0 0 #237a57; }
.la-tree-row.ref { color: #9aa39d; font-style: italic; }
.la-tree-row code { color: #237a57; font-weight: 600; }
.la-tree-via { color: #9aa39d; max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex-shrink: 0; }
.la-tree-line { color: #69736e; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.la-tree-orphan { background: #fdf0e5; color: #b26a21; font-size: 10px; padding: 1px 6px; border-radius: 999px; }
</style>
