<script setup>
import { onMounted, reactive, ref } from 'vue'
import { BookOpen, MessageCircle, PenLine, Plus, UserRound, X } from 'lucide-vue-next'
import { api, errorMessage, imageUploadErrorMessage } from '../api'
import { useToast } from '../composables/toast'
import UserAvatar from '../components/UserAvatar.vue'
import StoryDetailDialog from '../components/StoryDetailDialog.vue'
import ImageDropzone from '../components/ImageDropzone.vue'

const toast = useToast()
const stories = ref([])
const loading = ref(true)
const error = ref('')
const selected = ref(null)
const showCreate = ref(false)
const creating = ref(false)
const form = reactive({ title: '', content: '', is_anonymous: false })
const createPhotos = ref([])
const MAX_PHOTO_BYTES = 10 * 1024 * 1024

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/stories')
    stories.value = data
  } catch (err) {
    error.value = errorMessage(err, '故事加载失败')
  } finally {
    loading.value = false
  }
}

function create() {
  showCreate.value = true
}

async function submitCreate() {
  if (!form.title.trim()) return toast.error('请填写故事标题')
  if (form.content.trim().length < 10) return toast.error('故事正文请至少填写 10 个字符')
  if (createPhotos.value.length > 3) return toast.error('每篇故事最多上传 3 张图片')
  if (createPhotos.value.some((file) => file.size > MAX_PHOTO_BYTES)) return toast.error('单张故事图片不能超过 10 MB')
  if (createPhotos.value.reduce((sum, file) => sum + file.size, 0) > 30 * 1024 * 1024) return toast.error('本次故事图片总大小不能超过 30 MB')
  creating.value = true
  try {
    const hasPhotos = createPhotos.value.length > 0
    const body = new FormData()
    body.append('title', form.title.trim())
    body.append('content', form.content.trim())
    body.append('is_anonymous', form.is_anonymous ? 'true' : 'false')
    createPhotos.value.forEach((file) => body.append('photos', file))
    await api.post('/stories', body)
    showCreate.value = false
    form.title = ''
    form.content = ''
    form.is_anonymous = false
    createPhotos.value = []
    toast.success(hasPhotos ? '故事已发布，配图将在审核通过后公开' : '故事已发布')
    await load()
  } catch (err) {
    toast.error(imageUploadErrorMessage(err))
  } finally {
    creating.value = false
  }
}

function onDeleted(storyId) {
  stories.value = stories.value.filter((item) => item.id !== storyId)
  selected.value = null
}

onMounted(load)
</script>

<template>
  <div class="page inner-page stories-page">
    <div class="page-title">
      <div><span class="eyebrow"><BookOpen :size="15" /> STORY HALL</span><h1>故事会</h1><p>写下你的故事，可以署名也可以匿名；路过的旅人可以在这里留下评论。</p></div>
    </div>

    <section class="stories-toolbar">
      <span class="muted"><PenLine :size="15" /> 一人可以写多篇，配图通过审核后公开展示</span>
      <button class="button" type="button" @click="create"><Plus :size="17" />写故事</button>
    </section>

    <div v-if="loading" class="stories-grid"><div v-for="i in 6" :key="i" class="story-card skeleton" /></div>
    <div v-else-if="error" class="stories-empty error-notice">{{ error }}</div>
    <div v-else-if="!stories.length" class="stories-empty"><BookOpen :size="26" /><strong>还没有故事</strong><span>第一篇故事由你来写。</span></div>
    <div v-else class="stories-grid">
      <button v-for="story in stories" :key="story.id" class="story-card" type="button" @click="selected = story">
        <figure class="story-cover">
          <img v-if="story.cover_url" :src="story.cover_url" :alt="`${story.title} 的配图`" />
          <span v-else class="story-cover-fallback"><BookOpen :size="26" /></span>
          <span v-if="story.is_anonymous" class="story-flag"><UserRound :size="13" />匿名</span>
        </figure>
        <div class="story-body">
          <h3>{{ story.title }}</h3>
          <p>{{ story.excerpt }}</p>
          <footer>
            <span class="story-author"><UserAvatar :user="story.author" :size="20" />{{ story.author.nickname }}</span>
            <span class="story-comments"><MessageCircle :size="15" />{{ story.comment_count }}</span>
          </footer>
        </div>
      </button>
    </div>

    <div v-if="showCreate" class="modal-backdrop" @mousedown.self="showCreate = false">
      <section class="dialog create-dialog" role="dialog" aria-modal="true" aria-label="写故事">
        <button class="icon-button dialog-close" aria-label="关闭" title="关闭" @click="showCreate = false"><X :size="20" /></button>
        <div class="dialog-heading"><span class="eyebrow"><BookOpen :size="14" /> NEW STORY</span><h2>写一个故事</h2><p>把想说的话写下来吧，匿名与否由你决定。</p></div>
        <form class="form-stack" @submit.prevent="submitCreate">
          <label>故事标题<input v-model.trim="form.title" required minlength="1" maxlength="80" placeholder="给故事起一个名字" /></label>
          <label>故事正文<textarea v-model.trim="form.content" required minlength="10" maxlength="5000" rows="8" placeholder="慢慢写，这可以是一段回忆、一个故事，或者此刻的心情"></textarea><small>{{ form.content.length }}/5000</small></label>
          <div class="anonymous-field">
            <label class="checkbox-inline"><input v-model="form.is_anonymous" type="checkbox" /><span>匿名发布</span></label>
            <small class="field-hint">匿名故事在故事会里只显示“匿名作者”，不会公开你的昵称与个人资料。</small>
          </div>
          <div class="story-photo-field">
            <span>故事配图（可选，需审核）</span>
            <ImageDropzone v-model="createPhotos" :max-files="3" :max-bytes="MAX_PHOTO_BYTES" :max-total-bytes="30 * 1024 * 1024" :disabled="creating" @error="toast.error" />
          </div>
          <div class="dialog-footer"><button type="button" class="button secondary" :disabled="creating" @click="showCreate = false">取消</button><button class="button" :disabled="creating"><BookOpen :size="16" />{{ creating ? '发布中…' : '发布故事' }}</button></div>
        </form>
      </section>
    </div>

    <StoryDetailDialog v-if="selected" :story-id="selected.id" @close="selected = null" @deleted="onDeleted" />
  </div>
</template>

<style scoped>
.stories-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 18px;
}

.stories-toolbar .muted {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}

.stories-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 14px;
}

.story-card {
  position: relative;
  display: flex;
  flex-direction: column;
  padding: 0;
  border: 1px solid var(--line);
  border-radius: 14px;
  overflow: hidden;
  background: var(--paper);
  text-align: left;
  transition: box-shadow 0.15s ease;
}

.story-card:hover {
  box-shadow: var(--shadow);
}

.story-cover {
  position: relative;
  height: 130px;
  margin: 0;
  background: #eef1ef;
}

.story-cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.story-cover-fallback {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--muted);
}

.story-flag {
  position: absolute;
  top: 8px;
  left: 8px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  border-radius: 4px;
  background: rgba(42, 48, 45, 0.82);
  color: #fff;
  font-size: 11px;
}

.story-body {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px 14px 14px;
}

.story-body h3 {
  margin: 0;
  font-size: 15px;
}

.story-body p {
  margin: 0;
  font-size: 13px;
  color: var(--muted);
  line-height: 1.6;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.story-body footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 4px;
}

.story-author {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--muted);
}

.story-comments {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  color: var(--muted);
}

.stories-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 48px 16px;
  border: 1px dashed var(--line);
  border-radius: 14px;
  color: var(--muted);
  text-align: center;
}

.story-photo-field { display: grid; gap: 8px; color: #46504b; font-size: 12px; font-weight: 650; }
</style>
