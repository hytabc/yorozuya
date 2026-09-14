<script setup>
import { Award } from 'lucide-vue-next'

defineProps({
  title: { type: String, default: '' },
})
</script>

<template>
  <span v-if="title" class="title-tag" :title="title"><Award :size="12" />{{ title }}</span>
</template>
