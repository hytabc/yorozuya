<script setup>
import { computed, onMounted, ref } from 'vue'
import { ClipboardList, Plus } from 'lucide-vue-next'
import { api, errorMessage } from '../api'
import { useToast } from '../composables/toast'
import { useAuthStore } from '../stores/auth'
import TaskCard from '../components/TaskCard.vue'
import TaskDialog from '../components/TaskDialog.vue'
import CreateTaskDialog from '../components/CreateTaskDialog.vue'

const auth = useAuthStore()
const toast = useToast()
const tasks = ref([])
const loading = ref(true)
const selected = ref(null)
const busy = ref(false)
const showCreate = ref(false)
const tab = ref('active')
const tabs = [{ value: 'active', label: '进行中' }, { value: 'published', label: '我发布的' }, { value: 'accepted', label: '我接取的' }, { value: 'history', label: '历史记录' }]
const activeStatuses = ['published', 'accepted', 'awaiting', 'cancelling']
const me = computed(() => auth.user)
const isMyPublish = (task) => task.publisher_id === me.value?.id
const isMyAccept = (task) => task.members?.some((m) => m.user.id === me.value?.id)
const filtered = computed(() => tasks.value.filter((task) => {
  if (tab.value === 'active') return activeStatuses.includes(task.status)
  if (tab.value === 'published') return isMyPublish(task)
  if (tab.value === 'accepted') return isMyAccept(task)
  return ['completed', 'expired', 'cancelled'].includes(task.status)
}))

async function load() {
  loading.value = true
  try { tasks.value = (await api.get('/tasks/mine')).data } catch (error) { toast.error(errorMessage(error)) } finally { loading.value = false }
}

async function action(key, payload = {}) {
  busy.value = true
  try {
    const url = `/tasks/${selected.value.id}`
    let data
    if (key === 'accept') ({ data } = await api.post(`${url}/accept`, { password: payload.password }))
    else if (key === 'password') ({ data } = await api.patch(`${url}/password`, { password: payload.password }))
    else ({ data } = await api.post(`${url}/${key}`))
    selected.value = data
    tasks.value[tasks.value.findIndex((item) => item.id === data.id)] = data
    const messages = {
      accept: data.status === 'accepted' ? '人数已满，委托自动开始' : '已接取，等待委托人开始',
      start: '委托已开始，进入处理中',
      leave: '已退出接取',
      confirm: data.status === 'completed' ? '全体确认，委托完成' : '已确认完成，等待其他人确认',
      cancel: data.status === 'cancelled' ? '委托已取消' : '已发起取消，等待双方确认',
      'confirm-cancel': data.status === 'cancelled' ? '双方已同意，委托已取消' : '你已同意取消，等待其他人确认',
      'cancel-continue': '取消已撤销，委托继续',
      password: '接取密码已更新，请把新密码告知接单人',
    }
    toast.success(messages[key])
  } catch (error) { toast.error(errorMessage(error)) } finally { busy.value = false }
}
function created(task) { showCreate.value = false; tasks.value.unshift(task) }
function attention(task) {
  if (task.status !== 'awaiting' || !me.value) return ''
  if (isMyPublish(task)) return task.publisher_confirmed_at ? '' : '待你确认'
  if (isMyAccept(task)) {
    const mine = task.members.find((m) => m.user.id === me.value.id)
    return mine && !mine.confirmed_at ? '待你确认' : ''
  }
  return ''
}
onMounted(load)
</script>

<template>
  <div class="page inner-page">
    <div class="page-title"><div><span class="eyebrow">MY REQUESTS</span><h1>我的委托</h1><p>跟进正在进行的协作与过往记录。</p></div><button class="button" @click="showCreate = true"><Plus :size="18" />发布委托</button></div>
    <div class="tabs" role="tablist"><button v-for="item in tabs" :key="item.value" :class="{ active: tab === item.value }" @click="tab = item.value">{{ item.label }}<span>{{ item.value === 'active' ? tasks.filter(t => activeStatuses.includes(t.status)).length : '' }}</span></button></div>
    <div v-if="loading" class="task-grid"><div v-for="i in 3" :key="i" class="task-card skeleton" /></div>
    <div v-else-if="filtered.length" class="task-grid"><TaskCard v-for="task in filtered" :key="task.id" :task="task" show-role :hint="attention(task)" @select="selected = $event" /></div>
    <div v-else class="empty-state"><ClipboardList :size="34" /><h3>这里还没有委托</h3><p>切换其他分类查看，或去大厅联系接取委托。</p><RouterLink class="button secondary" to="/">浏览委托大厅</RouterLink></div>
    <CreateTaskDialog v-if="showCreate" @close="showCreate = false" @created="created" />
    <TaskDialog v-if="selected" :task="selected" :busy="busy" @close="selected = null" @action="action" />
  </div>
</template>
