<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { Check, CircleCheck, ClipboardList, Clock3, Eye, EyeOff, MessageCircle, RotateCcw, Save, Search, ShieldCheck, UsersRound } from 'lucide-vue-next'
import { api, errorMessage } from '../api'
import { useToast } from '../composables/toast'
import StatusBadge from '../components/StatusBadge.vue'
import { roleLabel } from '../constants'

const toast = useToast()
const tasks = ref([])
const users = ref([])
const feedbacks = ref([])
const userLimits = reactive({})
const stats = ref({ users: 0, tasks: 0, processing: 0, completed: 0, hidden: 0 })
const activeTab = ref('tasks')
const taskSearch = ref('')
const userSearch = ref('')
const loading = ref(true)
const savingUserId = ref(null)
const filteredTasks = computed(() => tasks.value.filter((task) => `${task.title}${task.publisher.nickname}`.toLowerCase().includes(taskSearch.value.toLowerCase())))
const filteredUsers = computed(() => users.value.filter((user) => `${user.username}${user.nickname}`.toLowerCase().includes(userSearch.value.toLowerCase())))
const pendingFeedbacks = computed(() => feedbacks.value.filter((item) => item.status === 'pending').length)
const statItems = computed(() => [
  { label: '注册用户', value: stats.value.users, icon: UsersRound },
  { label: '全部委托', value: stats.value.tasks, icon: ClipboardList },
  { label: '处理中', value: stats.value.processing, icon: Clock3 },
  { label: '已完成', value: stats.value.completed, icon: CircleCheck },
])
async function load() {
  loading.value = true
  try {
    const [taskRes, userRes, statRes, feedbackRes] = await Promise.all([
      api.get('/admin/tasks'),
      api.get('/admin/users'),
      api.get('/admin/stats'),
      api.get('/admin/feedback'),
    ])
    tasks.value = taskRes.data
    users.value = userRes.data
    stats.value = statRes.data
    feedbacks.value = feedbackRes.data
    users.value.forEach((user) => { userLimits[user.id] = user.max_concurrent_tasks })
  } catch (error) {
    toast.error(errorMessage(error))
  } finally {
    loading.value = false
  }
}
async function saveUserLimit(user) {
  savingUserId.value = user.id
  try {
    const { data } = await api.patch(`/admin/users/${user.id}/task-limit`, {
      max_concurrent_tasks: Number(userLimits[user.id]),
    })
    users.value[users.value.findIndex((item) => item.id === user.id)] = data
    userLimits[user.id] = data.max_concurrent_tasks
    toast.success(`已更新 ${data.nickname} 的接单上限`)
  } catch (error) {
    userLimits[user.id] = user.max_concurrent_tasks
    toast.error(errorMessage(error))
  } finally {
    savingUserId.value = null
  }
}

async function changeUserRole(user) {
  if (user.is_admin) return
  const targetRole = user.role === 'volunteer' ? 'user' : 'volunteer'
  try {
    const { data } = await api.patch(`/admin/users/${user.id}/role`, { role: targetRole })
    users.value[users.value.findIndex((item) => item.id === user.id)] = data
    toast.success(`${data.nickname} 已${targetRole === 'volunteer' ? '升级为志愿者' : '降为普通用户'}`)
  } catch (error) {
    toast.error(errorMessage(error))
  }
}
async function toggle(task) {
  let note = task.admin_note
  if (task.is_visible) {
    note = window.prompt('请输入隐藏原因（将展示给委托相关用户）', task.admin_note || '')
    if (note === null) return
  }
  try {
    const { data } = await api.patch(`/admin/tasks/${task.id}`, { is_visible: !task.is_visible, admin_note: task.is_visible ? note : null })
    tasks.value[tasks.value.findIndex((item) => item.id === task.id)] = data
    stats.value.hidden += data.is_visible ? -1 : 1
    toast.success(data.is_visible ? '委托已恢复公开' : '委托已隐藏')
  } catch (error) { toast.error(errorMessage(error)) }
}
async function handleFeedback(item) {
  const reply = window.prompt('处理这条反馈（填写处理说明或回复，可留空直接标记为已处理）', item.reply || '')
  if (reply === null) return
  try {
    const { data } = await api.patch(`/admin/feedback/${item.id}`, { status: 'handled', reply: reply.trim() || null })
    feedbacks.value[feedbacks.value.findIndex((f) => f.id === item.id)] = data
    toast.success('反馈已标记为处理完成')
  } catch (error) { toast.error(errorMessage(error)) }
}

async function reopenFeedback(item) {
  try {
    const { data } = await api.patch(`/admin/feedback/${item.id}`, { status: 'pending' })
    feedbacks.value[feedbacks.value.findIndex((f) => f.id === item.id)] = data
    toast.success('已重新标记为待处理')
  } catch (error) { toast.error(errorMessage(error)) }
}

const date = (value) => new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(new Date(value))
const authorOf = (item) => (item.user ? item.user.nickname : item.contact || '游客')
onMounted(load)
</script>

<template>
  <div class="page inner-page admin-page">
    <div class="page-title"><div><span class="eyebrow"><ShieldCheck :size="15" /> ADMIN CONSOLE</span><h1>委托监管台</h1><p>查看平台运行状态，管理委托与用户接单额度。</p></div></div>
    <div class="admin-stats"><div v-for="item in statItems" :key="item.label"><component :is="item.icon" :size="20" /><span>{{ item.label }}</span><strong>{{ item.value }}</strong></div></div>

    <div class="tabs admin-tabs" role="tablist" aria-label="后台管理内容">
      <button :class="{ active: activeTab === 'tasks' }" role="tab" :aria-selected="activeTab === 'tasks'" @click="activeTab = 'tasks'">委托管理</button>
      <button :class="{ active: activeTab === 'users' }" role="tab" :aria-selected="activeTab === 'users'" @click="activeTab = 'users'">用户接单上限</button>
      <button :class="{ active: activeTab === 'feedback' }" role="tab" :aria-selected="activeTab === 'feedback'" @click="activeTab = 'feedback'">用户反馈<span v-if="pendingFeedbacks">{{ pendingFeedbacks }}</span></button>
    </div>

    <section v-if="activeTab === 'tasks'" class="admin-table-section">
      <div class="admin-toolbar"><div><h2>全部委托</h2><span>隐藏 {{ stats.hidden }} 项</span></div><label class="search-field"><Search :size="17" /><input v-model="taskSearch" placeholder="搜索标题或发布人" /></label></div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>委托</th><th>发布人</th><th>状态</th><th>到期时间</th><th>可见性</th><th><span class="sr-only">操作</span></th></tr></thead>
          <tbody>
            <tr v-if="loading"><td colspan="6" class="table-loading">正在加载…</td></tr>
            <tr v-for="task in filteredTasks" v-else :key="task.id" :class="{ dimmed: !task.is_visible }">
              <td><strong>{{ task.title }}</strong><small>#{{ task.id }} · {{ task.category }}</small></td>
              <td>{{ task.publisher.nickname }}</td><td><StatusBadge :status="task.status" /></td><td>{{ date(task.expires_at) }}</td>
              <td><span class="visibility"><Eye v-if="task.is_visible" :size="15" /><EyeOff v-else :size="15" />{{ task.is_visible ? '公开' : '已隐藏' }}</span></td>
              <td><button class="icon-button" :title="task.is_visible ? '隐藏委托' : '恢复公开'" :aria-label="task.is_visible ? '隐藏委托' : '恢复公开'" @click="toggle(task)"><EyeOff v-if="task.is_visible" :size="18" /><Eye v-else :size="18" /></button></td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section v-else-if="activeTab === 'users'" class="admin-table-section">
      <div class="admin-toolbar"><div><h2>用户管理</h2><span>共 {{ users.length }} 人</span></div><label class="search-field"><Search :size="17" /><input v-model="userSearch" placeholder="搜索账号或昵称" /></label></div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>用户</th><th>权限等级</th><th>当前接单</th><th>接单上限</th><th><span class="sr-only">操作</span></th></tr></thead>
          <tbody>
            <tr v-if="loading"><td colspan="5" class="table-loading">正在加载…</td></tr>
            <tr v-for="user in filteredUsers" v-else :key="user.id">
              <td><strong>{{ user.nickname }}</strong><small>@{{ user.username }} · #{{ user.id }}</small></td>
              <td><span v-if="user.is_admin" class="admin-tag"><ShieldCheck :size="13" />管理员</span><span v-else class="role-tag" :class="`role-${user.role}`">{{ roleLabel(user) }}</span></td>
              <td><span class="limit-usage" :class="{ full: user.active_task_count >= user.max_concurrent_tasks }">{{ user.active_task_count }} / {{ user.max_concurrent_tasks }}</span></td>
              <td><input v-model.number="userLimits[user.id]" class="limit-input" type="number" min="0" max="999" :aria-label="`${user.nickname} 的接单上限`" /></td>
              <td>
                <div class="user-row-actions">
                  <button class="button secondary small" title="保存接单上限" aria-label="保存接单上限" :disabled="savingUserId === user.id || userLimits[user.id] === user.max_concurrent_tasks" @click="saveUserLimit(user)"><Save :size="15" /></button>
                  <button v-if="!user.is_admin" class="button small" :class="{ secondary: user.role === 'volunteer' }" :disabled="user.role === 'volunteer' && user.active_task_count > 0" @click="changeUserRole(user)">{{ user.role === 'volunteer' ? '降为普通用户' : '升级为志愿者' }}</button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section v-else-if="activeTab === 'feedback'" class="admin-table-section">
      <div class="admin-toolbar"><div><h2>用户反馈</h2><span>待处理 {{ pendingFeedbacks }} 条</span></div><span class="muted"><MessageCircle :size="15" /> 提交者会收到处理状态与回复</span></div>
      <div v-if="loading" class="feedback-admin-empty">正在加载…</div>
      <ul v-else-if="feedbacks.length" class="feedback-admin-list">
        <li v-for="item in feedbacks" :key="item.id" :class="{ handled: item.status === 'handled' }">
          <div class="fb-head">
            <span class="fb-state" :class="`state-${item.status}`">{{ item.status === 'pending' ? '待处理' : '已处理' }}</span>
            <strong>{{ authorOf(item) }}</strong>
            <span class="muted">{{ item.page || '未注明页面' }}</span>
            <time class="muted">{{ date(item.created_at) }}</time>
          </div>
          <p class="fb-content">{{ item.content }}</p>
          <div class="fb-actions">
            <span v-if="item.status === 'handled' && item.reply" class="fb-reply-admin">回复：{{ item.reply }}</span>
            <button v-if="item.status === 'pending'" class="button secondary small" @click="handleFeedback(item)"><Check :size="15" />标记处理</button>
            <button v-else class="button secondary small" @click="reopenFeedback(item)"><RotateCcw :size="15" />重开</button>
          </div>
        </li>
      </ul>
      <div v-else class="feedback-admin-empty"><MessageCircle :size="28" />还没有收到任何反馈</div>
    </section>
  </div>
</template>
