<script setup>
import { computed, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowRight, Check, KeyRound, UserRound } from 'lucide-vue-next'
import { useAuthStore } from '../stores/auth'
import { errorMessage } from '../api'

const props = defineProps({ initialMode: { type: String, default: 'login' } })
const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const mode = ref(props.initialMode)
const busy = ref(false)
const error = ref('')
const form = reactive({ username: '', password: '', nickname: '' })
const fieldErrors = reactive({ username: '', password: '', nickname: '' })
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
  form.password = form.password.trim()
  form.nickname = form.nickname.trim()
  return ['nickname', 'username', 'password'].map(validateRegistrationField).every(Boolean)
}

function validateLogin() {
  if (!form.username.trim() || !form.password) {
    error.value = '请输入用户名和密码'
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

async function submit() {
  error.value = ''
  if (isRegister.value ? !validateRegistration() : !validateLogin()) return
  busy.value = true
  try {
    if (isRegister.value) await auth.register(form)
    else await auth.login(form)
    router.push(route.query.redirect || '/')
  } catch (err) {
    if (!isRegister.value || !applyRegistrationApiErrors(err)) {
      error.value = errorMessage(err, isRegister.value ? '注册失败' : '登录失败')
    }
  } finally { busy.value = false }
}
function switchMode(next) {
  mode.value = next
  error.value = ''
  Object.keys(fieldErrors).forEach((field) => { fieldErrors[field] = '' })
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
      </ul>
      <div class="auth-monogram"><span>万</span><small>事事有回音</small></div>
    </section>
    <section class="auth-form-wrap">
      <div class="auth-form-header"><span class="eyebrow">{{ isRegister ? 'CREATE ACCOUNT' : 'WELCOME BACK' }}</span><h2>{{ isRegister ? '加入万事屋' : '欢迎回来' }}</h2><p>{{ isRegister ? '创建账号，发布你的第一份委托。' : '登录后继续处理你的委托。' }}</p></div>
      <div class="auth-switch"><button :class="{ active: !isRegister }" @click="switchMode('login')">登录</button><button :class="{ active: isRegister }" @click="switchMode('register')">注册</button></div>
      <form class="form-stack" novalidate @submit.prevent="submit">
        <label v-if="isRegister">昵称<div class="input-with-icon" :class="{ invalid: fieldErrors.nickname }"><UserRound :size="18" /><input v-model="form.nickname" placeholder="别人如何称呼你" :aria-invalid="Boolean(fieldErrors.nickname)" :aria-describedby="fieldErrors.nickname ? 'nickname-error' : undefined" @blur="validateRegistrationField('nickname')" @input="updateInvalidField('nickname')" /></div><small v-if="fieldErrors.nickname" id="nickname-error" class="field-error" role="alert">{{ fieldErrors.nickname }}</small></label>
        <label>用户名<div class="input-with-icon" :class="{ invalid: fieldErrors.username }"><UserRound :size="18" /><input v-model="form.username" autocomplete="username" placeholder="字母、数字或下划线" :aria-invalid="Boolean(fieldErrors.username)" :aria-describedby="fieldErrors.username ? 'username-error' : undefined" @blur="validateRegistrationField('username')" @input="updateInvalidField('username')" /></div><small v-if="fieldErrors.username" id="username-error" class="field-error" role="alert">{{ fieldErrors.username }}</small></label>
        <label>密码<div class="input-with-icon" :class="{ invalid: fieldErrors.password }"><KeyRound :size="18" /><input v-model="form.password" type="password" :autocomplete="isRegister ? 'new-password' : 'current-password'" placeholder="至少 8 位" :aria-invalid="Boolean(fieldErrors.password)" :aria-describedby="fieldErrors.password ? 'password-error' : undefined" @blur="validateRegistrationField('password')" @input="updateInvalidField('password')" /></div><small v-if="fieldErrors.password" id="password-error" class="field-error" role="alert">{{ fieldErrors.password }}</small></label>
        <p v-if="error" class="form-error" role="alert">{{ error }}</p>
        <button class="button wide" :disabled="busy">{{ busy ? '请稍候…' : isRegister ? '创建账号' : '登录' }}<ArrowRight :size="18" /></button>
      </form>
    </section>
  </div>
</template>
