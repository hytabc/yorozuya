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
const isRegister = computed(() => mode.value === 'register')

async function submit() {
  error.value = ''
  busy.value = true
  try {
    if (isRegister.value) await auth.register(form)
    else await auth.login(form)
    router.push(route.query.redirect || '/')
  } catch (err) { error.value = errorMessage(err, '登录失败') } finally { busy.value = false }
}
function switchMode(next) { mode.value = next; error.value = ''; router.replace(next === 'login' ? '/login' : '/register') }
</script>

<template>
  <div class="auth-page">
    <section class="auth-story">
      <span class="eyebrow">YOROZUYA MEMBERSHIP</span>
      <h1>小事有人回应，<br />难事有人同行。</h1>
      <p>一个账号即可发布委托、接受任务，并持续跟进每一次协作。</p>
      <ul>
        <li><Check :size="17" />清晰的委托状态与有效期</li>
        <li><Check :size="17" />仅向协作双方展示联系方式</li>
        <li><Check :size="17" />完整保留发布与接受记录</li>
      </ul>
      <div class="auth-monogram"><span>万</span><small>事事有回音</small></div>
    </section>
    <section class="auth-form-wrap">
      <div class="auth-form-header"><span class="eyebrow">{{ isRegister ? 'CREATE ACCOUNT' : 'WELCOME BACK' }}</span><h2>{{ isRegister ? '加入万事屋' : '欢迎回来' }}</h2><p>{{ isRegister ? '创建账号，发布你的第一份委托。' : '登录后继续处理你的委托。' }}</p></div>
      <div class="auth-switch"><button :class="{ active: !isRegister }" @click="switchMode('login')">登录</button><button :class="{ active: isRegister }" @click="switchMode('register')">注册</button></div>
      <form class="form-stack" @submit.prevent="submit">
        <label v-if="isRegister">昵称<div class="input-with-icon"><UserRound :size="18" /><input v-model.trim="form.nickname" required maxlength="32" placeholder="别人如何称呼你" /></div></label>
        <label>用户名<div class="input-with-icon"><UserRound :size="18" /><input v-model.trim="form.username" required minlength="3" maxlength="32" autocomplete="username" placeholder="字母、数字或下划线" /></div></label>
        <label>密码<div class="input-with-icon"><KeyRound :size="18" /><input v-model="form.password" required minlength="8" maxlength="72" type="password" autocomplete="current-password" placeholder="至少 8 位" /></div></label>
        <p v-if="error" class="form-error">{{ error }}</p>
        <button class="button wide" :disabled="busy">{{ busy ? '请稍候…' : isRegister ? '创建账号' : '登录' }}<ArrowRight :size="18" /></button>
      </form>
    </section>
  </div>
</template>
