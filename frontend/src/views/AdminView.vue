<script setup>
import { computed, onMounted, ref } from 'vue'
import { Eye, EyeOff, Search, ShieldCheck, UsersRound, ClipboardList, Clock3, CircleCheck } from 'lucide-vue-next'
import { api, errorMessage } from '../api'
import { useToast } from '../composables/toast'
import StatusBadge from '../components/StatusBadge.vue'

const toast = useToast()
const tasks = ref([])
const stats = ref({ users: 0, tasks: 0, processing: 0, completed: 0, hidden: 0 })
const search = ref('')
const loading = ref(true)
const filtered = computed(() => tasks.value.filter((task) => `${task.title}${task.publisher.nickname}`.toLowerCase().includes(search.value.toLowerCase())))
const statItems = computed(() => [
  { label: '注册用户', value: stats.value.users, icon: UsersRound },
  { label: '全部委托', value: stats.value.tasks, icon: ClipboardList },
  { label: '处理中', value: stats.value.processing, icon: Clock3 },
  { label: '已完成', value: stats.value.completed, icon: CircleCheck },
])
async function load() {
  loading.value = true
  try { const [taskRes, statRes] = await Promise.all([api.get('/admin/tasks'), api.get('/admin/stats')]); tasks.value = taskRes.data; stats.value = statRes.data }
  catch (error) { toast.error(errorMessage(error)) } finally { loading.value = false }
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
const date = (value) => new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(new Date(value))
onMounted(load)
</script>

<template>
  <div class="page inner-page admin-page">
    <div class="page-title"><div><span class="eyebrow"><ShieldCheck :size="15" /> ADMIN CONSOLE</span><h1>委托监管台</h1><p>查看平台运行状态，处理不合规委托。</p></div></div>
    <div class="admin-stats"><div v-for="item in statItems" :key="item.label"><component :is="item.icon" :size="20" /><span>{{ item.label }}</span><strong>{{ item.value }}</strong></div></div>
    <section class="admin-table-section">
      <div class="admin-toolbar"><div><h2>全部委托</h2><span>隐藏 {{ stats.hidden }} 项</span></div><label class="search-field"><Search :size="17" /><input v-model="search" placeholder="搜索标题或发布人" /></label></div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>委托</th><th>发布人</th><th>状态</th><th>到期时间</th><th>可见性</th><th><span class="sr-only">操作</span></th></tr></thead>
          <tbody>
            <tr v-if="loading"><td colspan="6" class="table-loading">正在加载…</td></tr>
            <tr v-for="task in filtered" v-else :key="task.id" :class="{ dimmed: !task.is_visible }">
              <td><strong>{{ task.title }}</strong><small>#{{ task.id }} · {{ task.category }}</small></td>
              <td>{{ task.publisher.nickname }}</td><td><StatusBadge :status="task.status" /></td><td>{{ date(task.expires_at) }}</td>
              <td><span class="visibility"><Eye v-if="task.is_visible" :size="15" /><EyeOff v-else :size="15" />{{ task.is_visible ? '公开' : '已隐藏' }}</span></td>
              <td><button class="icon-button" :title="task.is_visible ? '隐藏委托' : '恢复公开'" :aria-label="task.is_visible ? '隐藏委托' : '恢复公开'" @click="toggle(task)"><EyeOff v-if="task.is_visible" :size="18" /><Eye v-else :size="18" /></button></td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>
