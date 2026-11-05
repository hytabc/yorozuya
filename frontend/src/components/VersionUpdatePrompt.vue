<script setup>
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Check, History, Sparkles } from '@lucide/vue'
import { api } from '../api'
import { useAuthStore } from '../stores/auth'
import { track } from '../analytics'
import { currentVersion, currentVersionEntry, loadVersionNotes, missedVersionCount, shouldPromptVersion } from '../versionNotes'
import {
  claimPrompt,
  readAckedVersion,
  settleVersionDecision,
  writeAckedVersion,
} from '../composables/versionPrompt'

// 全屏游戏页与后台不打断；其余页面都在首次进入时判定。
const INELIGIBLE_META = ['lifeOnly', 'lifeManager', 'roleManager', 'moderator', 'operations']

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const visible = ref(false)
const entry = ref(null)
const missed = ref(0)
const confirmButton = ref(null)
const busy = ref(false)
let decided = false

function ineligible() {
  // /versions 本身就在展示完整更新记录，再盖一层摘要没有意义；
  // /frost 是独立美术体系的全屏游戏页，不打断。
  if (route.path === '/versions' || route.path === '/frost') return true
  return INELIGIBLE_META.some((key) => Boolean(route.meta[key]))
}

async function decide() {
  if (decided || !auth.ready) return
  // 全屏游戏页/后台不打断，也不消耗本次进入的唯一浮层位置：
  // 用户随后进入普通页面时再判定（同一次进入仍然只弹这一个）。
  if (ineligible()) return
  decided = true
  try {
    // 未验证邮箱时强制绑定框会盖住一切，先让用户去验证，下次进入再提示版本。
    if (auth.emailGateRequired) return
    const notes = await loadVersionNotes()
    const localAck = readAckedVersion()
    let acked = auth.isLoggedIn ? (auth.user?.version_ack || '') : localAck
    // 游客确认过同一版本后登录：把浏览器标记补记到账号，避免同一台设备再被弹一次。
    if (auth.isLoggedIn && !acked && localAck && localAck === currentVersion(notes)) {
      acked = localAck
      api.post('/version-ack', { version: localAck })
        .then(({ data }) => auth.patchUser({ version_ack: data.version_ack }))
        .catch(() => {})
    }
    if (!shouldPromptVersion(notes, acked)) return
    // 本次进入已经有别的浮层抢到位了，顺延到下次进入。
    if (!claimPrompt('version')) return
    entry.value = currentVersionEntry(notes)
    missed.value = missedVersionCount(notes, acked)
    visible.value = true
  } finally {
    // 无论弹不弹，都要放行公告/礼仪确认，否则它们会一直等下去。
    settleVersionDecision()
  }
}

watch(
  [() => auth.ready, () => route.fullPath],
  decide,
  { immediate: true },
)

// 只有版本号会重新弹；同一版本号下补改说明不打扰用户。
async function acknowledge() {
  const version = entry.value?.version
  if (!version) return
  writeAckedVersion(version)
  if (auth.isLoggedIn) {
    try {
      const { data } = await api.post('/version-ack', { version })
      await auth.patchUser({ version_ack: data.version_ack })
    } catch { /* 记录失败只影响下次是否再弹，不阻塞关闭 */ }
  }
}

async function confirm() {
  if (busy.value) return
  busy.value = true
  try {
    await acknowledge()
    visible.value = false
    track('version.confirm')
  } finally {
    busy.value = false
  }
}

async function openNotes() {
  if (busy.value) return
  busy.value = true
  try {
    await acknowledge()
    visible.value = false
    track('version.confirm')
    router.push('/versions')
  } finally {
    busy.value = false
  }
}

watch(visible, async (value) => {
  document.body.classList.toggle('modal-open', value)
  if (!value) return
  await nextTick()
  confirmButton.value?.focus()
})

onBeforeUnmount(() => document.body.classList.remove('modal-open'))
</script>

<template>
  <div v-if="visible && entry" class="modal-backdrop version-prompt-backdrop">
    <section
      class="dialog version-prompt"
      role="dialog"
      aria-modal="true"
      aria-labelledby="version-prompt-title"
      @keydown.esc.prevent
    >
      <header class="version-prompt-heading">
        <span class="eyebrow"><Sparkles :size="15" /> WHAT'S NEW</span>
        <h2 id="version-prompt-title">
          <span>{{ entry.version }}</span>
          <span v-if="entry.label" class="version-prompt-label">{{ entry.label }}</span>
        </h2>
        <p class="version-prompt-meta">
          <History :size="13" />
          <span>{{ entry.date }}</span>
          <span v-if="entry.tagline">· {{ entry.tagline }}</span>
        </p>
      </header>

      <div class="version-prompt-body">
        <p v-if="missed > 0" class="version-prompt-missed">
          你错过了 {{ missed }} 个版本，这里只列出最新一版的重点。
        </p>
        <ul>
          <li v-for="item in entry.summary" :key="item">{{ item }}</li>
        </ul>
      </div>

      <footer class="version-prompt-actions">
        <button class="text-link" type="button" @click="openNotes">查看完整更新记录</button>
        <button ref="confirmButton" class="button" type="button" :disabled="busy" @click="confirm">
          <Check :size="17" />我知道了
        </button>
      </footer>
    </section>
  </div>
</template>

<style scoped>
.version-prompt-backdrop { z-index: 160; }
.version-prompt {
  display: flex;
  flex-direction: column;
  width: min(560px, 100%);
  max-height: calc(100vh - 48px);
  padding: 0;
  overflow: hidden;
}
.version-prompt-heading { flex: 0 0 auto; padding: 30px 32px 20px; border-bottom: 1px solid var(--line); }
.version-prompt-heading h2 {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin: 12px 0 8px;
  font-family: Georgia, "Songti SC", serif;
  font-size: 28px;
}
.version-prompt-label {
  padding: 2px 8px;
  border: 1px solid var(--line);
  border-radius: 999px;
  color: var(--muted);
  font-family: inherit;
  font-size: 12px;
  font-weight: 400;
}
.version-prompt-meta { display: flex; align-items: center; gap: 6px; margin: 0; color: var(--muted); font-size: 12.5px; }
.version-prompt-body { min-height: 0; padding: 20px 32px; overflow-y: auto; }
.version-prompt-missed {
  margin: 0 0 14px;
  padding: 9px 12px;
  border-left: 3px solid var(--green-600, #4f8a6d);
  background: #f3f7f4;
  color: #46504b;
  font-size: 13px;
}
.version-prompt-body ul { margin: 0; padding-left: 20px; }
.version-prompt-body li { margin: 0 0 10px; color: #46504b; font-size: 14px; line-height: 1.7; }
.version-prompt-body li:last-child { margin-bottom: 0; }
.version-prompt-actions {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 32px;
  border-top: 1px solid var(--line);
  background: #f8f9f8;
}

@media (max-width: 680px) {
  .version-prompt { width: 100%; max-height: 92vh; border-radius: 6px 6px 0 0; }
  .version-prompt-heading { padding: 25px 20px 18px; }
  .version-prompt-heading h2 { font-size: 24px; }
  .version-prompt-body { padding: 18px 20px; }
  .version-prompt-actions { flex-direction: column-reverse; align-items: stretch; padding: 16px 20px max(18px, env(safe-area-inset-bottom)); }
  .version-prompt-actions .button { width: 100%; }
}
</style>
