<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { MessageCircle, Plus, Search, SlidersHorizontal, Sparkles, TriangleAlert } from 'lucide-vue-next'
import { api, errorMessage } from '../api'
import { useAuthStore } from '../stores/auth'
import { useToast } from '../composables/toast'
import TaskCard from '../components/TaskCard.vue'
import TaskDialog from '../components/TaskDialog.vue'
import CreateTaskDialog from '../components/CreateTaskDialog.vue'
import FeedbackDialog from '../components/FeedbackDialog.vue'
import { CATEGORIES } from '../constants'

const auth = useAuthStore()
const router = useRouter()
const toast = useToast()
const tasks = ref([])
const loading = ref(true)
const selected = ref(null)
const showCreate = ref(false)
const showFeedback = ref(false)
const busy = ref(false)
const filters = reactive({ search: '', category: '', status: auth.isAdmin || auth.isStaff ? '' : 'published', pay_type: '' })
const categories = CATEGORIES
const payOptions = [
  { value: '', label: '全部报酬' },
  { value: 'paid', label: '有偿' },
  { value: 'free', label: '无偿' },
]
const isManager = computed(() => auth.isAdmin || auth.isStaff)
// 普通用户在大厅只能查看招募中的委托；超级管理员/管理员可查看全部状态。
const statuses = computed(() => isManager.value
  ? [{ value: '', label: '全部状态' }, { value: 'published', label: '招募中' }, { value: 'accepted', label: '处理中' }, { value: 'awaiting', label: '待确认' }, { value: 'cancelling', label: '取消确认中' }, { value: 'completed', label: '已完成' }, { value: 'expired', label: '已过期' }]
  : [{ value: 'published', label: '招募中' }])

const stats = computed(() => ({
  open: tasks.value.filter((item) => item.status === 'published').length,
  active: tasks.value.filter((item) => ['accepted', 'awaiting'].includes(item.status)).length,
  done: tasks.value.filter((item) => item.status === 'completed').length,
}))

let timer
async function load() {
  loading.value = true
  try {
    const params = { search: filters.search, category: filters.category, status: filters.status }
    if (filters.pay_type) params.pay_type = filters.pay_type
    const { data } = await api.get('/tasks', { params })
    tasks.value = data
  } catch (error) { toast.error(errorMessage(error, '委托加载失败')) } finally { loading.value = false }
}
function create() {
  if (!auth.isLoggedIn) return router.push({ path: '/login', query: { redirect: '/' } })
  showCreate.value = true
}
function search() { clearTimeout(timer); timer = setTimeout(load, 280) }
function created(task) { showCreate.value = false; tasks.value.unshift(task) }
function reported() {
  selected.value = null
  load()
}

async function action(key, payload = {}) {
  if (key === 'login') return router.push({ path: '/login', query: { redirect: '/' } })
  busy.value = true
  try {
    const url = `/tasks/${selected.value.id}`
    let data
    if (key === 'accept') ({ data } = await api.post(`${url}/accept`, { password: payload.password ?? null }))
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
      cancel: data.status === 'cancelled' ? '委托已取消' : '已发起取消，等待双方确认',
      'confirm-cancel': data.status === 'cancelled' ? '双方已同意，委托已取消' : '你已同意取消，等待其他人确认',
      'cancel-continue': '取消已撤销，委托继续',
      password: '接取密码已更新，请把新密码告知接单人',
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
        <button class="text-link feedback-entry" type="button" @click="showFeedback = true"><MessageCircle :size="15" />有建议或遇到问题？告诉我们</button>
      </div>
      <div class="hall-stats" aria-label="委托统计">
        <div><strong>{{ stats.open }}</strong><span>正在招募</span></div>
        <div><strong>{{ stats.active }}</strong><span>正在处理</span></div>
        <div><strong>{{ stats.done }}</strong><span>顺利完成</span></div>
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
        <button class="button" @click="create"><Plus :size="18" />发布委托</button>
      </div>
      <div class="filterbar">
        <label class="search-field"><Search :size="18" /><input v-model="filters.search" placeholder="搜索委托标题或内容" aria-label="搜索委托" @input="search" /></label>
        <label class="select-field"><SlidersHorizontal :size="17" /><select v-model="filters.status" aria-label="状态筛选" @change="load"><option v-for="item in statuses" :key="item.value" :value="item.value">{{ item.label }}</option></select></label>
        <select v-model="filters.pay_type" aria-label="报酬筛选" @change="load"><option v-for="item in payOptions" :key="item.value" :value="item.value">{{ item.label }}</option></select>
        <select v-model="filters.category" aria-label="分类筛选" @change="load"><option value="">全部分类</option><option v-for="item in categories" :key="item">{{ item }}</option></select>
      </div>

      <div v-if="loading" class="task-grid"><div v-for="i in 6" :key="i" class="task-card skeleton" /></div>
      <div v-else-if="tasks.length" class="task-grid"><TaskCard v-for="task in tasks" :key="task.id" :task="task" @select="selected = $event" /></div>
      <div v-else class="empty-state"><span>空</span><h3>没有找到相关委托</h3><p>调整筛选条件，或发布第一份委托。</p><button class="button secondary" @click="create">发布委托</button></div>
    </section>

    <section class="disclaimer" aria-label="平台免责声明">
      <div class="section-heading">
        <div><span class="section-index">02</span><h2>免责声明</h2><p>使用本站即代表你已阅读并同意以下条款</p></div>
      </div>
      <div class="disclaimer-body">
        <div class="disclaimer-part">
          <h3>一、平台性质说明</h3>
          <p>本网站仅为信息撮合平台，提供委托需求发布、志愿者接单申请的信息展示服务。平台不参与、不担保、不介入任何委托的执行、报酬交易、线下沟通。所有委托内容由发布用户自行编写，平台不对委托内容真实性、合法性做前置人工审核，违规内容依靠用户举报机制进行处理。</p>
        </div>
        <div class="disclaimer-part">
          <h3>二、关于委托</h3>
          <ol>
            <li>平台不收取任何服务费、抽成，不接收、不处理任何资金流转。委托人与志愿者之间的报酬、转账、押金等全部由双方私下自行协商完成。</li>
            <li>平台不对资金安全、交易履约做任何担保。请用户提高警惕，谨防诈骗，拒绝任何提前缴纳押金、预付款等要求。</li>
          </ol>
        </div>
        <div class="disclaimer-part">
          <h3>三、双向自愿规则</h3>
          <p>本平台委托为双向自愿配对模式。委托人、志愿者均拥有随时取消委托的权利，平台不强制任何一方履行委托。因取消委托、沟通分歧产生的纠纷，由双方自行协商解决，平台不承担调解、赔付责任。</p>
        </div>
        <div class="disclaimer-part">
          <h3>四、用户责任</h3>
          <ol>
            <li>用户注册、发布委托、申请接单，代表用户承诺所提交的信息真实合法，不得发布色情、暴力、诈骗、违法违规内容。</li>
            <li>用户在平台外私下联系沟通产生的人身、财产、名誉损害，全部由当事人自行承担，本平台不承担法律责任。</li>
          </ol>
        </div>
        <div class="disclaimer-part">
          <h3>五、举报与处置</h3>
          <ol>
            <li>若发现违规委托、违规账号，用户可使用网站举报功能提交举报。</li>
            <li>平台收到举报后，将在空闲时间对内容进行核查，有权下架违规委托、限制或封禁违规账号；但不保证100%拦截全部违规内容。</li>
          </ol>
        </div>
        <div class="disclaimer-part">
          <h3>六、法律免责</h3>
          <p>因用户自身行为导致的一切损失，本平台不承担任何民事、刑事赔偿责任。如发生法律纠纷，由当事双方通过司法途径解决。</p>
        </div>
      </div>
    </section>
    <CreateTaskDialog v-if="showCreate" @close="showCreate = false" @created="created" />
    <TaskDialog v-if="selected" :task="selected" :busy="busy" @close="selected = null" @action="action" @reported="reported" />
    <FeedbackDialog v-if="showFeedback" @close="showFeedback = false" />
  </div>
</template>
