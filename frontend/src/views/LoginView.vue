<script setup>
import { computed, reactive, ref } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { ArrowRight, Check, Gamepad2, HeartHandshake, KeyRound, Mail, MailCheck, Map, MessagesSquare, Sparkles, UserRound } from '@lucide/vue'
import { useAuthStore } from '../stores/auth'
import { api, errorMessage } from '../api'
import { track } from '../analytics'
import CaptchaField from '../components/CaptchaField.vue'

const props = defineProps({ initialMode: { type: String, default: 'login' } })
const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const mode = ref(props.initialMode)
const busy = ref(false)
const error = ref('')
const captchaField = ref(null)
const form = reactive({ username: '', password: '', nickname: '', email: '', remember: true })
const fieldErrors = reactive({ username: '', password: '', nickname: '', email: '' })
// 注册成功后展示「去邮箱验证」面板：注册不再直接登录。
const pendingEmailMasked = ref('')
// 验证邮件可能没送到：面板里允许带人机验证重发一次。
const resendCaptcha = ref(null)
const resendInfo = ref('')
const isRegister = computed(() => mode.value === 'register')

function textLength(value) {
  return [...value].length
}

function registrationFieldError(field) {
  const value = field === 'password' ? form.password.trim() : form[field].trim()
  const length = textLength(value)

  if (field === 'username') {
    if (!value) return '请输入用户名'
    if (length < 3) return `用户名长度不足：当前 ${length} 位，至少需要 3 位`
    if (length > 32) return `用户名过长：当前 ${length} 位，最多允许 32 位`
    if (!/^[a-zA-Z0-9_]+$/.test(value)) return '用户名包含不支持的字符，只能使用字母、数字或下划线'
  }
  if (field === 'email') {
    if (!value) return '请输入邮箱'
    if (length > 254) return `邮箱过长：当前 ${length} 位，最多允许 254 位`
    if (!/^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/.test(value)) return '邮箱格式不正确，例如 name@example.com'
  }
  if (field === 'password') {
    if (!value) return '请输入密码'
    if (length < 8) return `密码长度不足：当前 ${length} 位，至少需要 8 位`
    if (length > 72) return `密码过长：当前 ${length} 位，最多允许 72 位`
  }
  if (field === 'nickname') {
    if (!value) return '请输入昵称'
    if (length > 32) return `昵称过长：当前 ${length} 位，最多允许 32 位`
  }
  return ''
}

function validateRegistrationField(field) {
  fieldErrors[field] = isRegister.value ? registrationFieldError(field) : ''
  return !fieldErrors[field]
}

function validateRegistration() {
  form.username = form.username.trim()
  form.email = form.email.trim()
  form.password = form.password.trim()
  form.nickname = form.nickname.trim()
  return ['nickname', 'username', 'email', 'password'].map(validateRegistrationField).every(Boolean)
}

function validateLogin() {
  if (!form.username.trim() || !form.password) {
    error.value = '请输入用户名（或邮箱）和密码'
    return false
  }
  return true
}

function updateInvalidField(field) {
  if (fieldErrors[field]) validateRegistrationField(field)
}

function applyRegistrationApiErrors(err) {
  const details = err.response?.data?.detail
  if (!Array.isArray(details)) return false

  let matched = false
  for (const detail of details) {
    const field = detail.loc?.at(-1)
    if (!(field in fieldErrors)) continue
    fieldErrors[field] = registrationFieldError(field) || detail.msg || '输入内容不符合规范'
    matched = true
  }
  return matched
}

function safeRedirect(target) {
  // 只允许站内相对路径，避免 redirect 参数被用来跳转到外站。
  if (typeof target !== 'string' || !target.startsWith('/') || target.startsWith('//')) return '/'
  return target
}

async function submit() {
  error.value = ''
  if (isRegister.value ? !validateRegistration() : !validateLogin()) return
  if (!captchaField.value?.isSatisfied()) {
    error.value = '请先完成人机验证'
    return
  }
  busy.value = true
  try {
    const captcha = captchaField.value?.payload() || {}
    if (isRegister.value) {
      // 注册接口不接受 remember（RequestModel 为 extra="forbid"），因此显式挑选字段。
      const result = await auth.register({
        username: form.username,
        password: form.password,
        nickname: form.nickname,
        email: form.email,
        ...captcha,
      })
      pendingEmailMasked.value = result?.email_masked || form.email
      track('auth.register')
    } else {
      await auth.login({ username: form.username, password: form.password, remember: form.remember, ...captcha })
      track('auth.login')
      router.push(safeRedirect(route.query.redirect))
    }
  } catch (err) {
    // 验证码一次性：任何到达服务端的失败都可能已消耗，需重新挑战。
    if (err.response) captchaField.value?.reset()
    if (!isRegister.value || !applyRegistrationApiErrors(err)) {
      error.value = errorMessage(err, isRegister.value ? '注册失败' : '登录失败')
    }
  } finally {
    busy.value = false
  }
}

async function resendVerification() {
  error.value = ''
  resendInfo.value = ''
  if (!resendCaptcha.value?.isSatisfied()) {
    error.value = '请先完成人机验证'
    return
  }
  busy.value = true
  try {
    await api.post('/auth/email/resend', {
      account: form.username.trim(),
      ...(resendCaptcha.value?.payload() || {}),
    })
    // 服务端对「账号是否存在」一律返回成功，因此这里也只提示「若存在则已发送」。
    resendInfo.value = '验证邮件已重新发送。如果几分钟内仍未收到，请检查垃圾邮件文件夹。'
  } catch (err) {
    if (err.response) resendCaptcha.value?.reset()
    error.value = errorMessage(err, '发送失败，请稍后重试')
  } finally {
    busy.value = false
  }
}

function switchMode(next) {
  mode.value = next
  error.value = ''
  pendingEmailMasked.value = ''
  Object.keys(fieldErrors).forEach((field) => { fieldErrors[field] = '' })
  captchaField.value?.reset()
  router.replace(next === 'login' ? '/login' : '/register')
}
</script>

<template>
  <div class="auth-page">
    <section class="auth-story">
      <span class="eyebrow">YOROZUYA MEMBERSHIP</span>
      <h1>小事有人回应，<br />难事有人同行。</h1>
      <p>一个账号即可发布委托、接取开放委托，并持续跟进每一次协作。</p>
      <ul>
        <li><Check :size="17" />可设置需几人接取，凑齐或手动点击即开始</li>
        <li><Check :size="17" />委托完成需委托人与全体接单人确认</li>
        <li><Check :size="17" />登录后可见委托人 QQ，直接联系洽谈</li>
        <li><Check :size="17" />绑定邮箱后可接收委托进展通知、也能用它找回密码</li>
      </ul>
      <div class="auth-sprites" aria-hidden="true">
        <Gamepad2 :size="20" />
        <MessagesSquare :size="20" />
        <HeartHandshake :size="20" />
        <Map :size="20" />
        <Sparkles :size="20" />
      </div>
      <div class="auth-monogram"><span>万</span><small>事事有回音</small></div>
    </section>
    <section class="auth-form-wrap">
      <!-- 注册成功：等邮箱验证 -->
      <template v-if="pendingEmailMasked">
        <div class="auth-form-header">
          <span class="eyebrow">CHECK YOUR EMAIL</span>
          <h2>验证邮件已发送</h2>
          <p>我们向 {{ pendingEmailMasked }} 发送了一封验证邮件，请点击邮件里的链接完成验证后再登录。</p>
        </div>
        <div class="auth-notice"><MailCheck :size="22" /><span>没收到？请先检查垃圾邮件文件夹，再用下方按钮重新发送。</span></div>
        <div class="form-stack">
          <CaptchaField ref="resendCaptcha" />
          <p v-if="resendInfo" class="form-hint-success" role="status">{{ resendInfo }}</p>
          <p v-if="error" class="form-error" role="alert">{{ error }}</p>
          <button class="button wide" :disabled="busy" @click="resendVerification">
            {{ busy ? '发送中…' : '重新发送验证邮件' }}
          </button>
          <button class="button secondary wide" :disabled="busy" @click="switchMode('login')">去登录</button>
        </div>
      </template>

      <!-- 常规登录 / 注册表单 -->
      <template v-else>
        <div class="auth-form-header"><span class="eyebrow">{{ isRegister ? 'CREATE ACCOUNT' : 'WELCOME BACK' }}</span><h2>{{ isRegister ? '加入万事屋' : '欢迎回来' }}</h2><p>{{ isRegister ? '创建账号，验证邮箱后即可发布第一份委托。' : '登录后继续处理你的委托。' }}</p></div>
        <div class="auth-switch"><button :class="{ active: !isRegister }" @click="switchMode('login')">登录</button><button :class="{ active: isRegister }" @click="switchMode('register')">注册</button></div>
        <form class="form-stack" novalidate @submit.prevent="submit">
          <label v-if="isRegister">昵称<div class="input-with-icon" :class="{ invalid: fieldErrors.nickname }"><UserRound :size="18" /><input v-model="form.nickname" placeholder="别人如何称呼你" :aria-invalid="Boolean(fieldErrors.nickname)" :aria-describedby="fieldErrors.nickname ? 'nickname-error' : undefined" @blur="validateRegistrationField('nickname')" @input="updateInvalidField('nickname')" /></div><small v-if="fieldErrors.nickname" id="nickname-error" class="field-error" role="alert">{{ fieldErrors.nickname }}</small></label>
          <label>{{ isRegister ? '用户名' : '用户名或邮箱' }}<div class="input-with-icon" :class="{ invalid: fieldErrors.username }"><UserRound :size="18" /><input v-model="form.username" autocomplete="username" :placeholder="isRegister ? '字母、数字或下划线' : '用户名或注册邮箱'" :aria-invalid="Boolean(fieldErrors.username)" :aria-describedby="fieldErrors.username ? 'username-error' : undefined" @blur="validateRegistrationField('username')" @input="updateInvalidField('username')" /></div><small v-if="fieldErrors.username" id="username-error" class="field-error" role="alert">{{ fieldErrors.username }}</small></label>
          <label v-if="isRegister">邮箱<div class="input-with-icon" :class="{ invalid: fieldErrors.email }"><Mail :size="18" /><input v-model="form.email" type="email" autocomplete="email" placeholder="用于验证与找回密码" :aria-invalid="Boolean(fieldErrors.email)" :aria-describedby="fieldErrors.email ? 'email-error' : undefined" @blur="validateRegistrationField('email')" @input="updateInvalidField('email')" /></div><small v-if="fieldErrors.email" id="email-error" class="field-error" role="alert">{{ fieldErrors.email }}</small><small v-else class="field-hint">注册后需要点击验证邮件里的链接才能登录。</small></label>
          <label>密码<div class="input-with-icon" :class="{ invalid: fieldErrors.password }"><KeyRound :size="18" /><input v-model="form.password" type="password" :autocomplete="isRegister ? 'new-password' : 'current-password'" placeholder="至少 8 位" :aria-invalid="Boolean(fieldErrors.password)" :aria-describedby="fieldErrors.password ? 'password-error' : undefined" @blur="validateRegistrationField('password')" @input="updateInvalidField('password')" /></div><small v-if="fieldErrors.password" id="password-error" class="field-error" role="alert">{{ fieldErrors.password }}</small></label>
          <CaptchaField ref="captchaField" />
          <div v-if="!isRegister" class="remember-field">
            <label class="checkbox-inline"><input v-model="form.remember" type="checkbox" /><span>自动登录</span></label>
            <small class="field-hint">勾选后 7 天内免登录；在公共电脑上请取消勾选。</small>
          </div>
          <p v-if="error" class="form-error" role="alert">{{ error }}</p>
          <button class="button wide" :disabled="busy">{{ busy ? '请稍候…' : isRegister ? '创建账号' : '登录' }}<ArrowRight :size="18" /></button>
          <RouterLink v-if="!isRegister" class="auth-back" to="/forgot-password">忘记密码？用邮箱重置</RouterLink>
        </form>
      </template>
    </section>
  </div>
</template>

<style scoped>
.remember-field { display: flex; flex-direction: column; gap: 6px; }
.auth-notice { display: flex; gap: 10px; align-items: flex-start; padding: 12px 14px; margin-bottom: 16px; border-radius: 10px; background: #f4f7f4; color: #3c4046; font-size: 13px; line-height: 1.6; }
.auth-back { text-align: center; color: var(--muted, #6b6f76); font-size: 13px; }
.form-hint-success { color: #2f6f4f; font-size: 13px; }
/* 招牌精灵图标：经典风不显示；像素风由 pixel.css 展示并驱动循环动画 */
.auth-sprites { display: none; }
</style>
