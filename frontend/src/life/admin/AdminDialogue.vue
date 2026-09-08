<script setup>
// 剧本文块:每个 NPC 的对话节点图编辑器(结构化表单)。
// 节点 = 一段 NPC 台词 + 若干玩家选项;选项的 next 指向下一节点(空 = 当天结束)。
import { computed, ref } from 'vue'
import { adminState, npcById, addDialogueNode, removeDialogueNode } from './useLifeAdmin'

const content = computed(() => adminState.content)
const activeNpc = ref('')
const script = computed(() => {
  const id = activeNpc.value || content.value?.npcIds[0]
  return id ? content.value.dialogue[id] : null
})
const npcId = computed(() => activeNpc.value || content.value?.npcIds[0])
const nodeIds = computed(() => Object.keys(script.value?.nodes || {}))

function addChoice(node) {
  node.choices.push({ label: '……', effects: { stats: {} }, reply: '……', next: null })
}
function removeChoice(node, index) {
  if (node.choices.length <= 1) return
  node.choices.splice(index, 1)
}
function submitRemoveNode(nodeId) {
  if (!window.confirm(`删除节点 ${nodeId}？指向它的选项会改为当天结束。`)) return
  removeDialogueNode(npcId.value, nodeId)
}
</script>

<template>
  <section class="la-section" v-if="script">
    <h2>剧本</h2>
    <p>每天每个 NPC 从起点节点开始一条对话链；选项 next 选「继续到节点」则玩家选择后当天进入下一节点，选「当天结束」则完成当日对话。</p>

    <nav class="la-npc-tabs">
      <button v-for="id in content.npcIds" :key="id"
              :class="{ active: id === npcId }"
              @click="activeNpc = id">{{ npcById(id)?.name || id }}</button>
    </nav>

    <div class="la-form" style="margin-bottom:14px">
      <label>起点节点
        <select v-model="script.start" style="width:140px">
          <option v-for="nid in nodeIds" :key="nid" :value="nid">{{ nid }}</option>
        </select>
      </label>
    </div>

    <div v-for="nid in nodeIds" :key="nid" class="la-node">
      <div class="la-node-head">
        <code>{{ nid }}</code>
        <span v-if="script.start === nid" class="la-active-tag">起点</span>
        <button class="la-mini" style="margin-left:auto" @click="addDialogueNode(npcId)">+ 新增节点</button>
        <button class="la-mini la-danger" :disabled="script.start === nid" @click="submitRemoveNode(nid)">删除节点</button>
      </div>
      <textarea v-model="script.nodes[nid].line" placeholder="NPC 台词"></textarea>

      <div class="la-choice la-choice-head">
        <span>选项文案</span><span>NPC 回复</span><span>好感</span><span>心情</span><span>精力</span><span>社交</span><span>探索</span><span>跳转</span><span></span>
      </div>
      <div v-for="(choice, ci) in script.nodes[nid].choices" :key="ci" class="la-choice">
        <input v-model="choice.label" type="text" placeholder="玩家选项" />
        <input v-model="choice.reply" type="text" placeholder="NPC 回复" />
        <input v-model.number="choice.effects.bond" type="number" min="0" max="100" placeholder="0" />
        <input v-model.number="choice.effects.stats.mood" type="number" min="-100" max="100" placeholder="0" />
        <input v-model.number="choice.effects.stats.energy" type="number" min="-100" max="100" placeholder="0" />
        <input v-model.number="choice.effects.stats.social" type="number" min="-100" max="100" placeholder="0" />
        <input v-model.number="choice.effects.stats.explore" type="number" min="-100" max="100" placeholder="0" />
        <select v-model="choice.next">
          <option :value="null">当天结束</option>
          <option v-for="target in nodeIds" :key="target" :value="target">→ {{ target }}</option>
        </select>
        <button class="la-mini la-danger" :disabled="script.nodes[nid].choices.length <= 1" @click="removeChoice(script.nodes[nid], ci)">删</button>
      </div>
      <button class="la-mini" @click="addChoice(script.nodes[nid])">+ 新增选项</button>
    </div>
  </section>
</template>
