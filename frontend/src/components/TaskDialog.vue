<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { CalendarClock, Coins, KeyRound, LockOpen, MessageCircle, Store, UserRound, UsersRound, X } from 'lucide-vue-next'
import { api } from '../api'
import { useAuthStore } from '../stores/auth'
import StatusBadge from './StatusBadge.vue'
import UserProfileCard from './UserProfileCard.vue'

const props = defineProps({ task: { type: Object, required: true }, busy: Boolean })
const emit = defineEmits(['close', 'action'])
const auth = useAuthStore()
const password = ref('')
const profileUserId = ref(null)
const staffGroupId = ref('')

function openProfile(userId) {
  if (!auth.isLoggedIn) return emit('action', 'login')
  profileUserId.value = userId
}

const isPublisher = computed(() => auth.user?.id === props.task.publisher_id)
const meMember = computed(() => props.task.members?.find((m) => m.user.id === auth.user?.id))
const isMember = computed(() => Boolean(meMember.value))
const isParticipant = computed(() => isPublisher.value || meMember.value?.response_status === 'accepted')
const published = computed(() => props.task.status === 'published')
const designated = computed(() => Boolean(props.task.is_designated))
const working = computed(() => props.task.status === 'accepted' || props.task.status === 'awaiting')
const finished = computed(() => props.task.status === 'completed')
const requiresPassword = computed(() => props.task.requires_password !== false)
const anonymousView = computed(() => props.task.is_anonymous && props.task.publisher.id === 0)

const required = computed(() => props.task.required_takers)
const requiredText = computed(() => (required.value == null ? '不限' : `${required.value} 人`))
const acceptedCount = computed(() => props.task.members?.filter((m) => m.response_status === 'accepted').length || 0)
const pendingMember = computed(() => meMember.value?.response_status === 'pending')
const joinedCount = computed(() => acceptedCount.value)
const pendingCount = computed(() => props.task.members?.filter((m) => m.response_status === 'pending').length || 0)
const autoRemain = computed(() => {
  if (published.value && required.value != null) return Math.max(0, required.value - joinedCount.value)
  return null
})

const viewerConfirmed = computed(() => (isPublisher.value ? Boolean(props.task.publisher_confirmed_at) : Boolean(meMember.value?.confirmed_at)))
const confirmedCount = computed(() => {
  const publisher = props.task.publisher_confirmed_at ? 1 : 0
  const members = props.task.members?.filter((m) => m.confirmed_at).length || 0
  return publisher + members
})
const totalPeople = computed(() => acceptedCount.value + 1)
const everyoneConfirmed = computed(() => finished.value || (working.value && confirmedCount.value >= totalPeople.value))
const canSeeProgress = computed(() => isParticipant.value || auth.isAdmin)

const canTakePanel = computed(() => published.value && auth.isLoggedIn && !isPublisher.value && !isMember.value && !auth.isAdmin && !designated.value && (!requiresPassword.value || ['volunteer', 'staff'].includes(auth.user?.role)))
const canRespondDesignated = computed(() => published.value && designated.value && pendingMember.value && !auth.isAdmin)
const isRegularUser = computed(() => published.value && requiresPassword.value && auth.isLoggedIn && !isPublisher.value && !isMember.value && !auth.isAdmin && auth.user?.role === 'user')

const confirmCopy = computed(() => {
  if (!isParticipant.value || !working.value || viewerConfirmed.value) return null
  const label = isPublisher.value ? '确认委托完成' : '我已完成，确认完成'
  return { label }
})

// ---- 取消流程 ----
const cancelling = computed(() => props.task.status === 'cancelling')
const cancellable = computed(() => isParticipant.value && !cancelling.value && ['published', 'accepted', 'awaiting'].includes(props.task.status))
const cancelAgreedByMe = computed(() => (isPublisher.value ? Boolean(props.task.publisher_cancel_confirmed_at) : Boolean(meMember.value?.cancel_confirmed_at)))
const cancelAgreedCount = computed(() => {
  const publisher = props.task.publisher_cancel_confirmed_at ? 1 : 0
  const members = props.task.members?.filter((m) => m.cancel_confirmed_at).length || 0
  return publisher + members
})
const cancelRequesterName = computed(() => {
  if (!props.task.cancel_requested_by) return ''
  if (props.task.publisher_id === props.task.cancel_requested_by) return props.task.publisher.nickname
  const requester = props.task.members?.find((m) => m.user.id === props.task.cancel_requested_by)
  return requester?.user.nickname || ''
})

const format = (value) => new Intl.DateTimeFormat('zh-CN', { dateStyle: 'long', timeStyle: 'short' }).format(new Date(value))
function onKey(event) { if (event.key === 'Escape') emit('close') }
onMounted(async () => {
  document.body.classList.add('modal-open')
  window.addEventListener('keydown', onKey)
  if (isRegularUser.value) {
    try { staffGroupId.value = (await api.get('/staff')).data.group_chat_id }
    catch { staffGroupId.value = '' }
  }
})
onUnmounted(() => { document.body.classList.remove('modal-open'); window.removeEventListener('keydown', onKey) })

function emitAccept() {
  if (!requiresPassword.value || password.value) emit('action', 'accept', { password: requiresPassword.value ? password.value : null })
}
function resetPassword() {
  const next = window.prompt(requiresPassword.value ? '输入新的接取密码（4-32 位），旧密码将立即失效' : '输入接取密码（4-32 位），设置后将仅允许志愿者或店员凭密码接取', '')
  if (next === null) return
  emit('action', 'password', { password: next.trim() })
}
</script>

<template>
  <div class="modal-backdrop" @mousedown.self="$emit('close')">
    <section class="dialog task-dialog" role="dialog" aria-modal="true" :aria-label="task.title">
      <button class="icon-button dialog-close" aria-label="关闭" title="关闭" @click="$emit('close')"><X :size="20" /></button>
      <div class="dialog-heading">
        <div class="task-tags"><StatusBadge :status="task.status" /><span class="category-tag">{{ task.category }}</span></div>
        <h2>{{ task.title }}</h2>
      </div>
      <p class="task-description">{{ task.description }}</p>
      <dl class="task-detail-grid">
        <div><dt><UserRound :size="16" />委托人</dt><dd><button v-if="task.publisher.id > 0" class="name-link" type="button" @click="openProfile(task.publisher.id)">{{ task.publisher.nickname }}</button><span v-else class="muted">匿名委托人</span></dd></div>
        <div><dt><CalendarClock :size="16" />有效期至</dt><dd>{{ format(task.expires_at) }}</dd></div>
        <div><dt><UsersRound :size="16" />需要接取人数</dt><dd>{{ requiredText }}<span v-if="!anonymousView" class="muted">（已响应 {{ joinedCount }} 人<template v-if="pendingCount">，待响应 {{ pendingCount }} 人</template>）</span></dd></div>
        <div><dt><component :is="designated ? UsersRound : (requiresPassword ? KeyRound : LockOpen)" :size="16" />接取方式</dt><dd>{{ designated ? '指定人员响应' : (requiresPassword ? '凭密码接取' : '无需密码，直接接取') }}</dd></div>
        <div><dt><Coins :size="16" />是否付费</dt><dd><span class="pay-tag" :class="`pay-${task.pay_type || 'paid'}`">{{ task.pay_type === 'free' ? '无偿' : '有偿' }}</span><template v-if="task.pay_type !== 'free' && task.reward"> · {{ task.reward }}</template><span v-if="task.pay_type !== 'free' && !task.reward" class="muted"> · 报酬待协商</span></dd></div>
        <div v-if="task.contact_qq"><dt><MessageCircle :size="16" />委托人 QQ</dt><dd>{{ task.contact_qq }}</dd></div>
      </dl>

      <!-- 点击成员名称查看个人资料 -->
      <UserProfileCard v-if="profileUserId" :user-id="profileUserId" @close="profileUserId = null" />

      <!-- 协作成员与完成进度 -->
      <div v-if="isParticipant || task.members?.length" class="crew-block">
        <h4>协作成员（{{ totalPeople }} 人<template v-if="canSeeProgress">，完成需全员确认</template>）</h4>
        <ul class="crew-list">
          <li :class="{ confirmed: canSeeProgress && task.publisher_confirmed_at }">
            <span class="crew-tag role-owner">委</span><button class="name-link" type="button" @click="openProfile(task.publisher_id)">{{ task.publisher.nickname }}</button><em v-if="canSeeProgress && task.publisher_confirmed_at">已确认</em>
          </li>
          <li v-for="m in task.members" :key="m.user.id" :class="{ confirmed: canSeeProgress && m.confirmed_at, declined: m.response_status === 'declined', pending: m.response_status === 'pending' }">
            <span class="crew-tag">{{ m.user.id === auth.user?.id ? '我' : '接' }}</span>
            <button class="name-link" type="button" @click="openProfile(m.user.id)">{{ m.user.nickname }}</button><span v-if="m.qq && canSeeProgress" class="crew-qq muted">QQ {{ m.qq }}</span><em v-if="m.response_status === 'pending'">待响应</em><em v-else-if="m.response_status === 'declined'">已拒绝</em><em v-else-if="canSeeProgress && m.confirmed_at">已确认</em>
          </li>
        </ul>
        <p v-if="canSeeProgress && (working || finished)" class="crew-progress muted">确认进度 {{ confirmedCount }} / {{ totalPeople }}<template v-if="!everyoneConfirmed"> · 还差 {{ totalPeople - confirmedCount }} 人确认</template></p>
      </div>

      <!-- 待开始（招募中） -->
      <div v-if="published && !auth.isLoggedIn" class="notice info-notice">
        <strong>想接这份委托？</strong>
        <p v-if="requiresPassword"><template v-if="anonymousView">登录后凭密码接取即可成为协作成员；接取后双方联系方式互见，可线下洽谈。</template><template v-else>登录后即可看到委托人 QQ 并洽谈；委托人同意后会把接取密码告诉你（本委托共需 {{ requiredText }}）。</template></p>
        <p v-else><template v-if="anonymousView">这是匿名无密码委托，所有权限等级的非管理员用户登录后均可直接接取；接取后双方联系方式互见。</template><template v-else>这是无密码委托，所有权限等级的非管理员用户登录后均可直接接取（本委托共需 {{ requiredText }}）。</template></p>
      </div>

      <div v-if="published && isPublisher && !isMember" class="notice info-notice">
        <strong>委托待开始，等待接单人</strong>
        <p v-if="designated">已指定 {{ requiredText }}，已响应 {{ joinedCount }} 人，待响应 {{ pendingCount }} 人。所有被指定人员响应后，委托才会开始。</p>
        <p v-else-if="requiresPassword">已加入 {{ joinedCount }} / {{ requiredText }}。凑齐人数会自动开始，也可以等接单人联系你谈妥后手动开始；想换人先重设密码。</p>
        <p v-else>已加入 {{ joinedCount }} / {{ requiredText }}。所有权限等级的非管理员用户均可直接接取，凑齐人数会自动开始。</p>
      </div>

      <div v-if="published && isMember && !isPublisher && !pendingMember" class="notice success-notice">
        <strong>你已接取，等待委托人开始</strong>
        <p v-if="autoRemain != null && autoRemain > 0">还需 {{ autoRemain }} 人接取后自动开始，委托人也可以提前手动开始。</p>
        <p v-else>委托人开始后即可进行任务。</p>
      </div>
      <div v-if="canRespondDesignated" class="take-panel">
        <div class="notice info-notice"><strong>你被指定接取此委托</strong><p>无需密码，请选择接受或拒绝。接受后将按协作成员参与完成确认。</p></div>
        <div class="accept-tools"><button class="button" :disabled="busy" @click="$emit('action', 'accept')">{{ busy ? '处理中…' : '接受委托' }}</button><button class="button secondary" :disabled="busy" @click="$emit('action', 'leave')">拒绝委托</button></div>
      </div>

      <div v-if="canTakePanel" class="take-panel">
        <div class="notice info-notice">
          <strong>{{ requiresPassword ? '接取流程' : '公开接取' }}</strong>
          <p v-if="requiresPassword"><template v-if="anonymousView"><KeyRound :size="14" /> 匿名委托：请输入委托人私下告知的接取密码，接取后双方联系方式互见，可线下洽谈。</template><template v-else><MessageCircle :size="14" /> 先联系委托人洽谈<template v-if="!task.contact_qq">（委托人暂未填写 QQ，可稍后再来或换个委托试试）</template><template v-else>：QQ {{ task.contact_qq }}</template>；<KeyRound :size="14" /> 对方同意后会把接取密码告诉你。</template></p>
          <p v-else><template v-if="anonymousView"><LockOpen :size="14" /> 匿名委托已开放直接接取，无需密码。接取后双方联系方式互见，可线下洽谈。</template><template v-else><LockOpen :size="14" />委托人已开放直接接取，无需密码。接取后你将成为协作成员，并需要参与完成及取消确认。</template></p>
        </div>
        <div v-if="requiresPassword" class="accept-tools">
          <input v-model.trim="password" type="password" minlength="1" maxlength="72" autocomplete="off" placeholder="输入委托人提供的接取密码" aria-label="接取密码" @keydown.enter="emitAccept" />
          <button class="button" :disabled="busy || !password" @click="emitAccept">{{ busy ? '处理中…' : '凭密码接取' }}</button>
        </div>
        <div v-else class="accept-tools"><button class="button wide" :disabled="busy" @click="emitAccept">{{ busy ? '处理中…' : '直接接取' }}</button></div>
      </div>

      <!-- 普通用户只能直接接取无密码委托 -->
      <div v-if="isRegularUser" class="notice info-notice">
        <strong>这是有密码委托，普通用户不能接取</strong>
        <p><Store :size="14" />请联系<RouterLink class="notice-link" to="/staff" @click="$emit('close')">任意店员</RouterLink>申请加入群聊<template v-if="staffGroupId">（群聊 ID：<strong class="inline-strong">{{ staffGroupId }}</strong>）</template>，由店员确认后手动提升为志愿者。</p>
      </div>
      <div v-if="published && auth.isLoggedIn && !isPublisher && !isMember && auth.isAdmin" class="notice info-notice">
        <strong>管理员账号不接取委托</strong>
        <p>管理员负责平台管理；如需测试接取流程，请使用志愿者账号。</p>
      </div>

      <!-- 进行中 / 待确认 -->
      <div v-if="working && isParticipant && viewerConfirmed" class="notice success-notice">
        <strong>你已确认完成，等待其余人确认</strong>
        <p>进度 {{ confirmedCount }} / {{ totalPeople }}，全部确认后委托即完成。</p>
      </div>
      <div v-else-if="working && isParticipant && task.status === 'awaiting'" class="notice info-notice">
        <strong>已有人确认完成，等待你确认</strong>
        <p>进度 {{ confirmedCount }} / {{ totalPeople }}；确认无误后点击下方按钮。</p>
      </div>
      <div v-else-if="working && isParticipant" class="notice info-notice">
        <strong>{{ isPublisher ? '任务进行中' : '任务进行中，完成后请确认' }}</strong>
        <p>委托人与每一位接单人都确认完成后，委托才会标记为已完成（进度 {{ confirmedCount }} / {{ totalPeople }}）。</p>
      </div>

      <!-- 已完成 -->
      <div v-if="finished && isParticipant" class="notice success-notice">
        <strong>委托已完成</strong>
        <p>委托人与全体接单人（{{ totalPeople }} 人）均已确认，感谢这次协作。</p>
      </div>

      <!-- 取消确认中 -->
      <div v-if="cancelling && isParticipant" class="notice info-notice">
        <strong>{{ cancelRequesterName }} 发起取消委托</strong>
        <p>需委托人与全体接单人（{{ totalPeople }} 人）确认，全部同意后委托才会取消（已同意 {{ cancelAgreedCount }} / {{ totalPeople }}）。</p>
      </div>
      <div v-if="cancelling && isParticipant && cancelAgreedByMe" class="notice success-notice">
        <strong>你已同意取消，等待其他人确认</strong>
      </div>
      <div v-else-if="cancelling && isParticipant" class="notice success-notice">
        <strong>对方正在确认取消，等待你的决定</strong>
        <p>可以同意取消，也可以选择继续委托。</p>
      </div>

      <div v-if="!task.is_visible" class="notice error-notice">该委托已被管理人员屏蔽：{{ task.admin_note || '未填写原因' }}</div>
      <footer class="dialog-footer">
        <span class="muted">发布于 {{ format(task.created_at) }}<template v-if="task.started_at"> · 开始于 {{ format(task.started_at) }}</template><template v-if="task.status === 'cancelling'"> · 取消请求发起于 {{ format(task.cancel_requested_at) }}</template></span>
        <div class="dialog-actions">
          <button v-if="published && isPublisher && !isMember && !designated" class="button" :disabled="busy || joinedCount === 0" @click="$emit('action', 'start')">{{ busy ? '处理中…' : '开始委托任务' }}</button>
          <button v-if="published && isPublisher && !isMember && !designated" class="button secondary small" :disabled="busy" @click="resetPassword">{{ requiresPassword ? '重设接取密码' : '设置接取密码' }}</button>
          <button v-if="published && isMember && !isPublisher && !designated && !cancelling" class="button danger small" :disabled="busy" @click="$emit('action', 'leave')">{{ busy ? '处理中…' : '退出接取' }}</button>
          <button v-if="cancellable && !cancelling" class="button danger small" :disabled="busy" @click="$emit('action', 'cancel')">{{ busy ? '处理中…' : '取消委托' }}</button>
          <button v-if="cancelling && isParticipant && cancelAgreedByMe" class="button secondary small" :disabled="busy" @click="$emit('action', 'cancel-continue')">{{ busy ? '处理中…' : '撤回，继续委托' }}</button>
          <template v-if="cancelling && isParticipant && !cancelAgreedByMe">
            <button class="button" :disabled="busy" @click="$emit('action', 'confirm-cancel')">{{ busy ? '处理中…' : '同意取消' }}</button>
            <button class="button secondary small" :disabled="busy" @click="$emit('action', 'cancel-continue')">{{ busy ? '处理中…' : '继续委托' }}</button>
          </template>
          <button v-if="confirmCopy && !viewerConfirmed" class="button" :disabled="busy" @click="$emit('action', 'confirm')">{{ busy ? '处理中…' : confirmCopy.label }}</button>
          <button v-if="published && !auth.isLoggedIn" class="button" @click="$emit('action', 'login')">{{ requiresPassword ? '登录后联系委托人' : '登录后直接接取' }}</button>
        </div>
      </footer>
    </section>
  </div>
</template>
