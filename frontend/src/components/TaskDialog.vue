<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { CalendarClock, Coins, KeyRound, MessageCircle, UserRound, X } from 'lucide-vue-next'
import { useAuthStore } from '../stores/auth'
import StatusBadge from './StatusBadge.vue'

const props = defineProps({ task: { type: Object, required: true }, busy: Boolean })
const emit = defineEmits(['close', 'action'])
const auth = useAuthStore()
const password = ref('')

const isPublisher = computed(() => auth.user?.id === props.task.publisher_id)
const isAssignee = computed(() => auth.user?.id === props.task.assignee_id)
const isParticipant = computed(() => isPublisher.value || isAssignee.value)
const published = computed(() => props.task.status === 'published')
const working = computed(() => props.task.status === 'accepted' || props.task.status === 'awaiting')
const contactLabel = computed(() => (isPublisher.value ? '接单人 QQ' : '委托人 QQ'))

const confirmedByMe = computed(() => {
  if (isPublisher.value) return Boolean(props.task.publisher_confirmed_at)
  if (isAssignee.value) return Boolean(props.task.assignee_confirmed_at)
  return false
})
const confirmedByOther = computed(() => {
  if (isPublisher.value) return Boolean(props.task.assignee_confirmed_at)
  if (isAssignee.value) return Boolean(props.task.publisher_confirmed_at)
  return false
})
const otherRole = computed(() => (isPublisher.value ? '接单人' : '委托人'))

const confirmCopy = computed(() => {
  if (!isParticipant.value || !working.value || confirmedByMe.value) return null
  if (isAssignee.value && props.task.status === 'accepted') {
    return { label: '我已完成，确认完成', hint: '完成委托后点击确认，等待委托人确认后即结单。' }
  }
  if (isPublisher.value && props.task.status === 'accepted') {
    return { label: '确认委托完成', hint: '确认收到成果后点击；双方都确认后委托才算完成。' }
  }
  return { label: '确认完成', hint: `对方已确认完成，等待你确认。` }
})

const format = (value) => new Intl.DateTimeFormat('zh-CN', { dateStyle: 'long', timeStyle: 'short' }).format(new Date(value))
function onKey(event) { if (event.key === 'Escape') emit('close') }
onMounted(() => { document.body.classList.add('modal-open'); window.addEventListener('keydown', onKey) })
onUnmounted(() => { document.body.classList.remove('modal-open'); window.removeEventListener('keydown', onKey) })

function emitAction() {
  if (password.value) emit('action', 'accept', { password: password.value })
}
function resetPassword() {
  const next = window.prompt('输入新的接取密码（4-32 位），旧密码将立即失效', '')
  if (next === null) return
  emit('action', 'password', { password: next.trim() })
}
</script>

<template>
  <div class="modal-backdrop" @mousedown.self="$emit('close')">
    <section class="dialog task-dialog" role="dialog" aria-modal="true" :aria-label="task.title">
      <button class="icon-button dialog-close" aria-label="关闭" title="关闭" @click="$emit('close')"><X :size="20" /></button>
      <div class="dialog-heading">
        <div class="task-tags"><StatusBadge :status="task.status" /><span class="category-tag">{{ task.category }}</span></div>
        <h2>{{ task.title }}</h2>
      </div>
      <p class="task-description">{{ task.description }}</p>
      <dl class="task-detail-grid">
        <div><dt><UserRound :size="16" />发布人</dt><dd>{{ task.publisher.nickname }}</dd></div>
        <div><dt><CalendarClock :size="16" />有效期至</dt><dd>{{ format(task.expires_at) }}</dd></div>
        <div v-if="task.reward"><dt><Coins :size="16" />委托报酬</dt><dd>{{ task.reward }}</dd></div>
        <div v-if="task.assignee"><dt><UserRound :size="16" />接单人</dt><dd>{{ task.assignee.nickname }}</dd></div>
        <div v-if="task.contact_qq"><dt><MessageCircle :size="16" />{{ contactLabel }}</dt><dd>{{ task.contact_qq }}</dd></div>
      </dl>

      <!-- 未登录时查看待接取的委托：提示登录后联系 -->
      <div v-if="published && !auth.isLoggedIn" class="notice info-notice">
        <strong>想接这份委托？</strong>
        <p>登录后即可看到委托人联系方式并洽谈；委托人同意并提供接取密码后，你凭密码即可接取。</p>
      </div>

      <!-- 委托人（发布人）查看自己尚未被接取的委托 -->
      <div v-if="published && isPublisher && !isAssignee" class="notice info-notice">
        <strong>委托已发布，等待接单人联系</strong>
        <p>接单人会看到你的 QQ 并联系你。谈妥后请把发布时设置的接取密码告诉对方，对方凭密码即可接取；想换人时请先重设密码。</p>
      </div>

      <!-- 潜在接单人：联系委托人 + 输入密码接取 -->
      <div v-if="published && auth.isLoggedIn && !isPublisher && !auth.isAdmin" class="take-panel">
        <div class="notice info-notice">
          <strong>接取流程</strong>
          <p><MessageCircle :size="14" /> 先联系委托人洽谈<template v-if="!task.contact_qq">（委托人暂未填写 QQ，可稍后再来或换个委托试试）</template><template v-else>：QQ {{ task.contact_qq }}</template>；<KeyRound :size="14" /> 对方同意后会把接取密码告诉你。</p>
        </div>
        <div class="accept-tools">
          <input v-model.trim="password" type="password" minlength="1" maxlength="72" autocomplete="off" placeholder="输入委托人提供的接取密码" aria-label="接取密码" @keydown.enter="emitAction" />
          <button class="button" :disabled="busy || !password" @click="emitAction">{{ busy ? '处理中…' : '凭密码接取' }}</button>
        </div>
      </div>

      <!-- 参与双方：完成确认 -->
      <div v-if="isParticipant && task.status === 'accepted' && !confirmedByMe && confirmCopy" class="notice info-notice">
        <strong>{{ confirmCopy.hint }}</strong>
        <p>只有委托人与接单人都确认完成后，委托才会标记为已完成。</p>
      </div>
      <div v-if="isParticipant && task.status === 'awaiting' && confirmedByMe" class="notice success-notice">
        <strong>你已确认完成，等待{{ otherRole }}确认。</strong>
      </div>
      <div v-else-if="isParticipant && task.status === 'awaiting' && confirmedByOther" class="notice info-notice">
        <strong>{{ otherRole }}已确认完成，等待你确认。</strong>
        <p>确认无误后点击下方按钮，双方确认后委托即完成。</p>
      </div>
      <div v-if="isParticipant && task.status === 'completed'" class="notice success-notice">
        <strong>委托已完成</strong>
        <p>双方均已确认完成，感谢这次协作。</p>
      </div>

      <div v-if="!task.is_visible" class="notice error-notice">该委托已被管理员隐藏：{{ task.admin_note || '未填写原因' }}</div>
      <footer class="dialog-footer">
        <span class="muted">发布于 {{ format(task.created_at) }}</span>
        <div class="dialog-actions">
          <button v-if="published && isPublisher && !isAssignee" class="button secondary small" :disabled="busy" @click="resetPassword">重设接取密码</button>
          <button v-if="published && isPublisher && !isAssignee" class="button danger small" :disabled="busy" @click="$emit('action', 'cancel')">{{ busy ? '处理中…' : '取消委托' }}</button>
          <button v-if="confirmCopy && !confirmedByMe" class="button" :disabled="busy" @click="$emit('action', 'confirm')">{{ busy ? '处理中…' : confirmCopy.label }}</button>
          <button v-if="published && !auth.isLoggedIn" class="button" @click="$emit('action', 'login')">登录后联系委托人</button>
        </div>
      </footer>
    </section>
  </div>
</template>
