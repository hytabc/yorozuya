<script setup>
// 未完成邮箱验证时的强制绑定浮层。
//
// 服务端对这些账号的写操作一律 403，因此这里必须挡住界面，避免用户到处点都失败。
// 「重新发送」走的是同一个绑定接口；完成验证后点「我已验证」重新拉取 /auth/me 即可解除。
import { computed, ref } from 'vue'
import { MailWarning } from 'lucide-vue-next'
import { api, errorMessage } from '../api'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const email = ref('')
const currentPassword = ref('')
const busy = ref(false)
const error = ref('')
const info = ref('')

const pending = computed(() => auth.user?.pending_email || '')
// 已经提交过绑定申请：显示「去邮箱确认」，否则让用户填邮箱
const waiting = computed(() => Boolean(pending.value))
const currentEmail = computed(() => auth.user?.email || '')

async function sendBinding() {
  error.value = ''
  info.value = ''
  const address = (waiting.value ? pending.value : email.value).trim()
  if (!address) {
    error.value = '请输入邮箱地址'
    return
  }
  if (!currentPassword.value) {
    error.value = '请输入当前密码'
    return
  }
  busy.value = true
  try {
    await api.post('/users/me/email', { email: address, current_password: currentPassword.value })
    await auth.restore()
    info.value = `验证邮件已发送到 ${address}，请点击邮件里的链接完成验证。`
  } catch (err) {
    error.value = errorMessage(err, '发送失败，请稍后重试')
  } finally {
    currentPassword.value = ''
    busy.value = false
  }
}

async function refresh() {
  error.value = ''
  info.value = ''
  busy.value = true
  try {
    await auth.restore()
    if (auth.emailGateRequired) info.value = '还没有检测到验证结果，请先在邮箱里点击验证链接。'
  } finally {
    busy.value = false
  }
}

function logout() {
  auth.logout()
}
</script>

<template>
  <div v-if="auth.emailGateRequired" class="email-gate" role="dialog" aria-modal="true" aria-labelledby="email-gate-title">
    <div class="email-gate-card">
      <div class="email-gate-head">
        <MailWarning :size="30" />
        <div>
          <span class="eyebrow">EMAIL REQUIRED</span>
          <h2 id="email-gate-title">请先完成邮箱验证</h2>
        </div>
      </div>
      <p>
        为了能接收委托进展通知、并支持用邮箱找回密码，本站要求每个账号绑定并验证邮箱。
        完成验证前，发布委托、留言、上传图片等功能会暂时不可用。
      </p>
      <p v-if="currentEmail && !auth.user.email_verified" class="muted">
        当前待验证邮箱：{{ currentEmail }}
      </p>

      <label>当前密码<input v-model="currentPassword" type="password" autocomplete="current-password" maxlength="128" /></label>
      <div v-if="waiting" class="form-stack">
        <p class="pending-note">验证邮件已发送到 <strong>{{ pending }}</strong>，请点击邮件里的链接，完成后重新登录。</p>
        <div class="email-gate-actions">
          <button class="button" :disabled="busy" @click="refresh">{{ busy ? '检查中…' : '我已完成验证' }}</button>
          <button class="button secondary" :disabled="busy" @click="sendBinding">重新发送</button>
        </div>
      </div>
      <form v-else class="form-stack" @submit.prevent="sendBinding">
        <label>
          邮箱地址
          <div class="input-with-icon">
            <input v-model="email" type="email" autocomplete="email" placeholder="example@example.com" />
          </div>
        </label>
        <button class="button wide" :disabled="busy">{{ busy ? '发送中…' : '发送验证邮件' }}</button>
      </form>

      <p v-if="info" class="form-hint-success" role="status">{{ info }}</p>
      <p v-if="error" class="form-error" role="alert">{{ error }}</p>

      <div class="email-gate-foot">
        <button class="link-button" type="button" @click="logout">退出登录</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.email-gate {
  position: fixed;
  inset: 0;
  z-index: 1200;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  background: rgba(24, 26, 24, 0.55);
  backdrop-filter: blur(2px);
}
.email-gate-card {
  width: min(520px, 100%);
  max-height: 90vh;
  overflow: auto;
  padding: 26px;
  border-radius: 16px;
  background: #ffffff;
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.25);
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.email-gate-head { display: flex; gap: 12px; align-items: flex-start; color: #b4741f; }
.email-gate-head h2 { margin: 4px 0 0; font-size: 19px; }
.email-gate-card p { margin: 0; line-height: 1.7; color: #3c4046; font-size: 14px; }
.email-gate-actions { display: flex; gap: 10px; flex-wrap: wrap; }
.pending-note { padding: 10px 12px; border-radius: 10px; background: #f4f7f4; }
.email-gate-foot { display: flex; justify-content: flex-end; }
.link-button { background: none; border: none; padding: 0; color: #6b6f76; cursor: pointer; font-size: 13px; text-decoration: underline; }
.form-hint-success { color: #2f6f4f; font-size: 13px; }
</style>
