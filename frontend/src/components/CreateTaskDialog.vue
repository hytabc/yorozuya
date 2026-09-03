<script setup>
import { reactive, ref, computed, onMounted, onUnmounted } from 'vue'
import { Check, TriangleAlert, X } from 'lucide-vue-next'
import { api, errorMessage } from '../api'
import { useToast } from '../composables/toast'
import { CATEGORIES } from '../constants'

const emit = defineEmits(['close', 'created'])
const toast = useToast()
const busy = ref(false)
const unlimited = ref(false)
const passwordless = ref(false)
const categories = CATEGORIES
const directory = ref({ staff: [], volunteers: [] })
const designated = ref(false)
const designatedIds = ref([])
const designatedUsers = computed(() => [...directory.value.staff, ...directory.value.volunteers])
const tomorrow = new Date(Date.now() + 24 * 60 * 60 * 1000)
tomorrow.setMinutes(tomorrow.getMinutes() - tomorrow.getTimezoneOffset())
const form = reactive({
  title: '',
  description: '',
  category: '',
  pay_type: 'paid',
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
      pay_type: form.pay_type,
      reward: form.pay_type === 'paid' ? (form.reward || null) : null,
      accept_password: passwordless.value ? null : form.accept_password,
      designated_user_ids: designated.value ? designatedIds.value : [],
    }
    const { data } = await api.post('/tasks', payload)
    toast.success(designated.value ? '指定委托已发布，等待被指定人员响应' : (unlimited.value || form.required_takers === 1 ? '委托已发布' : '委托已发布，凑齐人数后自动开始'))
    emit('created', data)
  } catch (error) { toast.error(errorMessage(error)) } finally { busy.value = false }
}
function onKey(event) { if (event.key === 'Escape') emit('close') }
onMounted(() => { document.body.classList.add('modal-open'); window.addEventListener('keydown', onKey) })
onMounted(async () => {
  try { directory.value = (await api.get('/staff')).data } catch { directory.value = { staff: [], volunteers: [] } }
})
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
          <label>委托分类<select v-model="form.category" required><option value="" disabled>请选择委托类型</option><option v-for="item in categories" :key="item">{{ item }}</option></select></label>
          <div class="pay-field">
            <span class="taker-label">是否付费</span>
            <div class="pay-toggle" role="radiogroup" aria-label="是否付费">
              <button type="button" role="radio" :aria-checked="form.pay_type === 'paid'" :class="{ active: form.pay_type === 'paid' }" @click="form.pay_type = 'paid'">有偿</button>
              <button type="button" role="radio" :aria-checked="form.pay_type === 'free'" :class="{ active: form.pay_type === 'free' }" @click="form.pay_type = 'free'">无偿</button>
            </div>
          </div>
        </div>
        <label v-if="form.pay_type === 'paid'">报酬说明<input v-model.trim="form.reward" maxlength="60" placeholder="如：50 元 / 一杯奶茶" /></label>
        <div class="taker-field">
          <span class="taker-label">需要几人接取</span>
          <div class="taker-row">
            <input v-model.number="form.required_takers" type="number" min="1" max="999" :disabled="unlimited" required aria-label="需要接取人数" />
            <label class="checkbox-inline"><input v-model="unlimited" type="checkbox" /><span>不限人数</span></label>
          </div>
          <small class="field-hint">凑齐人数后委托自动开始；不限人数时需要你手动点击开始。</small>
        </div>
        <div class="designated-field">
          <label class="checkbox-inline"><input v-model="designated" type="checkbox" /><span>指定店员/志愿者接取</span></label>
          <small class="field-hint">指定委托无需密码，仅名单内人员可响应；单人接受即开始，多人需全部响应后开始。</small>
          <div v-if="designated" class="designated-list">
            <label v-for="person in designatedUsers" :key="person.id" class="designated-option">
              <input v-model="designatedIds" type="checkbox" :value="person.id" />
              <span>{{ person.nickname }}</span><small>{{ person.role === 'staff' ? '店员' : '志愿者' }}</small><Check v-if="designatedIds.includes(person.id)" :size="15" />
            </label>
            <p v-if="!designatedUsers.length" class="field-hint">当前没有可指定的店员或志愿者。</p>
            <p v-if="designated && !designatedIds.length" class="field-error">请至少指定一名店员或志愿者</p>
          </div>
        </div>
        <div v-if="!designated" class="access-field">
          <span class="taker-label">接取方式</span>
          <div class="pay-toggle" role="radiogroup" aria-label="接取方式">
            <button type="button" role="radio" :aria-checked="!passwordless" :class="{ active: !passwordless }" @click="passwordless = false">密码接取</button>
            <button type="button" role="radio" :aria-checked="passwordless" :class="{ active: passwordless }" @click="passwordless = true">无密码</button>
          </div>
        </div>
        <label v-if="!designated && !passwordless">接取密码<input v-model="form.accept_password" type="password" required minlength="4" maxlength="32" autocomplete="new-password" placeholder="4-32 位，每位接单人凭此密码接取" />
          <small class="field-hint">每位接单人都要用这个密码接取。密码不会在站内展示，请通过 QQ 私下告知每一位你选定的人。</small>
        </label>
        <div v-else-if="!designated" class="notice risk-notice" role="alert">
          <strong><TriangleAlert :size="17" />无密码接取风险</strong>
          <p>所有非管理员用户无需联系你确认即可直接加入，可能快速占满名额；达到所需人数后委托会自动开始。请确认委托内容适合公开接取。</p>
        </div>
        <label>有效期<input v-model="form.expires_at" type="datetime-local" required /></label>
        <div class="dialog-footer"><button type="button" class="button secondary" @click="$emit('close')">暂不发布</button><button class="button" :disabled="busy || (designated && !designatedIds.length)">{{ busy ? '发布中…' : '确认发布' }}</button></div>
      </form>
    </section>
  </div>
</template>
