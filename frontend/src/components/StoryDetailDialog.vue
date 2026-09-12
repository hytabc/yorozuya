<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { BookOpen, EyeOff, MessageCircle, Send, Trash2, UserRound, X } from 'lucide-vue-next'
import { api, errorMessage } from '../api'
import { useToast } from '../composables/toast'
import UserAvatar from './UserAvatar.vue'
import UserProfileCard from './UserProfileCard.vue'

const props = defineProps({ storyId: { type: Number, required: true } })
const emit = defineEmits(['close', 'deleted'])

const toast = useToast()
const story = ref(null)
const loading = ref(true)
const error = ref('')
const deleting = ref(false)
const posting = ref(false)
const commentDraft = ref('')
const deletingCommentId = ref(null)
const profileUser = ref(null)

const publicPhotos = computed(() => (story.value?.photos || []).filter((photo) => photo.is_visible))
const myPendingPhotos = computed(() => (story.value?.photos || []).filter((photo) => photo.uploaded_by_me && !photo.is_visible))

const time = (value) =>
  new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(new Date(value))

async function load() {
  loading.value = true
  try {
    story.value = (await api.get(`/stories/${props.storyId}`)).data
  } catch (err) {
    error.value = errorMessage(err, '无法加载故事')
  } finally {
    loading.value = false
  }
}

async function submitComment() {
  const content = commentDraft.value.trim()
  if (!content) return toast.error('评论内容不能为空')
  posting.value = true
  try {
    const { data } = await api.post(`/stories/${props.storyId}/comments`, { content })
    story.value = data
    commentDraft.value = ''
  } catch (err) {
    toast.error(errorMessage(err))
  } finally {
    posting.value = false
  }
}

async function deleteComment(comment) {
  if (!window.confirm('确定删除这条评论吗？')) return
  deletingCommentId.value = comment.id
  try {
    await api.delete(`/stories/comments/${comment.id}`)
    story.value.comments = story.value.comments.filter((item) => item.id !== comment.id)
    toast.success('评论已删除')
  } catch (err) {
    toast.error(errorMessage(err))
  } finally {
    deletingCommentId.value = null
  }
}

async function deleteStory() {
  if (!window.confirm(`确定永久删除“${story.value.title}”这篇故事吗？其下的评论与配图也会一并删除。`)) return
  deleting.value = true
  try {
    await api.delete(`/stories/${props.storyId}`)
    toast.success('故事已删除')
    emit('deleted', props.storyId)
  } catch (err) {
    toast.error(errorMessage(err))
  } finally {
    deleting.value = false
  }
}

function onKey(event) { if (event.key === 'Escape') emit('close') }
onMounted(() => { document.body.classList.add('modal-open'); window.addEventListener('keydown', onKey); load() })
onBeforeUnmount(() => { document.body.classList.remove('modal-open'); window.removeEventListener('keydown', onKey) })
</script>

<template>
  <div class="modal-backdrop" @mousedown.self="$emit('close')">
    <section class="dialog story-dialog" role="dialog" aria-modal="true" aria-label="故事详情">
      <button class="icon-button dialog-close" aria-label="关闭" title="关闭" @click="$emit('close')"><X :size="20" /></button>

      <div v-if="loading" class="story-empty">正在加载故事…</div>
      <div v-else-if="error" class="story-empty error-notice">{{ error }}</div>
      <template v-else-if="story">
        <div class="dialog-heading">
          <span class="eyebrow"><BookOpen :size="14" /> STORY</span>
          <h2>{{ story.title }}</h2>
          <p class="story-meta">
            <button v-if="story.author.id" class="story-author-btn" type="button" @click="profileUser = story.author">
              <UserAvatar :user="story.author" :size="22" /><strong>{{ story.author.nickname }}</strong>
            </button>
            <span v-else class="story-author-btn static"><UserAvatar :user="story.author" :size="22" /><strong>{{ story.author.nickname }}</strong></span>
            <span v-if="story.is_anonymous" class="role-tag"><UserRound :size="12" />匿名</span>
            <time class="muted">{{ time(story.created_at) }}</time>
          </p>
        </div>

        <div v-if="publicPhotos.length || myPendingPhotos.length" class="story-photos">
          <figure v-for="photo in publicPhotos" :key="photo.id">
            <img :src="photo.image_url" :alt="`${story.title} 的配图`" />
          </figure>
          <figure v-for="photo in myPendingPhotos" :key="photo.id" class="blocked">
            <img :src="photo.image_url" alt="我上传的待审核配图" />
            <span class="photo-blocked"><EyeOff :size="14" />{{ photo.moderated ? '未通过审核' : '审核中' }}</span>
          </figure>
        </div>

        <p class="story-content">{{ story.content }}</p>

        <div class="story-actions">
          <button v-if="story.can_delete" class="button danger" type="button" :disabled="deleting" @click="deleteStory">
            <Trash2 :size="16" />{{ deleting ? '删除中…' : '删除故事' }}
          </button>
        </div>

        <div class="story-comments">
          <h3><MessageCircle :size="15" /> 评论 {{ story.comments.length }}</h3>
          <div v-if="!story.comments.length" class="story-empty muted">还没有评论，来说点什么吧。</div>
          <ul v-else class="comment-list">
            <li v-for="comment in story.comments" :key="comment.id" class="comment-item">
              <UserAvatar :user="comment.user" :size="28" />
              <div class="comment-body">
                <div class="comment-head">
                  <button class="comment-user" type="button" @click="profileUser = comment.user"><strong>{{ comment.user.nickname }}</strong></button>
                  <time class="muted">{{ time(comment.created_at) }}</time>
                  <button v-if="comment.can_delete" class="icon-button tiny" type="button" title="删除评论" aria-label="删除评论" :disabled="deletingCommentId === comment.id" @click="deleteComment(comment)"><Trash2 :size="14" /></button>
                </div>
                <p>{{ comment.content }}</p>
              </div>
            </li>
          </ul>
          <form class="comment-form" @submit.prevent="submitComment">
            <input v-model="commentDraft" maxlength="500" placeholder="写下你的评论…" />
            <button class="icon-button" type="submit" :disabled="posting" title="发表评论" aria-label="发表评论"><Send :size="16" /></button>
          </form>
        </div>
      </template>
    </section>

    <div v-if="profileUser" class="modal-backdrop" @mousedown.self="profileUser = null">
      <UserProfileCard :initial-user="profileUser" hide-contact @close="profileUser = null" />
    </div>
  </div>
</template>

<style scoped>
.story-dialog {
  width: min(680px, 94vw);
  max-height: 88vh;
  overflow-y: auto;
}

.story-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
  font-size: 13px;
}

.story-author-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--ink);
  font-size: 13px;
  cursor: pointer;
}

.story-author-btn.static { cursor: default; }

.story-content {
  margin: 14px 0;
  font-size: 15px;
  line-height: 1.85;
  white-space: pre-wrap;
  word-break: break-word;
}

.story-photos {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 8px;
  margin: 12px 0;
}

.story-photos figure {
  position: relative;
  margin: 0;
  aspect-ratio: 1;
  overflow: hidden;
  border-radius: 8px;
  border: 1px solid var(--line);
}

.story-photos img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.story-photos figure.blocked img {
  filter: grayscale(0.7);
  opacity: 0.75;
}

.photo-blocked {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 4px;
  background: rgba(42, 48, 45, 0.82);
  color: #fff;
  font-size: 11px;
}

.story-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 6px;
}

.story-comments {
  margin-top: 18px;
  padding-top: 14px;
  border-top: 1px solid var(--line);
}

.story-comments h3 {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0 0 12px;
  font-size: 15px;
}

.comment-list {
  display: grid;
  gap: 12px;
  margin: 0 0 12px;
  padding: 0;
  list-style: none;
}

.comment-item {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 10px;
}

.comment-head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.comment-user {
  padding: 0;
  border: 0;
  background: transparent;
  font-size: 13px;
  color: var(--ink);
  cursor: pointer;
}

.comment-head time { font-size: 11px; }
.comment-head .icon-button.tiny { margin-left: auto; }

.comment-body p {
  margin: 4px 0 0;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.comment-form {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
}

.comment-form input {
  min-height: 38px;
  padding: 0 12px;
  border: 1px solid var(--line);
  border-radius: 4px;
  background: var(--paper);
  font-size: 13px;
}

.story-empty {
  padding: 28px 8px;
  text-align: center;
  color: var(--muted);
}

.story-empty.muted { padding: 12px 0; font-size: 13px; }
</style>
