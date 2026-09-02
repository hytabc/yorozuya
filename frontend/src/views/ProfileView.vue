<script setup>
import { reactive, ref } from 'vue'
import { CalendarDays, Save, ShieldCheck } from 'lucide-vue-next'
import { api, errorMessage } from '../api'
import { useAuthStore } from '../stores/auth'
import { useToast } from '../composables/toast'

const auth = useAuthStore()
const toast = useToast()
const busy = ref(false)
const form = reactive({ nickname: auth.user.nickname, qq: auth.user.qq || '', bio: auth.user.bio || '' })
const joined = new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: 'long' }).format(new Date(auth.user.created_at))
async function save() {
  busy.value = true
  try { const { data } = await api.patch('/users/me', form); auth.updateUser(data); toast.success('个人资料已保存') }
  catch (error) { toast.error(errorMessage(error)) } finally { busy.value = false }
}
</script>

<template>
  <div class="page inner-page profile-page">
    <div class="page-title"><div><span class="eyebrow">PERSONAL SETTINGS</span><h1>个人设置</h1><p>管理公开资料与协作联系方式。</p></div></div>
    <div class="profile-layout">
      <aside class="profile-summary">
        <span class="profile-avatar">{{ auth.user.nickname.slice(0, 1) }}</span>
        <h2>{{ auth.user.nickname }}</h2><p>@{{ auth.user.username }}</p>
        <span v-if="auth.isAdmin" class="admin-tag"><ShieldCheck :size="15" />管理员</span>
        <div class="profile-divider" />
        <span class="profile-since"><CalendarDays :size="16" />{{ joined }} 加入</span>
      </aside>
      <section class="profile-form-section">
        <div class="section-heading compact"><div><span class="section-index">01</span><h2>公开资料</h2><p>昵称和简介会展示在委托中</p></div></div>
        <form class="form-stack" @submit.prevent="save">
          <label>昵称<input v-model.trim="form.nickname" required maxlength="32" /></label>
          <label>QQ 号<input v-model.trim="form.qq" inputmode="numeric" pattern="[0-9]{5,20}" maxlength="20" placeholder="仅向与你协作的用户展示" /><small>管理员及委托协作双方可见</small></label>
          <label>个人简介<textarea v-model.trim="form.bio" maxlength="300" rows="6" placeholder="简单介绍你擅长的事情、空闲时间等"></textarea><small>{{ form.bio.length }}/300</small></label>
          <div><button class="button" :disabled="busy"><Save :size="17" />{{ busy ? '保存中…' : '保存更改' }}</button></div>
        </form>
      </section>
    </div>
  </div>
</template>

