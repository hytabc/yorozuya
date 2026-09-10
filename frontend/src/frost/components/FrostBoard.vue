<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import FrostFragmentCard from './FrostFragmentCard.vue'

const props = defineProps({
  chain: { type: Array, required: true },
  fragments: { type: Array, required: true },
  draggable: { type: Object, required: true },
  canEdit: { type: Boolean, default: true },
  canSubmit: { type: Boolean, default: true },
  canUndo: { type: Boolean, default: true },
  highlight: { type: Array, default: () => [] },
})

const emit = defineEmits(['move', 'move-by', 'move-edge', 'undo', 'submit'])

const slotEls = []
function setSlotRef(el, index) { slotEls[index] = el }

const draggingIndex = ref(null)
const dropIndex = ref(null)
const shakeIndex = ref(null)
const lockedMessage = ref('')
const ghost = ref(null)
const liveMessage = ref('')
const flashIndex = ref(null)

let pending = null
let active = false
let longPressTimer = null

const lastIndex = computed(() => props.fragments.length - 1)

function isLocked(index) {
  const fragment = props.fragments[index]
  if (!fragment) return true
  if (index === 0 || index === lastIndex.value) return true
  return !props.draggable.has(fragment.id)
}

function clamp(value, lo, hi) { return Math.min(hi, Math.max(lo, value)) }

function clearPending() {
  window.removeEventListener('pointermove', onPointerMove)
  window.removeEventListener('pointerup', onPointerUp)
  window.removeEventListener('pointercancel', onPointerCancel)
  clearTimeout(longPressTimer)
  longPressTimer = null
  pending = null
  if (active) active = false
}

function onPointerDown(event, index) {
  if (!props.canEdit) return
  if (event.button !== undefined && event.button !== 0) return
  if (event.target.closest('button')) return
  if (isLocked(index)) {
    shakeIndex.value = index
    lockedMessage.value = index === 0 ? '这是固定的起点，无法移动。' : '这是固定的终点，无法移动。'
    window.setTimeout(() => { shakeIndex.value = null; lockedMessage.value = '' }, 900)
    return
  }
  pending = { index, startX: event.clientX, startY: event.clientY, pointerType: event.pointerType }
  window.addEventListener('pointermove', onPointerMove)
  window.addEventListener('pointerup', onPointerUp)
  window.addEventListener('pointercancel', onPointerCancel)
  if (event.pointerType === 'touch') {
    longPressTimer = window.setTimeout(() => activate(event.clientX, event.clientY), 200)
  }
}

function activate(x, y) {
  if (!pending) return
  active = true
  draggingIndex.value = pending.index
  dropIndex.value = pending.index
  ghost.value = { x, y, fragment: props.fragments[pending.index] }
}

function onPointerMove(event) {
  if (!pending) return
  if (!active) {
    const dist = Math.hypot(event.clientX - pending.startX, event.clientY - pending.startY)
    if (pending.pointerType === 'touch') return
    if (dist < 4) return
    activate(event.clientX, event.clientY)
  }
  event.preventDefault()
  ghost.value = { ...ghost.value, x: event.clientX, y: event.clientY }
  dropIndex.value = computeDropIndex(event.clientY)
}

function computeDropIndex(clientY) {
  const count = props.fragments.length
  let best = 1
  let bestDist = Infinity
  for (let i = 1; i <= count - 2; i++) {
    const el = slotEls[i]
    if (!el) continue
    const rect = el.getBoundingClientRect()
    const distance = Math.abs(rect.top + rect.height / 2 - clientY)
    if (distance < bestDist) { bestDist = distance; best = i }
  }
  return clamp(best, 1, count - 2)
}

function onPointerUp() {
  const from = draggingIndex.value
  const to = dropIndex.value
  clearPending()
  draggingIndex.value = null
  dropIndex.value = null
  ghost.value = null
  if (from !== null && to !== null && from !== to) {
    emit('move', from, to)
  }
}

function onPointerCancel() {
  clearPending()
  draggingIndex.value = null
  dropIndex.value = null
  ghost.value = null
}

function onKeydown(event, index) {
  const fragment = props.fragments[index]
  if (!fragment) return
  const meta = event.ctrlKey || event.metaKey
  if (meta && event.key === 'z') { event.preventDefault(); emit('undo'); return }
  if (!meta) return
  if (event.key === 'ArrowUp') { event.preventDefault(); emit('move-by', fragment.id, -1) }
  else if (event.key === 'ArrowDown') { event.preventDefault(); emit('move-by', fragment.id, 1) }
  else if (event.key === 'Home') { event.preventDefault(); emit('move-edge', fragment.id, 'start') }
  else if (event.key === 'End') { event.preventDefault(); emit('move-edge', fragment.id, 'end') }
}

function onMoved(fragmentId) {
  const index = props.chain.indexOf(fragmentId)
  liveMessage.value = `「${props.fragments.find((f) => f.id === fragmentId)?.text || ''}」已移动到第 ${index + 1} 位。`
  flashIndex.value = index
  window.setTimeout(() => { flashIndex.value = null }, 600)
}

function announce(message) { liveMessage.value = message }

onBeforeUnmount(clearPending)

defineExpose({ onMoved, announce })
</script>

<template>
  <div>
    <div class="frost-chain" role="list" aria-label="因果链">
      <template v-for="(fragment, index) in fragments" :key="fragment.id">
        <div v-if="dropIndex === index && draggingIndex !== null" class="frost-drop-line" aria-hidden="true" />
        <div class="frost-slot" :ref="(el) => setSlotRef(el, index)">
          <p v-if="index === 0" class="frost-slot-anchor-label">起点 · 固定</p>
          <FrostFragmentCard
            :fragment="fragment"
            :index="index"
            :locked="isLocked(index)"
            :draggable="draggable.has(fragment.id)"
            :highlighted="highlight.includes(fragment.id)"
            :flash="flashIndex === index"
            :shaking="shakeIndex === index"
            :dragging="draggingIndex === index"
            :show-tools="canEdit"
            :can-up="canEdit && !isLocked(index) && index > 1"
            :can-down="canEdit && !isLocked(index) && index < lastIndex - 1"
            @pointerdown="onPointerDown($event, index)"
            @keydown="onKeydown($event, index)"
            @up="emit('move-by', fragment.id, -1)"
            @down="emit('move-by', fragment.id, 1)"
          />
          <p v-if="index === lastIndex" class="frost-slot-anchor-label">终点 · 固定</p>
        </div>
      </template>
    </div>

    <p v-if="lockedMessage" class="frost-sub" role="status">{{ lockedMessage }}</p>
    <p class="frost-sr" aria-live="polite">{{ liveMessage }}</p>

    <div class="frost-actions">
      <button type="button" class="frost-btn" :disabled="!canEdit || !canUndo" @click="emit('undo')">
        撤销
      </button>
      <button type="button" class="frost-btn is-primary" :disabled="!canSubmit" @click="emit('submit')">
        让因果稳定
      </button>
    </div>

    <div v-if="ghost" class="frost-ghost" :style="{ left: `${ghost.x}px`, top: `${ghost.y}px` }" aria-hidden="true">
      <FrostFragmentCard :fragment="ghost.fragment" :index="0" />
    </div>
  </div>
</template>
