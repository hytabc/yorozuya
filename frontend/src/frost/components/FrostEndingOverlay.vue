<script setup>
import { computed } from 'vue'
import { ENDING_GRADIENT, ENDING_LABEL } from '../engine/constants.js'

const props = defineProps({
  ending: { type: Object, required: true },
  isChaos: { type: Boolean, default: false },
  isGlobal: { type: Boolean, default: false },
  alreadySeen: { type: Boolean, default: false },
  score: { type: Number, default: 0 },
  coherence: { type: Number, default: 0 },
  valence: { type: Number, default: 0 },
})

defineEmits(['keep', 'retry', 'close'])

const gradient = computed(() => {
  const pair = ENDING_GRADIENT[props.ending.type] || ENDING_GRADIENT.chaos
  return `linear-gradient(140deg, ${pair[0]}, ${pair[1]})`
})

const badgeLabel = computed(() => ENDING_LABEL[props.ending.type] || '结局')
</script>

<template>
  <div
    class="frost-ending"
    :class="[`is-type-${ending.type}`, { 'is-global': isGlobal }]"
    :style="{ background: gradient }"
    role="dialog"
    aria-modal="true"
  >
    <div class="frost-ending-inner">
      <span class="frost-badge">{{ badgeLabel }}<template v-if="isGlobal"> · 全局结局</template></span>
      <h2>{{ ending.title }}</h2>
      <p v-if="ending.subtitle" class="frost-sub">{{ ending.subtitle }}</p>
      <p class="frost-ending-text">{{ ending.text }}</p>

      <p v-if="!isGlobal && !isChaos && alreadySeen" class="frost-ending-seen">这个结局你已经见过了。</p>
      <p v-if="!isGlobal && !isChaos" class="frost-ending-seen">
        得分 {{ score }}/100 · 连贯度 {{ coherence }} · 情感走向 {{ valence > 0 ? `+${valence}` : valence }}
      </p>

      <div class="frost-ending-actions">
        <template v-if="isGlobal">
          <button type="button" class="frost-btn is-primary" @click="$emit('close')">收下这个结局</button>
        </template>
        <template v-else>
          <button type="button" class="frost-btn" @click="$emit('retry')">重新排列</button>
          <button type="button" class="frost-btn is-primary" @click="$emit('keep')">保留此结局</button>
        </template>
      </div>
    </div>
  </div>
</template>
