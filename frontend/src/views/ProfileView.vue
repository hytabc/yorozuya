<script setup>
import { computed, reactive, ref } from 'vue'
import { CalendarDays, EyeOff, Heart, ImagePlus, Save, ShieldCheck, Store, Trash2, UserRound } from 'lucide-vue-next'
import { api, errorMessage } from '../api'
import { useAuthStore } from '../stores/auth'
import { useToast } from '../composables/toast'
import { roleLabel, ROLE_HINTS } from '../constants'

const auth = useAuthStore()
const toast = useToast()
const busy = ref(false)
const photoBusy = ref(false)
const photos = ref(auth.user.photos || [])
const remaining = computed(() => Math.max(0, 3 - photos.value.length))
const form = reactive({ nickname: auth.user.nickname, qq: auth.user.qq || '', bio: auth.user.bio || '' })
const joined = new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: 'long' }).format(new Date(auth.user.created_at))
async function save() {
  busy.value = true
  try { const { data } = await api.patch('/users/me', form); auth.updateUser(data); toast.success('个人资料已保存') }
  catch (error) { toast.error(errorMessage(error)) } finally { busy.value = false }
}
async function uploadPhotos(event) {
  const files = [...event.target.files]
  event.target.value = ''
  if (!files.length) return
  if (files.length > remaining.value) return toast.error(`还可以上传 ${remaining.value} 张图片`)
  if (files.some((file) => file.size > 5 * 1024 * 1024)) return toast.error('单张图片不能超过 5 MiB')
  const body = new FormData()
  files.forEach((file) => body.append('photos', file))
  photoBusy.value = true
  try {
    const { data } = await api.post('/users/me/photos', body)
    photos.value = data.photos
    auth.updateUser({ ...auth.user, photos: data.photos })
    toast.success('图片已上传')
  } catch (error) { toast.error(errorMessage(error)) } finally { photoBusy.value = false }
}
async function deletePhoto(photo) {
  photoBusy.value = true
  try {
    const { data } = await api.delete(`/users/me/photos/${photo.id}`)
    photos.value = data.photos
    auth.updateUser({ ...auth.user, photos: data.photos })
    toast.success('图片已删除')
  } catch (error) { toast.error(errorMessage(error)) } finally { photoBusy.value = false }
}
</script>

<template>
  <div class="page inner-page profile-page">
    <div class="page-title"><div><span class="eyebrow">PERSONAL SETTINGS</span><h1>个人设置</h1><p>管理公开资料、权限等级与协作联系方式。</p></div></div>
    <div class="profile-layout">
      <aside class="profile-summary">
        <span class="profile-avatar">{{ auth.user.nickname.slice(0, 1) }}</span>
        <h2>{{ auth.user.nickname }}</h2><p>@{{ auth.user.username }}</p>
        <div class="profile-role-tags">
          <span v-if="auth.isAdmin" class="admin-tag"><ShieldCheck :size="15" />管理员</span>
          <span v-else class="role-tag" :class="`role-${auth.user.role}`">
            <Store v-if="auth.user.role === 'staff'" :size="15" />
            <Heart v-else-if="auth.user.role === 'volunteer'" :size="15" />
            <UserRound v-else :size="15" />{{ roleLabel(auth.user) }}
          </span>
        </div>
        <p v-if="!auth.isAdmin" class="role-hint muted">{{ ROLE_HINTS[auth.user.role] }}</p>
        <div class="profile-divider" />
        <span class="profile-since"><CalendarDays :size="16" />{{ joined }} 加入</span>
      </aside>
      <section class="profile-form-section">
        <div class="section-heading compact"><div><span class="section-index">01</span><h2>公开资料</h2><p>昵称和简介会展示在委托中</p></div></div>
        <form class="form-stack" @submit.prevent="save">
          <label>昵称<input v-model.trim="form.nickname" required maxlength="32" /></label>
          <label>QQ 号<input v-model.trim="form.qq" inputmode="numeric" pattern="[0-9]{5,20}" maxlength="20" placeholder="接单人需要靠它联系你" /><small>{{ ['staff', 'volunteer'].includes(auth.user.role) ? `${roleLabel(auth.user)}的 QQ 和个人资料会向所有访客公开` : '发布委托后，登录用户可在委托详情看到该 QQ，用于洽谈接取' }}</small></label>
          <label>个人简介<textarea v-model.trim="form.bio" maxlength="300" rows="6" placeholder="简单介绍你擅长的事情、空闲时间等"></textarea><small>{{ form.bio.length }}/300</small></label>
          <div><button class="button" :disabled="busy"><Save :size="17" />{{ busy ? '保存中…' : '保存更改' }}</button></div>
        </form>
        <div class="profile-photo-section">
          <div class="section-heading compact"><div><span class="section-index">02</span><h2>介绍图片</h2><p>最多 3 张，单张不超过 5 MiB</p></div></div>
          <div class="photo-grid profile-photo-grid">
            <figure v-for="photo in photos" :key="photo.id" :class="{ blocked: !photo.is_visible }">
              <img :src="photo.image_url" alt="个人介绍图片" />
              <span v-if="!photo.is_visible" class="photo-blocked"><EyeOff :size="14" />已屏蔽</span>
              <button class="icon-button photo-delete" type="button" title="删除图片" aria-label="删除图片" :disabled="photoBusy" @click="deletePhoto(photo)"><Trash2 :size="16" /></button>
            </figure>
            <label v-if="remaining" class="photo-add" :class="{ disabled: photoBusy }">
              <ImagePlus :size="24" /><span>{{ photoBusy ? '上传中…' : '添加图片' }}</span>
              <input type="file" accept="image/jpeg,image/png,image/gif,image/webp" multiple :disabled="photoBusy" @change="uploadPhotos" />
            </label>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>
