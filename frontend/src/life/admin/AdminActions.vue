<script setup>
// 动作区块:互动动作(摸摸头/戳戳脸等)编辑。
import { computed, reactive } from 'vue'
import { adminState } from './useLifeAdmin'

const content = computed(() => adminState.content)

const draft = reactive({ id: '', label: '', error: '' })
function submitAdd() {
  const id = draft.id.trim()
  if (!/^[a-z0-9-]+$/.test(id)) { draft.error = 'id 只能用小写字母、数字、连字符'; return }
  if (content.value.actions.some(a => a.id === id)) { draft.error = 'id 已存在'; return }
  if (!draft.label.trim()) { draft.error = '缺少动作名称'; return }
  content.value.actions.push({ id, label: draft.label.trim(), reward: 1, threshold: 0, reply: '……' })
  draft.error = ''
  draft.id = ''; draft.label = ''
}
function submitRemove(action) {
  if (content.value.actions.length <= 1) return
  if (!window.confirm(`删除动作「${action.label}」？`)) return
  content.value.actions = content.value.actions.filter(a => a.id !== action.id)
}
</script>

<template>
  <section class="la-section">
    <h2>动作</h2>
    <p>对话面板的互动动作。每个动作每天每人物首次使用奖励好感；threshold 为解锁所需好感度，reward 为首次奖励。</p>
    <table class="la-table">
      <thead><tr><th>id</th><th>名称</th><th>首次好感奖励</th><th>好感门槛</th><th>NPC 反馈文案</th><th></th></tr></thead>
      <tbody>
        <tr v-for="action in content.actions" :key="action.id">
          <td><code>{{ action.id }}</code></td>
          <td><input v-model="action.label" type="text" style="width:90px" /></td>
          <td><input v-model.number="action.reward" type="number" min="0" max="100" /></td>
          <td><input v-model.number="action.threshold" type="number" min="0" max="100" /></td>
          <td><input v-model="action.reply" type="text" style="width:100%;min-width:220px" /></td>
          <td><button class="la-mini la-danger" :disabled="content.actions.length <= 1" @click="submitRemove(action)">删</button></td>
        </tr>
      </tbody>
    </table>
    <div class="la-add-row">
      <input v-model="draft.id" type="text" placeholder="新动作 id（如 hug）" />
      <input v-model="draft.label" type="text" placeholder="名称（如 抱抱）" />
      <button class="la-mini" @click="submitAdd">+ 新增动作</button>
      <small v-if="draft.error" class="la-missing">{{ draft.error }}</small>
    </div>
  </section>
</template>
