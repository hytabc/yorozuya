<!-- // 全屏图片灯箱：点击遮罩/ESC 关闭，带放大缩小动效；支持滚轮、按钮、双击与双指缩放，可拖动平移。 -->
<template>
  <Teleport to="body">
    <div
      class="image-lightbox"
      :class="{ closing }"
      role="dialog"
      aria-modal="true"
      :aria-label="alt"
      @click.self="requestClose"
    >
      <div class="image-lightbox__frame" @click.self="requestClose">
        <img
          class="image-lightbox__image"
          :class="{ dragging }"
          :src="src"
          :alt="alt"
          :style="imageStyle"
          draggable="false"
          @dblclick="toggleZoom"
          @wheel.prevent="onWheel"
          @pointerdown="onPointerDown"
          @pointermove="onPointerMove"
          @pointerup="onPointerUp"
          @pointercancel="onPointerUp"
        />
      </div>
      <div class="image-lightbox__toolbar" @click.stop>
        <button type="button" aria-label="缩小" title="缩小" :disabled="scale <= MIN_SCALE" @click="zoomBy(1 / STEP)">−</button>
        <button type="button" class="image-lightbox__level" title="重置缩放" @click="reset">{{ zoomLabel }}</button>
        <button type="button" aria-label="放大" title="放大" :disabled="scale >= MAX_SCALE" @click="zoomBy(STEP)">＋</button>
      </div>
      <button class="image-lightbox__close" type="button" aria-label="关闭图片" title="关闭" @click.stop="requestClose">×</button>
    </div>
  </Teleport>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'

const emit = defineEmits(['close'])

defineProps({
  src: {
    type: String,
    required: true,
  },
  alt: {
    type: String,
    default: '图片',
  },
})

const MIN_SCALE = 1
const MAX_SCALE = 5
const STEP = 1.4

const scale = ref(1)
const offsetX = ref(0)
const offsetY = ref(0)
const dragging = ref(false)
const closing = ref(false)

const pointers = new Map()
let pinchDistance = 0
let pinchScale = 1
let dragStart = null
let previousOverflow = ''
let closeTimer = null

const imageStyle = computed(() => ({
  transform: `translate(${offsetX.value}px, ${offsetY.value}px) scale(${scale.value})`,
  cursor: scale.value > 1 ? (dragging.value ? 'grabbing' : 'grab') : 'zoom-in',
}))

const zoomLabel = computed(() => `${Math.round(scale.value * 100)}%`)

function zoomAt(nextScale) {
  scale.value = Math.min(MAX_SCALE, Math.max(MIN_SCALE, nextScale))
  if (scale.value === MIN_SCALE) {
    offsetX.value = 0
    offsetY.value = 0
  }
}

function zoomBy(factor) {
  zoomAt(scale.value * factor)
}

function reset() {
  scale.value = MIN_SCALE
  offsetX.value = 0
  offsetY.value = 0
}

function toggleZoom() {
  if (scale.value > MIN_SCALE) reset()
  else zoomAt(2)
}

function onWheel(event) {
  zoomBy(event.deltaY < 0 ? STEP : 1 / STEP)
}

function onPointerDown(event) {
  pointers.set(event.pointerId, { x: event.clientX, y: event.clientY })
  if (pointers.size === 2) {
    const [first, second] = [...pointers.values()]
    pinchDistance = Math.hypot(first.x - second.x, first.y - second.y)
    pinchScale = scale.value
    dragging.value = false
    dragStart = null
    return
  }
  if (scale.value > MIN_SCALE) {
    dragging.value = true
    dragStart = { x: event.clientX - offsetX.value, y: event.clientY - offsetY.value }
    event.currentTarget.setPointerCapture?.(event.pointerId)
  }
}

function onPointerMove(event) {
  const point = pointers.get(event.pointerId)
  if (!point) return
  point.x = event.clientX
  point.y = event.clientY
  if (pointers.size === 2 && pinchDistance) {
    const [first, second] = [...pointers.values()]
    const distance = Math.hypot(first.x - second.x, first.y - second.y)
    zoomAt(pinchScale * (distance / pinchDistance))
    return
  }
  if (dragging.value && dragStart) {
    offsetX.value = event.clientX - dragStart.x
    offsetY.value = event.clientY - dragStart.y
  }
}

function onPointerUp(event) {
  pointers.delete(event.pointerId)
  if (pointers.size < 2) pinchDistance = 0
  if (pointers.size === 0) {
    dragging.value = false
    dragStart = null
  }
}

function handleKeydown(event) {
  if (event.key === 'Escape') requestClose()
}

function requestClose() {
  if (closing.value) return
  closing.value = true
  closeTimer = window.setTimeout(() => emit('close'), 180)
}

onMounted(() => {
  previousOverflow = document.body.style.overflow
  document.body.style.overflow = 'hidden'
  document.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeydown)
  if (closeTimer) window.clearTimeout(closeTimer)
  document.body.style.overflow = previousOverflow
})
</script>

<style scoped>
.image-lightbox {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  background: rgba(0, 0, 0, .78);
  touch-action: none;
  animation: lightbox-backdrop-in .16s ease;
}

.image-lightbox.closing {
  animation: lightbox-backdrop-out .18s ease forwards;
}

.image-lightbox__frame {
  display: flex;
  align-items: center;
  justify-content: center;
  animation: lightbox-image-in .28s cubic-bezier(.2, .8, .35, 1.18);
}

.image-lightbox.closing .image-lightbox__frame {
  animation: lightbox-image-out .18s ease forwards;
}

.image-lightbox__image {
  display: block;
  max-width: 90vw;
  max-height: 90vh;
  object-fit: contain;
  border-radius: 8px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, .25);
  user-select: none;
  -webkit-user-drag: none;
  will-change: transform;
  transition: transform .16s ease;
}

.image-lightbox__image.dragging {
  transition: none;
}

.image-lightbox__toolbar {
  position: absolute;
  left: 50%;
  bottom: 24px;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px;
  border-radius: 999px;
  background: rgba(255, 255, 255, .92);
  box-shadow: 0 6px 24px rgba(0, 0, 0, .28);
  transform: translateX(-50%);
}

.image-lightbox__toolbar button {
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 34px;
  height: 34px;
  padding: 0 10px;
  border: none;
  border-radius: 999px;
  background: transparent;
  color: #222;
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
}

.image-lightbox__toolbar button:hover:not(:disabled) {
  background: rgba(0, 0, 0, .08);
}

.image-lightbox__toolbar button:disabled {
  opacity: .35;
  cursor: default;
}

.image-lightbox__level {
  font-size: 13px;
  font-variant-numeric: tabular-nums;
}

.image-lightbox__close {
  position: absolute;
  top: 16px;
  right: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
  width: 34px;
  height: 34px;
  padding: 0;
  border: none;
  border-radius: 50%;
  background: rgba(255, 255, 255, .92);
  color: #222;
  font-size: 24px;
  line-height: 1;
  cursor: pointer;
  box-shadow: 0 2px 10px rgba(0, 0, 0, .28);
}

@keyframes lightbox-backdrop-in {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes lightbox-backdrop-out {
  from { opacity: 1; }
  to { opacity: 0; }
}

@keyframes lightbox-image-in {
  from { opacity: 0; transform: scale(.92); }
  to { opacity: 1; transform: scale(1); }
}

@keyframes lightbox-image-out {
  from { opacity: 1; transform: scale(1); }
  to { opacity: 0; transform: scale(.92); }
}
</style>
