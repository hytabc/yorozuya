<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { ChevronLeft, ChevronRight, Star, Trophy } from '@lucide/vue'
import { api, errorMessage } from '../api'
import { useToast } from '../composables/toast'
import { useAuthStore } from '../stores/auth'

const toast = useToast()
const auth = useAuthStore()
const loading = ref(true)
const board = ref('points')
const page = ref(1)
const PAGE_SIZE = 20
const data = ref({ board: 'points', title: '', page: 1, page_size: PAGE_SIZE, total: 0, min_count: 0, items: [] })

const BOARDS = [
  { key: 'points', label: '累计积分' },
  { key: 'taker_rating', label: '接单人评分' },
  { key: 'publisher_rating', label: '委托人评分' },
  { key: 'completed', label: '真实委托' },
]
const totalPages = computed(() => Math.max(1, Math.ceil((data.value.total || 0) / PAGE_SIZE)))
const isRatingBoard = computed(() => board.value.endsWith('_rating'))

async function load() {
  loading.value = true
  try {
    data.value = (await api.get('/rankings', { params: { board: board.value, page: page.value, page_size: PAGE_SIZE } })).data
  } catch (error) {
    toast.error(errorMessage(error, '排行榜加载失败'))
  } finally {
    loading.value = false
  }
}

function pick(next) {
  if (board.value === next) return
  board.value = next
  page.value = 1
  load()
}

function go(next) {
  if (next < 1 || next > totalPages.value) return
  page.value = next
  load()
}

const valueText = (item) => (isRatingBoard.value ? `${item.value.toFixed(2)} 星` : `${Math.round(item.value)} ${board.value === 'points' ? '分' : '单'}`)

watch(() => auth.user?.id, load)
onMounted(load)
</script>

<template>
  <div class="page inner-page ranking-page">
    <div class="page-title">
      <div><span class="eyebrow"><Trophy :size="15" />RANKINGS</span><h1>排行榜</h1><p>评分榜使用贝叶斯平滑并至少 5 条评价，一次满分不会直接霸榜；真实委托完成数与积分公开可查，官方委托不计入。</p></div>
    </div>
    <div class="tabs" role="tablist" aria-label="排行榜类别">
      <button v-for="item in BOARDS" :key="item.key" role="tab" :aria-selected="board === item.key" :class="{ active: board === item.key }" @click="pick(item.key)">{{ item.label }}</button>
    </div>

    <div v-if="loading" class="skeleton-list"><div v-for="i in 6" :key="i" class="skeleton-block" /></div>
    <template v-else>
      <p v-if="isRatingBoard" class="field-hint">上榜门槛：至少 {{ data.min_count }} 条评价。</p>
      <ol class="ranking-list">
        <li v-for="item in data.items" :key="item.user.id" :class="{ me: item.is_me }">
          <span class="ranking-pos">{{ item.rank }}</span>
          <RouterLink class="ranking-user" :to="`/creators/${item.user.id}`">{{ item.user.nickname }}<span class="role-tag">Lv{{ item.user.level }}</span></RouterLink>
          <span class="ranking-value"><Star v-if="isRatingBoard" :size="14" />{{ valueText(item) }}</span>
          <span class="muted ranking-count">{{ isRatingBoard ? `${item.count} 条评价` : '' }}</span>
        </li>
      </ol>
      <div v-if="!data.items.length" class="empty-state"><Trophy :size="28" /><h3>这个榜单还没有人上榜</h3><p>完成委托、获得评价后就会出现在这里。</p></div>
      <div v-if="totalPages > 1" class="pager">
        <button class="button secondary small" :disabled="page <= 1" @click="go(page - 1)"><ChevronLeft :size="14" />上一页</button>
        <span class="muted">{{ page }} / {{ totalPages }}</span>
        <button class="button secondary small" :disabled="page >= totalPages" @click="go(page + 1)">下一页<ChevronRight :size="14" /></button>
      </div>
    </template>
  </div>
</template>
