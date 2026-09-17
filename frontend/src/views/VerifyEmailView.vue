<script setup>
// 邮箱确认落地页：邮件里的链接指向 /verify-email?token=...
//
// 同一个入口处理两件事：新注册账号的邮箱验证、以及换绑邮箱的确认。
// 令牌通过 POST 提交（不放进后续请求的 URL），避免被写进日志或 Referer。
import { onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { MailCheck, MailX } from 'lucide-vue-next'
import { api, errorMessage } from '../api'
import { useAuthStore } from '../stores/auth'

const route = useRoute()
const status = ref('working')
const message = ref('')

async function confirm() {
  const token = String(route.query.token || '')
  if (!token) {
    status.value = 'failed'
    message.value = '链接不完整，请重新打开邮件里的链接，或回到登录页重新获取。'
    return
  }
  try {
    await api.post('/auth/email/confirm', { token })
    const auth = useAuthStore()
    if (auth.token) await auth.restore()
    status.value = 'ok'
  } catch (error) {
    status.value = 'failed'
    message.value = errorMessage(error, '链接无效或已过期，请重新获取')
  }
}

onMounted(confirm)
</script>

<template>
  <div class="auth-page">
    <section class="auth-form-wrap">
      <div class="auth-form-header">
        <span class="eyebrow">EMAIL VERIFICATION</span>
        <h2>
          <template v-if="status === 'working'">正在验证邮箱…</template>
          <template v-else-if="status === 'ok'">邮箱验证成功</template>
          <template v-else>验证失败</template>
        </h2>
        <p v-if="status === 'ok'">你的邮箱已完成验证，现在可以登录了。</p>
        <p v-else-if="status === 'failed'">{{ message }}</p>
      </div>

      <div v-if="status === 'ok'" class="verify-icon ok"><MailCheck :size="34" /></div>
      <div v-else-if="status === 'failed'" class="verify-icon failed"><MailX :size="34" /></div>

      <div class="form-stack">
        <RouterLink v-if="status === 'ok'" class="button wide" to="/login">去登录</RouterLink>
        <template v-else-if="status === 'failed'">
          <RouterLink class="button wide" to="/login">返回登录页</RouterLink>
          <RouterLink class="button secondary wide" to="/forgot-password">忘记密码？</RouterLink>
        </template>
      </div>
    </section>
  </div>
</template>

<style scoped>
.verify-icon { display: flex; justify-content: center; margin: 8px 0 20px; }
.verify-icon.ok { color: #2f6f4f; }
.verify-icon.failed { color: #b4322b; }
</style>
