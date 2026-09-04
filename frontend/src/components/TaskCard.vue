<script setup>
import { computed } from 'vue'
import { CalendarClock, Coins, EyeOff, LockOpen, UserRound, UsersRound } from 'lucide-vue-next'
import StatusBadge from './StatusBadge.vue'
import { useAuthStore } from '../stores/auth'

const props = defineProps({ task: { type: Object, required: true }, showRole: Boolean, hint: String })
defineEmits(['select'])

const auth = useAuthStore()
const deadline = computed(() => new Intl.DateTimeFormat('zh-CN', {
  month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
}).format(new Date(props.task.expires_at)))

const role = computed(() => {
  const me = auth.user
  if (!me) return ''
  if (me.id === props.task.publisher_id) return '我发布的'
  if (props.task.members?.some((m) => m.user.id === me.id)) return '我接取的'
  return ''
})

const requiredText = computed(() => (props.task.required_takers == null ? '不限' : props.task.required_takers))
const joined = computed(() => props.task.members?.filter((m) => m.response_status === 'accepted').length || 0)
</script>

<template>
  <article class="task-card" :class="`edge-${task.status}`" tabindex="0" @click="$emit('select', task)" @keydown.enter="$emit('select', task)">
    <div class="task-card-top">
      <div class="task-tags">
        <StatusBadge :status="task.status" />
        <span class="pay-tag" :class="`pay-${task.pay_type || 'paid'}`">{{ task.pay_type === 'free' ? '无偿' : '有偿' }}</span>
        <span v-if="task.requires_password === false" class="role-tag open-access-tag"><LockOpen :size="13" />免密码</span>
        <span v-if="task.is_designated" class="role-tag">指定人员</span>
        <span class="category-tag">{{ task.category }}</span>
        <span v-if="showRole && role" class="role-tag">{{ role }}</span>
        <span v-if="hint" class="role-tag confirm-hint">{{ hint }}</span>
      </div>
      <EyeOff v-if="!task.is_visible" :size="18" class="muted" aria-label="已隐藏" />
    </div>
    <h3>{{ task.title }}</h3>
    <p class="task-summary">{{ task.description }}</p>
    <div class="task-meta">
      <span><UserRound :size="15" />{{ task.publisher.nickname }}</span>
      <span><CalendarClock :size="15" />{{ deadline }}</span>
      <span v-if="task.members?.length || task.required_takers != null"><UsersRound :size="15" />已 {{ joined }}/需 {{ requiredText }} 人</span>
      <span v-if="task.reward"><Coins :size="15" />{{ task.reward }}</span>
    </div>
  </article>
</template>
