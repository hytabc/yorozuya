<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { BadgeCheck, MessageSquare, MessagesSquare, Plus, Search, Send } from '@lucide/vue'
import { api, errorMessage } from '../api'
import { track } from '../analytics'
import { useToast } from '../composables/toast'
import { useAuthStore } from '../stores/auth'
import { TALK_BOARDS } from '../constants'
import UserAvatar from '../components/UserAvatar.vue'
import UserTitleTag from '../components/UserTitleTag.vue'
import TalkThreadDialog from '../components/TalkThreadDialog.vue'

const PAGE_SIZE = 20

const toast = useToast()
const auth = useAuthStore()
const boards = TALK_BOARDS
const loading = ref(true)
const error = ref('')
const threads = ref([])
const total = ref(0)
const page = ref(1)
const boardFilter = ref('')
const searchTerm = ref('')
const search = ref('')
const showComposer = ref(false)
const posting = ref(false)
const openThreadId = ref(null)
const form = reactive({ board: 'newbie', title: '', content: '', is_anonymous: false })

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))
const time = (value) =>
  new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(new Date(value))

async function load(target = page.value) {
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.get('/talk/threads', {
      params: { board: boardFilter.value, search: search.value, page: target, page_size: PAGE_SIZE },
    })
    threads.value = data.items
    total.value = data.total
    page.value = data.page
  } catch (err) {
    error.value = errorMessage(err, '无法加载疑难解答')
  } finally {
    loading.value = false
  }
}

function applyFilter() {
  search.value = searchTerm.value.trim()
  load(1)
}

function selectBoard(key) {
  boardFilter.value = key
  load(1)
}

async function submitThread() {
  const title = form.title.trim()
  const content = form.content.trim()
  if (title.length < 2) return toast.error('标题至少 2 个字')
  if (content.length < 5) return toast.error('正文至少 5 个字')
  posting.value = true
  try {
    await api.post('/talk/threads', {
      board: form.board,
      title,
      content,
      is_anonymous: form.is_anonymous,
    })
    toast.success('帖子已发布')
    track('talk.create')
    Object.assign(form, { board: form.board, title: '', content: '', is_anonymous: false })
    showComposer.value = false
    boardFilter.value = ''
    await load(1)
  } catch (err) {
    toast.error(errorMessage(err))
  } finally {
    posting.value = false
  }
}

function onDeleted(threadId) {
  openThreadId.value = null
  threads.value = threads.value.filter((item) => item.id !== threadId)
  total.value = Math.max(0, total.value - 1)
}

onMounted(() => load(1))
</script>

<template>
  <div class="page inner-page talk-page">
    <div class="page-title">
      <div>
        <span class="eyebrow"><MessagesSquare :size="15" /> TALK HALL</span>
        <h1>疑难解答</h1>
        <p>把问题发出来，让大家一层层帮你排查；有用的回答可以被楼主采纳。</p>
      </div>
      <button v-if="auth.isLoggedIn" class="button" type="button" @click="showComposer = !showComposer">
        <Plus :size="16" />{{ showComposer ? '收起' : '发布帖子' }}
      </button>
    </div>

    <form v-if="showComposer" class="talk-composer" @submit.prevent="submitThread">
      <div class="composer-row">
        <label>子版块
          <select v-model="form.board">
            <option v-for="item in boards" :key="item.key" :value="item.key">{{ item.label }}</option>
          </select>
        </label>
        <label class="grow">标题
          <input v-model="form.title" maxlength="80" placeholder="一句话说清你的问题" />
        </label>
      </div>
      <textarea v-model="form.content" rows="5" maxlength="5000" placeholder="描述背景、已尝试的做法和期待的结果…（最多 5000 字）" aria-label="帖子正文"></textarea>
      <div class="composer-footer">
        <label class="anonymous-toggle"><input v-model="form.is_anonymous" type="checkbox" />匿名发布</label>
        <small class="muted">{{ form.content.length }}/5000</small>
        <button class="button" type="submit" :disabled="posting"><Send :size="15" />{{ posting ? '发布中…' : '发布帖子' }}</button>
      </div>
    </form>

    <div class="talk-toolbar">
      <div class="board-chips">
        <button class="chip" :class="{ active: boardFilter === '' }" type="button" @click="selectBoard('')">全部</button>
        <button v-for="item in boards" :key="item.key" class="chip" :class="{ active: boardFilter === item.key }" type="button" @click="selectBoard(item.key)">{{ item.label }}</button>
      </div>
      <form class="talk-search" @submit.prevent="applyFilter">
        <input v-model="searchTerm" maxlength="80" placeholder="搜索标题或内容…" aria-label="搜索帖子" />
        <button class="icon-button" type="submit" title="搜索" aria-label="搜索"><Search :size="16" /></button>
      </form>
    </div>

    <ul v-if="loading" class="talk-list">
      <li v-for="i in 3" :key="i" class="talk-card skeleton" />
    </ul>
    <div v-else-if="error" class="talk-empty error-notice">{{ error }}</div>
    <div v-else-if="!threads.length" class="talk-empty"><strong>还没有相关帖子</strong><span>把你的疑问发出来，让大家一起看看。</span></div>
    <ul v-else class="talk-list">
      <li v-for="item in threads" :key="item.id" class="talk-card" @click="openThreadId = item.id">
        <header class="talk-card-head">
          <span class="board-tag">{{ item.board_label }}</span>
          <span v-if="item.solved" class="solved-tag"><BadgeCheck :size="13" />已解决</span>
          <time class="muted">{{ time(item.last_reply_at) }}</time>
        </header>
        <h2>{{ item.title }}</h2>
        <p class="talk-excerpt">{{ item.excerpt }}</p>
        <footer class="talk-card-foot">
          <span class="talk-author">
            <UserAvatar :user="item.user" :size="22" /><strong>{{ item.user.nickname }}</strong><UserTitleTag :title="item.user.title" />
          </span>
          <span class="muted"><MessageSquare :size="13" />{{ item.reply_count }}</span>
        </footer>
      </li>
    </ul>

    <div v-if="!loading && !error && totalPages > 1" class="pager">
      <button class="button secondary small" type="button" :disabled="page <= 1" @click="load(page - 1)">上一页</button>
      <span class="muted">{{ page }} / {{ totalPages }}</span>
      <button class="button secondary small" type="button" :disabled="page >= totalPages" @click="load(page + 1)">下一页</button>
    </div>

    <TalkThreadDialog v-if="openThreadId" :thread-id="openThreadId" @close="openThreadId = null" @deleted="onDeleted" />
  </div>
</template>

<style scoped>
.talk-composer {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  margin-bottom: 18px;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: var(--paper);
}

.composer-row {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.composer-row label {
  display: flex;
  flex-direction: column;
  gap: 5px;
  font-size: 12px;
  color: var(--muted);
}

.composer-row .grow { flex: 1; min-width: 200px; }

.composer-row select,
.composer-row input {
  min-height: 38px;
  padding: 0 10px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: white;
}

.talk-composer textarea {
  width: 100%;
  border: 0;
  outline: 0;
  resize: vertical;
  min-height: 90px;
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

.talk-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.board-chips {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.chip {
  padding: 6px 12px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: var(--paper);
  color: var(--muted);
  font-size: 12px;
  cursor: pointer;
}

.chip.active {
  border-color: var(--green);
  background: var(--green-soft, #e5f3eb);
  color: var(--green);
}

.talk-search {
  display: flex;
  align-items: center;
  gap: 6px;
}

.talk-search input {
  min-height: 36px;
  padding: 0 12px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: var(--paper);
  outline: none;
}

.talk-search input:focus { border-color: var(--green); }

.talk-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.talk-card {
  padding: 16px;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: var(--paper);
  cursor: pointer;
}

.talk-card:hover { border-color: var(--green); }

.talk-card.skeleton {
  min-height: 120px;
  cursor: default;
}

.talk-card-head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.talk-card-head time {
  margin-left: auto;
  font-size: 11px;
}

.board-tag,
.solved-tag {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
}

.board-tag { background: var(--blue-soft, #e3f1f5); color: var(--blue); }
.solved-tag { background: var(--green-soft, #e5f3eb); color: var(--green); }

.talk-card h2 {
  margin: 10px 0 6px;
  font-size: 16px;
}

.talk-excerpt {
  margin: 0;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.6;
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.talk-card-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 12px;
  font-size: 12px;
}

.talk-author {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.talk-card-foot .muted {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.talk-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 44px 20px;
  border: 1px dashed var(--line);
  border-radius: 14px;
  color: var(--muted);
}
</style>
