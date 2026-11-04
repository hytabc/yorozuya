<script setup>
import { computed } from 'vue'
import { CalendarClock, EyeOff, Ghost, UserRound, UsersRound } from '@lucide/vue'
import StatusBadge from './StatusBadge.vue'
import UserTitleTag from './UserTitleTag.vue'
import { useAuthStore } from '../stores/auth'
import { cardFacets } from '../facets'

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
// 卡片只承担「快速判断」：最多 3 个技能 + 1 个平台，其余折叠为 +N。
const facets = computed(() => cardFacets(props.task.facets))
</script>

<template>
  <article class="task-card" :class="`edge-${task.status}`" tabindex="0" @click="$emit('select', task)" @keydown.enter="$emit('select', task)">
    <div class="task-card-top">
      <div class="task-tags">
        <StatusBadge :status="task.status" />
        <span v-if="task.is_designated" class="role-tag">指定人员</span>
        <span v-if="task.is_anonymous" class="role-tag anon-tag"><Ghost :size="13" />匿名</span>
        <span class="category-tag">{{ task.category }}</span>
        <span v-if="showRole && role" class="role-tag">{{ role }}</span>
        <span v-if="hint" class="role-tag confirm-hint">{{ hint }}</span>
      </div>
      <EyeOff v-if="!task.is_visible" :size="18" class="muted" aria-label="已隐藏" />
    </div>
    <h3>{{ task.title }}</h3>
    <div v-if="facets.platform || facets.skills.length" class="task-facets">
      <span v-if="facets.platform" class="facet-chip static">{{ facets.platform }}</span>
      <span v-for="skill in facets.skills" :key="skill" class="facet-chip static">{{ skill }}</span>
      <span v-if="facets.moreSkills" class="facet-chip static">+{{ facets.moreSkills }}</span>
    </div>
    <p class="task-summary">{{ task.description }}</p>
    <div class="task-meta">
      <span><UserRound :size="15" />{{ task.publisher.nickname }}<UserTitleTag :title="task.publisher.title" /></span>
      <span><CalendarClock :size="15" />{{ deadline }}</span>
      <span v-if="(!task.is_anonymous || task.publisher.id > 0) && (task.members?.length || task.required_takers != null)"><UsersRound :size="15" />已 {{ joined }}/需 {{ requiredText }} 人</span>
    </div>
  </article>
</template>
