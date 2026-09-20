<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { BadgeCheck, MessageSquare, MessagesSquare, Send, Trash2, UserRound, X } from '@lucide/vue'
import { api, errorMessage } from '../api'
import { track } from '../analytics'
import { useToast } from '../composables/toast'
import { useAuthStore } from '../stores/auth'
import UserAvatar from './UserAvatar.vue'
import UserTitleTag from './UserTitleTag.vue'
import UserProfileCard from './UserProfileCard.vue'

const props = defineProps({ threadId: { type: Number, required: true } })
const emit = defineEmits(['close', 'deleted'])

const PAGE_SIZE = 20

const toast = useToast()
const auth = useAuthStore()
const thread = ref(null)
const replies = ref([])
const replyTotal = ref(0)
const page = ref(1)
const loading = ref(true)
const error = ref('')
const draft = ref('')
const anonymousReply = ref(false)
const posting = ref(false)
const busyReplyId = ref(null)
const deleting = ref(false)
const profileUser = ref(null)

const totalPages = computed(() => Math.max(1, Math.ceil(replyTotal.value / PAGE_SIZE)))
const time = (value) =>
  new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(new Date(value))

async function load(target = page.value) {
  loading.value = true
  try {
    const { data } = await api.get(`/talk/threads/${props.threadId}`, {
      params: { page: target, page_size: PAGE_SIZE },
    })
    thread.value = data.thread
    replies.value = data.replies
    replyTotal.value = data.reply_total
    page.value = data.reply_page
  } catch (err) {
    error.value = errorMessage(err, '无法加载帖子')
  } finally {
    loading.value = false
  }
}

function openProfile(user) {
  if (!user?.id) return
  profileUser.value = user
}

async function submitReply() {
  const content = draft.value.trim()
  if (!content) return toast.error('回复内容不能为空')
  posting.value = true
  try {
    await api.post(`/talk/threads/${props.threadId}/replies`, {
      content,
      is_anonymous: anonymousReply.value,
    })
    draft.value = ''
    anonymousReply.value = false
    track('talk.reply')
    // 新楼层永远排最后，直接跳到最后一页看结果。
    await load(Math.max(1, Math.ceil((replyTotal.value + 1) / PAGE_SIZE)))
  } catch (err) {
    toast.error(errorMessage(err))
  } finally {
    posting.value = false
  }
}

async function toggleAccept(reply) {
  busyReplyId.value = reply.id
  try {
    await api.post(`/talk/threads/${props.threadId}/accept`, {
      reply_id: reply.accepted ? null : reply.id,
    })
    track('talk.accept')
    await load()
    toast.success(reply.accepted ? '已取消采纳' : '已采纳为最佳回答')
  } catch (err) {
    toast.error(errorMessage(err))
  } finally {
    busyReplyId.value = null
  }
}

async function deleteReply(reply) {
  if (!window.confirm(`确定删除 ${reply.floor} 楼吗？`)) return
  busyReplyId.value = reply.id
  try {
    await api.delete(`/talk/replies/${reply.id}`)
    track('talk.delete')
    await load()
    toast.success('楼层已删除')
  } catch (err) {
    toast.error(errorMessage(err))
  } finally {
    busyReplyId.value = null
  }
}

async function deleteThread() {
  if (!window.confirm(`确定永久删除“${thread.value.title}”吗？其下所有楼层也会一并删除。`)) return
  deleting.value = true
  try {
    await api.delete(`/talk/threads/${props.threadId}`)
    track('talk.delete')
    toast.success('帖子已删除')
    emit('deleted', props.threadId)
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
    <section class="dialog talk-dialog" role="dialog" aria-modal="true" aria-label="疑难解答详情">
      <button class="icon-button dialog-close" aria-label="关闭" title="关闭" @click="$emit('close')"><X :size="20" /></button>

      <div v-if="loading" class="talk-empty">正在加载帖子…</div>
      <div v-else-if="error" class="talk-empty error-notice">{{ error }}</div>
      <template v-else-if="thread">
        <div class="dialog-heading">
          <span class="eyebrow"><MessagesSquare :size="14" /> {{ thread.board_label }}</span>
          <h2>{{ thread.title }}<span v-if="thread.solved" class="solved-tag"><BadgeCheck :size="14" />已解决</span></h2>
        </div>

        <article class="talk-floor talk-floor-main">
          <header class="talk-floor-head">
            <button v-if="thread.user.id" class="talk-user" type="button" title="查看资料" @click="openProfile(thread.user)">
              <UserAvatar :user="thread.user" :size="32" /><strong>{{ thread.user.nickname }}</strong><UserTitleTag :title="thread.user.title" />
            </button>
            <span v-else class="talk-user static"><UserAvatar :user="thread.user" :size="32" /><strong>{{ thread.user.nickname }}</strong></span>
            <span v-if="thread.is_anonymous" class="role-tag"><UserRound :size="12" />匿名</span>
            <span class="floor-no">1 楼 · 楼主</span>
            <time class="muted">{{ time(thread.created_at) }}</time>
          </header>
          <p class="talk-content">{{ thread.content }}</p>
        </article>

        <div class="talk-replies">
          <h3><MessageSquare :size="15" /> 回复 {{ replyTotal }}</h3>
          <ul v-if="replies.length" class="floor-list">
            <li v-for="reply in replies" :key="reply.id" class="talk-floor" :class="{ accepted: reply.accepted }">
              <header class="talk-floor-head">
                <button v-if="reply.user.id" class="talk-user" type="button" title="查看资料" @click="openProfile(reply.user)">
                  <UserAvatar :user="reply.user" :size="28" /><strong>{{ reply.user.nickname }}</strong><UserTitleTag :title="reply.user.title" />
                </button>
                <span v-else class="talk-user static"><UserAvatar :user="reply.user" :size="28" /><strong>{{ reply.user.nickname }}</strong></span>
                <span v-if="reply.is_anonymous" class="role-tag"><UserRound :size="12" />匿名</span>
                <span class="floor-no">{{ reply.floor }} 楼</span>
                <span v-if="reply.accepted" class="solved-tag"><BadgeCheck :size="13" />最佳回答</span>
                <time class="muted">{{ time(reply.created_at) }}</time>
                <button v-if="thread.can_accept" class="icon-button tiny" type="button" :disabled="busyReplyId === reply.id" :title="reply.accepted ? '取消采纳' : '采纳为最佳回答'" @click="toggleAccept(reply)"><BadgeCheck :size="14" /></button>
                <button v-if="reply.can_delete" class="icon-button tiny" type="button" :disabled="busyReplyId === reply.id" title="删除楼层" aria-label="删除楼层" @click="deleteReply(reply)"><Trash2 :size="14" /></button>
              </header>
              <p class="talk-content">{{ reply.content }}</p>
            </li>
          </ul>
          <p v-else class="talk-empty muted">还没有人回复，来抢沙发吧。</p>

          <div v-if="totalPages > 1" class="pager">
            <button class="button secondary small" type="button" :disabled="page <= 1" @click="load(page - 1)">上一页</button>
            <span class="muted">{{ page }} / {{ totalPages }}</span>
            <button class="button secondary small" type="button" :disabled="page >= totalPages" @click="load(page + 1)">下一页</button>
          </div>
        </div>

        <form v-if="auth.isLoggedIn" class="talk-composer" @submit.prevent="submitReply">
          <textarea v-model="draft" rows="3" maxlength="2000" placeholder="写下你的回答…（最多 2000 字）" aria-label="回复内容"></textarea>
          <div class="composer-footer">
            <label class="anonymous-toggle"><input v-model="anonymousReply" type="checkbox" />匿名回复</label>
            <small class="muted">{{ draft.length }}/2000</small>
            <button class="button" type="submit" :disabled="posting"><Send :size="15" />{{ posting ? '回复中…' : '回复' }}</button>
          </div>
        </form>
        <div v-else class="hall-notice">
          <div class="notice-content"><MessagesSquare :size="18" /><span>登录后即可回复，<RouterLink class="text-link" to="/login">去登录</RouterLink> 或 <RouterLink class="text-link" to="/register">注册账号</RouterLink>。</span></div>
        </div>

        <div v-if="thread.can_delete" class="talk-actions">
          <button class="button danger" type="button" :disabled="deleting" @click="deleteThread"><Trash2 :size="16" />{{ deleting ? '删除中…' : '删除帖子' }}</button>
        </div>
      </template>
    </section>

    <div v-if="profileUser" class="modal-backdrop" @mousedown.self="profileUser = null">
      <UserProfileCard :initial-user="profileUser" hide-contact @close="profileUser = null" />
    </div>
  </div>
</template>

<style scoped>
.talk-dialog {
  width: min(700px, 94vw);
  max-height: 88vh;
  overflow-y: auto;
}

.dialog-heading h2 {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.solved-tag {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 2px 7px;
  border-radius: 999px;
  background: var(--green-soft, #e5f3eb);
  color: var(--green);
  font-size: 11px;
}

.talk-floor {
  padding: 12px 0;
  border-bottom: 1px solid var(--line);
}

.talk-floor.accepted {
  background: linear-gradient(90deg, var(--green-soft, #e5f3eb), transparent);
}

.talk-floor-main {
  border-bottom: 1px solid var(--line);
}

.talk-floor-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.talk-floor-head time {
  margin-left: auto;
  font-size: 11px;
}

.floor-no {
  color: var(--muted);
  font-size: 11px;
}

.talk-user {
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

.talk-user.static { cursor: default; }

.talk-user:hover strong { text-decoration: underline; }

.talk-content {
  margin: 8px 0 0;
  font-size: 14px;
  line-height: 1.75;
  white-space: pre-wrap;
  word-break: break-word;
}

.talk-replies {
  margin-top: 16px;
}

.talk-replies h3 {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0 0 4px;
  font-size: 15px;
}

.floor-list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.talk-composer {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 16px;
  padding: 14px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--paper);
}

.talk-composer textarea {
  width: 100%;
  border: 0;
  outline: 0;
  resize: vertical;
  min-height: 60px;
  background: transparent;
  font: inherit;
}

.composer-footer {
  display: flex;
  align-items: center;
  gap: 12px;
}

.composer-footer .button { margin-left: auto; }

.anonymous-toggle {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  color: var(--muted);
}

.talk-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
}

.talk-empty {
  padding: 28px 8px;
  text-align: center;
  color: var(--muted);
}

.talk-empty.muted { padding: 12px 0; font-size: 13px; }
</style>
