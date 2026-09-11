<script setup>
import { nextTick, onMounted, ref, watch } from 'vue'
import { RefreshCw, ShieldCheck } from 'lucide-vue-next'
import { useCaptcha } from '../composables/useCaptcha'

const { captcha, load, attach, reset, payload, isSatisfied } = useCaptcha()
const container = ref(null)

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
  <label v-if="captcha.provider !== 'off'" class="captcha-field">
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
    <small v-if="captcha.error" class="field-error" role="alert">{{ captcha.error }}</small>
  </label>
</template>
