<script setup>
import { computed } from 'vue'
import { CalendarClock, Coins, UserRound, EyeOff } from 'lucide-vue-next'
import StatusBadge from './StatusBadge.vue'

const props = defineProps({ task: { type: Object, required: true }, showRole: Boolean, hint: String })
defineEmits(['select'])

const deadline = computed(() => new Intl.DateTimeFormat('zh-CN', {
  month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
}).format(new Date(props.task.expires_at)))

const role = computed(() => {
  const me = JSON.parse(localStorage.getItem('wsw_user') || 'null')
  return me?.id === props.task.publisher_id ? '我发布的' : '我接取的'
})
</script>

<template>
  <article class="task-card" :class="`edge-${task.status}`" tabindex="0" @click="$emit('select', task)" @keydown.enter="$emit('select', task)">
    <div class="task-card-top">
      <div class="task-tags">
        <StatusBadge :status="task.status" />
        <span class="category-tag">{{ task.category }}</span>
        <span v-if="showRole" class="role-tag">{{ role }}</span>
        <span v-if="hint" class="role-tag confirm-hint">{{ hint }}</span>
      </div>
      <EyeOff v-if="!task.is_visible" :size="18" class="muted" aria-label="已隐藏" />
    </div>
    <h3>{{ task.title }}</h3>
    <p class="task-summary">{{ task.description }}</p>
    <div class="task-meta">
      <span><UserRound :size="15" />{{ task.publisher.nickname }}</span>
      <span><CalendarClock :size="15" />{{ deadline }}</span>
      <span v-if="task.reward"><Coins :size="15" />{{ task.reward }}</span>
    </div>
  </article>
</template>

