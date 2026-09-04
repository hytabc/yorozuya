<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { EyeOff, Flag, Heart, ImagePlus, Map as MapIcon, Send, UploadCloud, X } from 'lucide-vue-next'
import { api, errorMessage, imageUploadErrorMessage } from '../api'
import { useAuthStore } from '../stores/auth'
import { useToast } from '../composables/toast'
import UserAvatar from './UserAvatar.vue'

const MAX_PHOTO_BYTES = 10 * 1024 * 1024
const PHOTO_TYPES = new Set(['image/jpeg', 'image/png'])

const props = defineProps({ map: { type: Object, required: true } })
const emit = defineEmits(['close', 'updated'])
const auth = useAuthStore()
const toast = useToast()
const busy = ref(false)
const liking = ref(false)
const uploading = ref(false)
const showReport = ref(false)
const reportReason = ref('')

// 上传按钮旁的鼓励文案：推动大家分享在地图里拍摄的实拍照片
const UPLOAD_PROMPT = '在这张地图里拍到了满意的瞬间？上传你的实拍照片——黄昏的天台、迷宫尽头的彩蛋……让没去过的人一眼种草，让去过的人会心一笑。照片经管理员审核后展示。'

const myPhoto = computed(() => props.map.photos.find((photo) => !photo.is_visible) || null)
const publicPhotos = computed(() => props.map.photos.filter((photo) => photo.is_visible))

function onKey(event) { if (event.key === 'Escape') emit('close') }
onMounted(() => { document.body.classList.add('modal-open'); window.addEventListener('keydown', onKey) })
onBeforeUnmount(() => { document.body.classList.remove('modal-open'); window.removeEventListener('keydown', onKey) })

async function toggleLike() {
  if (!auth.isLoggedIn) return toast.error('请先登录后再点赞')
  liking.value = true
  try {
    const { data } = await api.post(`/vr-maps/${props.map.id}/like`)
    emit('updated', { ...props.map, like_count: data.like_count, liked_by_me: data.liked })
    if (data.liked) toast.success('已点赞')
  } catch (error) {
    toast.error(errorMessage(error))
  } finally {
    liking.value = false
  }
}

async function submitReport() {
  if (reportReason.value.trim().length < 2) return toast.error('请填写至少 2 个字符的举报原因')
  busy.value = true
  try {
    const { data } = await api.post(`/vr-maps/${props.map.id}/report`, { reason: reportReason.value.trim() })
    toast.success('举报已提交，管理员会尽快处理')
    showReport.value = false
    reportReason.value = ''
    emit('updated', data)
  } catch (error) {
    toast.error(errorMessage(error))
  } finally {
    busy.value = false
  }
}

async function uploadPhoto(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  if (file.size > MAX_PHOTO_BYTES) return toast.error('地图照片不能超过 10 MB')
  if (!PHOTO_TYPES.has(file.type)) return toast.error('地图照片仅支持 PNG 或 JPG 格式')
  uploading.value = true
  try {
    const body = new FormData()
    body.append('photo', file)
    const { data } = await api.post(`/vr-maps/${props.map.id}/photos`, body)
    toast.success('照片已上传，等待管理员审核')
    emit('updated', data)
  } catch (error) {
    toast.error(imageUploadErrorMessage(error))
  } finally {
    uploading.value = false
  }
}
</script>

<template>
  <div class="modal-backdrop" @mousedown.self="$emit('close')">
    <section class="dialog vrmap-dialog" role="dialog" aria-modal="true" :aria-label="`${map.name} 详情`">
      <button class="icon-button dialog-close" aria-label="关闭" title="关闭" @click="$emit('close')"><X :size="20" /></button>
      <div class="dialog-heading">
        <span class="eyebrow"><MapIcon :size="14" /> VRCHAT MAP</span>
        <h2>{{ map.name }}</h2>
        <p><span class="role-tag">{{ map.category }}</span> 推荐人：<UserAvatar :user="map.uploader" :size="20" />{{ map.uploader.nickname }}</p>
      </div>

      <div v-if="!map.is_visible" class="map-notice blocked"><EyeOff :size="16" />该地图已被管理员屏蔽{{ map.admin_note ? `：${map.admin_note}` : '' }}，仅你与管理员可见。</div>
      <div v-else-if="map.has_pending_report" class="map-notice pending"><Flag :size="16" />该地图有举报待处理，暂不对外展示。</div>

      <p class="map-description">{{ map.description }}</p>

      <div v-if="publicPhotos.length" class="map-photos">
        <figure v-for="photo in publicPhotos" :key="photo.id"><img :src="photo.image_url" :alt="`${map.name} 实拍照片`" /></figure>
      </div>

      <div class="map-actions">
        <button class="button like-button" :class="{ liked: map.liked_by_me }" :disabled="liking" @click="toggleLike">
          <Heart :size="16" />{{ map.liked_by_me ? '已点赞' : '点赞' }} {{ map.like_count }}
        </button>
        <button v-if="auth.isLoggedIn && !map.reported_by_me" class="button secondary" :disabled="busy" @click="showReport = !showReport">
          <Flag :size="16" />举报
        </button>
        <span v-else-if="map.reported_by_me" class="muted reported-hint"><Flag :size="14" />已举报过这张地图</span>
      </div>

      <form v-if="showReport" class="form-stack report-form" @submit.prevent="submitReport">
        <label>举报原因<textarea v-model.trim="reportReason" required minlength="2" maxlength="200" rows="3" placeholder="如：简介与实际内容不符 / 违规内容"></textarea><small>{{ reportReason.length }}/200</small></label>
        <div class="dialog-footer"><button type="button" class="button secondary" @click="showReport = false">取消</button><button class="button" :disabled="busy"><Send :size="15" />{{ busy ? '提交中…' : '提交举报' }}</button></div>
      </form>

      <template v-if="auth.isLoggedIn">
        <div class="upload-section">
          <div v-if="myPhoto" class="my-photo">
            <figure :class="{ blocked: !myPhoto.is_visible }">
              <img :src="myPhoto.image_url" alt="我上传的实拍照片" />
              <span v-if="!myPhoto.is_visible" class="photo-blocked"><EyeOff :size="14" />{{ myPhoto.moderated ? '未通过审核' : '审核中' }}</span>
            </figure>
            <p class="muted">{{ myPhoto.moderated ? '这张照片未通过审核，可重新上传一张替换。' : '你的照片正在等待管理员审核，审核通过后会公开展示。' }}</p>
          </div>
          <p class="upload-prompt">{{ UPLOAD_PROMPT }}</p>
          <label class="button secondary upload-label" :class="{ disabled: uploading }">
            <UploadCloud :size="16" />{{ uploading ? '上传中…' : myPhoto ? '重新上传替换' : '上传我的实拍照片' }}
            <span class="upload-hint">仅支持 PNG / JPG，最大 10 MB</span>
            <input type="file" accept="image/png,image/jpeg" :disabled="uploading" @change="uploadPhoto" />
          </label>
        </div>
      </template>
    </section>
  </div>
</template>

<style scoped>
.vrmap-dialog {
  width: min(640px, 94vw);
  max-height: 88vh;
  overflow-y: auto;
}

.dialog-heading p {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 8px;
  font-size: 13px;
}

.map-notice {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-radius: 10px;
  font-size: 13px;
  margin-bottom: 12px;
}

.map-notice.blocked {
  color: var(--red);
  background: var(--red-soft);
}

.map-notice.pending {
  color: var(--yellow);
  background: var(--yellow-soft);
}

.map-description {
  font-size: 14px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}

.map-photos {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 8px;
  margin: 12px 0;
}

.map-photos figure {
  position: relative;
  margin: 0;
  aspect-ratio: 1;
  overflow: hidden;
  border-radius: 8px;
  border: 1px solid var(--line);
}

.map-photos img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.map-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 14px;
}

.like-button.liked {
  color: var(--red);
  border-color: var(--red);
}

.reported-hint {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 13px;
}

.report-form {
  margin-top: 12px;
}

.upload-section {
  margin-top: 18px;
  padding-top: 14px;
  border-top: 1px solid var(--line);
}

.upload-prompt {
  margin: 10px 0;
  padding: 10px 12px;
  border-radius: 8px;
  background: var(--green-soft);
  color: #1d6649;
  font-size: 13px;
  line-height: 1.6;
}

.upload-label {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  overflow: hidden;
  cursor: pointer;
}

.upload-label input {
  position: absolute;
  inset: 0;
  opacity: 0;
  cursor: pointer;
}

.upload-label.disabled {
  opacity: 0.6;
  pointer-events: none;
}

.upload-hint {
  font-size: 11px;
  color: var(--muted);
}

.my-photo {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  margin-bottom: 8px;
}

.my-photo figure {
  position: relative;
  width: 96px;
  margin: 0;
  flex-shrink: 0;
}

.my-photo img {
  width: 96px;
  height: 96px;
  border-radius: 8px;
  object-fit: cover;
  display: block;
}

.my-photo figure.blocked img {
  filter: grayscale(0.7);
  opacity: 0.75;
}

.my-photo .photo-blocked {
  left: 0;
  right: 0;
  white-space: normal;
}

.my-photo p {
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
}
</style>
