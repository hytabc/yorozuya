<script setup>
import { computed, onMounted, ref } from 'vue'
import { CalendarDays, Heart, HeartHandshake, MessageCircle, ShieldAlert, Sparkles, Store } from 'lucide-vue-next'
import { api, errorMessage } from '../api'
import { useAuthStore } from '../stores/auth'
import UserProfileCard from '../components/UserProfileCard.vue'
import UserAvatar from '../components/UserAvatar.vue'
import VolunteerApplyDialog from '../components/VolunteerApplyDialog.vue'

const auth = useAuthStore()
const loading = ref(true)
const error = ref('')
const staff = ref([])
const disciplinarians = ref([])
const mascots = ref([])
const volunteers = ref([])
const selectedUser = ref(null)
const showApplyDialog = ref(false)
const myApplication = ref(null)

const canApply = computed(() =>
  auth.user && !auth.user.is_admin && auth.user.role === 'user' && myApplication.value?.status !== 'pending'
)

const directorySections = computed(() => [
  { id: 'staff', label: '管理员', members: staff.value, icon: Store, cardClass: '', empty: '暂时没有可联系的管理员' },
  { id: 'disciplinarians', label: '风纪委员', members: disciplinarians.value, icon: ShieldAlert, cardClass: 'disciplinarian-card', empty: '暂时没有风纪委员' },
  { id: 'mascots', label: '看板娘', members: mascots.value, icon: Sparkles, cardClass: 'mascot-card', empty: '暂时没有看板娘' },
  { id: 'volunteers', label: '志愿者', members: volunteers.value, icon: Heart, cardClass: 'volunteer-card', empty: '暂时没有志愿者' },
])

const joined = (value) =>
  new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: 'long' }).format(new Date(value))

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
    staff.value = data.staff
    disciplinarians.value = data.disciplinarians
    mascots.value = data.mascots
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
      <div><span class="eyebrow"><Store :size="15" /> MEMBER DIRECTORY</span><h1>社区服务成员</h1><p>查看管理员、风纪委员、看板娘与志愿者资料；普通用户可在下方申请成为志愿者。</p></div>
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

    <div v-if="loading" class="staff-empty">正在加载成员信息…</div>
    <div v-else-if="error" class="staff-empty error-notice">{{ error }}</div>
    <template v-else>
      <section v-for="section in directorySections" :key="section.id" class="directory-section" :aria-labelledby="`${section.id}-heading`">
        <div class="directory-heading"><component :is="section.icon" :size="19" /><h2 :id="`${section.id}-heading`">{{ section.label }}</h2><span>{{ section.members.length }} 人</span></div>
        <div v-if="!section.members.length" class="staff-empty compact"><strong>{{ section.empty }}</strong></div>
        <div v-else class="staff-grid">
          <button v-for="member in section.members" :key="member.id" class="staff-card" :class="section.cardClass" type="button" @click="selectedUser = member">
            <header>
              <UserAvatar :user="member" :size="50" />
              <div><h3>{{ member.nickname }}</h3><span class="role-tag" :class="`role-${member.role}`"><component :is="section.icon" :size="13" />{{ section.label }}</span></div>
            </header>
            <p class="staff-bio">{{ member.bio || `这位${section.label}还没有填写个人简介。` }}</p>
            <footer>
              <span><MessageCircle :size="15" />QQ：<strong>{{ member.qq || (member.role === 'staff' ? '未填写' : '未公开') }}</strong></span>
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
