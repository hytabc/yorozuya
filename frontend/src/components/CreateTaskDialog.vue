<script setup>
import { reactive, ref, onMounted, onUnmounted } from 'vue'
import { X } from 'lucide-vue-next'
import { api, errorMessage } from '../api'
import { useToast } from '../composables/toast'

const emit = defineEmits(['close', 'created'])
const toast = useToast()
const busy = ref(false)
const unlimited = ref(false)
const categories = ['跑腿', '设计', '技术', '学习', '生活', '其他']
const tomorrow = new Date(Date.now() + 24 * 60 * 60 * 1000)
tomorrow.setMinutes(tomorrow.getMinutes() - tomorrow.getTimezoneOffset())
const form = reactive({
  title: '',
  description: '',
  category: '生活',
  reward: '',
  accept_password: '',
  required_takers: 1,
  expires_at: tomorrow.toISOString().slice(0, 16),
})

async function submit() {
  busy.value = true
  try {
    const payload = {
      ...form,
      required_takers: unlimited.value ? null : form.required_takers,
      expires_at: new Date(form.expires_at).toISOString(),
      reward: form.reward || null,
    }
    const { data } = await api.post('/tasks', payload)
    toast.success(unlimited.value || form.required_takers === 1 ? '委托已发布' : '委托已发布，凑齐人数后自动开始')
    emit('created', data)
  } catch (error) { toast.error(errorMessage(error)) } finally { busy.value = false }
}
function onKey(event) { if (event.key === 'Escape') emit('close') }
onMounted(() => { document.body.classList.add('modal-open'); window.addEventListener('keydown', onKey) })
onUnmounted(() => { document.body.classList.remove('modal-open'); window.removeEventListener('keydown', onKey) })
</script>

<template>
  <div class="modal-backdrop" @mousedown.self="$emit('close')">
    <section class="dialog create-dialog" role="dialog" aria-modal="true" aria-label="发布新委托">
      <button class="icon-button dialog-close" aria-label="关闭" title="关闭" @click="$emit('close')"><X :size="20" /></button>
      <div class="dialog-heading"><span class="eyebrow">NEW REQUEST</span><h2>发布新委托</h2><p>把交付目标、时间和报酬说清楚，更容易遇到合适的人。</p></div>
      <form class="form-stack" @submit.prevent="submit">
        <label>委托标题<input v-model.trim="form.title" required minlength="2" maxlength="80" placeholder="一句话说明需要什么" /></label>
        <label>详细说明<textarea v-model.trim="form.description" required minlength="10" maxlength="3000" rows="6" placeholder="说明背景、具体要求和交付方式"></textarea><small>{{ form.description.length }}/3000</small></label>
        <div class="form-row">
          <label>委托分类<select v-model="form.category"><option v-for="item in categories" :key="item">{{ item }}</option></select></label>
          <label>报酬说明<input v-model.trim="form.reward" maxlength="60" placeholder="如：50 元 / 一杯奶茶" /></label>
        </div>
        <div class="taker-field">
          <span class="taker-label">需要几人接取</span>
          <div class="taker-row">
            <input v-model.number="form.required_takers" type="number" min="1" max="999" :disabled="unlimited" required aria-label="需要接取人数" />
            <label class="checkbox-inline"><input v-model="unlimited" type="checkbox" /><span>不限人数</span></label>
          </div>
          <small class="field-hint">凑齐人数后委托自动开始；不限人数时需要你手动点击开始。</small>
        </div>
        <label>接取密码<input v-model="form.accept_password" type="password" required minlength="4" maxlength="32" autocomplete="new-password" placeholder="4-32 位，每位接单人凭此密码接取" />
          <small class="field-hint">每位接单人都要用这个密码接取。密码不会在站内展示，请通过 QQ 私下告知每一位你选定的人。</small>
        </label>
        <label>有效期<input v-model="form.expires_at" type="datetime-local" required /></label>
        <div class="dialog-footer"><button type="button" class="button secondary" @click="$emit('close')">暂不发布</button><button class="button" :disabled="busy">{{ busy ? '发布中…' : '确认发布' }}</button></div>
      </form>
    </section>
  </div>
</template>
