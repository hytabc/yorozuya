<script setup>
import { computed, onMounted, ref } from 'vue'
import { CalendarDays, Check, Copy, Heart, HeartHandshake, MessageCircle, Store } from 'lucide-vue-next'
import { api, errorMessage } from '../api'
import { useToast } from '../composables/toast'
import { useAuthStore } from '../stores/auth'
import UserProfileCard from '../components/UserProfileCard.vue'
import UserAvatar from '../components/UserAvatar.vue'
import VolunteerApplyDialog from '../components/VolunteerApplyDialog.vue'

const toast = useToast()
const auth = useAuthStore()
const loading = ref(true)
const error = ref('')
const groupChatId = ref('')
const staff = ref([])
const volunteers = ref([])
const copied = ref(false)
const selectedUser = ref(null)
const showApplyDialog = ref(false)
const myApplication = ref(null)

const canApply = computed(() =>
  auth.user && !auth.user.is_admin && auth.user.role === 'user' && myApplication.value?.status !== 'pending'
)

const joined = (value) =>
  new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: 'long' }).format(new Date(value))

async function copyGroupId() {
  if (!groupChatId.value) return
  try {
    await navigator.clipboard.writeText(groupChatId.value)
    copied.value = true
    toast.success('群聊 ID 已复制')
    window.setTimeout(() => { copied.value = false }, 1800)
  } catch {
    toast.error('复制失败，请手动选择群聊 ID')
  }
}

async function loadMyApplication() {
  if (!auth.user) return
  try {
    const { data } = await api.get('/volunteer-applications/mine')
    myApplication.value = data
  } catch { /* 未登录或加载失败时不展示申请状态 */ }
}

onMounted(async () => {
  try {
    const { data } = await api.get('/staff')
    groupChatId.value = data.group_chat_id
    staff.value = data.staff
    volunteers.value = data.volunteers
  } catch (err) {
    error.value = errorMessage(err, '无法加载成员名录')
  } finally {
    loading.value = false
  }
  loadMyApplication()
})
</script>

<template>
  <div class="page inner-page staff-page">
    <div class="page-title staff-title">
      <div><span class="eyebrow"><Store :size="15" /> MEMBER DIRECTORY</span><h1>管理员与志愿者</h1><p>公开展示服务成员资料；想成为志愿者，普通用户可直接在下方提交申请。</p></div>
    </div>

    <section v-if="canApply" class="apply-section" aria-label="志愿者申请">
      <div v-if="myApplication?.status === 'pending'" class="apply-banner pending">
        <HeartHandshake :size="18" /><span>你的志愿者申请正在审核中，请耐心等待管理员处理。</span>
      </div>
      <template v-else>
        <div v-if="myApplication?.status === 'rejected'" class="apply-banner rejected">
          <span>上一次申请未通过{{ myApplication.review_note ? `：${myApplication.review_note}` : '' }}，欢迎补充理由后再次申请。</span>
        </div>
        <button class="button" type="button" @click="showApplyDialog = true"><HeartHandshake :size="16" />申请成为志愿者</button>
      </template>
    </section>

    <section class="staff-group-band" aria-label="群聊信息">
      <div><MessageCircle :size="21" /><span><small>权限申请群聊 ID</small><strong>{{ groupChatId || '暂未配置' }}</strong></span></div>
      <button v-if="groupChatId" class="icon-button" :title="copied ? '已复制' : '复制群聊 ID'" :aria-label="copied ? '群聊 ID 已复制' : '复制群聊 ID'" @click="copyGroupId">
        <Check v-if="copied" :size="18" /><Copy v-else :size="18" />
      </button>
    </section>

    <div v-if="loading" class="staff-empty">正在加载成员信息…</div>
    <div v-else-if="error" class="staff-empty error-notice">{{ error }}</div>
    <template v-else>
      <section class="directory-section" aria-labelledby="staff-heading">
        <div class="directory-heading"><Store :size="19" /><h2 id="staff-heading">管理员</h2><span>{{ staff.length }} 人</span></div>
        <div v-if="!staff.length" class="staff-empty compact"><strong>暂时没有可联系的管理员</strong></div>
        <div v-else class="staff-grid">
          <button v-for="member in staff" :key="member.id" class="staff-card" type="button" @click="selectedUser = member">
            <header>
              <UserAvatar :user="member" :size="50" />
              <div><h3>{{ member.nickname }}</h3><span class="role-tag role-staff"><Store :size="13" />管理员</span></div>
            </header>
            <p class="staff-bio">{{ member.bio || '这位管理员还没有填写个人简介。' }}</p>
            <footer>
              <span><MessageCircle :size="15" />QQ：<strong>{{ member.qq || '未填写' }}</strong></span>
              <span><CalendarDays :size="15" />{{ joined(member.created_at) }} 加入</span>
            </footer>
          </button>
        </div>
      </section>

      <section class="directory-section" aria-labelledby="volunteer-heading">
        <div class="directory-heading"><Heart :size="19" /><h2 id="volunteer-heading">志愿者</h2><span>{{ volunteers.length }} 人</span></div>
        <div v-if="!volunteers.length" class="staff-empty compact"><strong>暂时没有志愿者</strong></div>
        <div v-else class="staff-grid">
          <button v-for="member in volunteers" :key="member.id" class="staff-card volunteer-card" type="button" @click="selectedUser = member">
            <header>
              <UserAvatar :user="member" :size="50" />
              <div><h3>{{ member.nickname }}</h3><span class="role-tag role-volunteer"><Heart :size="13" />志愿者</span></div>
            </header>
            <p class="staff-bio">{{ member.bio || '这位志愿者还没有填写个人简介。' }}</p>
            <footer>
              <span><MessageCircle :size="15" />QQ：<strong>{{ member.qq || (member.qq_public ? '未填写' : '未公开') }}</strong></span>
              <span><CalendarDays :size="15" />{{ joined(member.created_at) }} 加入</span>
            </footer>
          </button>
        </div>
      </section>
    </template>
    <div v-if="selectedUser" class="modal-backdrop" @mousedown.self="selectedUser = null">
      <UserProfileCard :initial-user="selectedUser" class="directory-profile-dialog" @close="selectedUser = null" />
    </div>
    <VolunteerApplyDialog v-if="showApplyDialog" @close="showApplyDialog = false" @submitted="myApplication = $event" />
  </div>
</template>

<style scoped>
.apply-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
  align-items: flex-start;
  margin-bottom: 18px;
}

.apply-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 10px 14px;
  border-radius: 12px;
  font-size: 14px;
}

.apply-banner.pending {
  color: var(--accent, #6c5ce7);
  background: color-mix(in srgb, var(--accent, #6c5ce7) 10%, transparent);
}

.apply-banner.rejected {
  color: inherit;
  background: var(--surface-muted, rgba(128, 128, 128, 0.12));
}
</style>
