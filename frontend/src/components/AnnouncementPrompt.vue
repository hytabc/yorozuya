<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { CalendarDays, Check, Megaphone, Pin } from 'lucide-vue-next'

defineProps({
  announcements: { type: Array, required: true },
})
defineEmits(['confirm'])

const confirmButton = ref(null)

const formatDate = (value) =>
  new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))

onMounted(async () => {
  document.body.classList.add('modal-open')
  await nextTick()
  confirmButton.value?.focus()
})
onBeforeUnmount(() => document.body.classList.remove('modal-open'))
</script>

<template>
  <div class="modal-backdrop announcement-prompt-backdrop">
    <section class="dialog announcement-prompt" role="dialog" aria-modal="true" aria-labelledby="announcement-prompt-title" @keydown.esc.prevent>
      <header class="announcement-prompt-heading">
        <span class="eyebrow"><Megaphone :size="15" /> COMMUNITY BULLETIN</span>
        <h2 id="announcement-prompt-title">社区公告</h2>
        <p>网站动态与近期社区活动</p>
      </header>

      <div class="announcement-prompt-list">
        <article v-for="item in announcements" :key="item.id" class="announcement-prompt-item">
          <div class="announcement-prompt-meta">
            <span class="notice-kind" :class="item.kind">{{ item.kind === 'site' ? '网站公告' : '活动公告' }}</span>
            <span v-if="item.is_pinned" class="announcement-prompt-pin"><Pin :size="12" />置顶</span>
          </div>
          <h3>{{ item.title }}</h3>
          <p>{{ item.content }}</p>
          <footer>
            <span><CalendarDays :size="13" />{{ formatDate(item.updated_at) }}</span>
            <span>发布人 {{ item.author_name }}</span>
          </footer>
        </article>
      </div>

      <footer class="announcement-prompt-actions">
        <button ref="confirmButton" class="button" type="button" @click="$emit('confirm')"><Check :size="17" />确认并关闭</button>
      </footer>
    </section>
  </div>
</template>

<style scoped>
.announcement-prompt-backdrop { z-index: 140; }
.announcement-prompt {
  display: flex;
  flex-direction: column;
  width: min(740px, 100%);
  max-height: calc(100vh - 48px);
  padding: 0;
  overflow: hidden;
}
.announcement-prompt-heading { flex: 0 0 auto; padding: 30px 32px 22px; border-bottom: 1px solid var(--line); }
.announcement-prompt-heading h2 { margin: 12px 0 6px; font-family: Georgia, "Songti SC", serif; font-size: 28px; }
.announcement-prompt-heading p { margin: 0; color: var(--muted); font-size: 13px; }
.announcement-prompt-list { min-height: 0; padding: 0 32px; overflow-y: auto; }
.announcement-prompt-item { padding: 22px 0; border-bottom: 1px solid var(--line); }
.announcement-prompt-item:last-child { border-bottom: 0; }
.announcement-prompt-meta { display: flex; align-items: center; gap: 8px; }
.announcement-prompt-pin { display: inline-flex; align-items: center; gap: 4px; color: var(--muted); font-size: 11px; }
.announcement-prompt-item h3 { margin: 13px 0 9px; overflow-wrap: anywhere; font-size: 18px; }
.announcement-prompt-item > p { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; color: #46504b; font-size: 14px; line-height: 1.75; }
.announcement-prompt-item footer { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px 18px; margin-top: 17px; color: var(--muted); font-size: 11px; }
.announcement-prompt-item footer span { display: inline-flex; align-items: center; gap: 5px; }
.announcement-prompt-actions { flex: 0 0 auto; display: flex; justify-content: flex-end; padding: 18px 32px; border-top: 1px solid var(--line); background: #f8f9f8; }

@media (max-width: 680px) {
  .announcement-prompt { width: 100%; max-height: 92vh; border-radius: 6px 6px 0 0; }
  .announcement-prompt-heading { padding: 25px 20px 19px; }
  .announcement-prompt-heading h2 { font-size: 24px; }
  .announcement-prompt-list { padding: 0 20px; }
  .announcement-prompt-actions { padding: 16px 20px max(18px, env(safe-area-inset-bottom)); }
  .announcement-prompt-actions .button { width: 100%; }
}
</style>
