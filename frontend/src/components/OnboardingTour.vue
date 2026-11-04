<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { useAuthStore } from '../stores/auth'
import TourOverlay from './TourOverlay.vue'
import { ONBOARDING_VERSION, onboardingStorageKey, onboardingSteps } from '../composables/onboardingSteps'
import { pickAnchor } from '../composables/tourGeometry.js'

// 全站新手引导：只在委托大厅启动（锚点都在那儿），所以由 TaskHall 控制时机。
// "看过哪一版"以服务端为准；localStorage 只做同一浏览器的防闪烁缓存。
const auth = useAuthStore()
const router = useRouter()
const tour = ref(null)
let dismissed = false

function seenLocally(userId) {
  const key = onboardingStorageKey(userId)
  if (!key) return false
  try {
    return localStorage.getItem(key) === 'done'
  } catch {
    return false
  }
}

function start({ force = false } = {}) {
  const userId = auth.user?.id
  if (!userId) return
  if (!force && (dismissed || seenLocally(userId))) return
  dismissed = false
  tour.value?.start()
}

async function onClose(reason) {
  dismissed = true
  const userId = auth.user?.id
  if (userId) {
    try {
      const { data } = await api.post('/onboarding/complete', { version: ONBOARDING_VERSION })
      await auth.patchUser({ onboarding_version: data.onboarding_version })
      const key = onboardingStorageKey(userId)
      if (key) localStorage.setItem(key, 'done')
    } catch {
      /* 接口失败就保持未读：下次登录会再展示一次，本次不再打扰 */
    }
  }
  // 最后一步的按钮是「去看看」：直接把用户带到引导里提到的个人设置。
  if (reason === 'finish') router.push('/profile')
}

defineExpose({ start })
</script>

<template>
  <TourOverlay
    ref="tour"
    :steps="onboardingSteps"
    :resolve-target="(step) => pickAnchor(step)"
    guide-id="onboarding-guide-title"
    label="新手引导"
    badge="看板娘 · 新手引导"
    avatar-text="白"
    finish-label="去看看"
    @close="onClose"
  >
    <template #note="{ rect }">
      <small v-if="!rect">这一步的位置暂时不可见，直接下一步也没关系。</small>
    </template>
  </TourOverlay>
</template>
