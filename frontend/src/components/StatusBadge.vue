<script setup>
import { computed } from 'vue'

const props = defineProps({ status: { type: String, required: true } })
const labels = {
  published: '已发布',
  accepted: '处理中',
  submitted: '待验收',
  completed: '已完成',
  expired: '已过期',
  cancelled: '已取消',
}
const label = computed(() => labels[props.status] || props.status)
</script>

<template><span class="status-badge" :class="`status-${status}`"><i />{{ label }}</span></template>

