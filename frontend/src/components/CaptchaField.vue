<script setup>
import { nextTick, onMounted, ref, watch } from 'vue'
import { RefreshCw, ShieldCheck } from '@lucide/vue'
import { useCaptcha } from '../composables/useCaptcha'

const { captcha, load, attach, reset, payload, isSatisfied, selectPoint, clearClicks } = useCaptcha()
const container = ref(null)

// click：把页面坐标换算成相对图片的归一化坐标（0..1），与渲染尺寸无关，避免泄露/依赖原图尺寸。
function onClick(event) {
  if (captcha.clicks.length >= captcha.targetCount) return
  const rect = event.currentTarget.getBoundingClientRect()
  if (!rect.width || !rect.height) return
  const x = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width))
  const y = Math.min(1, Math.max(0, (event.clientY - rect.top) / rect.height))
  selectPoint(x, y)
}

onMounted(() => { load() })

// provider 确定后才渲染容器；等 DOM 更新完再挂载 Turnstile 组件。
watch(
  () => captcha.provider,
  async (value) => {
    if (value !== 'turnstile') return
    await nextTick()
    attach(container.value)
  },
  { flush: 'post' },
)

defineExpose({ load, reset, payload, isSatisfied })
</script>

<template>
  <!-- click 分支内含按钮，若用 <label> 会把点击转发给首个可标注控件，故改用 <div>。 -->
  <component
    :is="captcha.provider === 'click' ? 'div' : 'label'"
    v-if="captcha.provider !== 'off'"
    class="captcha-field"
  >
    人机验证
    <div v-if="captcha.provider === 'turnstile'" ref="container" class="captcha-turnstile" />
    <div v-else-if="captcha.provider === 'builtin'" class="captcha-row">
      <div class="input-with-icon" :class="{ invalid: Boolean(captcha.error) }">
        <ShieldCheck :size="18" />
        <input v-model="captcha.code" autocomplete="off" maxlength="8" placeholder="请输入图中字符" />
      </div>
      <button type="button" class="captcha-image-button" title="看不清？点击刷新" @click="load">
        <img v-if="captcha.image" class="captcha-image" :src="captcha.image" alt="点击刷新验证码" />
        <RefreshCw v-else :size="18" />
      </button>
    </div>
    <div v-else-if="captcha.provider === 'click'" class="captcha-click">
      <p class="captcha-click-prompt">{{ captcha.prompt }}</p>
      <div
        class="captcha-click-canvas"
        :class="{ done: captcha.clicks.length >= captcha.targetCount }"
        @click="onClick"
      >
        <img v-if="captcha.image" :src="captcha.image" alt="请按题面依次点击图形" draggable="false" />
        <span
          v-for="(point, index) in captcha.clicks"
          :key="index"
          class="captcha-click-marker"
          :style="{ left: `${point.x * 100}%`, top: `${point.y * 100}%` }"
        >{{ index + 1 }}</span>
      </div>
      <div class="captcha-click-actions">
        <span class="captcha-click-hint">已选 {{ captcha.clicks.length }} / {{ captcha.targetCount }}</span>
        <button type="button" class="captcha-click-action" @click="clearClicks">重选</button>
        <button type="button" class="captcha-click-action" @click="load">换一张</button>
      </div>
    </div>
    <small v-if="captcha.error" class="field-error" role="alert">{{ captcha.error }}</small>
  </component>
</template>
