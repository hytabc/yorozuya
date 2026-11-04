<script setup>
import { onMounted, ref } from 'vue'
import { CalendarCheck, Check, Coins, Sparkles } from '@lucide/vue'
import { api, errorMessage } from '../api'
import { useToast } from '../composables/toast'
import { useAuthStore } from '../stores/auth'

const toast = useToast()
const auth = useAuthStore()
const loading = ref(true)
const busyKey = ref('')
const data = ref({ day: '', items: [], claimed_count: 0 })

async function load() {
  loading.value = true
  try {
    data.value = (await api.get('/daily')).data
  } catch (error) {
    toast.error(errorMessage(error, '每日任务加载失败'))
  } finally {
    loading.value = false
  }
}

async function claim(item) {
  if (!item.can_claim) return
  busyKey.value = item.key
  try {
    const { data: result } = await api.post(`/daily/${item.key}/claim`)
    data.value = result.daily
    auth.patchUser({ lifetime_points: result.lifetime_points, wallet_points: result.wallet_points })
    toast.success(`已领取 ${result.reward} 积分`)
  } catch (error) {
    toast.error(errorMessage(error))
  } finally {
    busyKey.value = ''
  }
}

onMounted(load)
</script>

<template>
  <div class="page inner-page daily-page">
    <div class="page-title">
      <div>
        <span class="eyebrow"><CalendarCheck :size="15" />DAILY</span>
        <h1>每日任务</h1>
        <p>每天 0 点（北京时间）刷新，完成并领取即可获得少量积分。当前累计 {{ auth.user?.lifetime_points || 0 }} 分。</p>
      </div>
    </div>

    <div v-if="loading" class="skeleton-list"><div v-for="i in 4" :key="i" class="skeleton-block" /></div>
    <template v-else>
      <section class="daily-summary">
        <span><Sparkles :size="16" />已领取 {{ data.claimed_count }} / {{ data.items.length }} 项</span>
        <span class="muted">{{ data.day }}</span>
      </section>
      <ul class="daily-list">
        <li v-for="item in data.items" :key="item.key" :class="{ done: item.claimed, clear: item.key === 'all_clear' }">
          <div class="daily-main">
            <strong>{{ item.label }}<span v-if="item.key === 'all_clear'" class="role-tag">额外</span></strong>
            <small class="muted">{{ item.detail }}</small>
          </div>
          <div class="daily-progress">
            <span class="daily-bar"><i :style="{ width: `${Math.min(100, (item.progress / item.target) * 100)}%` }" /></span>
            <small class="muted">{{ item.progress }} / {{ item.target }}</small>
          </div>
          <div class="daily-reward"><Coins :size="15" />{{ item.reward }} 分</div>
          <button v-if="item.claimed" class="button secondary small" disabled><Check :size="15" />已领取</button>
          <button v-else class="button small" :disabled="!item.can_claim || busyKey === item.key" @click="claim(item)">
            {{ busyKey === item.key ? '领取中…' : item.can_claim ? '领取' : '进行中' }}
          </button>
        </li>
      </ul>
      <p class="field-hint">发布任务要求描述不少于 30 字；分享同一份委托每天只计一次。官方活跃委托已移到委托大厅，接取后完成站内动作即可确认。</p>

    </template>
  </div>
</template>
