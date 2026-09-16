<script setup>
// 忘记密码：按用户名或邮箱申请重置链接。
//
// 服务端对「账号是否存在」始终返回同样的结果，因此这里无论怎样都提示「若账号存在，邮件已发送」，
// 不要根据响应去推断账号是否存在。
import { reactive, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { ArrowRight, KeyRound } from 'lucide-vue-next'
import { api, errorMessage } from '../api'
import CaptchaField from '../components/CaptchaField.vue'

const form = reactive({ account: '' })
const busy = ref(false)
const error = ref('')
const sent = ref(false)
const captchaField = ref(null)

async function submit() {
  error.value = ''
  if (!form.account.trim()) {
    error.value = '请输入用户名或邮箱'
    return
  }
  if (!captchaField.value?.isSatisfied()) {
    error.value = '请先完成人机验证'
    return
  }
  busy.value = true
  try {
    const captcha = captchaField.value?.payload() || {}
    await api.post('/auth/password-reset/request', { account: form.account.trim(), ...captcha })
    sent.value = true
  } catch (err) {
    // 验证码一次性：任何到达服务端的失败都可能已被消耗
    if (err.response) captchaField.value?.reset()
    error.value = errorMessage(err, '申请失败，请稍后重试')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="auth-page">
    <section class="auth-form-wrap">
      <div class="auth-form-header">
        <span class="eyebrow">RESET PASSWORD</span>
        <h2>{{ sent ? '邮件已发送' : '找回密码' }}</h2>
        <p v-if="sent">如果该账号存在且已绑定邮箱，我们已发送一封重置密码的邮件，请在 30 分钟内点击邮件里的链接设置新密码。</p>
        <p v-else>填写注册用的用户名或邮箱，我们会发送一封重置密码的邮件。</p>
      </div>

      <div v-if="sent" class="form-stack">
        <RouterLink class="button wide" to="/login">返回登录</RouterLink>
        <button class="button secondary wide" type="button" @click="sent = false">再试一个账号</button>
      </div>
      <form v-else class="form-stack" novalidate @submit.prevent="submit">
        <label>
          用户名或邮箱
          <div class="input-with-icon">
            <KeyRound :size="18" />
            <input v-model="form.account" autocomplete="username" placeholder="用户名或注册邮箱" />
          </div>
        </label>
        <CaptchaField ref="captchaField" />
        <p v-if="error" class="form-error" role="alert">{{ error }}</p>
        <button class="button wide" :disabled="busy">
          {{ busy ? '发送中…' : '发送重置邮件' }}<ArrowRight :size="18" />
        </button>
        <RouterLink class="auth-back" to="/login">返回登录</RouterLink>
      </form>
    </section>
  </div>
</template>

<style scoped>
.auth-back { text-align: center; color: var(--muted, #6b6f76); font-size: 13px; }
</style>
