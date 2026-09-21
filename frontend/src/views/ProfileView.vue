<script setup>
import { computed, reactive, ref } from 'vue'
import { CalendarDays, EyeOff, Heart, ImagePlus, KeyRound, Mail, Moon, Save, ShieldCheck, Store, Sun, Trash2, UserRound } from '@lucide/vue'
import { api, errorMessage, imageUploadErrorMessage } from '../api'
import { track } from '../analytics'
import { useAuthStore } from '../stores/auth'
import { useToast } from '../composables/toast'
import { MODE_SOURCES, THEMES, applyThemeById, mode, modeSource, setModeSource, theme } from '../composables/theme'
import { roleLabel, ROLE_HINTS } from '../constants'
import UserAvatar from '../components/UserAvatar.vue'
import UserTitleTag from '../components/UserTitleTag.vue'
import LazyImage from '../components/LazyImage.vue'
import ImageLightbox from '../components/ImageLightbox.vue'

const MAX_AVATAR_BYTES = 2 * 1024 * 1024
const AVATAR_TYPES = new Set(['image/jpeg', 'image/png'])

const auth = useAuthStore()
const toast = useToast()
const busy = ref(false)
const passwordBusy = ref(false)
const photoBusy = ref(false)
const avatarBusy = ref(false)
const appearanceBusy = ref(false)
const photos = ref(auth.user.photos || [])
const viewerSrc = ref('')
const viewerAlt = ref('')

function openViewer(photo) {
  viewerSrc.value = photo.image_url
  viewerAlt.value = '个人介绍图片'
}
const remaining = computed(() => Math.max(0, 3 - photos.value.length))
const SUPPORTED_IMAGE_TYPES = new Set(['image/jpeg', 'image/png', 'image/gif', 'image/webp'])
const form = reactive({
  nickname: auth.user.nickname,
  qq: auth.user.qq || '',
  qq_public: Boolean(auth.user.qq_public),
  bio: auth.user.bio || '',
})
const passwordForm = reactive({ current: '', password: '', confirm: '' })
const emailForm = reactive({ email: '', currentPassword: '' })
const emailBusy = ref(false)
const notifyBusy = ref(false)
const joined = new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: 'long' }).format(new Date(auth.user.created_at))
async function bindEmail() {
  const address = emailForm.email.trim()
  if (!address) return toast.error('请输入邮箱地址')
  if (!emailForm.currentPassword) return toast.error('请输入当前密码')
  if (!/^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$/.test(address)) return toast.error('邮箱格式不正确')
  emailBusy.value = true
  try {
    await api.post('/users/me/email', { email: address, current_password: emailForm.currentPassword })
    // 拉一次最新状态：pending_email 与验证进度都以后端为准
    const { data } = await api.get('/auth/me')
    auth.updateUser(data)
    emailForm.email = ''
    toast.success('验证邮件已发送，请到邮箱里点击链接完成验证')
    track('profile.email_bind')
  } catch (error) {
    toast.error(errorMessage(error))
  } finally {
    emailForm.currentPassword = ''
    emailBusy.value = false
  }
}

async function toggleNotify() {
  notifyBusy.value = true
  try {
    const { data } = await api.patch('/users/me/email-notify', { notify_email: !auth.user.notify_email })
    auth.updateUser(data)
    toast.success(data.notify_email ? '已开启邮件通知' : '已关闭邮件通知')
  } catch (error) {
    toast.error(errorMessage(error))
  } finally {
    notifyBusy.value = false
  }
}

// 外观偏好落到账号上：路径与悬浮按钮一致，都走 PATCH /users/me/theme。
async function saveAppearance(partial) {
  appearanceBusy.value = true
  try {
    const { data } = await api.patch('/users/me/theme', partial)
    await auth.patchUser({ theme_mode: data.theme_mode, theme_style: data.theme_style })
  } catch (error) {
    toast.error(errorMessage(error))
  } finally {
    appearanceBusy.value = false
  }
}

// 先本地生效再落库：切换不该等网络往返，失败时提示但不回滚（下次登录会回到服务端的值）。
function chooseTheme(id) {
  applyThemeById(id)
  saveAppearance({ theme_style: id })
}

function chooseMode(id) {
  setModeSource(id)
  saveAppearance({ theme_mode: id })
}

async function save() {
  busy.value = true
  try { const { data } = await api.patch('/users/me', form); auth.updateUser(data); toast.success('个人资料已保存'); track('profile.save') }
  catch (error) { toast.error(errorMessage(error)) } finally { busy.value = false }
}
async function changePassword() {
  if (!passwordForm.current) return toast.error('请输入当前密码')
  if (passwordForm.password.length < 8) return toast.error('新密码至少需要 8 位')
  if (passwordForm.password !== passwordForm.confirm) return toast.error('两次输入的新密码不一致')
  passwordBusy.value = true
  try {
    const { data } = await api.patch('/users/me/password', {
      current_password: passwordForm.current,
      password: passwordForm.password,
    })
    auth.updateUser(data)
    passwordForm.current = ''
    passwordForm.password = ''
    passwordForm.confirm = ''
    toast.success('密码已重置，请使用新密码登录')
  } catch (error) { toast.error(errorMessage(error)) } finally { passwordBusy.value = false }
}
async function uploadPhotos(event) {
  const files = [...event.target.files]
  event.target.value = ''
  if (!files.length) return
  if (files.length > remaining.value) return toast.error(`还可以上传 ${remaining.value} 张图片`)
  if (files.some((file) => file.size > 5 * 1024 * 1024)) return toast.error('单张图片不能超过 5 MiB')
  if (files.some((file) => !SUPPORTED_IMAGE_TYPES.has(file.type))) return toast.error('仅支持 JPEG、PNG、GIF 或 WebP 图片')
  const body = new FormData()
  files.forEach((file) => body.append('photos', file))
  photoBusy.value = true
  try {
    const { data } = await api.post('/users/me/photos', body)
    photos.value = data.photos
    auth.updateUser({ ...auth.user, photos: data.photos })
    toast.success('图片已上传')
  } catch (error) { toast.error(imageUploadErrorMessage(error)) } finally { photoBusy.value = false }
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
function applyAvatar(data) {
  auth.updateUser({ ...auth.user, avatar_url: data.avatar_url, avatar_visible: data.avatar_visible })
}
async function uploadAvatar(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  if (file.size > MAX_AVATAR_BYTES) return toast.error('头像图片不能超过 2 MB')
  if (!AVATAR_TYPES.has(file.type)) return toast.error('头像仅支持 PNG 或 JPG 格式')
  avatarBusy.value = true
  try {
    const body = new FormData()
    body.append('avatar', file)
    const { data } = await api.post('/users/me/avatar', body)
    applyAvatar(data)
    toast.success('头像已上传，等待管理员审核')
  } catch (error) { toast.error(imageUploadErrorMessage(error)) } finally { avatarBusy.value = false }
}
async function deleteAvatar() {
  avatarBusy.value = true
  try {
    const { data } = await api.delete('/users/me/avatar')
    applyAvatar(data)
    toast.success('头像已删除')
  } catch (error) { toast.error(errorMessage(error)) } finally { avatarBusy.value = false }
}
</script>

<template>
  <div class="page inner-page profile-page">
    <div class="page-title"><div><span class="eyebrow">PERSONAL SETTINGS</span><h1>个人设置</h1><p>管理公开资料、权限等级与协作联系方式。</p></div></div>
    <div class="profile-layout">
      <aside class="profile-summary">
        <UserAvatar :user="auth.user" :size="96" />
        <div class="avatar-actions">
          <label class="button secondary small avatar-upload" :class="{ disabled: avatarBusy }">
            <ImagePlus :size="15" />{{ avatarBusy ? '上传中…' : auth.user.avatar_url ? '更换头像' : '上传头像' }}
            <input type="file" accept="image/png,image/jpeg" :disabled="avatarBusy" @change="uploadAvatar" />
          </label>
          <button v-if="auth.user.avatar_url" class="icon-button" type="button" title="删除头像" aria-label="删除头像" :disabled="avatarBusy" @click="deleteAvatar"><Trash2 :size="16" /></button>
        </div>
        <p class="avatar-hint muted">仅支持 PNG / JPG，最大 2 MB；上传后需管理员审核通过才会公开展示。</p>
        <h2>{{ auth.user.nickname }}</h2><p>@{{ auth.user.username }}</p>
        <div class="profile-role-tags">
          <span v-if="auth.isAdmin" class="admin-tag"><ShieldCheck :size="15" />超级管理员</span>
          <span v-else class="role-tag" :class="`role-${auth.role}`">
            <Store v-if="auth.role === 'staff'" :size="15" />
            <Heart v-else-if="auth.role === 'volunteer'" :size="15" />
            <UserRound v-else :size="15" />{{ roleLabel({ is_admin: auth.isAdmin, role: auth.role }) }}
          </span>
          <UserTitleTag :title="auth.user.title" />
          <span v-if="auth.isBetaTester" class="role-tag beta-tag">内测用户</span>
        </div>
        <p v-if="!auth.isAdmin" class="role-hint muted">{{ ROLE_HINTS[auth.role] }}</p>
        <div class="profile-divider" />
        <span class="profile-since"><CalendarDays :size="16" />{{ joined }} 加入</span>
      </aside>
      <section class="profile-form-section">
        <div class="section-heading compact"><div><span class="section-index">01</span><h2>公开资料</h2><p>昵称和简介会展示在委托中</p></div></div>
        <form class="form-stack" @submit.prevent="save">
          <label>昵称<input v-model.trim="form.nickname" required maxlength="32" /></label>
          <label>QQ 号<input v-model.trim="form.qq" inputmode="numeric" pattern="[0-9]{5,20}" maxlength="20" placeholder="接单人需要靠它联系你" /><small>{{ auth.role === 'staff' ? '管理员 QQ 会在成员名录中向所有访客公开' : '委托双方始终可以看到彼此的 QQ，用于协作联系' }}</small></label>
          <label v-if="auth.role === 'volunteer' || auth.role === 'staff'" class="checkbox-inline profile-qq-public"><input v-model="form.qq_public" type="checkbox" /><span>在成员名录中公开 QQ 号</span></label>
          <label>个人简介<textarea v-model.trim="form.bio" maxlength="300" rows="6" placeholder="简单介绍你擅长的事情、空闲时间等"></textarea><small>{{ form.bio.length }}/300</small></label>
          <div><button class="button" :disabled="busy"><Save :size="17" />{{ busy ? '保存中…' : '保存更改' }}</button></div>
        </form>
        <div class="profile-email-section">
          <div class="section-heading compact"><div><span class="section-index">02</span><h2>邮箱</h2><p>用于接收委托进展通知，也是忘记密码时找回账号的唯一途径</p></div></div>
          <div class="email-status">
            <span v-if="auth.user.email_verified" class="email-badge verified"><ShieldCheck :size="15" />已验证</span>
            <span v-else class="email-badge pending">未验证</span>
            <span class="email-value">{{ auth.user.email || '尚未绑定邮箱' }}</span>
          </div>
          <p v-if="auth.user.pending_email" class="email-pending">待确认的新邮箱：<strong>{{ auth.user.pending_email }}</strong>，请到该邮箱点击验证链接；确认前当前邮箱仍然有效。</p>
          <form class="form-stack" @submit.prevent="bindEmail">
            <label>{{ auth.user.email_verified ? '更换邮箱' : '绑定邮箱' }}<input v-model.trim="emailForm.email" type="email" autocomplete="email" placeholder="example@example.com" /><small>我们会先向该地址发送确认链接，验证通过后才会生效，并需要重新登录。</small></label>
            <label>当前密码<input v-model="emailForm.currentPassword" type="password" autocomplete="current-password" maxlength="128" required /></label>
            <div><button class="button" :disabled="emailBusy"><Mail :size="17" />{{ emailBusy ? '发送中…' : '发送验证邮件' }}</button></div>
          </form>
          <label class="checkbox-inline email-notify-toggle">
            <input :checked="Boolean(auth.user.notify_email)" type="checkbox" :disabled="notifyBusy" @change="toggleNotify" />
            <span>接收委托进度、审核结果等邮件通知（账号安全类邮件不受此开关影响）</span>
          </label>
        </div>
        <div class="profile-password-section">
          <div class="section-heading compact"><div><span class="section-index">03</span><h2>重置密码</h2><p>先验证当前密码，再设置至少 8 位的新密码</p></div></div>
          <form class="form-stack" @submit.prevent="changePassword">
            <label>当前密码<input v-model="passwordForm.current" type="password" required maxlength="128" autocomplete="current-password" placeholder="请输入当前密码" /></label>
            <label>新密码<input v-model="passwordForm.password" type="password" required minlength="8" maxlength="72" autocomplete="new-password" placeholder="至少 8 位" /></label>
            <label>确认新密码<input v-model="passwordForm.confirm" type="password" required minlength="8" maxlength="72" autocomplete="new-password" placeholder="再次输入新密码" /></label>
            <div><button class="button" :disabled="passwordBusy"><KeyRound :size="17" />{{ passwordBusy ? '重置中…' : '确认重置密码' }}</button></div>
          </form>
        </div>
        <div class="profile-photo-section">
          <div class="section-heading compact"><div><span class="section-index">04</span><h2>介绍图片</h2><p>最多 3 张，单张不超过 5 MiB</p></div></div>
          <div class="photo-grid profile-photo-grid">
            <figure v-for="photo in photos" :key="photo.id" :class="{ blocked: !photo.is_visible }">
              <LazyImage class="zoomable" :src="photo.image_url" alt="个人介绍图片" @click="openViewer(photo)" />
              <span v-if="!photo.is_visible" class="photo-blocked"><EyeOff :size="14" />已屏蔽</span>
              <button class="icon-button photo-delete" type="button" title="删除图片" aria-label="删除图片" :disabled="photoBusy" @click="deletePhoto(photo)"><Trash2 :size="16" /></button>
            </figure>
            <label v-if="remaining" class="photo-add" :class="{ disabled: photoBusy }">
              <ImagePlus :size="24" /><span>{{ photoBusy ? '上传中…' : '添加图片' }}</span>
              <input type="file" accept="image/jpeg,image/png,image/gif,image/webp" multiple :disabled="photoBusy" @change="uploadPhotos" />
            </label>
          </div>
        </div>
        <div class="profile-appearance-section">
          <div class="section-heading compact"><div><span class="section-index">05</span><h2>外观</h2><p>页面风格与深色模式偏好保存在账号上，换设备登录依然生效</p></div></div>
          <p class="appearance-label">页面风格</p>
          <div class="mode-options">
            <label v-for="item in THEMES" :key="item.id" class="mode-option" :class="{ active: theme === item.id }">
              <input type="radio" name="page-theme" :value="item.id" :checked="theme === item.id" @change="chooseTheme(item.id)" />
              <span class="mode-option-text"><strong>{{ item.label }}</strong><small>{{ item.id === 'pixel' ? '像素木质招牌与直角硬面板' : '默认的纸色与圆角风格' }}</small></span>
            </label>
          </div>
          <p class="appearance-label">深色模式</p>
          <div class="mode-options">
            <label v-for="item in MODE_SOURCES" :key="item.id" class="mode-option" :class="{ active: modeSource === item.id }">
              <input type="radio" name="color-mode" :value="item.id" :checked="modeSource === item.id" @change="chooseMode(item.id)" />
              <span class="mode-option-text"><strong>{{ item.label }}</strong><small>{{ item.hint }}</small></span>
            </label>
          </div>
          <p class="mode-current">
            <component :is="mode === 'night' ? Moon : Sun" :size="15" />
            当前显示：{{ theme === 'pixel' ? '像素风' : '经典风' }} · {{ mode === 'night' ? '夜间模式' : '日间模式' }}
            <span v-if="modeSource === 'day' || modeSource === 'night'">（已固定，不再自动切换）</span>
            <span v-if="appearanceBusy">保存中…</span>
          </p>
        </div>
      </section>
    </div>

    <ImageLightbox v-if="viewerSrc" :src="viewerSrc" :alt="viewerAlt" @close="viewerSrc = ''" />
  </div>
</template>

<style scoped>
.zoomable {
  cursor: zoom-in;
}

/* 外观设置：与「公开资料 / 邮箱 / 重置密码 / 介绍图片」同级的第 05 区 */
.profile-appearance-section {
  margin-top: 42px;
  padding-top: 35px;
  border-top: 1px solid var(--line);
}

.mode-options {
  display: grid;
  gap: 8px;
  margin: 18px 0 14px;
}

/* 「页面风格」「深色模式」两组之间的分组标签 */
.appearance-label {
  margin: 20px 0 -6px;
  color: var(--ink);
  font-size: 12.5px;
  font-weight: 700;
}

.mode-option {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 11px 13px;
  border: 1px solid var(--line);
  border-radius: 6px;
  cursor: pointer;
}

.mode-option:hover {
  border-color: var(--muted);
}

.mode-option.active {
  border-color: var(--green);
  background: var(--green-soft);
}

.mode-option input {
  width: auto;
  margin-top: 2px;
}

.mode-option-text {
  display: grid;
  gap: 2px;
}

.mode-option-text strong {
  font-size: 13px;
}

.mode-option-text small,
.mode-current {
  color: var(--muted);
  font-size: 11.5px;
}

.mode-current {
  display: flex;
  align-items: center;
  gap: 6px;
}

.profile-summary .u-avatar {
  display: flex;
  margin: 0 auto 12px;
}

.avatar-actions {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-bottom: 8px;
}

.avatar-upload {
  position: relative;
  overflow: hidden;
}

.avatar-upload input {
  position: absolute;
  inset: 0;
  opacity: 0;
  cursor: pointer;
}

.avatar-upload.disabled {
  opacity: 0.6;
  pointer-events: none;
}

.avatar-hint {
  max-width: 240px;
  margin: 0 auto 14px;
  font-size: 12px;
  line-height: 1.6;
}

.role-tag.beta-tag {
  color: var(--green);
  background: var(--green-soft);
}

.email-status {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}

.email-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 9px;
  border-radius: 999px;
  font-size: 12px;
}

.email-badge.verified {
  color: var(--green);
  background: var(--green-soft);
}

.email-badge.pending {
  color: #9a6412;
  background: #fdf3e2;
}

.email-value {
  font-size: 14px;
  color: var(--ink);
  word-break: break-all;
}

.email-pending {
  margin: 0 0 14px;
  padding: 10px 12px;
  border-radius: 10px;
  background: #fdf3e2;
  font-size: 13px;
  line-height: 1.6;
}

.email-notify-toggle {
  margin-top: 12px;
}
</style>
