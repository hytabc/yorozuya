<script setup>
import { onMounted, ref } from 'vue'
import { CalendarDays, Coins, Star, Trophy } from '@lucide/vue'
import { api } from '../api'

const props = defineProps({ userId: { type: Number, required: true } })
const loading = ref(true)
const data = ref(null)

const date = (value) => (value ? new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium' }).format(new Date(value)) : '—')

async function load() {
  loading.value = true
  try {
    data.value = (await api.get(`/users/${props.userId}/records`)).data
  } catch {
    data.value = null
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="life-records">
    <div v-if="loading" class="skeleton-block" />
    <template v-else-if="data">
      <div class="life-grid">
        <div><span class="muted"><Trophy :size="15" />等级</span><strong>Lv{{ data.level }}</strong><small v-if="data.next_threshold" class="muted">距下一级还差 {{ data.next_threshold - data.lifetime_points }} 分</small></div>
        <div><span class="muted"><Coins :size="15" />累计积分</span><strong>{{ data.lifetime_points }}</strong></div>
        <div><span class="muted"><CalendarDays :size="15" />加入</span><strong>{{ data.joined_days }} 天</strong></div>
        <div><span class="muted">完成委托</span><strong>{{ data.completed_taken + data.completed_published }}</strong><small class="muted">接单 {{ data.completed_taken }} · 发布 {{ data.completed_published }}</small></div>
        <div><span class="muted"><Star :size="15" />接单评分</span><strong>{{ data.taker_rating.count ? data.taker_rating.average : '—' }}</strong><small class="muted">{{ data.taker_rating.count }} 条评价</small></div>
        <div><span class="muted"><Star :size="15" />委托评分</span><strong>{{ data.publisher_rating.count ? data.publisher_rating.average : '—' }}</strong><small class="muted">{{ data.publisher_rating.count }} 条评价</small></div>
        <div><span class="muted">成就</span><strong>{{ data.achievements_unlocked }}</strong></div>
        <div><span class="muted">首次 / 最近完成</span><strong class="life-dates">{{ date(data.first_completed_at) }} / {{ date(data.last_completed_at) }}</strong></div>
      </div>
      <div v-if="data.top_categories.length" class="life-categories">
        <span class="muted">常做分类：</span>
        <span v-for="item in data.top_categories" :key="item.category" class="facet-chip static">{{ item.category }} ×{{ item.count }}</span>
      </div>
    </template>
    <p v-else class="muted">暂时无法加载人生记录。</p>
  </div>
</template>
