<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Plus, Search, SlidersHorizontal, Sparkles } from 'lucide-vue-next'
import { api, errorMessage } from '../api'
import { useAuthStore } from '../stores/auth'
import { useToast } from '../composables/toast'
import TaskCard from '../components/TaskCard.vue'
import TaskDialog from '../components/TaskDialog.vue'
import CreateTaskDialog from '../components/CreateTaskDialog.vue'

const auth = useAuthStore()
const router = useRouter()
const toast = useToast()
const tasks = ref([])
const loading = ref(true)
const selected = ref(null)
const showCreate = ref(false)
const busy = ref(false)
const filters = reactive({ search: '', category: '', status: '' })
const categories = ['跑腿', '设计', '技术', '学习', '生活', '其他']
const statuses = [{ value: '', label: '全部状态' }, { value: 'published', label: '招募中' }, { value: 'accepted', label: '处理中' }, { value: 'awaiting', label: '待确认' }, { value: 'completed', label: '已完成' }, { value: 'expired', label: '已过期' }]

const stats = computed(() => ({
  open: tasks.value.filter((item) => item.status === 'published').length,
  active: tasks.value.filter((item) => ['accepted', 'awaiting'].includes(item.status)).length,
  done: tasks.value.filter((item) => item.status === 'completed').length,
}))

let timer
async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/tasks', { params: { ...filters } })
    tasks.value = data
  } catch (error) { toast.error(errorMessage(error, '委托加载失败')) } finally { loading.value = false }
}
function create() {
  if (!auth.isLoggedIn) return router.push({ path: '/login', query: { redirect: '/' } })
  showCreate.value = true
}
function search() { clearTimeout(timer); timer = setTimeout(load, 280) }
function created(task) { showCreate.value = false; tasks.value.unshift(task) }

async function action(key, payload = {}) {
  if (key === 'login') return router.push({ path: '/login', query: { redirect: '/' } })
  busy.value = true
  try {
    const url = `/tasks/${selected.value.id}`
    let data
    if (key === 'accept') ({ data } = await api.post(`${url}/accept`, { password: payload.password }))
    else if (key === 'password') ({ data } = await api.patch(`${url}/password`, { password: payload.password }))
    else ({ data } = await api.post(`${url}/${key}`))
    selected.value = data
    const index = tasks.value.findIndex((item) => item.id === data.id)
    if (index !== -1) tasks.value[index] = data
    const messages = {
      accept: data.status === 'accepted' ? '人数已满，委托自动开始' : '已接取，等待委托人开始',
      start: '委托已开始，进入处理中',
      leave: '已退出接取',
      confirm: data.status === 'completed' ? '全体确认，委托完成' : '已确认完成，等待其他人确认',
      password: '接取密码已更新，请把新密码告知接单人',
      cancel: '委托已取消',
    }
    toast.success(messages[key])
  } catch (error) { toast.error(errorMessage(error)) } finally { busy.value = false }
}
onMounted(load)
</script>

<template>
  <div class="page hall-page">
    <section class="hall-intro">
      <div>
        <span class="eyebrow"><Sparkles :size="15" /> YOROZUYA REQUEST BOARD</span>
        <h1>总有一件事，<br />有人恰好擅长。</h1>
        <p>发布需要帮助的事情，或者接下一份你能完成的委托。</p>
      </div>
      <div class="hall-stats" aria-label="委托统计">
        <div><strong>{{ stats.open }}</strong><span>正在招募</span></div>
        <div><strong>{{ stats.active }}</strong><span>正在处理</span></div>
        <div><strong>{{ stats.done }}</strong><span>顺利完成</span></div>
      </div>
    </section>

    <section class="task-workspace">
      <div class="section-heading">
        <div><span class="section-index">01</span><h2>委托大厅</h2><p>浏览当前公开委托</p></div>
        <button class="button" @click="create"><Plus :size="18" />发布委托</button>
      </div>
      <div class="filterbar">
        <label class="search-field"><Search :size="18" /><input v-model="filters.search" placeholder="搜索委托标题或内容" aria-label="搜索委托" @input="search" /></label>
        <label class="select-field"><SlidersHorizontal :size="17" /><select v-model="filters.status" aria-label="状态筛选" @change="load"><option v-for="item in statuses" :key="item.value" :value="item.value">{{ item.label }}</option></select></label>
        <select v-model="filters.category" aria-label="分类筛选" @change="load"><option value="">全部分类</option><option v-for="item in categories" :key="item">{{ item }}</option></select>
      </div>

      <div v-if="loading" class="task-grid"><div v-for="i in 6" :key="i" class="task-card skeleton" /></div>
      <div v-else-if="tasks.length" class="task-grid"><TaskCard v-for="task in tasks" :key="task.id" :task="task" @select="selected = $event" /></div>
      <div v-else class="empty-state"><span>空</span><h3>没有找到相关委托</h3><p>调整筛选条件，或发布第一份委托。</p><button class="button secondary" @click="create">发布委托</button></div>
    </section>
    <CreateTaskDialog v-if="showCreate" @close="showCreate = false" @created="created" />
    <TaskDialog v-if="selected" :task="selected" :busy="busy" @close="selected = null" @action="action" />
  </div>
</template>

