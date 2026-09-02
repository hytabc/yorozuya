<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { CalendarClock, Coins, KeyRound, MessageCircle, UserRound, UsersRound, X } from 'lucide-vue-next'
import { useAuthStore } from '../stores/auth'
import StatusBadge from './StatusBadge.vue'
import UserProfileCard from './UserProfileCard.vue'

const props = defineProps({ task: { type: Object, required: true }, busy: Boolean })
const emit = defineEmits(['close', 'action'])
const auth = useAuthStore()
const password = ref('')
const profileUserId = ref(null)

function openProfile(userId) {
  if (!auth.isLoggedIn) return emit('action', 'login')
  profileUserId.value = userId
}

const isPublisher = computed(() => auth.user?.id === props.task.publisher_id)
const meMember = computed(() => props.task.members?.find((m) => m.user.id === auth.user?.id))
const isMember = computed(() => Boolean(meMember.value))
const isParticipant = computed(() => isPublisher.value || isMember.value)
const published = computed(() => props.task.status === 'published')
const working = computed(() => props.task.status === 'accepted' || props.task.status === 'awaiting')
const finished = computed(() => props.task.status === 'completed')

const required = computed(() => props.task.required_takers)
const requiredText = computed(() => (required.value == null ? '不限' : `${required.value} 人`))
const joinedCount = computed(() => props.task.members?.length || 0)
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
const totalPeople = computed(() => (props.task.members?.length || 0) + 1)
const everyoneConfirmed = computed(() => finished.value || (working.value && confirmedCount.value >= totalPeople.value))
const canSeeProgress = computed(() => isParticipant.value || auth.isAdmin)

const canTakePanel = computed(() => published.value && auth.isLoggedIn && !isPublisher.value && !isMember.value && !auth.isAdmin)

const confirmCopy = computed(() => {
  if (!isParticipant.value || !working.value || viewerConfirmed.value) return null
  const label = isPublisher.value ? '确认委托完成' : '我已完成，确认完成'
  return { label }
})

const format = (value) => new Intl.DateTimeFormat('zh-CN', { dateStyle: 'long', timeStyle: 'short' }).format(new Date(value))
function onKey(event) { if (event.key === 'Escape') emit('close') }
onMounted(() => { document.body.classList.add('modal-open'); window.addEventListener('keydown', onKey) })
onUnmounted(() => { document.body.classList.remove('modal-open'); window.removeEventListener('keydown', onKey) })

function emitAccept() {
  if (password.value) emit('action', 'accept', { password: password.value })
}
function resetPassword() {
  const next = window.prompt('输入新的接取密码（4-32 位），旧密码将立即失效', '')
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
        <div><dt><UserRound :size="16" />委托人</dt><dd><button class="name-link" type="button" @click="openProfile(task.publisher_id)">{{ task.publisher.nickname }}</button></dd></div>
        <div><dt><CalendarClock :size="16" />有效期至</dt><dd>{{ format(task.expires_at) }}</dd></div>
        <div><dt><UsersRound :size="16" />需要接取人数</dt><dd>{{ requiredText }}<span class="muted">（已 {{ joinedCount }} 人）</span></dd></div>
        <div v-if="task.reward"><dt><Coins :size="16" />委托报酬</dt><dd>{{ task.reward }}</dd></div>
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
          <li v-for="m in task.members" :key="m.user.id" :class="{ confirmed: canSeeProgress && m.confirmed_at }">
            <span class="crew-tag">{{ m.user.id === auth.user?.id ? '我' : '接' }}</span>
            <button class="name-link" type="button" @click="openProfile(m.user.id)">{{ m.user.nickname }}</button><span v-if="m.qq && canSeeProgress" class="crew-qq muted">QQ {{ m.qq }}</span><em v-if="canSeeProgress && m.confirmed_at">已确认</em>
          </li>
        </ul>
        <p v-if="canSeeProgress && (working || finished)" class="crew-progress muted">确认进度 {{ confirmedCount }} / {{ totalPeople }}<template v-if="!everyoneConfirmed"> · 还差 {{ totalPeople - confirmedCount }} 人确认</template></p>
      </div>

      <!-- 待开始（招募中） -->
      <div v-if="published && !auth.isLoggedIn" class="notice info-notice">
        <strong>想接这份委托？</strong>
        <p>登录后即可看到委托人 QQ 并洽谈；委托人同意后会把接取密码告诉你（本委托共需 {{ requiredText }}）。</p>
      </div>

      <div v-if="published && isPublisher && !isMember" class="notice info-notice">
        <strong>委托待开始，等待接单人</strong>
        <p>已加入 {{ joinedCount }} / {{ requiredText }}。凑齐人数会自动开始，也可以等接单人联系你谈妥后手动开始；想换人先重设密码。</p>
      </div>

      <div v-if="published && isMember && !isPublisher" class="notice success-notice">
        <strong>你已接取，等待委托人开始</strong>
        <p v-if="autoRemain != null && autoRemain > 0">还需 {{ autoRemain }} 人接取后自动开始，委托人也可以提前手动开始。</p>
        <p v-else>委托人开始后即可进行任务。</p>
      </div>

      <div v-if="canTakePanel" class="take-panel">
        <div class="notice info-notice">
          <strong>接取流程</strong>
          <p><MessageCircle :size="14" /> 先联系委托人洽谈<template v-if="!task.contact_qq">（委托人暂未填写 QQ，可稍后再来或换个委托试试）</template><template v-else>：QQ {{ task.contact_qq }}</template>；<KeyRound :size="14" /> 对方同意后会把接取密码告诉你。</p>
        </div>
        <div class="accept-tools">
          <input v-model.trim="password" type="password" minlength="1" maxlength="72" autocomplete="off" placeholder="输入委托人提供的接取密码" aria-label="接取密码" @keydown.enter="emitAccept" />
          <button class="button" :disabled="busy || !password" @click="emitAccept">{{ busy ? '处理中…' : '凭密码接取' }}</button>
        </div>
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

      <div v-if="!task.is_visible" class="notice error-notice">该委托已被管理员隐藏：{{ task.admin_note || '未填写原因' }}</div>
      <footer class="dialog-footer">
        <span class="muted">发布于 {{ format(task.created_at) }}<template v-if="task.started_at"> · 开始于 {{ format(task.started_at) }}</template></span>
        <div class="dialog-actions">
          <button v-if="published && isPublisher && !isMember" class="button" :disabled="busy || joinedCount === 0" @click="$emit('action', 'start')">{{ busy ? '处理中…' : '开始委托任务' }}</button>
          <button v-if="published && isPublisher && !isMember" class="button secondary small" :disabled="busy" @click="resetPassword">重设接取密码</button>
          <button v-if="published && isPublisher && !isMember" class="button danger small" :disabled="busy" @click="$emit('action', 'cancel')">{{ busy ? '处理中…' : '取消委托' }}</button>
          <button v-if="published && isMember && !isPublisher" class="button danger small" :disabled="busy" @click="$emit('action', 'leave')">{{ busy ? '处理中…' : '退出接取' }}</button>
          <button v-if="confirmCopy && !viewerConfirmed" class="button" :disabled="busy" @click="$emit('action', 'confirm')">{{ busy ? '处理中…' : confirmCopy.label }}</button>
          <button v-if="published && !auth.isLoggedIn" class="button" @click="$emit('action', 'login')">登录后联系委托人</button>
        </div>
      </footer>
    </section>
  </div>
</template>
