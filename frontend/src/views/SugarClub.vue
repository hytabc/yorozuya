<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { Camera, Crown, HeartHandshake, ImagePlus, MessageCircle, Pencil, Save, Trash2, X } from 'lucide-vue-next'
import { api, errorMessage, imageUploadErrorMessage } from '../api'
import { useAuthStore } from '../stores/auth'
import { useToast } from '../composables/toast'

const MAX_IMAGE_BYTES = 5 * 1024 * 1024
const MAX_PHOTOS = 6
const SUPPORTED_IMAGE_TYPES = new Set(['image/jpeg', 'image/png', 'image/gif', 'image/webp'])
const auth = useAuthStore()
const toast = useToast()
const profiles = ref([])
const topPairs = ref([])
const myPairs = ref([])
const loading = ref(true)
const detail = ref(null)
const detailLoading = ref(false)
const editorOpen = ref(false)
const saving = ref(false)
const pendingPhotos = ref([])
const form = reactive({ about: '' })

const ownProfile = computed(() => profiles.value.find((profile) => profile.user.id === auth.user.id) || null)
const activePair = computed(() => myPairs.value.find((pair) => pair.status === 'active') || null)
const pendingPairs = computed(() => myPairs.value.filter((pair) => pair.status === 'pending'))
const canAddPhotos = computed(() => (ownProfile.value?.photos.length || 0) + pendingPhotos.value.length < MAX_PHOTOS)

function partner(pair) {
  return pair.first_user.id === auth.user.id ? pair.second_user : pair.first_user
}

function duration(seconds) {
  const days = Math.floor(seconds / 86400)
  if (days) return `${days} 天`
  const hours = Math.floor(seconds / 3600)
  if (hours) return `${hours} 小时`
  return '刚刚开始'
}

function setEditor(profile = ownProfile.value) {
  form.about = profile?.about || ''
  clearPendingPhotos()
  editorOpen.value = true
}

function clearPendingPhotos() {
  pendingPhotos.value.forEach((item) => URL.revokeObjectURL(item.url))
  pendingPhotos.value = []
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
    const [profileResponse, topResponse, pairResponse] = await Promise.all([
      api.get('/sugar/profiles'),
      api.get('/sugar/pairs/top'),
      api.get('/sugar/pairs/mine'),
    ])
    profiles.value = profileResponse.data
    topPairs.value = topResponse.data
    myPairs.value = pairResponse.data
  } catch (error) {
    toast.error(errorMessage(error, '砂糖社加载失败'))
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
    await api.post('/sugar/profile', body)
    clearPendingPhotos()
    editorOpen.value = false
    await load()
    toast.success('砂糖社档案已保存')
  } catch (error) {
    toast.error(pendingPhotos.value.length ? imageUploadErrorMessage(error) : errorMessage(error))
  } finally {
    saving.value = false
  }
}

async function deletePhoto(photo) {
  if (!window.confirm('确定删除这张照片吗？')) return
  try {
    await api.delete(`/sugar/photos/${photo.id}`)
    await load()
  } catch (error) {
    toast.error(errorMessage(error))
  }
}

async function deleteProfile() {
  if (!window.confirm('确定删除已登记的砂糖社资料吗？进行中的关系也会结束。')) return
  try {
    await api.delete('/sugar/profile')
    editorOpen.value = false
    await load()
    toast.success('砂糖社资料已删除')
  } catch (error) {
    toast.error(errorMessage(error))
  }
}

async function openDetail(userId) {
  detail.value = null
  detailLoading.value = true
  try {
    detail.value = (await api.get(`/sugar/profiles/${userId}`)).data
  } catch (error) {
    toast.error(errorMessage(error, '无法加载该档案'))
  } finally {
    detailLoading.value = false
  }
}

async function confirmPair() {
  if (!detail.value) return
  try {
    const { data } = await api.post(`/sugar/pairs/${detail.value.user.id}/confirm`)
    toast.success(data.status === 'active' ? '已登记为砂糖' : '已等待对方确认')
    await load()
    detail.value = (await api.get(`/sugar/profiles/${detail.value.user.id}`)).data
  } catch (error) {
    toast.error(errorMessage(error))
  }
}

async function endPair(pair) {
  if (!window.confirm('确定结束这段砂糖关系吗？')) return
  try {
    await api.post(`/sugar/pairs/${pair.id}/end`)
    detail.value = null
    await load()
    toast.success('砂糖关系已结束')
  } catch (error) {
    toast.error(errorMessage(error))
  }
}

onMounted(load)
onBeforeUnmount(clearPendingPhotos)
</script>

<template>
  <div class="page inner-page sugar-page">
    <div class="page-title sugar-title">
      <div><span class="eyebrow"><HeartHandshake :size="15" /> SUGAR CLUB</span><h1>砂糖社</h1><p>在这里留下你的名片，也找到愿意相识的人。</p></div>
      <button class="button" @click="setEditor()"><Pencil :size="17" />{{ ownProfile ? '编辑档案' : '登记资料' }}</button>
    </div>

    <section v-if="activePair || pendingPairs.length" class="sugar-status" :class="{ active: activePair }">
      <HeartHandshake :size="22" />
      <div v-if="activePair"><small>当前砂糖</small><strong>{{ partner(activePair).nickname }}</strong><span>已维持 {{ duration(activePair.duration_seconds) }}</span></div>
      <div v-else class="pending-sugar-list"><small>待确认砂糖</small><div v-for="pair in pendingPairs" :key="pair.id" class="pending-sugar-row"><strong>{{ partner(pair).nickname }}</strong><span>{{ pair.initiated_by_id === auth.user.id ? '等待对方确认' : '等待你的确认' }}</span><button class="button secondary small" @click="openDetail(partner(pair).id)">查看</button></div></div>
      <button v-if="activePair" class="button secondary small" @click="endPair(activePair)">结束关系</button>
    </section>

    <section class="sugar-ranking">
      <div class="section-heading compact"><div><span class="section-index">01</span><h2>砂糖榜</h2><p>维持时间最长的三对砂糖</p></div></div>
      <div v-if="topPairs.length" class="pair-grid">
        <article v-for="(pair, index) in topPairs" :key="pair.id" class="pair-card">
          <span class="pair-rank">0{{ index + 1 }}</span>
          <Crown v-if="index === 0" :size="18" />
          <h3>{{ pair.first_user.nickname }} <span>&amp;</span> {{ pair.second_user.nickname }}</h3>
          <p>{{ duration(pair.duration_seconds) }}</p>
          <small :class="pair.status">{{ pair.status === 'active' ? '仍在维持' : '已结束' }}</small>
        </article>
      </div>
      <div v-else class="sugar-empty"><Crown :size="24" /><span>还没有已确认的砂糖</span></div>
    </section>

    <section class="sugar-directory">
      <div class="section-heading compact"><div><span class="section-index">02</span><h2>砂糖名片</h2><p>点击卡片查看资料</p></div></div>
      <div v-if="loading" class="sugar-card-grid"><div v-for="i in 6" :key="i" class="sugar-card skeleton" /></div>
      <div v-else-if="profiles.length" class="sugar-card-grid">
        <button v-for="profile in profiles" :key="profile.id" class="sugar-card" type="button" @click="openDetail(profile.user.id)">
          <img :src="profile.photos[0]?.image_url" :alt="`${profile.user.nickname} 的照片`" />
          <span class="sugar-card-body"><strong>{{ profile.user.nickname }}</strong><small>{{ profile.about }}</small></span>
          <span v-if="profile.user.id === auth.user.id" class="mine-tag">我的档案</span>
        </button>
      </div>
      <div v-else class="sugar-empty"><Camera :size="24" /><span>还没有公开名片</span></div>
    </section>

    <div v-if="editorOpen" class="modal-backdrop" @mousedown.self="editorOpen = false">
      <section class="dialog sugar-editor" role="dialog" aria-modal="true" aria-label="登记砂糖社资料">
        <button class="icon-button dialog-close" title="关闭" aria-label="关闭" @click="editorOpen = false"><X :size="18" /></button>
        <div class="dialog-heading"><span class="eyebrow">SUGAR PROFILE</span><h2>{{ ownProfile ? '编辑我的名片' : '登记我的名片' }}</h2></div>
        <form class="form-stack" @submit.prevent="saveProfile">
          <label>介绍<textarea v-model="form.about" rows="5" maxlength="1000" placeholder="写下想让别人认识的你" /><small>{{ form.about.length }}/1000</small></label>
          <div class="photo-field"><span>照片 <small>单张不超过 5 MiB，最多 {{ MAX_PHOTOS }} 张</small></span>
            <div class="photo-grid edit">
              <figure v-for="photo in ownProfile?.photos || []" :key="photo.id"><img :src="photo.image_url" alt="已上传照片" /><button class="icon-button photo-delete" type="button" title="删除照片" aria-label="删除照片" @click="deletePhoto(photo)"><Trash2 :size="15" /></button></figure>
              <figure v-for="(photo, index) in pendingPhotos" :key="photo.url"><img :src="photo.url" alt="待上传照片" /><button class="icon-button photo-delete" type="button" title="移除照片" aria-label="移除照片" @click="removePending(index)"><X :size="15" /></button></figure>
              <label v-if="canAddPhotos" class="photo-add"><ImagePlus :size="22" /><input type="file" accept="image/jpeg,image/png,image/gif,image/webp" multiple @change="selectPhotos" /></label>
            </div>
          </div>
          <div class="dialog-footer"><button v-if="ownProfile" class="button danger small" type="button" @click="deleteProfile">删除档案</button><span class="dialog-footer-spacer" /><button class="button secondary" type="button" @click="editorOpen = false">取消</button><button class="button" :disabled="saving"><Save :size="16" />{{ saving ? '保存中…' : '保存档案' }}</button></div>
        </form>
      </section>
    </div>

    <div v-if="detail || detailLoading" class="modal-backdrop" @mousedown.self="detail = null">
      <section class="dialog sugar-detail" role="dialog" aria-modal="true" aria-label="砂糖社档案">
        <button class="icon-button dialog-close" title="关闭" aria-label="关闭" @click="detail = null"><X :size="18" /></button>
        <p v-if="detailLoading" class="muted">正在加载资料…</p>
        <template v-else-if="detail">
          <div class="dialog-heading"><span class="eyebrow">SUGAR PROFILE</span><h2>{{ detail.user.nickname }}</h2></div>
          <div class="photo-grid detail"><img v-for="photo in detail.photos" :key="photo.id" :src="photo.image_url" :alt="`${detail.user.nickname} 的照片`" /></div>
          <p class="sugar-about">{{ detail.about }}</p>
          <div class="sugar-qq"><MessageCircle :size="17" /><span><small>QQ</small><strong>{{ detail.qq || '暂未填写' }}</strong></span></div>
          <div v-if="detail.user.id !== auth.user.id" class="dialog-footer sugar-detail-actions">
            <span v-if="detail.relationship?.status === 'active'" class="muted">你们正在维持砂糖关系</span>
            <span v-else-if="detail.relationship?.status === 'pending' && detail.relationship.initiated_by_id === auth.user.id" class="muted">等待对方确认</span>
            <button v-else class="button" @click="confirmPair"><HeartHandshake :size="17" />{{ detail.relationship?.status === 'pending' ? '确认成为砂糖' : '发起砂糖确认' }}</button>
            <button v-if="detail.relationship?.status === 'active'" class="button danger" @click="endPair(detail.relationship)">结束关系</button>
          </div>
        </template>
      </section>
    </div>
  </div>
</template>
