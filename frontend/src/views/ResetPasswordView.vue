<script setup>
// 用邮件链接设置新密码：/reset-password?token=...
//
// 令牌一次性：提交成功后所有旧登录会话都会失效，需要重新登录。
import { computed, reactive, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { KeyRound } from 'lucide-vue-next'
import { api, errorMessage } from '../api'

const route = useRoute()
const form = reactive({ password: '', confirm: '' })
const busy = ref(false)
const error = ref('')
const done = ref(false)
const token = computed(() => String(route.query.token || ''))

async function submit() {
  error.value = ''
  if (!token.value) {
    error.value = '链接不完整，请重新打开邮件里的链接。'
    return
  }
  if (form.password.length < 8) {
    error.value = '新密码至少需要 8 位'
    return
  }
  if (form.password !== form.confirm) {
    error.value = '两次输入的新密码不一致'
    return
  }
  busy.value = true
  try {
    await api.post('/auth/password-reset/confirm', { token: token.value, password: form.password })
    done.value = true
  } catch (err) {
    error.value = errorMessage(err, '重置失败，请重新获取邮件链接')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="auth-page">
    <section class="auth-form-wrap">
      <div class="auth-form-header">
        <span class="eyebrow">NEW PASSWORD</span>
        <h2>{{ done ? '密码已重置' : '设置新密码' }}</h2>
        <p v-if="done">新密码已生效，此前登录的设备都已退出，请用新密码重新登录。</p>
        <p v-else>设置一个至少 8 位的新密码，重置后所有旧登录会话都会失效。</p>
      </div>

      <div v-if="done" class="form-stack">
        <RouterLink class="button wide" to="/login">去登录</RouterLink>
      </div>
      <form v-else class="form-stack" novalidate @submit.prevent="submit">
        <label>
          新密码
          <div class="input-with-icon">
            <KeyRound :size="18" />
            <input v-model="form.password" type="password" required minlength="8" maxlength="72" autocomplete="new-password" placeholder="至少 8 位" />
          </div>
        </label>
        <label>
          确认新密码
          <div class="input-with-icon">
            <KeyRound :size="18" />
            <input v-model="form.confirm" type="password" required minlength="8" maxlength="72" autocomplete="new-password" placeholder="再次输入新密码" />
          </div>
        </label>
        <p v-if="error" class="form-error" role="alert">{{ error }}</p>
        <button class="button wide" :disabled="busy">{{ busy ? '提交中…' : '确认重置密码' }}</button>
        <RouterLink class="auth-back" to="/login">返回登录</RouterLink>
      </form>
    </section>
  </div>
</template>

<style scoped>
.auth-back { text-align: center; color: var(--muted, #6b6f76); font-size: 13px; }
</style>
