<script setup>
// 人物区块：NPC 基本资料、立绘、在场状态与默认回复；新增/删除人物。
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { adminState, npcById, addNpc, removeNpc } from './useLifeAdmin'
import AdminImageField from './AdminImageField.vue'

const content = computed(() => adminState.content)
const roomOptions = computed(() => (content.value?.rooms || []).map(r => ({ id: r.id, label: `${r.id}（${r.label}）` })))
const statuses = [
  { id: 'green', label: '在线 · 可加入' },
  { id: 'orange', label: '请勿加入' },
  { id: 'red', label: '忙碌' },
  { id: 'offline', label: '离线' },
]

const selectedId = ref('')
const editorRef = ref(null)
const selected = computed(() => content.value?.npcIds.includes(selectedId.value) ? npcById(selectedId.value) : null)
// 换包或删除人物时清空选择，避免编辑器仍指向旧人物。
watch(content, () => { selectedId.value = '' }, { flush: 'sync' })
watch(selected, npc => {
  if (!npc) selectedId.value = ''
})

async function selectNpc(id) {
  const npc = npcById(id)
  if (!npc || !content.value?.npcIds.includes(id)) return
  // 旧内容包可能没有默认回复字段，首次编辑时补齐。
  npc.fallbackReplies ||= []
  selectedId.value = id
  await nextTick()
  editorRef.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
function addFallbackReply() {
  if (!selected.value) return
  selected.value.fallbackReplies ||= []
  selected.value.fallbackReplies.push({ minBond: 0, text: '' })
}
function setMinBond(reply, event) {
  // 与事件的 setStat 一样硬钳制并回写输入框；空值、非有限数归零。
  const raw = event.target.value
  reply.minBond = raw === '' || !Number.isFinite(Number(raw))
    ? 0
    : Math.max(0, Math.min(100, Math.trunc(Number(raw))))
  event.target.value = reply.minBond
}

const draft = reactive({ id: '', name: '', error: '' })
function submitAdd() {
  const id = draft.id.trim()
  if (!/^[a-z0-9-]+$/.test(id)) { draft.error = 'id 只能用小写字母、数字、连字符'; return }
  draft.error = addNpc(id, draft.name.trim())
  if (!draft.error) { draft.id = ''; draft.name = '' }
}
function submitRemove(id) {
  if (!window.confirm(`删除人物「${npcById(id)?.name || id}」？其剧本与初始对话将一并删除。`)) return
  const error = removeNpc(id)
  if (!error && selectedId.value === id) selectedId.value = ''
}
</script>

<template>
  <section v-if="content" class="la-section la-npcs">
    <h2>人物</h2>
    <p>玩家在世界中遇到的 NPC。立绘、在场状态决定场景展示；删除人物会同步清理其剧本与初始对话。</p>
    <table class="la-table">
      <thead>
        <tr><th>id</th><th>名字</th><th>身份</th><th>头像</th><th>状态文案</th><th>初始好感</th><th>立绘</th><th>在线状态</th><th>所在房间</th><th>简介</th><th></th></tr>
      </thead>
      <tbody>
        <tr v-for="id in content.npcIds" :key="id" :class="{ selected: selectedId === id }">
          <td><code>{{ id }}</code></td>
          <td><input v-model="npcById(id).name" type="text" style="width:80px" /></td>
          <td><input v-model="npcById(id).role" type="text" style="width:100px" /></td>
          <td>
            <div class="la-npc-avatar">
              <img v-if="content.portraits[id]" :src="content.portraits[id]" :alt="`${npcById(id).name || id}头像`" class="la-npc-thumbnail" />
              <span v-else class="la-npc-thumbnail la-npc-placeholder">{{ npcById(id).avatar || '？' }}</span>
              <input v-model="npcById(id).avatar" type="text" class="la-npc-emoji" :aria-label="`${npcById(id).name || id}的 emoji 头像`" />
              <small class="la-hint">场景头像用立绘列上传</small>
            </div>
          </td>
          <td><input v-model="npcById(id).status" type="text" style="width:110px" /></td>
          <td><input v-model.number="npcById(id).bond" type="number" min="0" max="100" /></td>
          <td><AdminImageField v-model="content.portraits[id]" placeholder="立绘 URL 或上传" /></td>
          <td>
            <select v-model="content.presence[id].status">
              <option v-for="s in statuses" :key="s.id" :value="s.id">{{ s.label }}</option>
            </select>
          </td>
          <td>
            <select v-model="content.presence[id].roomId">
              <option :value="null">离线 · 无房间</option>
              <option v-for="r in roomOptions" :key="r.id" :value="r.id">{{ r.label }}</option>
            </select>
          </td>
          <td><input v-model="content.presence[id].intro" type="text" style="width:140px" /></td>
          <td>
            <div class="la-npc-actions">
              <button class="la-mini" :aria-pressed="selectedId === id" @click="selectNpc(id)">默认回复</button>
              <button class="la-mini la-danger" :disabled="content.npcIds.length <= 1" @click="submitRemove(id)">删</button>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
    <div class="la-add-row">
      <input v-model="draft.id" type="text" placeholder="新人物 id（如 luna）" />
      <input v-model="draft.name" type="text" placeholder="名字" />
      <button class="la-mini" @click="submitAdd">+ 新增人物</button>
      <small v-if="draft.error" class="la-missing">{{ draft.error }}</small>
      <small v-else class="la-hint">新增后记得上传立绘、编写剧本与初始对话，否则保存时校验不通过。</small>
    </div>
    <div v-if="selected" :key="selectedId" ref="editorRef" class="la-fallback-editor">
      <h3>{{ selected.name || selectedId }} · 默认回复</h3>
      <p class="la-hint">当天对话说完后，玩家再点头像时随机回一条：取好感够得着的最高一档。</p>
      <div v-for="(reply, index) in selected.fallbackReplies" :key="index" class="la-fallback-row">
        <label>最低好感
          <input :value="reply.minBond" type="number" min="0" max="100" step="1" @input="setMinBond(reply, $event)" />
        </label>
        <label class="la-fallback-text">回复内容
          <input v-model="reply.text" type="text" />
        </label>
        <button class="la-mini la-danger" @click="selected.fallbackReplies.splice(index, 1)">删除</button>
      </div>
      <button class="la-mini" @click="addFallbackReply">+ 加一条</button>
    </div>
  </section>
</template>

<style scoped>
.la-npcs .la-hint { color: #69736e; }
.la-table tr.selected { background: #f4f9f5; }
.la-table tr.selected > td:first-child { box-shadow: inset 4px 0 0 #237a57; }
.la-npc-avatar { display: flex; flex-direction: column; align-items: center; gap: 6px; }
.la-npc-thumbnail { display: block; width: 40px; height: 40px; border-radius: 50%; object-fit: cover; }
.la-npc-placeholder { display: flex; align-items: center; justify-content: center; background: #d9dedb; color: #69736e; font-size: 22px; }
.la-npc-avatar .la-npc-emoji { width: 40px; box-sizing: border-box; text-align: center; }
.la-npc-actions { display: flex; flex-direction: column; align-items: flex-start; gap: 6px; white-space: nowrap; }
.la-npc-actions [aria-pressed=true] { color: #237a57; border-color: #237a57; }
.la-fallback-editor { margin-top: 20px; padding-top: 8px; border-top: 1px solid #d9dedb; scroll-margin-top: 16px; }
.la-fallback-editor h3 { font-size: 14px; color: #237a57; }
.la-fallback-row { display: flex; align-items: end; flex-wrap: wrap; gap: 10px; margin-bottom: 10px; }
.la-fallback-row label { display: flex; flex-direction: column; gap: 4px; color: #69736e; font-size: 12px; }
.la-fallback-row input[type=number] { width: 64px; }
.la-fallback-text { flex: 1; min-width: 160px; }
.la-fallback-text input { width: 100%; box-sizing: border-box; }
</style>
