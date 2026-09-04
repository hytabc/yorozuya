<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { MessagesSquare, Send, Trash2 } from 'lucide-vue-next'
import { api, errorMessage } from '../api'
import { useToast } from '../composables/toast'
import { useAuthStore } from '../stores/auth'
import UserAvatar from '../components/UserAvatar.vue'

const toast = useToast()
const auth = useAuthStore()
const loading = ref(true)
const error = ref('')
const messages = ref([])
const newContent = ref('')
const posting = ref(false)
const commentDrafts = reactive({})
const commentBusy = reactive({})
const deletingId = ref(null)

const canPost = computed(() => auth.isLoggedIn)

const time = (value) =>
  new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(new Date(value))

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/board')
    messages.value = data
  } catch (err) {
    error.value = errorMessage(err, '无法加载留言板')
  } finally {
    loading.value = false
  }
}

async function postMessage() {
  const content = newContent.value.trim()
  if (!content) return toast.error('留言内容不能为空')
  posting.value = true
  try {
    const { data } = await api.post('/board', { content })
    messages.value.unshift(data)
    newContent.value = ''
    toast.success('留言已发布')
  } catch (err) {
    toast.error(errorMessage(err))
  } finally {
    posting.value = false
  }
}

async function postComment(message) {
  const content = (commentDrafts[message.id] || '').trim()
  if (!content) return toast.error('评论内容不能为空')
  commentBusy[message.id] = true
  try {
    const { data } = await api.post(`/board/${message.id}/comments`, { content })
    messages.value[messages.value.findIndex((item) => item.id === message.id)] = data
    delete commentDrafts[message.id]
  } catch (err) {
    toast.error(errorMessage(err))
  } finally {
    commentBusy[message.id] = false
  }
}

async function deleteMessage(message) {
  if (!window.confirm('确定删除这条留言吗？它下面的评论也会一并删除。')) return
  deletingId.value = message.id
  try {
    await api.delete(`/board/${message.id}`)
    messages.value = messages.value.filter((item) => item.id !== message.id)
    toast.success('留言已删除')
  } catch (err) {
    toast.error(errorMessage(err))
  } finally {
    deletingId.value = null
  }
}

async function deleteComment(message, comment) {
  if (!window.confirm('确定删除这条评论吗？')) return
  deletingId.value = comment.id
  try {
    await api.delete(`/board/comments/${comment.id}`)
    message.comments = message.comments.filter((item) => item.id !== comment.id)
    toast.success('评论已删除')
  } catch (err) {
    toast.error(errorMessage(err))
  } finally {
    deletingId.value = null
  }
}

onMounted(load)
</script>

<template>
  <div class="page inner-page board-page">
    <div class="page-title">
      <div><span class="eyebrow"><MessagesSquare :size="15" /> MESSAGE BOARD</span><h1>留言板</h1><p>登录后可以发布留言，也可以回应其他用户的留言。</p></div>
    </div>

    <section v-if="canPost" class="board-composer">
      <textarea v-model="newContent" rows="3" maxlength="500" placeholder="写点什么…（最多 500 字）" aria-label="留言内容"></textarea>
      <div class="composer-footer"><small class="muted">{{ newContent.length }}/500</small><button class="button" :disabled="posting" @click="postMessage"><Send :size="15" />{{ posting ? '发布中…' : '发布留言' }}</button></div>
    </section>
    <div v-else class="hall-notice">
      <div class="notice-content"><MessagesSquare :size="18" /><span>登录后即可留言和评论，<RouterLink class="text-link" to="/login">去登录</RouterLink> 或 <RouterLink class="text-link" to="/register">注册账号</RouterLink>。</span></div>
    </div>

    <div v-if="loading" class="board-empty">正在加载留言…</div>
    <div v-else-if="error" class="board-empty error-notice">{{ error }}</div>
    <div v-else-if="!messages.length" class="board-empty"><strong>还没有留言</strong><span>来抢第一个沙发吧。</span></div>
    <ul v-else class="board-list">
      <li v-for="message in messages" :key="message.id" class="board-item">
        <header class="board-head">
          <UserAvatar :user="message.user" :size="36" />
          <div class="board-meta"><strong>{{ message.user.nickname }}</strong><time class="muted">{{ time(message.created_at) }}</time></div>
          <button v-if="message.can_delete" class="icon-button" :disabled="deletingId === message.id" title="删除留言" aria-label="删除留言" @click="deleteMessage(message)"><Trash2 :size="17" /></button>
        </header>
        <p class="board-content">{{ message.content }}</p>
        <div class="board-comments">
          <div v-for="comment in message.comments" :key="comment.id" class="board-comment">
            <UserAvatar :user="comment.user" :size="28" />
            <div class="comment-body">
              <div class="board-meta"><strong>{{ comment.user.nickname }}</strong><time class="muted">{{ time(comment.created_at) }}</time><button v-if="comment.can_delete" class="icon-button tiny" :disabled="deletingId === comment.id" title="删除评论" aria-label="删除评论" @click="deleteComment(message, comment)"><Trash2 :size="14" /></button></div>
              <p>{{ comment.content }}</p>
            </div>
          </div>
          <form v-if="canPost" class="comment-form" @submit.prevent="postComment(message)">
            <input v-model="commentDrafts[message.id]" maxlength="500" placeholder="写下你的评论…" :aria-label="`评论 ${message.user.nickname} 的留言`" />
            <button class="icon-button" type="submit" :disabled="commentBusy[message.id]" title="发送评论" aria-label="发送评论"><Send :size="16" /></button>
          </form>
        </div>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.board-composer {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 16px;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: var(--paper);
  margin-bottom: 18px;
}

.board-composer textarea {
  width: 100%;
  border: none;
  resize: vertical;
  min-height: 64px;
  outline: none;
  background: transparent;
}

.composer-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.board-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 44px 20px;
  border: 1px dashed var(--line);
  border-radius: 14px;
  color: var(--muted);
}

.board-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.board-item {
  padding: 16px;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: var(--paper);
}

.board-head {
  display: flex;
  align-items: center;
  gap: 10px;
}

.board-head .icon-button {
  margin-left: auto;
}

.board-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.board-meta time {
  font-size: 12px;
}

.board-meta .icon-button.tiny {
  margin-left: 4px;
}

.board-content {
  margin: 10px 0 0 46px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}

.board-comments {
  margin: 12px 0 0 46px;
  padding: 10px 12px;
  border-radius: 10px;
  background: #f6f8f5;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.board-comment {
  display: flex;
  gap: 8px;
}

.comment-body {
  flex: 1;
  min-width: 0;
}

.comment-body p {
  margin: 3px 0 0;
  font-size: 14px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.comment-form {
  display: flex;
  align-items: center;
  gap: 8px;
}

.comment-form input {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: var(--paper);
  outline: none;
}

.comment-form input:focus {
  border-color: var(--green);
}
</style>
