<script setup>
import { computed, onMounted, onUnmounted } from 'vue'
import { CalendarClock, Coins, MessageCircle, UserRound, X } from 'lucide-vue-next'
import { useAuthStore } from '../stores/auth'
import StatusBadge from './StatusBadge.vue'

const props = defineProps({ task: { type: Object, required: true }, busy: Boolean })
const emit = defineEmits(['close', 'action'])
const auth = useAuthStore()

const isPublisher = computed(() => auth.user?.id === props.task.publisher_id)
const isAssignee = computed(() => auth.user?.id === props.task.assignee_id)
const action = computed(() => {
  if (!auth.isLoggedIn && props.task.status === 'published') return { key: 'login', label: '登录后接受委托' }
  if (props.task.status === 'published' && !isPublisher.value) return { key: 'accept', label: '接受这份委托' }
  if (props.task.status === 'published' && isPublisher.value) return { key: 'cancel', label: '取消委托', danger: true }
  if (props.task.status === 'accepted' && isAssignee.value) return { key: 'submit', label: '标记为已完成' }
  if (props.task.status === 'submitted' && isPublisher.value) return { key: 'confirm', label: '确认验收' }
  return null
})

const format = (value) => new Intl.DateTimeFormat('zh-CN', { dateStyle: 'long', timeStyle: 'short' }).format(new Date(value))
function onKey(event) { if (event.key === 'Escape') emit('close') }
onMounted(() => { document.body.classList.add('modal-open'); window.addEventListener('keydown', onKey) })
onUnmounted(() => { document.body.classList.remove('modal-open'); window.removeEventListener('keydown', onKey) })
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
        <div v-if="task.contact_qq"><dt><MessageCircle :size="16" />联系 QQ</dt><dd>{{ task.contact_qq }}</dd></div>
      </dl>
      <div v-if="!task.is_visible" class="notice error-notice">该委托已被管理员隐藏：{{ task.admin_note || '未填写原因' }}</div>
      <footer class="dialog-footer">
        <span class="muted">发布于 {{ format(task.created_at) }}</span>
        <button v-if="action" class="button" :class="{ danger: action.danger }" :disabled="busy" @click="$emit('action', action.key)">
          {{ busy ? '处理中…' : action.label }}
        </button>
      </footer>
    </section>
  </div>
</template>

