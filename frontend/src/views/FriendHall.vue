<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { Camera, Check, Crown, EyeOff, ImagePlus, MessageCircle, Pencil, Save, Trash2, UserPlus, UserRound, UsersRound, X } from 'lucide-vue-next'
import { api, errorMessage, imageUploadErrorMessage } from '../api'
import { useToast } from '../composables/toast'
import { useAuthStore } from '../stores/auth'

const MAX_PHOTOS = 5
const MAX_IMAGE_BYTES = 5 * 1024 * 1024
const SUPPORTED_IMAGE_TYPES = new Set(['image/jpeg', 'image/png', 'image/gif', 'image/webp'])

const auth = useAuthStore()
const toast = useToast()
const loading = ref(true)
const profiles = ref([])
const topUsers = ref([])
const requests = ref([])
const editorOpen = ref(false)
const detail = ref(null)
const detailLoading = ref(false)
const saving = ref(false)
const pendingPhotos = ref([])
const form = reactive({ about: '' })

const ownProfile = computed(() => profiles.value.find((profile) => profile.user.id === auth.user?.id) || null)
const incomingRequests = computed(() => requests.value.filter((item) => item.requester_id !== auth.user?.id))
const outgoingRequests = computed(() => requests.value.filter((item) => item.requester_id === auth.user?.id))
const canAddPhotos = computed(() => (ownProfile.value?.photos.length || 0) + pendingPhotos.value.length < MAX_PHOTOS)

function clearPendingPhotos() {
  pendingPhotos.value.forEach((item) => URL.revokeObjectURL(item.url))
  pendingPhotos.value = []
}

function setEditor(profile = ownProfile.value) {
  form.about = profile?.about || ''
  clearPendingPhotos()
  editorOpen.value = true
}

function selectPhotos(event) {
  const files = [...event.target.files]
  event.target.value = ''
  const available = MAX_PHOTOS - (ownProfile.value?.photos.length || 0) - pendingPhotos.value.length
  const accepted = []
  for (const file of files.slice(0, available)) {
    if (file.size > MAX_IMAGE_BYTES) {
      toast.error(`${file.name} 超过 5 MiB`)
      continue
    }
    if (!SUPPORTED_IMAGE_TYPES.has(file.type)) {
      toast.error(`${file.name} 仅支持 JPEG、PNG、GIF 或 WebP 格式`)
      continue
    }
    accepted.push({ file, url: URL.createObjectURL(file) })
  }
  pendingPhotos.value.push(...accepted)
  if (files.length > accepted.length) toast.error(`最多保留 ${MAX_PHOTOS} 张照片`)
}

function removePending(index) {
  URL.revokeObjectURL(pendingPhotos.value[index].url)
  pendingPhotos.value.splice(index, 1)
}

async function load() {
  loading.value = true
  try {
    const [profileResponse, topResponse, requestResponse] = await Promise.all([
      api.get('/friends/profiles'),
      api.get('/friends/top'),
      api.get('/friends/requests/mine'),
    ])
    profiles.value = profileResponse.data
    topUsers.value = topResponse.data
    requests.value = requestResponse.data
  } catch (error) {
    toast.error(errorMessage(error, '交友厅加载失败'))
  } finally {
    loading.value = false
  }
}

async function saveProfile() {
  if (!form.about.trim()) return toast.error('请填写介绍')
  if (!ownProfile.value && !pendingPhotos.value.length) return toast.error('首次登记请上传至少一张照片')
  saving.value = true
  try {
    const body = new FormData()
    body.append('about', form.about.trim())
    pendingPhotos.value.forEach(({ file }) => body.append('photos', file))
    await api.post('/friends/profile', body)
    clearPendingPhotos()
    editorOpen.value = false
    await load()
    toast.success('交友厅资料已保存')
  } catch (error) {
    toast.error(pendingPhotos.value.length ? imageUploadErrorMessage(error) : errorMessage(error))
  } finally {
    saving.value = false
  }
}

async function deletePhoto(photo) {
  if (!window.confirm('确定删除这张照片吗？')) return
  try {
    await api.delete(`/friends/photos/${photo.id}`)
    await load()
    toast.success('照片已删除')
  } catch (error) { toast.error(errorMessage(error)) }
}

async function deleteProfile() {
  if (!window.confirm('确定删除交友厅资料吗？已建立的好友关系不会被删除。')) return
  try {
    await api.delete('/friends/profile')
    editorOpen.value = false
    await load()
    toast.success('交友厅资料已删除')
  } catch (error) { toast.error(errorMessage(error)) }
}

async function openDetail(userId) {
  detail.value = null
  detailLoading.value = true
  try {
    detail.value = (await api.get(`/friends/profiles/${userId}`)).data
  } catch (error) {
    toast.error(errorMessage(error, '无法加载该档案'))
  } finally {
    detailLoading.value = false
  }
}

async function sendRequest() {
  if (!detail.value) return
  try {
    const { data } = await api.post(`/friends/requests/${detail.value.user.id}`)
    detail.value.relationship = data
    await load()
    toast.success('好友申请已发送')
  } catch (error) { toast.error(errorMessage(error)) }
}

async function resolveRequest(request, action) {
  try {
    const { data } = await api.post(`/friends/requests/${request.id}/${action}`)
    requests.value = requests.value.filter((item) => item.id !== request.id)
    if (detail.value?.user.id === data.requester.id || detail.value?.user.id === data.target.id) detail.value.relationship = data
    await load()
    toast.success(action === 'accept' ? '已添加好友' : '已拒绝好友申请')
  } catch (error) { toast.error(errorMessage(error)) }
}

async function cancelRequest(request) {
  try {
    await api.delete(`/friends/requests/${request.id}`)
    await load()
    if (detail.value?.relationship?.id === request.id) detail.value.relationship = null
    toast.success('好友申请已取消')
  } catch (error) { toast.error(errorMessage(error)) }
}

onMounted(load)
onBeforeUnmount(clearPendingPhotos)
</script>

<template>
  <div class="page inner-page sugar-page friend-page">
    <div class="page-title sugar-title">
      <div><span class="eyebrow"><UsersRound :size="15" /> FRIEND HALL</span><h1>交友厅</h1><p>留下你的名片，认识更多一起玩 VRChat 的人。</p></div>
      <button class="button" @click="setEditor()"><Pencil :size="17" />{{ ownProfile ? '编辑资料' : '登记资料' }}</button>
    </div>

    <section class="sugar-ranking">
      <div class="section-heading compact"><div><span class="section-index">01</span><h2>好友榜</h2><p>好友数量最多的三位用户</p></div></div>
      <div v-if="topUsers.length" class="pair-grid friend-ranking-grid">
        <article v-for="(item, index) in topUsers" :key="item.user.id" class="pair-card friend-rank-card">
          <span class="pair-rank">0{{ index + 1 }}</span><Crown v-if="index === 0" :size="18" />
          <img v-if="item.photo" :src="item.photo.image_url" :alt="`${item.user.nickname} 的照片`" />
          <UserRound v-else class="friend-rank-placeholder" :size="32" />
          <h3>{{ item.user.nickname }}</h3><p>{{ item.friend_count }} 位好友</p>
        </article>
      </div>
      <div v-else class="sugar-empty"><Crown :size="24" /><span>还没有好友榜记录</span></div>
    </section>

    <section class="friend-requests" v-if="incomingRequests.length || outgoingRequests.length">
      <div class="section-heading compact"><div><span class="section-index">02</span><h2>好友申请</h2><p>处理想认识你的用户</p></div></div>
      <div class="friend-request-list">
        <div v-for="request in incomingRequests" :key="request.id" class="friend-request-row">
          <UserRound :size="20" /><div><strong>{{ request.requester.nickname }}</strong><span>想添加你为好友</span></div>
          <button class="button small" @click="resolveRequest(request, 'accept')"><Check :size="15" />同意</button>
          <button class="button secondary small" @click="resolveRequest(request, 'reject')">拒绝</button>
        </div>
        <div v-for="request in outgoingRequests" :key="request.id" class="friend-request-row outgoing">
          <UserPlus :size="20" /><div><strong>{{ request.target.nickname }}</strong><span>等待对方处理你的申请</span></div>
          <button class="button secondary small" @click="cancelRequest(request)">取消申请</button>
        </div>
      </div>
    </section>

    <section class="sugar-directory">
      <div class="section-heading compact"><div><span class="section-index">03</span><h2>交友名片</h2><p>点击卡片查看资料并申请添加好友</p></div></div>
      <div v-if="loading" class="sugar-card-grid"><div v-for="i in 6" :key="i" class="sugar-card skeleton" /></div>
      <div v-else-if="profiles.length" class="sugar-card-grid">
        <button v-for="profile in profiles" :key="profile.id" class="sugar-card" type="button" @click="openDetail(profile.user.id)">
          <img v-if="profile.photos[0]" :src="profile.photos[0].image_url" :alt="`${profile.user.nickname} 的照片`" />
          <div v-else class="friend-card-placeholder"><UserRound :size="38" /></div>
          <span class="sugar-card-body"><strong>{{ profile.user.nickname }}</strong><small>{{ profile.about }}</small><em><UsersRound :size="13" />{{ profile.friend_count }} 位好友</em></span>
          <span v-if="profile.user.id === auth.user.id" class="mine-tag">我的资料</span>
        </button>
      </div>
      <div v-else class="sugar-empty"><Camera :size="24" /><span>还没有公开交友名片</span></div>
    </section>

    <div v-if="editorOpen" class="modal-backdrop" @mousedown.self="editorOpen = false">
      <section class="dialog sugar-editor" role="dialog" aria-modal="true" aria-label="登记交友厅资料">
        <button class="icon-button dialog-close" title="关闭" aria-label="关闭" @click="editorOpen = false"><X :size="18" /></button>
        <div class="dialog-heading"><span class="eyebrow">FRIEND PROFILE</span><h2>{{ ownProfile ? '编辑我的资料' : '登记我的资料' }}</h2></div>
        <form class="form-stack" @submit.prevent="saveProfile">
          <label>介绍<textarea v-model="form.about" rows="5" maxlength="1000" placeholder="写下兴趣、常去的世界或想认识的朋友类型" /><small>{{ form.about.length }}/1000</small></label>
          <div class="photo-field"><span>照片 <small>单张不超过 5 MiB，最多 {{ MAX_PHOTOS }} 张，新照片需审核</small></span>
            <div class="photo-grid edit">
              <figure v-for="photo in ownProfile?.photos || []" :key="photo.id" :class="{ blocked: !photo.is_visible }"><img :src="photo.image_url" alt="已上传照片" /><span v-if="!photo.is_visible" class="photo-blocked sugar-blocked"><EyeOff :size="14" />{{ photo.admin_note ? `已屏蔽：${photo.admin_note}` : '审核中' }}</span><button class="icon-button photo-delete" type="button" title="删除照片" aria-label="删除照片" @click="deletePhoto(photo)"><Trash2 :size="15" /></button></figure>
              <figure v-for="(photo, index) in pendingPhotos" :key="photo.url"><img :src="photo.url" alt="待上传照片" /><button class="icon-button photo-delete" type="button" title="移除照片" aria-label="移除照片" @click="removePending(index)"><X :size="15" /></button></figure>
              <label v-if="canAddPhotos" class="photo-add"><ImagePlus :size="22" /><input type="file" accept="image/jpeg,image/png,image/gif,image/webp" multiple @change="selectPhotos" /></label>
            </div>
          </div>
          <div class="dialog-footer"><button v-if="ownProfile" class="button danger small" type="button" @click="deleteProfile">删除资料</button><span class="dialog-footer-spacer" /><button class="button secondary" type="button" @click="editorOpen = false">取消</button><button class="button" :disabled="saving"><Save :size="16" />{{ saving ? '保存中…' : '保存资料' }}</button></div>
        </form>
      </section>
    </div>

    <div v-if="detail || detailLoading" class="modal-backdrop" @mousedown.self="detail = null">
      <section class="dialog sugar-detail" role="dialog" aria-modal="true" aria-label="交友厅档案">
        <button class="icon-button dialog-close" title="关闭" aria-label="关闭" @click="detail = null"><X :size="18" /></button>
        <p v-if="detailLoading" class="muted">正在加载资料…</p>
        <template v-else-if="detail">
          <div class="dialog-heading"><span class="eyebrow">FRIEND PROFILE</span><h2>{{ detail.user.nickname }}</h2><p>{{ detail.friend_count }} 位好友</p></div>
          <div class="photo-grid detail"><figure v-for="photo in detail.photos" :key="photo.id" :class="{ blocked: !photo.is_visible }"><img :src="photo.image_url" :alt="`${detail.user.nickname} 的照片`" /><span v-if="!photo.is_visible" class="photo-blocked sugar-blocked"><EyeOff :size="14" />{{ photo.admin_note || '审核中' }}</span></figure><div v-if="!detail.photos.length" class="friend-detail-placeholder"><UserRound :size="38" /><span>暂未公开照片</span></div></div>
          <p class="sugar-about">{{ detail.about }}</p>
          <div v-if="detail.qq !== null || detail.user.id === auth.user.id" class="sugar-qq"><MessageCircle :size="17" /><span><small>QQ</small><strong>{{ detail.qq || '暂未填写' }}</strong></span></div>
          <div v-if="detail.user.id !== auth.user.id" class="dialog-footer sugar-detail-actions">
            <span v-if="detail.relationship?.status === 'accepted'" class="muted">你们已经是好友</span>
            <span v-else-if="detail.relationship?.status === 'pending' && detail.relationship.requester_id === auth.user.id" class="muted">好友申请已发送，等待对方处理</span>
            <button v-else-if="detail.relationship?.status === 'pending'" class="button" @click="resolveRequest(detail.relationship, 'accept')"><Check :size="17" />同意添加好友</button>
            <button v-else class="button" @click="sendRequest"><UserPlus :size="17" />申请添加好友</button>
          </div>
        </template>
      </section>
    </div>
  </div>
</template>

<style scoped>
.friend-ranking-grid .friend-rank-card { min-height: 205px; }
.friend-rank-card > img, .friend-rank-card > .friend-rank-placeholder { width: 58px; height: 58px; margin-top: 18px; border-radius: 50%; object-fit: cover; color: #a7657d; background: #f4eaf0; }
.friend-rank-card > .friend-rank-placeholder { padding: 13px; }
.friend-rank-card h3 { margin-top: 13px; }
.friend-rank-card p { font-family: inherit; font-size: 14px; }
.friend-request-list { display: grid; gap: 8px; margin: 17px 0 55px; }
.friend-request-row { display: flex; align-items: center; gap: 12px; min-height: 60px; padding: 12px 16px; border: 1px solid var(--line); background: white; }
.friend-request-row > svg { flex-shrink: 0; color: #a7657d; }
.friend-request-row > div { display: grid; gap: 3px; min-width: 0; margin-right: auto; }
.friend-request-row strong { overflow-wrap: anywhere; }
.friend-request-row span { color: var(--muted); font-size: 12px; }
.friend-card-placeholder { display: grid; place-items: center; height: 225px; color: #a7657d; background: #f4eaf0; }
.sugar-card-body em { display: flex; align-items: center; gap: 4px; color: #a7657d; font-size: 11px; font-style: normal; }
.friend-detail-placeholder { display: grid; place-items: center; min-height: 150px; gap: 8px; color: var(--muted); }
@media (max-width: 680px) {
  .friend-request-row { align-items: flex-start; flex-wrap: wrap; }
  .friend-request-row > div { min-width: calc(100% - 45px); }
  .friend-request-row .button { margin-left: 32px; }
}
</style>
