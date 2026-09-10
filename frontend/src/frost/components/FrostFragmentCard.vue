<script setup>
import { computed } from 'vue'
import {
  CHARACTER_BG,
  CHARACTER_COLOR,
  CHARACTER_LABEL,
  CHARACTER_SHAPE,
} from '../engine/constants.js'

const props = defineProps({
  fragment: { type: Object, required: true },
  index: { type: Number, required: true },
  locked: { type: Boolean, default: false },
  draggable: { type: Boolean, default: false },
  highlighted: { type: Boolean, default: false },
  flash: { type: Boolean, default: false },
  shaking: { type: Boolean, default: false },
  dragging: { type: Boolean, default: false },
  showTools: { type: Boolean, default: false },
  canUp: { type: Boolean, default: false },
  canDown: { type: Boolean, default: false },
})

defineEmits(['pointerdown', 'keydown', 'up', 'down'])

const accent = computed(() => CHARACTER_COLOR[props.fragment.character] || '#D8D8D2')
const background = computed(() => CHARACTER_BG[props.fragment.character] || '#FAFAF7')
const shape = computed(() => CHARACTER_SHAPE[props.fragment.character] || 'dot')
const label = computed(() => CHARACTER_LABEL[props.fragment.character] || '旁白')

const classes = computed(() => [
  `is-type-${props.fragment.type}`,
  {
    'is-locked': props.locked,
    'is-gold': props.fragment.type === 'gold',
    'is-red': props.fragment.type === 'red',
    'is-highlight': props.highlighted,
    'is-flash': props.flash,
    'is-shaking': props.shaking,
    'is-dragging': props.dragging,
  },
])

const ariaLabel = computed(
  () => `碎片 ${props.index + 1}。${props.fragment.text}${props.locked ? '（固定，不可移动）' : ''}`,
)
</script>

<template>
  <article
    class="frost-card"
    :class="classes"
    :style="{ borderColor: accent, background }"
    role="listitem"
    tabindex="0"
    :aria-label="ariaLabel"
    @pointerdown="$emit('pointerdown', $event)"
    @keydown="$emit('keydown', $event)"
  >
    <span class="frost-card-index">{{ index + 1 }}</span>
    <div style="flex: 1; min-width: 0">
      <p class="frost-card-text">{{ fragment.text }}</p>
      <div class="frost-card-meta">
        <span
          class="frost-shape"
          :class="`shape-${shape}`"
          :style="{ background: accent, color: accent }"
          aria-hidden="true"
        />
        <span>{{ label }}</span>
        <span v-if="fragment.type === 'gold'">关键事件</span>
        <span v-if="fragment.type === 'red'">负面事件</span>
      </div>
    </div>
    <div v-if="showTools && draggable" class="frost-card-tools">
      <button type="button" :disabled="!canUp" aria-label="上移一位" @click.stop="$emit('up')">↑</button>
      <button type="button" :disabled="!canDown" aria-label="下移一位" @click.stop="$emit('down')">↓</button>
    </div>
    <span v-else-if="locked" class="frost-lock-badge">固定</span>
  </article>
</template>
