<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { EyeOff, Flag, Heart, ImagePlus, LogIn, Map as MapIcon, Pencil, Send, Trash2, X } from 'lucide-vue-next'
import { useRouter } from 'vue-router'
import { api, errorMessage, imageUploadErrorMessage } from '../api'
import { useAuthStore } from '../stores/auth'
import { useToast } from '../composables/toast'
import UserAvatar from './UserAvatar.vue'
import ImageDropzone from './ImageDropzone.vue'

const MAX_PHOTO_BYTES = 10 * 1024 * 1024
const props = defineProps({ map: { type: Object, required: true } })
const emit = defineEmits(['close', 'updated'])
const auth = useAuthStore()
const router = useRouter()
const toast = useToast()
const busy = ref(false)
const liking = ref(false)
const uploading = ref(false)
const changingPhotoId = ref(null)
const deletingPhotoId = ref(null)
const deletingMap = ref(false)
const showReport = ref(false)
const reportReason = ref('')
const pendingPhotos = ref([])

const UPLOAD_PROMPT = '你也来过这里吗？把镜头里的光影、朋友和难忘瞬间留在这里，让每一次到访都成为这张地图共同的回忆。照片审核通过后公开展示。'

const isOwner = computed(() => auth.user?.id === props.map.uploader.id)
const myPrivatePhotos = computed(() => props.map.photos.filter((photo) => photo.uploaded_by_me && !photo.is_visible))
const publicPhotos = computed(() => props.map.photos.filter((photo) => photo.is_visible))
const myPhotoCount = computed(() => props.map.photos.filter((photo) => photo.uploaded_by_me).length)
const remainingPhotos = computed(() => Math.max(0, 5 - myPhotoCount.value))

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

async function uploadPhotos(files) {
  pendingPhotos.value = files
  if (!files.length) return
  uploading.value = true
  try {
    const body = new FormData()
    files.forEach((file) => body.append('photos', file))
    const { data } = await api.post(`/vr-maps/${props.map.id}/photos`, body)
    toast.success(`${files.length} 张照片已上传，等待管理员审核`)
    emit('updated', data, { keepOpen: true })
  } catch (error) {
    toast.error(imageUploadErrorMessage(error))
  } finally {
    uploading.value = false
    pendingPhotos.value = []
  }
}

async function replacePhoto(photo, event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  if (file.size > MAX_PHOTO_BYTES) return toast.error('地图照片不能超过 10 MB')
  if (!['image/png', 'image/jpeg'].includes(file.type)) return toast.error('地图照片仅支持 PNG 或 JPG 格式')
  changingPhotoId.value = photo.id
  try {
    const body = new FormData()
    body.append('photo', file)
    const { data } = await api.patch(`/vr-maps/${props.map.id}/photos/${photo.id}`, body)
    toast.success('图片已更新，等待管理员重新审核')
    emit('updated', data, { keepOpen: true })
  } catch (error) {
    toast.error(imageUploadErrorMessage(error))
  } finally {
    changingPhotoId.value = null
  }
}

async function deletePhoto(photo) {
  if (!window.confirm('确定删除这张地图图片吗？')) return
  deletingPhotoId.value = photo.id
  try {
    const { data } = await api.delete(`/vr-maps/${props.map.id}/photos/${photo.id}`)
    toast.success('地图图片已删除')
    emit('updated', data, { keepOpen: true })
  } catch (error) {
    toast.error(errorMessage(error))
  } finally {
    deletingPhotoId.value = null
  }
}

async function deleteMap() {
  if (!window.confirm(`确定永久删除“${props.map.name}”这条地图推荐吗？其下的图片、点赞和举报记录也会一并删除。`)) return
  deletingMap.value = true
  try {
    await api.delete(`/vr-maps/${props.map.id}`)
    toast.success('地图推荐已删除')
    emit('deleted', props.map.id)
  } catch (error) {
    toast.error(errorMessage(error))
  } finally {
    deletingMap.value = false
  }
}

function loginToUpload() {
  emit('close')
  router.push({ path: '/login', query: { redirect: '/maps' } })
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
        <figure v-for="photo in publicPhotos" :key="photo.id">
          <img :src="photo.image_url" :alt="`${map.name} 实拍照片`" />
          <div v-if="auth.isLoggedIn && photo.uploaded_by_me" class="photo-actions">
            <label class="icon-button" title="更新图片" aria-label="更新图片" :class="{ disabled: changingPhotoId === photo.id || deletingPhotoId === photo.id }">
              <Pencil :size="15" /><input type="file" accept="image/png,image/jpeg" :disabled="changingPhotoId === photo.id || deletingPhotoId === photo.id" @change="replacePhoto(photo, $event)" />
            </label>
            <button class="icon-button danger-icon" type="button" title="删除图片" aria-label="删除图片" :disabled="changingPhotoId === photo.id || deletingPhotoId === photo.id" @click="deletePhoto(photo)"><Trash2 :size="15" /></button>
          </div>
        </figure>
      </div>

      <div class="map-actions">
        <button class="button like-button" :class="{ liked: map.liked_by_me }" :disabled="liking" @click="toggleLike">
          <Heart :size="16" />{{ map.liked_by_me ? '已点赞' : '点赞' }} {{ map.like_count }}
        </button>
        <button v-if="auth.isLoggedIn && !isOwner && !map.reported_by_me" class="button secondary" :disabled="busy" @click="showReport = !showReport">
          <Flag :size="16" />举报
        </button>
        <span v-else-if="map.reported_by_me" class="muted reported-hint"><Flag :size="14" />已举报过这张地图</span>
        <button v-if="isOwner" class="button danger map-delete" type="button" :disabled="deletingMap" @click="deleteMap"><Trash2 :size="16" />{{ deletingMap ? '删除中…' : '删除推荐' }}</button>
      </div>

      <form v-if="showReport" class="form-stack report-form" @submit.prevent="submitReport">
        <label>举报原因<textarea v-model.trim="reportReason" required minlength="2" maxlength="200" rows="3" placeholder="如：简介与实际内容不符 / 违规内容"></textarea><small>{{ reportReason.length }}/200</small></label>
        <div class="dialog-footer"><button type="button" class="button secondary" @click="showReport = false">取消</button><button class="button" :disabled="busy"><Send :size="15" />{{ busy ? '提交中…' : '提交举报' }}</button></div>
      </form>

      <div class="upload-section">
        <template v-if="auth.isLoggedIn">
          <div v-if="myPrivatePhotos.length" class="my-photo">
            <figure v-for="photo in myPrivatePhotos" :key="photo.id" class="blocked">
              <img :src="photo.image_url" alt="我上传的待审核实拍照片" />
              <span class="photo-blocked"><EyeOff :size="14" />{{ photo.moderated ? '未通过审核' : '审核中' }}</span>
              <div class="photo-actions">
                <label class="icon-button" title="更新图片" aria-label="更新图片" :class="{ disabled: changingPhotoId === photo.id || deletingPhotoId === photo.id }">
                  <Pencil :size="15" /><input type="file" accept="image/png,image/jpeg" :disabled="changingPhotoId === photo.id || deletingPhotoId === photo.id" @change="replacePhoto(photo, $event)" />
                </label>
                <button class="icon-button danger-icon" type="button" title="删除图片" aria-label="删除图片" :disabled="changingPhotoId === photo.id || deletingPhotoId === photo.id" @click="deletePhoto(photo)"><Trash2 :size="15" /></button>
              </div>
            </figure>
            <p class="muted">已提交的照片将在审核通过后公开展示。</p>
          </div>
        </template>
        <p class="upload-prompt">{{ UPLOAD_PROMPT }}</p>
        <ImageDropzone
          v-if="auth.isLoggedIn && remainingPhotos > 0"
          :model-value="pendingPhotos"
          :max-files="remainingPhotos"
          :max-bytes="MAX_PHOTO_BYTES"
          :max-total-bytes="50 * 1024 * 1024"
          :disabled="uploading"
          @update:model-value="uploadPhotos"
          @error="toast.error"
        />
        <div v-else-if="auth.isLoggedIn" class="upload-limit"><ImagePlus :size="17" />你已上传 5 张照片</div>
        <button v-else class="button secondary" type="button" @click="loginToUpload"><LogIn :size="16" />登录后分享照片</button>
      </div>
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

.photo-actions {
  position: absolute;
  top: 6px;
  right: 6px;
  display: flex;
  gap: 5px;
}

.photo-actions .icon-button {
  width: 30px;
  height: 30px;
  border-color: rgba(255, 255, 255, 0.82);
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 2px 8px rgba(24, 34, 29, 0.18);
  cursor: pointer;
}

.photo-actions label input { display: none; }
.photo-actions .disabled { opacity: 0.55; cursor: wait; pointer-events: none; }

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

.map-delete { margin-left: auto; }

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

.upload-limit { min-height: 44px; display: flex; align-items: center; gap: 8px; padding: 0 12px; border: 1px solid var(--line); border-radius: 4px; color: var(--muted); font-size: 12px; }

.my-photo {
  display: flex;
  align-items: flex-end;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 8px;
}

.my-photo figure {
  position: relative;
  width: 96px;
  margin: 0;
  flex-shrink: 0;
}

.my-photo .photo-actions {
  z-index: 2;
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
  flex: 1 1 180px;
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
}
</style>
