<script setup>
import { computed } from 'vue'
import { BadgeCheck, Link2, TriangleAlert } from '@lucide/vue'
import { trustSummary } from '../trust'

const props = defineProps({
  trust: { type: Object, default: null },
  // 未绑定时是否显示中性提示：列表/详情里显示，卡片里不显示，避免占位噪音。
  showEmpty: Boolean,
  compact: Boolean,
})

const summary = computed(() => trustSummary(props.trust))
const profileUrl = computed(() => (props.trust?.profile_url?.startsWith('https://') ? props.trust.profile_url : ''))
</script>

<template>
  <span v-if="summary" class="vr-trust" :class="{ compact, stale: summary.stale }" :title="summary.source">
    <BadgeCheck v-if="summary.verified" :size="13" aria-hidden="true" />
    <TriangleAlert v-else :size="13" aria-hidden="true" />
    <span>{{ summary.text }}</span>
    <span v-if="summary.stale" class="vr-trust-stale">数据可能已过期</span>
    <a v-if="profileUrl" class="vr-trust-link" :href="profileUrl" target="_blank" rel="noopener noreferrer" :title="summary.source" @click.stop><Link2 :size="12" />主页</a>
  </span>
  <span v-else-if="showEmpty" class="vr-trust muted" title="绑定后可以选择展示哪些信息；不绑定也不影响使用">
    <BadgeCheck :size="13" aria-hidden="true" />
    <span>未绑定 VRChat</span>
  </span>
</template>
