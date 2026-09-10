<script setup>
import { CHARACTER_LABEL } from '../engine/constants.js'

defineProps({
  insights: { type: Array, default: () => [] },
})
</script>

<template>
  <div class="frost-panel">
    <h3>内心独白</h3>
    <template v-if="insights.length">
      <div v-for="fragment in insights" :key="fragment.id" class="frost-insight">
        <span class="frost-insight-owner">{{ CHARACTER_LABEL[fragment.character] || '旁白' }} · 独白</span>
        {{ fragment.text }}
      </div>
    </template>
    <p v-else class="frost-sub">还没有听见任何人的心声。</p>
  </div>
</template>
