<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Bell, CheckCheck } from '@lucide/vue'
import { useAuthStore } from '../stores/auth'
import { eventLabel, eventTarget, relativeTime, unreadBadge } from '../events'
import {
  loadNotifications,
  loadNotificationSummary,
  markAllRead,
  notifications,
  resetNotifications,
  startNotificationPolling,
  stopNotificationPolling,
} from '../composables/useNotifications'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const open = ref(false)
const panel = ref(null)

const badge = computed(() => unreadBadge(notifications.unread))

async function toggle() {
  open.value = !open.value
  if (!open.value) return
  await loadNotifications(1)
  // 列表已经按未读状态渲染；打开后立即落库为已读，角标随之清零。
  await markAllRead()
}

function go(event) {
  open.value = false
  router.push(eventTarget(event))
}

function onDocumentClick(event) {
  if (!open.value) return
  if (panel.value?.contains(event.target) || event.target?.closest?.('.notification-toggle')) return
  open.value = false
}

watch(() => auth.isLoggedIn, (loggedIn) => {
  if (loggedIn) {
    startNotificationPolling()
  } else {
    stopNotificationPolling()
    resetNotifications()
    open.value = false
  }
}, { immediate: true })

watch(() => route.fullPath, () => { open.value = false })

onMounted(() => {
  document.addEventListener('click', onDocumentClick)
  if (auth.isLoggedIn) startNotificationPolling()
  else loadNotificationSummary()
})
onBeforeUnmount(() => {
  document.removeEventListener('click', onDocumentClick)
  stopNotificationPolling()
})
</script>

<template>
  <div v-if="auth.isLoggedIn" class="notification-wrap">
    <button
      type="button"
      class="icon-button notification-toggle"
      data-tour="notifications"
      :aria-expanded="open"
      aria-haspopup="dialog"
      :aria-label="badge ? `站内通知，${badge} 条未读` : '站内通知'"
      title="站内通知"
      @click.stop="toggle"
    >
      <Bell :size="19" />
      <span v-if="badge" class="notification-badge">{{ badge }}</span>
    </button>

    <section v-if="open" ref="panel" class="notification-panel" role="dialog" aria-label="站内通知">
      <header class="notification-head">
        <strong>站内通知</strong>
        <span class="muted">只显示与你有关的委托动态</span>
      </header>
      <div v-if="notifications.loading" class="skeleton-list"><div class="skeleton-block" /></div>
      <ul v-else-if="notifications.items.length" class="notification-list">
        <li v-for="item in notifications.items" :key="item.id" :class="{ unread: !item.read }">
          <button type="button" @click="go(item)">
            <span class="notification-kind">{{ eventLabel(item.kind) }}</span>
            <span class="notification-title">{{ item.title }}</span>
            <span class="notification-time muted">{{ relativeTime(item.created_at) }}</span>
          </button>
        </li>
      </ul>
      <p v-else class="notification-empty muted">还没有通知。委托有人接取、开始、完成或发起取消时，会在这里提醒你。</p>
      <footer class="notification-foot">
        <span class="muted">每 30 秒刷新一次；也可打开本面板手动拉取。</span>
        <button type="button" class="text-link" @click="loadNotifications(1)"><CheckCheck :size="14" />刷新</button>
      </footer>
    </section>
  </div>
</template>
