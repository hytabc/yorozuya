<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { BarChart3, Edit3, Eye, EyeOff, Megaphone, Pin, Plus, Save, Trash2, UsersRound, X } from 'lucide-vue-next'
import { api, errorMessage } from '../api'
import { useToast } from '../composables/toast'

const toast = useToast()
const activeTab = ref('analytics')
const loading = ref(true)
const announcements = ref([])
const rangeDays = ref(7)
const analytics = ref({ days: 7, total_views: 0, total_visitors: 0, today_views: 0, today_visitors: 0, pages: [], daily: [] })
const editing = ref(false)
const saving = ref(false)
const form = reactive({ id: null, kind: 'site', title: '', content: '', is_published: false, is_pinned: false, starts_at: '', ends_at: '' })
const maxDailyViews = computed(() => Math.max(1, ...analytics.value.daily.map((item) => item.views)))

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

async function loadAnnouncements() {
  announcements.value = (await api.get('/operations/announcements')).data
}
async function loadAnalytics() {
  analytics.value = (await api.get('/operations/analytics', { params: { days: rangeDays.value } })).data
}
async function load() {
  loading.value = true
  try {
    await Promise.all([loadAnnouncements(), loadAnalytics()])
  } catch (error) {
    toast.error(errorMessage(error, '运营数据加载失败'))
  } finally {
    loading.value = false
  }
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

onMounted(load)
</script>

<template>
  <div class="page inner-page operations-page">
    <div class="page-title operations-title">
      <div><span class="eyebrow"><BarChart3 :size="15" /> COMMUNITY OPERATIONS</span><h1>社区运营</h1><p>维护公告并观察站内页面活跃情况</p></div>
      <button v-if="activeTab === 'announcements'" class="button" type="button" @click="resetForm()"><Plus :size="17" />新建公告</button>
    </div>

    <div class="tabs operations-tabs" role="tablist">
      <button :class="{ active: activeTab === 'analytics' }" role="tab" @click="activeTab = 'analytics'"><BarChart3 :size="16" />数据分析</button>
      <button :class="{ active: activeTab === 'announcements' }" role="tab" @click="activeTab = 'announcements'"><Megaphone :size="16" />公告管理</button>
    </div>

    <div v-if="loading" class="notice-empty">正在加载运营数据…</div>
    <template v-else-if="activeTab === 'analytics'">
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
    </template>

    <template v-else>
      <div class="announcement-admin-list">
        <article v-for="item in announcements" :key="item.id" class="announcement-admin-row">
          <div class="announcement-admin-main"><span class="notice-kind" :class="item.kind">{{ item.kind === 'site' ? '网站公告' : '活动公告' }}</span><span v-if="item.is_pinned" class="pin-label"><Pin :size="12" />置顶</span><h2>{{ item.title }}</h2><p>{{ item.content }}</p></div>
          <div class="announcement-admin-meta"><span class="publish-state"><Eye v-if="statusOf(item) === '展示中'" :size="14" /><EyeOff v-else :size="14" />{{ statusOf(item) }}</span><small>{{ formatDate(item.starts_at || item.created_at) }}</small><div><button class="icon-button" title="编辑公告" aria-label="编辑公告" @click="resetForm(item)"><Edit3 :size="16" /></button><button class="icon-button danger-icon" title="删除公告" aria-label="删除公告" @click="removeAnnouncement(item)"><Trash2 :size="16" /></button></div></div>
        </article>
        <div v-if="!announcements.length" class="notice-empty"><Megaphone :size="28" />暂无公告</div>
      </div>
    </template>

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
