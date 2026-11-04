<script setup>
import { computed, defineAsyncComponent, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { MessageCircle, Plus, Search, SlidersHorizontal, Sparkles, TriangleAlert } from '@lucide/vue'
import { api, errorMessage } from '../api'
import { track } from '../analytics'
import { useAuthStore } from '../stores/auth'
import { useToast } from '../composables/toast'
import TaskCard from '../components/TaskCard.vue'
import TaskDialog from '../components/TaskDialog.vue'
import CreateTaskDialog from '../components/CreateTaskDialog.vue'
import FeedbackDialog from '../components/FeedbackDialog.vue'
import AnnouncementPrompt from '../components/AnnouncementPrompt.vue'
import OnboardingTour from '../components/OnboardingTour.vue'
import { markAnnouncementsSeen, unseenAnnouncements } from '../composables/announcementPrompt'
import { needsOnboarding } from '../composables/onboardingSteps'
import {
  atmosphere,
  loadAtmosphere,
  needsAtmosphereAck,
  openAtmosphereGate,
} from '../composables/useAtmosphere'
import { CATEGORIES, TASK_SKILLS, TASK_PLATFORMS, ATMOSPHERE_TAGS } from '../constants'
import { facetQueryParams } from '../facets'

// 星图按需加载：Three.js 不进入大厅首屏 chunk，切到星图时才拉取。
const HallSpaceView = defineAsyncComponent(() => import('../hall/space/HallSpaceView.vue'))

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const toast = useToast()
const tasks = ref([])
const loading = ref(true)
const selected = ref(null)
const showCreate = ref(false)
const showFeedback = ref(false)
const activeAnnouncements = ref([])
const promptAnnouncements = ref([])
const showAnnouncementPrompt = ref(false)
const busy = ref(false)
// 新手引导：账号级一次性；`?tour=1`（个人设置的「重新查看」）会强制重播一次。
const tourRef = ref(null)
const forceTour = ref(Boolean(route.query.tour))
// 列表始终是默认视图；星图是补充视图，且受服务端开关控制。
const view = ref('list')
const spaceEnabled = ref(false)
// 星图选中只用于高亮；打开详情仍由双击/按钮触发，避免单击就弹窗。
const spaceSelected = ref(null)
const filters = reactive({ search: '', category: '', status: auth.isAdmin || auth.isStaff ? '' : 'published', skill: '', platform: '', atmosphere: '' })
const categories = CATEGORIES
const skillOptions = TASK_SKILLS
const platformOptions = TASK_PLATFORMS
const atmosphereOptions = ATMOSPHERE_TAGS
const isManager = computed(() => auth.isAdmin || auth.isStaff)
const hasFilters = computed(() => Boolean(
  filters.search || filters.category || filters.skill || filters.platform || filters.atmosphere
  || filters.status !== (isManager.value ? '' : 'published'),
))
// 普通用户在大厅只能查看招募中的委托；超级管理员/管理员可查看全部状态。
const statuses = computed(() => isManager.value
  ? [{ value: '', label: '全部状态' }, { value: 'published', label: '招募中' }, { value: 'accepted', label: '处理中' }, { value: 'awaiting', label: '待确认' }, { value: 'cancelling', label: '取消确认中' }, { value: 'completed', label: '已完成' }, { value: 'expired', label: '已过期' }]
  : [{ value: 'published', label: '招募中' }])

// 顶部统计走独立数量接口，展示全站数量，不受筛选与角色可见性影响
const stats = ref({ published: 0, processing: 0, completed: 0 })

async function loadStats() {
  try {
    stats.value = (await api.get('/tasks/stats')).data
  } catch { /* 统计加载失败不影响委托列表 */ }
}

async function loadAnnouncements() {
  try {
    const { data } = await api.get('/announcements')
    activeAnnouncements.value = data
    const userId = auth.isLoggedIn ? auth.user?.id : null
    promptAnnouncements.value = unseenAnnouncements(data, userId)
    showAnnouncementPrompt.value = promptAnnouncements.value.length > 0
  } catch { /* 公告加载失败不影响委托大厅 */ }
}

function confirmAnnouncements() {
  if (auth.isLoggedIn) markAnnouncementsSeen(activeAnnouncements.value, auth.user?.id)
  showAnnouncementPrompt.value = false
  track('announcement.confirm')
  openPendingAtmosphere()
}

let timer
async function load() {
  loading.value = true
  try {
    const params = { search: filters.search, category: filters.category, status: filters.status, ...facetQueryParams(filters) }
    const { data } = await api.get('/tasks', { params })
    tasks.value = data
  } catch (error) { toast.error(errorMessage(error, '委托加载失败')) } finally { loading.value = false }
  loadStats()
}
function clearFilters() {
  filters.search = ''
  filters.category = ''
  filters.skill = ''
  filters.platform = ''
  filters.atmosphere = ''
  filters.status = isManager.value ? '' : 'published'
  load()
}
function create() {
  if (!auth.isLoggedIn) return router.push({ path: '/login', query: { redirect: '/' } })
  // 发布前先完成礼仪确认；确认后用户再点一次发布即可（不做自动续跳，避免歧义）。
  if (needsAtmosphereAck()) return openAtmosphereGate()
  showCreate.value = true
}
function openTask(task) {
  selected.value = task
  track('task.open_detail')
}
function search() { clearTimeout(timer); timer = setTimeout(load, 280) }
function created(task) { showCreate.value = false; tasks.value.unshift(task) }
function reported() {
  selected.value = null
  load()
}

async function action(key, payload = {}) {
  if (key === 'login') return router.push({ path: '/login', query: { redirect: '/' } })
  if (key === 'accept' && needsAtmosphereAck()) return openAtmosphereGate()
  busy.value = true
  try {
    const url = `/tasks/${selected.value.id}`
    let data
    if (key === 'accept') ({ data } = await api.post(`${url}/accept`))
    else ({ data } = await api.post(`${url}/${key}`))
    selected.value = data
    const index = tasks.value.findIndex((item) => item.id === data.id)
    if (index !== -1) tasks.value[index] = data
    const messages = {
      accept: data.status === 'accepted' ? '人数已满，委托自动开始' : '已接取，等待委托人开始',
      start: '委托已开始，进入处理中',
      leave: '已退出接取',
      confirm: data.status === 'completed' ? '全体确认，委托完成' : '已确认完成，等待其他人确认',
      cancel: data.status === 'cancelled' ? '委托已取消' : '已发起取消，等待双方确认',
      'confirm-cancel': data.status === 'cancelled' ? '双方已同意，委托已取消' : '你已同意取消，等待其他人确认',
      'cancel-continue': '取消已撤销，委托继续',
    }
    toast.success(messages[key])
    const trackedEvents = {
      accept: 'task.accept',
      leave: 'task.leave',
      start: 'task.start',
      confirm: 'task.confirm',
      cancel: 'task.cancel',
      'confirm-cancel': 'task.cancel_confirm',
    }
    if (trackedEvents[key]) track(trackedEvents[key])
    loadStats()
  } catch (error) { toast.error(errorMessage(error)) } finally { busy.value = false }
}
// 首次进入委托大厅时展示礼仪确认；已确认过的用户不会再看到。
// 公告弹窗（z-index 140）与礼仪确认（z-index 1200）同时弹出时后者会盖住前者，
// 因此先记下"待确认"，等公告关闭后再弹，首屏浮层才能真正串行。
const atmospherePending = ref(false)
function openPendingAtmosphere() {
  if (!atmospherePending.value || showAnnouncementPrompt.value) return
  atmospherePending.value = false
  openAtmosphereGate()
}
async function checkAtmosphere() {
  await loadAtmosphere({ force: true })
  atmospherePending.value = needsAtmosphereAck()
  openPendingAtmosphere()
}
// 先取公告再决定要不要弹礼仪确认，否则两条并发请求谁先回来都可能让礼仪盖住公告。
async function bootPrompts() {
  await loadAnnouncements()
  await checkAtmosphere()
}
async function loadSiteFlags() {
  try {
    const { data } = await api.get('/site-config')
    spaceEnabled.value = Boolean(data.hall_space_view)
  } catch {
    spaceEnabled.value = false
  }
}
function switchView(next) {
  if (next === 'space' && !spaceEnabled.value) return
  view.value = next
  spaceSelected.value = null
}
// 通知中心点击后跳回 /?task=<id>：复用现有详情弹窗，不新建详情路由。
async function openTaskFromQuery() {
  const taskId = Number(route.query.task)
  if (!taskId) return
  try {
    const { data } = await api.get(`/tasks/${taskId}`)
    openTask(data)
  } catch {
    toast.error('该委托已不可查看')
  }
}
// 首屏可能连着出现三个浮层：公告 → 礼仪确认 → 新手引导。按这个顺序串行，
// 前一个关闭后才起下一个；引导只在委托大厅启动（它的锚点都在这里）。
function maybeStartOnboarding() {
  if (!tourRef.value || !auth.isLoggedIn) return
  if (forceTour.value) {
    forceTour.value = false
    if (route.query.tour) {
      const query = { ...route.query }
      delete query.tour
      router.replace({ path: route.path, query })
    }
    tourRef.value.start({ force: true })
    return
  }
  if (!auth.emailVerified || auth.emailGateRequired) return
  if (!needsOnboarding(auth.user?.onboarding_version)) return
  if (loading.value || showAnnouncementPrompt.value || atmosphere.open) return
  tourRef.value.start()
}

watch(
  [tourRef, () => auth.ready, () => auth.user?.onboarding_version, loading, showAnnouncementPrompt, () => atmosphere.open],
  maybeStartOnboarding,
  { flush: 'post' },
)
onMounted(() => { load(); bootPrompts(); loadSiteFlags(); openTaskFromQuery() })
watch(() => route.query.task, openTaskFromQuery)
watch(() => auth.ready, (ready) => {
  if (!ready) return
  bootPrompts()
}, { immediate: true })
</script>

<template>
  <div class="page hall-page">
    <section class="hall-intro" data-tour="intro">
      <div>
        <span class="eyebrow"><Sparkles :size="15" /> YOROZUYA REQUEST BOARD</span>
        <h1>总有一件事，<br />有人恰好擅长。</h1>
        <p>发布需要帮助的事情，或者接下一份你能完成的委托。</p>
        <button class="text-link feedback-entry" type="button" @click="showFeedback = true"><MessageCircle :size="15" />有建议或遇到问题？告诉我们</button>
      </div>
      <div class="hall-stats" aria-label="委托统计">
        <div><strong>{{ stats.published }}</strong><span>正在招募</span></div>
        <div><strong>{{ stats.processing }}</strong><span>正在处理</span></div>
        <div><strong>{{ stats.completed }}</strong><span>顺利完成</span></div>
      </div>
    </section>

    <section class="hall-notice" role="note" aria-label="平台内容规范">
      <div class="notice-content">
        <TriangleAlert :size="19" class="notice-icon" />
        <div>
          <strong>内容规范提醒</strong>
          <p>本站严禁发布违法违规、色情低俗、暴力恐怖、侵权诽谤、垃圾广告等内容。一经发现，视情节予以删除、禁言或永久封禁账号处理。请自觉遵守法律法规，共同维护良好社区环境。</p>
        </div>
      </div>
    </section>

    <section class="task-workspace">
      <div class="section-heading">
        <div><span class="section-index">01</span><h2>委托大厅</h2><p>浏览当前公开委托</p></div>
        <div class="hall-heading-actions">
          <div v-if="spaceEnabled" class="hall-view-switch" role="group" aria-label="视图切换">
            <button type="button" class="button small" :class="{ secondary: view !== 'list' }" :aria-pressed="view === 'list'" @click="switchView('list')">列表</button>
            <button type="button" class="button small" :class="{ secondary: view !== 'space' }" :aria-pressed="view === 'space'" @click="switchView('space')">星图</button>
          </div>
          <button class="button" data-tour="create-task" @click="create"><Plus :size="18" />发布委托</button>
        </div>
      </div>
      <div class="filterbar">
        <label class="search-field"><Search :size="18" /><input v-model="filters.search" placeholder="搜索委托标题或内容" aria-label="搜索委托" @input="search" /></label>
        <label class="select-field"><SlidersHorizontal :size="17" /><select v-model="filters.status" aria-label="状态筛选" @change="load"><option v-for="item in statuses" :key="item.value" :value="item.value">{{ item.label }}</option></select></label>
        <select v-model="filters.category" aria-label="分类筛选" @change="load"><option value="">全部分类</option><option v-for="item in categories" :key="item">{{ item }}</option></select>
      </div>
      <div class="filterbar facet-filterbar">
        <select v-model="filters.skill" aria-label="技能筛选" @change="load"><option value="">全部技能</option><option v-for="item in skillOptions" :key="item">{{ item }}</option></select>
        <select v-model="filters.platform" aria-label="平台筛选" @change="load"><option value="">全部平台</option><option v-for="item in platformOptions" :key="item">{{ item }}</option></select>
        <select v-model="filters.atmosphere" aria-label="氛围筛选" @change="load"><option value="">全部氛围</option><option v-for="item in atmosphereOptions" :key="item">{{ item }}</option></select>
        <button v-if="hasFilters" class="button secondary small" type="button" @click="clearFilters">清除筛选</button>
      </div>

      <div v-if="loading" class="task-grid"><div v-for="i in 6" :key="i" class="task-card skeleton" /></div>
      <HallSpaceView
        v-else-if="view === 'space'"
        :tasks="tasks"
        :selected="spaceSelected"
        @select="spaceSelected = $event"
        @open="openTask"
        @fallback="switchView('list')"
      />
      <div v-else-if="tasks.length" class="task-grid"><TaskCard v-for="task in tasks" :key="task.id" :task="task" @select="openTask" /></div>
      <div v-else class="empty-state"><span>空</span><h3>这片区域暂时没有符合条件的委托</h3><p>试试清除筛选，或发布一份你真正需要的委托。</p><div class="empty-actions"><button v-if="hasFilters" class="button secondary" @click="clearFilters">清除筛选</button><button class="button" @click="create">发布委托</button></div></div>
    </section>

    <section class="hall-notice" role="note" aria-label="使用条款入口">
      <div class="notice-content">
        <TriangleAlert :size="19" class="notice-icon" />
        <div>
          <strong>这里不担保交易，但这里记录信誉</strong>
          <p>进入大厅前会先展示一屏委托礼仪。完整的平台性质说明、委托规则、用户责任与法律免责条款，始终保留在 <RouterLink class="text-link" to="/terms">使用条款</RouterLink> 页面。</p>
        </div>
      </div>
    </section>
    <CreateTaskDialog v-if="showCreate" @close="showCreate = false" @created="created" />
    <TaskDialog v-if="selected" :task="selected" :busy="busy" @close="selected = null" @action="action" @reported="reported" />
    <FeedbackDialog v-if="showFeedback" @close="showFeedback = false" />
    <AnnouncementPrompt v-if="showAnnouncementPrompt" :announcements="promptAnnouncements" @confirm="confirmAnnouncements" />
    <OnboardingTour v-if="auth.isLoggedIn" ref="tourRef" />
  </div>
</template>
