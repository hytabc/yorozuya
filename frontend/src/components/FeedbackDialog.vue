<script setup>
import { onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { MessageCircle, Send, X } from 'lucide-vue-next'
import { api, errorMessage } from '../api'
import { useAuthStore } from '../stores/auth'
import { useToast } from '../composables/toast'

const emit = defineEmits(['close'])
const auth = useAuthStore()
const toast = useToast()
const submitting = ref(false)
const mine = ref([])
const form = reactive({ page: '', content: '', contact: '' })

const date = (value) => new Intl.DateTimeFormat('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }).format(new Date(value))

async function loadMine() {
  if (!auth.isLoggedIn) return
  try {
    mine.value = (await api.get('/feedback/mine')).data
  } catch {
    /* 静默失败即可 */
  }
}

async function submit() {
  if (form.content.trim().length < 5) return
  submitting.value = true
  try {
    const payload = {
      content: form.content.trim(),
      page: form.page.trim() || null,
    }
    if (!auth.isLoggedIn) payload.contact = form.contact.trim()
    await api.post('/feedback', payload)
    toast.success('反馈已提交，感谢你的建议')
    form.content = ''
    form.page = ''
    await loadMine()
  } catch (error) {
    toast.error(errorMessage(error))
  } finally {
    submitting.value = false
  }
}

function onKey(event) { if (event.key === 'Escape') emit('close') }
onMounted(() => { loadMine(); document.body.classList.add('modal-open'); window.addEventListener('keydown', onKey) })
onBeforeUnmount(() => { document.body.classList.remove('modal-open'); window.removeEventListener('keydown', onKey) })

const statusLabel = { pending: '待处理', handled: '已处理' }
</script>

<template>
  <div class="modal-backdrop" @mousedown.self="$emit('close')">
    <section class="dialog feedback-dialog" role="dialog" aria-modal="true" aria-label="意见反馈">
      <button class="icon-button dialog-close" aria-label="关闭" title="关闭" @click="$emit('close')"><X :size="20" /></button>
      <div class="dialog-heading"><span class="eyebrow"><MessageCircle :size="14" /> FEEDBACK</span><h2>意见与反馈</h2><p>对页面、委托流程或网站的建议都可以告诉我们，管理员会查看并处理。</p></div>
      <form class="form-stack" @submit.prevent="submit">
        <label>相关页面<input v-model.trim="form.page" maxlength="120" placeholder="如：委托大厅 / 委托详情 / 发布流程（可留空）" /></label>
        <label>你的建议<textarea v-model.trim="form.content" required minlength="5" maxlength="2000" rows="5" placeholder="想反馈什么内容？"></textarea><small>{{ form.content.length }}/2000</small></label>
        <label v-if="!auth.isLoggedIn">联系方式（游客填写，便于管理员联系你）<input v-model.trim="form.contact" maxlength="80" placeholder="如 QQ / Telegram" /></label>
        <div class="dialog-footer"><button type="button" class="button secondary" @click="$emit('close')">稍后再说</button><button class="button" :disabled="submitting || form.content.trim().length < 5"><Send :size="16" />{{ submitting ? '提交中…' : '提交反馈' }}</button></div>
      </form>

      <div v-if="auth.isLoggedIn" class="feedback-history">
        <h4>我提交过的反馈</h4>
        <ul v-if="mine.length">
          <li v-for="item in mine" :key="item.id">
            <div class="fb-row">
              <span class="fb-state" :class="`state-${item.status}`">{{ statusLabel[item.status] }}</span>
              <span class="muted">{{ date(item.created_at) }}</span>
            </div>
            <p>{{ item.content }}</p>
            <p v-if="item.reply" class="fb-reply"><strong>管理员回复：</strong>{{ item.reply }}</p>
          </li>
        </ul>
        <p v-else class="muted">还没有提交过反馈。</p>
      </div>
    </section>
  </div>
</template>
