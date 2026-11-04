<script setup>
import { computed, nextTick, onBeforeUnmount, ref } from 'vue'
import { spotlightRect } from '../composables/tourGeometry.js'

// 聚光灯引导的展示层：遮罩拼洞、高亮框、卡片避让、Esc/Tab 焦点陷阱、逐帧跟随布局。
// 步骤从哪来、跳到哪里由调用方通过 props 决定，组件本身不认识任何业务页面。
const props = defineProps({
  steps: { type: Array, required: true },
  resolveTarget: { type: Function, required: true },
  beforeEnter: { type: Function, default: null },
  guideId: { type: String, required: true },
  label: { type: String, default: '新手引导' },
  finishLabel: { type: String, default: '完成指引' },
  // 卡片小标题：{ index, total } → 文本
  badge: { type: String, default: '新手引导' },
  avatarText: { type: String, default: '' },
})

const emit = defineEmits(['close', 'target-click', 'enter'])

const active = ref(false)
const index = ref(0)
const rect = ref(null)
const viewport = ref({ width: 1, height: 1 })
const cardEl = ref(null)
let frame = 0
let enterToken = 0
let originalFocus = null
let originalScroll = 0

const step = computed(() => props.steps[index.value] || {})
const total = computed(() => props.steps.length)
const actionable = computed(() => Boolean(step.value.action))

function measure() {
  viewport.value = { width: window.innerWidth, height: window.innerHeight }
  const target = props.resolveTarget?.(step.value)
  rect.value = spotlightRect(target?.getBoundingClientRect?.(), viewport.value.width, viewport.value.height)
}

async function prepare() {
  if (!active.value) return
  const own = ++enterToken
  emit('enter', step.value, index.value)
  if (props.beforeEnter) await props.beforeEnter(step.value)
  await nextTick()
  if (!active.value || own !== enterToken) return
  const target = props.resolveTarget?.(step.value)
  target?.scrollIntoView?.({ block: 'nearest', inline: 'nearest', behavior: 'instant' })
  measure()
  cardEl.value?.focus({ preventScroll: true })
}

function tick() {
  if (!active.value) return
  measure()
  frame = requestAnimationFrame(tick)
}

function start() {
  if (active.value || !props.steps.length) return
  originalFocus = document.activeElement
  originalScroll = window.scrollY
  index.value = 0
  active.value = true
  document.body.classList.add('modal-open')
  document.addEventListener('keydown', keydown, true)
  prepare()
  frame = requestAnimationFrame(tick)
}

function close(reason = 'skip') {
  if (!active.value) return
  teardown()
  emit('close', reason)
  nextTick(() => {
    window.scrollTo({ top: originalScroll || 0, behavior: 'instant' })
    originalFocus?.focus?.({ preventScroll: true })
  })
}

// 卸载（例如引导途中换了路由）不算"看过"：只收尾，不通知调用方。
function teardown() {
  active.value = false
  enterToken += 1
  if (frame) cancelAnimationFrame(frame)
  frame = 0
  document.removeEventListener('keydown', keydown, true)
  document.body.classList.remove('modal-open')
}

function next() {
  if (index.value >= total.value - 1) close('finish')
  else {
    index.value += 1
    prepare()
  }
}

function prev() {
  if (index.value <= 0) return
  index.value -= 1
  prepare()
}

function keydown(event) {
  if (!active.value) return
  // 遮罩下的元素（含原有焦点）必须完全拿不到键盘。
  if (event.key === 'Escape') {
    event.preventDefault()
    event.stopImmediatePropagation()
    close('skip')
    return
  }
  if (event.key === 'Tab') {
    event.preventDefault()
    event.stopImmediatePropagation()
    const buttons = [...(cardEl.value?.querySelectorAll('button:not(:disabled)') || [])]
    if (!buttons.length) return
    const current = buttons.indexOf(document.activeElement)
    const direction = event.shiftKey ? -1 : 1
    buttons[(current + direction + buttons.length) % buttons.length]?.focus()
  } else if (!cardEl.value?.contains(event.target)) {
    event.preventDefault()
    event.stopImmediatePropagation()
  }
}

onBeforeUnmount(teardown)

defineExpose({ start, next, prev, measure, teardown })

const holeStyle = computed(() =>
  rect.value
    ? { left: `${rect.value.left}px`, top: `${rect.value.top}px`, width: `${rect.value.width}px`, height: `${rect.value.height}px` }
    : {},
)
const panels = computed(() => {
  const r = rect.value
  const { width: w, height: h } = viewport.value
  if (!r) return [{ left: 0, top: 0, width: w, height: h }]
  return [
    { left: 0, top: 0, width: w, height: r.top },
    { left: 0, top: r.top, width: r.left, height: r.height },
    { left: r.left + r.width, top: r.top, width: w - r.left - r.width, height: r.height },
    { left: 0, top: r.top + r.height, width: w, height: h - r.top - r.height },
  ]
})
const cardStyle = computed(() => {
  const r = rect.value
  const h = viewport.value.height
  const side = r && r.left + r.width / 2 < viewport.value.width / 2 ? { left: 'auto', right: '18px' } : { left: '18px', right: 'auto' }
  return { ...side, ...(r && r.top > h / 2 ? { top: '18px' } : { bottom: '18px' }) }
})
const panelStyle = (panel) => Object.fromEntries(Object.entries(panel).map(([key, value]) => [key, `${value}px`]))
</script>

<template>
  <Teleport to="body">
    <div v-if="active" class="tour-overlay" :aria-label="label">
      <div
        v-for="(panel, i) in panels"
        :key="i"
        class="tutorial-mask"
        :style="panelStyle(panel)"
        @wheel.prevent
        @touchmove.prevent
      />
      <button
        v-if="rect"
        class="tutorial-hole"
        :class="{ actionable }"
        :style="holeStyle"
        :aria-label="actionable ? `体验：${step.title}` : step.title"
        tabindex="-1"
        @click.stop.prevent="emit('target-click')"
        @wheel.prevent
      />
      <section
        ref="cardEl"
        class="tutorial-card"
        :style="cardStyle"
        tabindex="-1"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="guideId"
      >
        <div v-if="avatarText" class="guide-avatar" aria-hidden="true">{{ avatarText }}</div>
        <div class="tutorial-copy">
          <small>{{ badge }} {{ index + 1 }}/{{ total }}</small>
          <h3 :id="guideId">{{ step.title }}</h3>
          <p>{{ step.text }}</p>
          <slot name="note" :rect="rect" :step="step" :index="index" />
          <div class="tutorial-controls">
            <button type="button" @click="close('skip')">跳过</button>
            <span />
            <button type="button" :disabled="index === 0" @click="prev">上一步</button>
            <button type="button" class="primary" @click="next">
              {{ index === total - 1 ? finishLabel : '下一步' }}
            </button>
          </div>
        </div>
      </section>
    </div>
  </Teleport>
</template>
