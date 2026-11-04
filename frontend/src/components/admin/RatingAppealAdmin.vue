<script setup>
import { onMounted, ref } from 'vue'
import { Check, RotateCcw, Scale } from '@lucide/vue'
import { api, errorMessage } from '../../api'
import { useToast } from '../../composables/toast'

const toast = useToast()
const loading = ref(true)
const items = ref([])
const busyId = ref(null)
const changeStars = ref({})

const date = (value) => new Intl.DateTimeFormat('zh-CN', {
  month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
}).format(new Date(value))

async function load() {
  loading.value = true
  try {
    items.value = (await api.get('/admin/rating-appeals', { params: { status: 'pending' } })).data
  } catch (error) {
    toast.error(errorMessage(error, '评价申诉加载失败'))
  } finally {
    loading.value = false
  }
}

async function resolve(item, action, starsHalf) {
  busyId.value = item.id
  try {
    await api.post(`/admin/rating-appeals/${item.id}/resolve`, {
      action,
      stars_half: action === 'change' ? Number(starsHalf) : null,
      note: action === 'reject' ? '申诉未通过' : null,
    })
    items.value = items.value.filter((row) => row.id !== item.id)
    toast.success(action === 'reject' ? '已驳回申诉' : '已调整该评价')
  } catch (error) {
    toast.error(errorMessage(error))
  } finally {
    busyId.value = null
  }
}

function starsOptions(item) {
  return Array.from({ length: 11 }, (_, half) => half)
}

onMounted(load)
</script>

<template>
  <div>
    <div class="admin-toolbar"><div><h2>评价申诉</h2><span>待处理 {{ items.length }} 条</span></div><span class="muted"><Scale :size="15" /> 撤销或改星后会重算该单积分与聚合分</span></div>
    <div v-if="loading" class="skeleton-list" aria-hidden="true"><div v-for="i in 3" :key="i" class="skeleton-block" /></div>
    <ul v-else-if="items.length" class="feedback-admin-list">
      <li v-for="item in items" :key="item.id">
        <div class="fb-head">
          <span class="fb-state">待处理</span>
          <strong>#{{ item.task_id }} {{ item.task_title }}</strong>
          <span class="muted">申诉人：{{ item.user.nickname }}</span>
          <span class="muted">{{ item.rater_role === 'publisher' ? '被委托人评价' : '被接单人评价' }} · {{ item.stars }} 星</span>
          <time class="muted">{{ date(item.created_at) }}</time>
        </div>
        <p class="fb-content">原评价：{{ item.comment || '（无文字）' }}</p>
        <p class="fb-content">申诉理由：{{ item.reason }}</p>
        <div class="fb-actions">
          <button class="button secondary small" :disabled="busyId === item.id" @click="resolve(item, 'reject')"><Check :size="15" />驳回</button>
          <button class="button secondary small" :disabled="busyId === item.id" @click="resolve(item, 'revoke')"><RotateCcw :size="15" />撤销该评价</button>
          <select v-model.number="changeStars[item.id]" aria-label="改为星级">
            <option v-for="half in starsOptions(item)" :key="half" :value="half">{{ (half / 2).toFixed(half % 2 === 0 ? 0 : 1) }} 星</option>
          </select>
          <button class="button secondary small" :disabled="busyId === item.id || changeStars[item.id] == null" @click="resolve(item, 'change', changeStars[item.id])"><Scale :size="15" />改为该星级</button>
        </div>
      </li>
    </ul>
    <div v-else class="feedback-admin-empty"><Scale :size="28" />暂无待处理的评价申诉</div>
  </div>
</template>
