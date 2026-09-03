<script setup>
import { onMounted, ref } from 'vue'
import { CalendarDays, Check, Copy, Heart, MessageCircle, Store } from 'lucide-vue-next'
import { api, errorMessage } from '../api'
import { useToast } from '../composables/toast'
import UserProfileCard from '../components/UserProfileCard.vue'

const toast = useToast()
const loading = ref(true)
const error = ref('')
const groupChatId = ref('')
const staff = ref([])
const volunteers = ref([])
const copied = ref(false)
const selectedUserId = ref(null)

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
})
</script>

<template>
  <div class="page inner-page staff-page">
    <div class="page-title staff-title">
      <div><span class="eyebrow"><Store :size="15" /> MEMBER DIRECTORY</span><h1>店员与志愿者</h1><p>公开展示服务成员资料；需要提升权限时，可联系任意店员申请加入群聊。</p></div>
    </div>

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
        <div class="directory-heading"><Store :size="19" /><h2 id="staff-heading">店员</h2><span>{{ staff.length }} 人</span></div>
        <div v-if="!staff.length" class="staff-empty compact"><strong>暂时没有可联系的店员</strong></div>
        <div v-else class="staff-grid">
          <button v-for="member in staff" :key="member.id" class="staff-card" type="button" @click="selectedUserId = member.id">
            <header>
              <span class="user-avatar-lg">{{ member.nickname.slice(0, 1) }}</span>
              <div><h3>{{ member.nickname }}</h3><span class="role-tag role-staff"><Store :size="13" />店员</span></div>
            </header>
            <p class="staff-bio">{{ member.bio || '这位店员还没有填写个人简介。' }}</p>
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
          <button v-for="member in volunteers" :key="member.id" class="staff-card volunteer-card" type="button" @click="selectedUserId = member.id">
            <header>
              <span class="user-avatar-lg">{{ member.nickname.slice(0, 1) }}</span>
              <div><h3>{{ member.nickname }}</h3><span class="role-tag role-volunteer"><Heart :size="13" />志愿者</span></div>
            </header>
            <p class="staff-bio">{{ member.bio || '这位志愿者还没有填写个人简介。' }}</p>
            <footer>
              <span><MessageCircle :size="15" />QQ：<strong>{{ member.qq || '未填写' }}</strong></span>
              <span><CalendarDays :size="15" />{{ joined(member.created_at) }} 加入</span>
            </footer>
          </button>
        </div>
      </section>
    </template>
    <div v-if="selectedUserId" class="modal-backdrop" @mousedown.self="selectedUserId = null">
      <UserProfileCard :user-id="selectedUserId" class="directory-profile-dialog" @close="selectedUserId = null" />
    </div>
  </div>
</template>
