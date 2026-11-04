<script setup>
import { nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { errorMessage } from '../api'
import { useToast } from '../composables/toast'
import {
  acknowledgeAtmosphere,
  atmosphere,
  closeAtmosphereGate,
} from '../composables/useAtmosphere'

const router = useRouter()
const toast = useToast()
const busy = ref(false)
const panel = ref(null)
const primary = ref(null)

function close() {
  if (!busy.value) closeAtmosphereGate()
}

function openTerms() {
  closeAtmosphereGate()
  router.push('/terms')
}

async function confirm() {
  busy.value = true
  try {
    await acknowledgeAtmosphere()
    toast.success('已记录你的确认，欢迎来到委托大厅')
  } catch (error) {
    toast.error(errorMessage(error, '确认失败，请稍后重试'))
  } finally {
    busy.value = false
  }
}

// 焦点陷阱：遮罩打开时键盘只能在本面板内循环，Esc 可关闭（浏览场景）。
function onKey(event) {
  if (!atmosphere.open) return
  if (event.key === 'Escape') {
    close()
    return
  }
  if (event.key !== 'Tab' || !panel.value) return
  const focusable = panel.value.querySelectorAll('button, a[href], [tabindex]:not([tabindex="-1"])')
  if (!focusable.length) return
  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

watch(
  () => atmosphere.open,
  async (open) => {
    if (open) {
      document.body.classList.add('modal-open')
      await nextTick()
      primary.value?.focus()
    } else {
      document.body.classList.remove('modal-open')
    }
  },
)

onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => {
  window.removeEventListener('keydown', onKey)
  document.body.classList.remove('modal-open')
})
</script>

<template>
  <div v-if="atmosphere.open" class="atmosphere-gate" role="dialog" aria-modal="true" aria-labelledby="atmosphere-title">
    <section ref="panel" class="atmosphere-card">
      <span class="eyebrow">BEFORE YOU ENTER</span>
      <h2 id="atmosphere-title">这里不担保交易，<br />但这里记录信誉。</h2>
      <p class="atmosphere-line">请只发布你真正需要帮助的事，只接下你真正能完成的事。</p>
      <p class="atmosphere-line">尊重对方的时间、劳动与边界。遇到分歧，先沟通，再决定是否继续。</p>
      <p class="atmosphere-note">数据与记录可能滞后，本站不构成平台担保；完整条款仍可随时查看。</p>
      <div class="atmosphere-actions">
        <button ref="primary" type="button" class="button" :disabled="busy" @click="confirm">{{ busy ? '记录中…' : '我明白，进入委托大厅' }}</button>
        <button type="button" class="button secondary" @click="openTerms">查看完整说明</button>
        <button type="button" class="text-link atmosphere-close" @click="close">先看看</button>
      </div>
    </section>
  </div>
</template>
