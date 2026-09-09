<script setup>
import { computed, onMounted, ref } from 'vue'
import { CalendarDays, Megaphone } from 'lucide-vue-next'
import { api, errorMessage } from '../api'

const announcements = ref([])
const loading = ref(true)
const error = ref('')
const siteItems = computed(() => announcements.value.filter((item) => item.kind === 'site'))
const eventItems = computed(() => announcements.value.filter((item) => item.kind === 'event'))

function formatDate(value) {
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
}

async function load() {
  try {
    announcements.value = (await api.get('/announcements')).data
  } catch (requestError) {
    error.value = errorMessage(requestError, '公告加载失败')
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="page inner-page announcements-page">
    <div class="page-title">
      <div><span class="eyebrow"><Megaphone :size="15" /> COMMUNITY BULLETIN</span><h1>公告中心</h1><p>网站动态与近期社区活动</p></div>
    </div>

    <div v-if="loading" class="notice-empty">正在加载公告…</div>
    <div v-else-if="error" class="notice-empty error-notice">{{ error }}</div>
    <div v-else class="announcement-columns">
      <section class="announcement-section" aria-labelledby="site-notice-heading">
        <header><Megaphone :size="20" /><div><h2 id="site-notice-heading">网站公告</h2><p>功能更新、服务安排与规则调整</p></div></header>
        <div v-if="siteItems.length" class="announcement-list">
          <article v-for="item in siteItems" :key="item.id" class="announcement-item" :class="{ pinned: item.is_pinned }">
            <span v-if="item.is_pinned" class="notice-kind">置顶</span>
            <h3>{{ item.title }}</h3>
            <p>{{ item.content }}</p>
            <footer><span>{{ formatDate(item.starts_at || item.created_at) }}</span><span>发布人 {{ item.author_name }}</span></footer>
          </article>
        </div>
        <div v-else class="notice-empty compact">暂无网站公告</div>
      </section>

      <section class="announcement-section event-section" aria-labelledby="event-notice-heading">
        <header><CalendarDays :size="20" /><div><h2 id="event-notice-heading">活动公告</h2><p>社区活动、报名信息与时间安排</p></div></header>
        <div v-if="eventItems.length" class="announcement-list">
          <article v-for="item in eventItems" :key="item.id" class="announcement-item" :class="{ pinned: item.is_pinned }">
            <span v-if="item.is_pinned" class="notice-kind">置顶</span>
            <h3>{{ item.title }}</h3>
            <p>{{ item.content }}</p>
            <footer><span>{{ formatDate(item.starts_at || item.created_at) }}</span><span v-if="item.ends_at">截至 {{ formatDate(item.ends_at) }}</span></footer>
          </article>
        </div>
        <div v-else class="notice-empty compact">暂无活动公告</div>
      </section>
    </div>
  </div>
</template>
