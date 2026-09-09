<script setup>
// 结局区块:条件结局列表(顺序即优先级) + 兜底说明。
// 每个结局可设属性阈值与好感阈值,全部满足才触发;无条件结局恒成立,应排在最后。
import { computed } from 'vue'
import { adminState } from './useLifeAdmin'
import AdminImageField from './AdminImageField.vue'

const content = computed(() => adminState.content)
const endings = computed(() => content.value?.endings || [])
const npcs = computed(() => content.value?.npcs || [])
const statDefs = [['mood', '心情'], ['energy', '精力'], ['social', '社交'], ['explore', '探索']]

function addEnding() {
  content.value.endings.push({
    id: 'e' + Date.now().toString(36),
    name: '新结局',
    text: '',
    image: null,
    conditions: { stats: {}, bonds: {} },
  })
}
function removeEnding(index) {
  const ending = endings.value[index]
  if (!window.confirm(`删除结局「${ending.name}」？`)) return
  content.value.endings.splice(index, 1)
}
function move(index, delta) {
  const list = content.value.endings
  const target = index + delta
  if (target < 0 || target >= list.length) return
  ;[list[index], list[target]] = [list[target], list[index]]
}
// 条件输入:留空=不限,非法值删除该条件;写入时立即钳制 0-100。
function setCond(obj, key, event) {
  const raw = event.target.value.trim()
  if (raw === '' || !Number.isFinite(Number(raw))) delete obj[key]
  else obj[key] = Math.max(0, Math.min(100, Math.trunc(Number(raw))))
  event.target.value = obj[key] ?? ''
}
function condSummary(ending) {
  const parts = []
  for (const [key, label] of statDefs) {
    const v = ending.conditions?.stats?.[key]
    if (v != null) parts.push(`${label}≥${v}`)
  }
  for (const [id, v] of Object.entries(ending.conditions?.bonds || {})) {
    parts.push(`${npcs.value.find(n => n.id === id)?.name || id}好感≥${v}`)
  }
  return parts.length ? parts.join('，') : '无条件（恒成立，适合兜底）'
}
</script>

<template>
  <section class="la-section" v-if="content">
    <h2>结局</h2>
    <p>第 7 天结算时按列表顺序匹配：第一个满足全部条件的结局生效。把无条件的兜底结局放在最后。</p>

    <div v-for="(ending, i) in endings" :key="ending.id" class="la-ending">
      <header class="la-ending-head">
        <strong>{{ i + 1 }}. {{ ending.name || '(未命名)' }}</strong>
        <code>{{ ending.id }}</code>
        <span class="la-ending-cond">{{ condSummary(ending) }}</span>
        <button class="la-mini" :disabled="i === 0" @click="move(i, -1)">上移</button>
        <button class="la-mini" :disabled="i === endings.length - 1" @click="move(i, 1)">下移</button>
        <button class="la-mini la-danger" @click="removeEnding(i)">删</button>
      </header>
      <div class="la-grid2 la-form">
        <label>结局名称
          <input v-model="ending.name" type="text" placeholder="如：温暖的日常" />
        </label>
        <label style="grid-column: 1 / -1">结局文案
          <textarea v-model="ending.text" rows="3" style="width:100%" placeholder="达成条件后展示的结算文字"></textarea>
        </label>
        <label style="grid-column: 1 / -1">结局图片（可选）
          <AdminImageField v-model="ending.image" placeholder="留空则不展示图片" />
        </label>
      </div>
      <div class="la-ending-conds">
        <span class="la-hint">属性条件（留空不限）：</span>
        <label v-for="[key, label] in statDefs" :key="key">{{ label }}≥
          <input :value="ending.conditions.stats[key] ?? ''" @input="setCond(ending.conditions.stats, key, $event)"
                 type="number" min="0" max="100" step="1" style="width:64px" />
        </label>
      </div>
      <div class="la-ending-conds">
        <span class="la-hint">好感条件（留空不限）：</span>
        <label v-for="npc in npcs" :key="npc.id">{{ npc.name }}≥
          <input :value="ending.conditions.bonds[npc.id] ?? ''" @input="setCond(ending.conditions.bonds, npc.id, $event)"
                 type="number" min="0" max="100" step="1" style="width:64px" />
        </label>
      </div>
    </div>

    <button class="la-mini" @click="addEnding">+ 新增结局</button>
    <small class="la-hint" style="display:block;margin-top:8px">
      一个结局都不配置时，玩家看到的是内置默认结局「七日的旅程」。
    </small>
  </section>
</template>

<style>
.la-ending { border: 1px solid #d9dedb; border-radius: 8px; padding: 12px; margin-bottom: 12px; }
.la-ending-head { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; }
.la-ending-head strong { font-size: 13px; }
.la-ending-head code { color: #69736e; font-size: 11px; }
.la-ending-cond { flex: 1; font-size: 11px; color: #237a57; }
.la-ending-conds { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-top: 8px; font-size: 12px; color: #69736e; }
.la-ending-conds label { display: flex; align-items: center; gap: 4px; }
</style>
