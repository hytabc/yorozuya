<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { BarChart3, Check, Edit3, Eye, EyeOff, Megaphone, Pin, Plus, Save, Sparkles, Trash2, UsersRound, X } from '@lucide/vue'
import { useRouter } from 'vue-router'
import { api, errorMessage } from '../api'
import { useToast } from '../composables/toast'
import { useAuthStore } from '../stores/auth'
import UserTitleTag from '../components/UserTitleTag.vue'

const toast = useToast()
const auth = useAuthStore()
const router = useRouter()
// 标签页可见性：数据看板仅管理员组（超管/管理员）可见；公告管理归看板娘/超管；内测申请三者皆可。
const canSeeAnalytics = computed(() => auth.canManageRoles)
const canSeeAnnouncements = computed(() => auth.isAdmin || auth.isMascot)
const canSeeBetaApplications = computed(() => auth.isAdmin || auth.isStaff || auth.isMascot)
function defaultTab() {
  if (canSeeAnalytics.value) return 'analytics'
  if (canSeeAnnouncements.value) return 'announcements'
  return 'beta-applications'
}
const activeTab = ref('analytics')
// 按标签页懒加载：只请求当前标签的数据，其余标签首次切入时才加载。
const tabLoading = reactive({ analytics: false, announcements: false, 'beta-applications': false })
const tabLoaded = reactive({ analytics: false, announcements: false, 'beta-applications': false })
// 尚未加载完成即显示骨架（含「未开始」与「请求中」两种状态）。
const isFirstLoad = (tab) => !tabLoaded[tab]
const announcements = ref([])
const betaApplications = ref([])
const reviewBetaAppId = ref(null)
const rangeDays = ref(7)
const analytics = ref({ days: 7, total_views: 0, total_visitors: 0, today_views: 0, today_visitors: 0, pages: [], daily: [], events: [] })
const editing = ref(false)
const saving = ref(false)
const form = reactive({ id: null, kind: 'site', title: '', content: '', is_published: false, is_pinned: false, starts_at: '', ends_at: '' })
const maxDailyViews = computed(() => Math.max(1, ...analytics.value.daily.map((item) => item.views)))
const maxEventCount = computed(() => Math.max(1, ...analytics.value.events.map((item) => item.count)))
// 内测申请角标走独立轻量接口（看板娘也能取），数据看板不再承担该角标。
const pendingBetaApplications = ref(0)

function formatDate(value) {
  if (!value) return '长期有效'
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
}
function dateInput(value) {
  if (!value) return ''
  const date = new Date(value)
  const offset = date.getTimezoneOffset() * 60000
  return new Date(date.getTime() - offset).toISOString().slice(0, 16)
}
function statusOf(item) {
  const now = Date.now()
  if (!item.is_published) return '草稿'
  if (item.starts_at && new Date(item.starts_at).getTime() > now) return '待生效'
  if (item.ends_at && new Date(item.ends_at).getTime() <= now) return '已结束'
  return '展示中'
}
function resetForm(item = null) {
  Object.assign(form, item ? {
    id: item.id, kind: item.kind, title: item.title, content: item.content,
    is_published: item.is_published, is_pinned: item.is_pinned,
    starts_at: dateInput(item.starts_at), ends_at: dateInput(item.ends_at),
  } : { id: null, kind: 'site', title: '', content: '', is_published: false, is_pinned: false, starts_at: '', ends_at: '' })
  editing.value = true
}

async function loadSummary() {
  try { pendingBetaApplications.value = (await api.get('/operations/summary')).data.pending_beta_applications || 0 } catch { /* 角标失败不影响页面 */ }
}
async function loadAnnouncements() {
  tabLoading.announcements = true
  try {
    announcements.value = (await api.get('/operations/announcements')).data
    tabLoaded.announcements = true
  } finally { tabLoading.announcements = false }
}
async function loadAnalytics() {
  tabLoading.analytics = true
  try {
    analytics.value = (await api.get('/operations/analytics', { params: { days: rangeDays.value } })).data
    tabLoaded.analytics = true
  } finally { tabLoading.analytics = false }
}
async function loadBetaApplications() {
  tabLoading['beta-applications'] = true
  try {
    betaApplications.value = (await api.get('/operations/beta-applications')).data
    tabLoaded['beta-applications'] = true
  } finally { tabLoading['beta-applications'] = false }
}
function loadTab(tab) {
  if (tabLoaded[tab] || tabLoading[tab]) return
  const loaders = {
    analytics: loadAnalytics,
    announcements: loadAnnouncements,
    'beta-applications': loadBetaApplications,
  }
  loaders[tab]?.().catch((error) => toast.error(errorMessage(error, '运营数据加载失败')))
}
async function changeRange() {
  try { await loadAnalytics() } catch (error) { toast.error(errorMessage(error)) }
}
async function saveAnnouncement() {
  if (form.title.trim().length < 2 || form.content.trim().length < 2) return toast.error('请填写完整的公告标题和内容')
  if (form.starts_at && form.ends_at && new Date(form.ends_at) <= new Date(form.starts_at)) return toast.error('结束时间必须晚于开始时间')
  saving.value = true
  const payload = {
    kind: form.kind, title: form.title, content: form.content,
    is_published: form.is_published, is_pinned: form.is_pinned,
    starts_at: form.starts_at ? new Date(form.starts_at).toISOString() : null,
    ends_at: form.ends_at ? new Date(form.ends_at).toISOString() : null,
  }
  try {
    if (form.id) await api.put(`/operations/announcements/${form.id}`, payload)
    else await api.post('/operations/announcements', payload)
    await loadAnnouncements()
    editing.value = false
    toast.success(form.id ? '公告已更新' : '公告已创建')
  } catch (error) {
    toast.error(errorMessage(error, '公告保存失败'))
  } finally {
    saving.value = false
  }
}
async function removeAnnouncement(item) {
  if (!window.confirm(`确定永久删除“${item.title}”吗？也可以编辑后暂停展示。`)) return
  try {
    await api.delete(`/operations/announcements/${item.id}`)
    announcements.value = announcements.value.filter((current) => current.id !== item.id)
    toast.success('公告已删除')
  } catch (error) { toast.error(errorMessage(error)) }
}

async function reviewBetaApplication(item, action) {
  let note = null
  if (action === 'reject') {
    note = window.prompt('请输入拒绝理由（会展示给申请人，可留空）', item.review_note || '')
    if (note === null) return
  }
  reviewBetaAppId.value = item.id
  try {
    const { data } = await api.post(`/operations/beta-applications/${item.id}/review`, { action, note: note?.trim() || null })
    betaApplications.value[betaApplications.value.findIndex((current) => current.id === item.id)] = data
    toast.success(action === 'approve' ? `已为 ${data.user.nickname} 开通虚拟人生` : '已拒绝该内测申请')
  } catch (error) { toast.error(errorMessage(error)) } finally { reviewBetaAppId.value = null }
}

onMounted(async () => {
  // 双保险：即使路由守卫被绕过，也先确认服务端身份再拉取运营数据。
  await auth.restore()
  if (!auth.canOperate) { router.replace('/'); return }
  // 依角色落到第一个可见标签：管理员组看数据、看板娘看公告。
  activeTab.value = defaultTab()
  loadSummary()
  loadTab(activeTab.value)
})
watch(activeTab, (tab) => loadTab(tab))
</script>

<template>
  <div class="page inner-page operations-page">
    <div class="page-title operations-title">
      <div><span class="eyebrow"><BarChart3 :size="15" /> COMMUNITY OPERATIONS</span><h1>社区运营</h1><p>维护公告并观察站内页面活跃情况</p></div>
      <button v-if="activeTab === 'announcements'" class="button" type="button" @click="resetForm()"><Plus :size="17" />新建公告</button>
    </div>

    <div class="tabs operations-tabs" role="tablist">
      <button v-if="canSeeAnalytics" :class="{ active: activeTab === 'analytics' }" role="tab" @click="activeTab = 'analytics'"><BarChart3 :size="16" />数据分析</button>
      <button v-if="canSeeAnnouncements" :class="{ active: activeTab === 'announcements' }" role="tab" @click="activeTab = 'announcements'"><Megaphone :size="16" />公告管理</button>
      <button v-if="canSeeBetaApplications" :class="{ active: activeTab === 'beta-applications' }" role="tab" @click="activeTab = 'beta-applications'"><Sparkles :size="16" />内测申请<span v-if="pendingBetaApplications">{{ pendingBetaApplications }}</span></button>
    </div>

    <template v-if="activeTab === 'analytics'">
      <div v-if="isFirstLoad('analytics')" aria-hidden="true">
        <section class="metric-grid"><div v-for="i in 4" :key="i" class="skeleton-block" /></section>
        <div class="analytics-layout"><section class="analytics-panel skeleton" /><section class="analytics-panel skeleton" /></div>
      </div>
      <template v-else>
      <div class="analytics-toolbar"><div><h2>活跃概览</h2><span>按北京时间统计，访客按账号或匿名会话去重</span></div><select v-model.number="rangeDays" aria-label="统计周期" @change="changeRange"><option :value="7">近 7 天</option><option :value="30">近 30 天</option><option :value="90">近 90 天</option></select></div>
      <section class="metric-grid" aria-label="关键指标">
        <div><Eye :size="19" /><span>今日浏览</span><strong>{{ analytics.today_views }}</strong></div>
        <div><UsersRound :size="19" /><span>今日访客</span><strong>{{ analytics.today_visitors }}</strong></div>
        <div><Eye :size="19" /><span>{{ rangeDays }} 天浏览</span><strong>{{ analytics.total_views }}</strong></div>
        <div><UsersRound :size="19" /><span>{{ rangeDays }} 天访客</span><strong>{{ analytics.total_visitors }}</strong></div>
      </section>

      <div class="analytics-layout">
        <section class="analytics-panel">
          <header><h2>每日趋势</h2><span>浏览次数</span></header>
          <div class="trend-chart">
            <div v-for="item in analytics.daily" :key="item.date" class="trend-column" :title="`${item.date}：${item.views} 次浏览，${item.visitors} 位访客`">
              <span class="trend-value">{{ item.views }}</span><i :style="{ height: item.views ? `${Math.max(4, item.views / maxDailyViews * 100)}%` : '0' }" /><small>{{ item.date.slice(5) }}</small>
            </div>
          </div>
        </section>
        <section class="analytics-panel page-ranking">
          <header><h2>页面活跃</h2><span>访客 / 浏览</span></header>
          <div v-for="item in analytics.pages" :key="item.page_key" class="ranking-row">
            <span>{{ item.label }}</span><div><i :style="{ width: `${analytics.total_visitors ? item.visitors / Math.max(...analytics.pages.map((page) => page.visitors), 1) * 100 : 0}%` }" /></div><strong>{{ item.visitors }} / {{ item.views }}</strong>
          </div>
        </section>
      </div>
      <section class="analytics-panel page-ranking">
        <header><h2>热门操作</h2><span>次数</span></header>
        <div v-for="item in analytics.events" :key="`${item.page_key}-${item.event_key}`" class="ranking-row">
          <span>{{ item.label }}<small v-if="item.page_label" class="muted"> · {{ item.page_label }}</small></span><div><i :style="{ width: `${item.count / maxEventCount * 100}%` }" /></div><strong>{{ item.count }}</strong>
        </div>
        <p v-if="!analytics.events.length" class="muted">暂无操作事件</p>
      </section>
      </template>
    </template>

    <template v-else-if="activeTab === 'announcements'">
      <div v-if="isFirstLoad('announcements')" class="announcement-admin-list" aria-hidden="true">
        <div v-for="i in 3" :key="i" class="announcement-admin-row skeleton" />
      </div>
      <div v-else class="announcement-admin-list">
        <article v-for="item in announcements" :key="item.id" class="announcement-admin-row">
          <div class="announcement-admin-main"><span class="notice-kind" :class="item.kind">{{ item.kind === 'site' ? '网站公告' : '活动公告' }}</span><span v-if="item.is_pinned" class="pin-label"><Pin :size="12" />置顶</span><h2>{{ item.title }}</h2><p>{{ item.content }}</p></div>
          <div class="announcement-admin-meta"><span class="publish-state"><Eye v-if="statusOf(item) === '展示中'" :size="14" /><EyeOff v-else :size="14" />{{ statusOf(item) }}</span><small>{{ formatDate(item.starts_at || item.created_at) }}</small><div><button class="icon-button" title="编辑公告" aria-label="编辑公告" @click="resetForm(item)"><Edit3 :size="16" /></button><button class="icon-button danger-icon" title="删除公告" aria-label="删除公告" @click="removeAnnouncement(item)"><Trash2 :size="16" /></button></div></div>
        </article>
        <div v-if="!announcements.length" class="notice-empty"><Megaphone :size="28" />暂无公告</div>
      </div>
    </template>

    <section v-else class="admin-table-section">
      <div class="admin-toolbar"><div><h2>虚拟人生内测申请</h2><span>待审核 {{ pendingBetaApplications }} 条</span></div><span>通过后自动开通内测资格</span></div>
      <div v-if="isFirstLoad('beta-applications')" class="skeleton-list" aria-hidden="true">
        <div v-for="i in 3" :key="i" class="skeleton-block" />
      </div>
      <ul v-else-if="betaApplications.length" class="feedback-admin-list">
        <li v-for="item in betaApplications" :key="item.id" :class="{ handled: item.status !== 'pending' }">
          <div class="fb-head"><span class="fb-state" :class="`state-${item.status}`">{{ item.status === 'pending' ? '待审核' : item.status === 'approved' ? '已通过' : '已拒绝' }}</span><strong>{{ item.user.nickname }}</strong><UserTitleTag :title="item.user.title" /><time class="muted">{{ formatDate(item.created_at) }}</time></div>
          <p class="fb-content">{{ item.reason }}</p>
          <div class="fb-actions">
            <span v-if="item.status !== 'pending' && item.review_note" class="fb-reply-admin">审核说明：{{ item.review_note }}</span>
            <template v-if="item.status === 'pending'"><button class="button secondary small" :disabled="reviewBetaAppId === item.id" @click="reviewBetaApplication(item, 'approve')"><Check :size="15" />通过</button><button class="button secondary small" :disabled="reviewBetaAppId === item.id" @click="reviewBetaApplication(item, 'reject')"><X :size="15" />拒绝</button></template>
          </div>
        </li>
      </ul>
      <div v-else class="notice-empty"><Sparkles :size="28" />还没有收到内测申请</div>
    </section>

    <div v-if="editing" class="modal-backdrop" @click.self="editing = false">
      <form class="dialog announcement-editor" @submit.prevent="saveAnnouncement">
        <button class="icon-button dialog-close" type="button" aria-label="关闭" @click="editing = false"><X :size="19" /></button>
        <div class="dialog-heading"><span class="eyebrow"><Megaphone :size="14" /> ANNOUNCEMENT</span><h2>{{ form.id ? '编辑公告' : '新建公告' }}</h2></div>
        <div class="form-stack">
          <div class="form-row"><label>公告类型<select v-model="form.kind"><option value="site">网站公告</option><option value="event">活动公告</option></select></label><label>标题<input v-model="form.title" maxlength="80" placeholder="公告标题" /></label></div>
          <label>公告内容<textarea v-model="form.content" rows="7" maxlength="5000" placeholder="填写需要向社区公开的信息" /></label>
          <div class="form-row"><label>开始时间（可选）<input v-model="form.starts_at" type="datetime-local" /></label><label>结束时间（可选）<input v-model="form.ends_at" type="datetime-local" /></label></div>
          <div class="toggle-row"><label><input v-model="form.is_published" type="checkbox" />发布展示</label><label><input v-model="form.is_pinned" type="checkbox" />置顶显示</label></div>
        </div>
        <div class="dialog-footer"><button class="button secondary" type="button" @click="editing = false">取消</button><button class="button" :disabled="saving"><Save :size="16" />{{ saving ? '保存中…' : '保存公告' }}</button></div>
      </form>
    </div>
  </div>
</template>
