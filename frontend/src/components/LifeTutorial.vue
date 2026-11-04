<script setup>
import { nextTick, ref, watch } from 'vue'
import TourOverlay from './TourOverlay.vue'
import { LIFE_TUTORIAL_STEPS as steps, lifeTutorialKey } from '../composables/lifeTutorialSteps'

// 虚拟人生专属的步骤语义（prepare 切视图、action 安全演示）留在本组件，
// 遮罩/高亮/焦点陷阱等展示逻辑抽在 TourOverlay 里，与全站新手引导共用。
const props = defineProps({ ready: Boolean, userId: [Number, String] })
const emit = defineEmits(['prepare', 'close'])

const tour = ref(null)
const experienced = ref(false)
const current = ref(steps[0])
let autoKey = null

function resolveTarget(step) {
  const actionView = experienced.value
    ? { history: '.history-drawer', worlds: '.drawer-body', roster: '.npc-avatars' }[step?.action]
    : null
  return document.querySelector(actionView || step?.target || '')
}

async function beforeEnter(step) {
  experienced.value = false
  current.value = step
  emit('prepare', step?.prepare || 'main')
  await nextTick()
}

function start() {
  if (!props.ready || !lifeTutorialKey(props.userId)) return
  tour.value?.start()
}

function onTargetClick() {
  const step = current.value
  if (!step?.action) return
  if (!experienced.value) {
    emit('prepare', step.action)
    experienced.value = true
    nextTick(() => tour.value?.measure())
  } else {
    tour.value?.next()
  }
}

function onClose(reason) {
  // 完成与跳过都算"这个账号在本浏览器看过"；卸载（换页面）由 TourOverlay 静默收尾。
  if ((reason === 'skip' || reason === 'finish') && autoKey) {
    try {
      localStorage.setItem(autoKey, 'done')
    } catch {
      /* 隐私模式写不进去：下次会再看一遍，不影响游玩 */
    }
  }
  emit('close')
}

watch(
  () => [props.ready, props.userId],
  () => {
    if (!props.ready) return
    const key = lifeTutorialKey(props.userId)
    if (!key) return
    autoKey = key
    let seen = false
    try {
      seen = localStorage.getItem(key) === 'done'
    } catch {
      /* 读不到就按没看过处理 */
    }
    if (!seen) start()
  },
  { immediate: true, flush: 'post' },
)

defineExpose({ start })
</script>

<template>
  <TourOverlay
    ref="tour"
    :steps="steps"
    :resolve-target="resolveTarget"
    :before-enter="beforeEnter"
    guide-id="life-guide-title"
    label="小白新手指引"
    badge="小白 · 新手指引模板"
    avatar-text="白"
    @close="onClose"
    @target-click="onTargetClick"
  >
    <template #note="{ rect }">
      <small v-if="!rect">此位置暂不可见，仍可阅读说明并点击下一步。</small>
      <small v-else-if="current?.action">{{ experienced ? '已展开教学位置，点击下一步继续。' : '可点击亮起的位置体验（仅教学，不执行游戏操作）。' }}</small>
    </template>
  </TourOverlay>
</template>
