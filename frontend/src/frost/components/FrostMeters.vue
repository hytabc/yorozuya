<script setup>
import { computed } from 'vue'

const props = defineProps({
  coherence: { type: Number, default: 0 },
  valence: { type: Number, default: 0 },
})

const coherenceNote = computed(() => {
  const value = props.coherence
  if (value >= 80) return '因果已经稳定。'
  if (value >= 60) return '似乎有某种走向。'
  if (value >= 30) return '因果还不稳定。'
  return ''
})

const valenceWidth = computed(() => Math.abs(props.valence) / 2)
const valenceLeft = computed(() => (props.valence >= 0 ? 50 : 50 - valenceWidth.value))
const valenceWarm = computed(() => props.valence >= 0)
</script>

<template>
  <div class="frost-panel">
    <h3>因果指标</h3>

    <div class="frost-meter">
      <div class="frost-meter-head">
        <span>因果连贯度</span>
        <span>{{ coherence }}</span>
      </div>
      <div class="frost-meter-track">
        <div
          class="frost-meter-fill is-coherence"
          :class="{ 'is-glow': coherence >= 80 }"
          :style="{ width: `${coherence}%` }"
        />
      </div>
      <p v-if="coherenceNote" class="frost-meter-note">{{ coherenceNote }}</p>
    </div>

    <div class="frost-meter">
      <div class="frost-meter-head">
        <span>情感走向</span>
        <span>{{ valence > 0 ? `+${valence}` : valence }}</span>
      </div>
      <div class="frost-meter-track frost-bipolar">
        <div class="frost-bipolar-center" />
        <div
          class="frost-bipolar-fill"
          :class="valenceWarm ? 'is-warm' : 'is-cold'"
          :style="{ left: `${valenceLeft}%`, width: `${valenceWidth}%` }"
        />
      </div>
      <p class="frost-meter-note">{{ valence >= 20 ? '靠近' : valence <= -20 ? '疏离' : '中性' }}</p>
    </div>
  </div>
</template>
