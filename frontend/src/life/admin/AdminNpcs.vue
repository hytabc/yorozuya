<script setup>
// 人物区块:NPC 基本资料、立绘、在场状态;新增/删除人物。
import { computed, reactive } from 'vue'
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

const draft = reactive({ id: '', name: '', error: '' })
function submitAdd() {
  const id = draft.id.trim()
  if (!/^[a-z0-9-]+$/.test(id)) { draft.error = 'id 只能用小写字母、数字、连字符'; return }
  draft.error = addNpc(id, draft.name.trim())
  if (!draft.error) { draft.id = ''; draft.name = '' }
}
function submitRemove(id) {
  if (!window.confirm(`删除人物「${npcById(id)?.name || id}」？其剧本与初始对话将一并删除。`)) return
  removeNpc(id)
}
</script>

<template>
  <section class="la-section">
    <h2>人物</h2>
    <p>玩家在世界中遇到的 NPC。立绘、在场状态决定场景展示；删除人物会同步清理其剧本与初始对话。</p>
    <table class="la-table">
      <thead>
        <tr><th>id</th><th>名字</th><th>身份</th><th>头像</th><th>状态文案</th><th>初始好感</th><th>立绘</th><th>在线状态</th><th>所在房间</th><th>简介</th><th></th></tr>
      </thead>
      <tbody>
        <tr v-for="id in content.npcIds" :key="id">
          <td><code>{{ id }}</code></td>
          <td><input v-model="npcById(id).name" type="text" style="width:80px" /></td>
          <td><input v-model="npcById(id).role" type="text" style="width:100px" /></td>
          <td><input v-model="npcById(id).avatar" type="text" style="width:44px" /></td>
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
          <td><button class="la-mini la-danger" :disabled="content.npcIds.length <= 1" @click="submitRemove(id)">删</button></td>
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
  </section>
</template>
