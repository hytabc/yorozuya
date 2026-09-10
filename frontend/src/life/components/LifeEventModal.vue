<script setup>
// 群聊式事件播放：主线与选项回复共用逐组推进，图片只挂在最后一句。
import { computed, nextTick, ref, watch } from 'vue'
import LifeImageLightbox from './LifeImageLightbox.vue'

const props = defineProps({
  script: { type: Object, required: true },
  title: { type: String, default: '事件' },
  icon: { type: String, default: '❗' },
  resolveSpeaker: { type: Function, required: true },
  playerName: { type: String, default: '你' },
})
const emit = defineEmits(['choice', 'finish', 'close'])
const messageArea = ref(null)
const displayed = ref([])
const pendingReplies = ref([])
const cursor = ref(0)
const activeChoice = ref(null)
const lightboxSrc = ref('')
const dismissed = ref(false)
const messages = computed(() => Array.isArray(props.script?.messages) ? props.script.messages : [])
const isEmpty = computed(() => messages.value.length === 0)
const finished = computed(() => !activeChoice.value && !pendingReplies.value.length && cursor.value >= messages.value.length)
let nextId = 0

function scrollToBottom() {
  nextTick(() => {
    const area = messageArea.value
    if (area) area.scrollTop = area.scrollHeight
  })
}

function resolveIdentity(speaker) {
  try {
    const result = props.resolveSpeaker(speaker)
    if (typeof result?.name === 'string' && result.name.trim()) {
      return { name: result.name, portrait: typeof result.portrait === 'string' ? result.portrait : '' }
    }
  } catch {
    // 外部解析失败不影响剧本播放。
  }
  return { name: '未知', portrait: '?' }
}

function isPortraitImage(portrait) {
  return /^(https?:\/\/|\/|\.\.?\/|data:image\/|blob:)/i.test(portrait)
}

function appendGroup(group) {
  displayed.value.push({
    id: nextId++,
    ...resolveIdentity(group.speaker),
    lines: group.lines,
    image: typeof group.image === 'string' && group.image.startsWith('/uploads/') ? group.image : null,
    player: false,
  })
  scrollToBottom()
}

// 读到选项即暂停；空选项点跳过，避免底部无按钮而卡住。
function prepareChoice() {
  if (pendingReplies.value.length) return
  while (cursor.value < messages.value.length && messages.value[cursor.value]?.choice) {
    const choice = messages.value[cursor.value++].choice
    if (Array.isArray(choice.options) && choice.options.length) {
      activeChoice.value = choice
      return
    }
  }
}

function advance() {
  if (dismissed.value || lightboxSrc.value || activeChoice.value) return
  if (pendingReplies.value.length) {
    appendGroup(pendingReplies.value.shift())
  } else {
    prepareChoice()
    if (activeChoice.value || finished.value) return
    appendGroup(messages.value[cursor.value++])
  }
  prepareChoice()
}

function choose(option) {
  if (dismissed.value || !activeChoice.value) return
  activeChoice.value = null
  displayed.value.push({
    id: nextId++, name: props.playerName, portrait: '我',
    lines: [option.label], image: null, player: true,
  })
  // 回复队列只接受消息组，不展开嵌套选项；之后再继续主线。
  pendingReplies.value = Array.isArray(option.reply)
    ? option.reply.filter(group => group && !group.choice && Array.isArray(group.lines) && group.lines.length)
    : []
  prepareChoice()
  scrollToBottom()
  emit('choice', option.effects || {})
}

function dismiss() {
  if (dismissed.value) return
  dismissed.value = true
  emit(finished.value ? 'finish' : 'close')
}

watch(() => props.script, () => {
  displayed.value = []
  pendingReplies.value = []
  cursor.value = 0
  activeChoice.value = null
  lightboxSrc.value = ''
  dismissed.value = false
  nextId = 0
  advance()
}, { immediate: true })
</script>

<template>
  <Teleport to="body">
    <div class="event-overlay">
      <section class="event-panel" role="dialog" aria-modal="true" :aria-label="title">
        <header class="event-header">
          <h2><span aria-hidden="true">{{ icon }}</span> {{ title }}</h2>
          <button v-if="!isEmpty" class="event-close" type="button" aria-label="关闭事件" @click="dismiss">✕</button>
        </header>

        <div ref="messageArea" class="event-messages" aria-live="polite" @click="advance">
          <p v-if="isEmpty" class="event-empty">本日没有事件内容</p>
          <div v-for="group in displayed" :key="group.id" :class="['message-group', { player: group.player }]">
            <div class="message-avatar" aria-hidden="true">
              <img v-if="isPortraitImage(group.portrait)" :src="group.portrait" alt="" @error="group.portrait = '?'" />
              <span v-else>{{ group.portrait || '?' }}</span>
            </div>
            <div class="message-content">
              <div class="message-name">{{ group.name }}</div>
              <div v-for="(line, index) in group.lines" :key="index" class="message-bubble" :style="{ animationDelay: (index * 90) + 'ms' }">
                <span>{{ line }}</span>
                <button v-if="group.image && index === group.lines.length - 1" class="message-image" type="button"
                        aria-label="查看事件图片" @click.stop="lightboxSrc = group.image">
                  <img :src="group.image" alt="事件图片" @load="scrollToBottom" />
                </button>
              </div>
            </div>
          </div>
        </div>

        <footer class="event-footer">
          <div v-if="activeChoice" class="event-options">
            <button v-for="(option, index) in activeChoice.options" :key="index" class="option-button" type="button" :style="{ animationDelay: (index * 80) + 'ms' }" @click="choose(option)">
              <span class="option-number">{{ index + 1 }}.</span> {{ option.label }}
            </button>
          </div>
          <template v-else-if="finished">
            <p v-if="!isEmpty" class="event-ending">—— 剧终 ——</p>
            <button class="primary-button" type="button" @click="dismiss">关闭</button>
          </template>
          <button v-else class="continue-button" type="button" @click="advance">继续 ▾</button>
        </footer>
      </section>
    </div>
    <LifeImageLightbox v-if="lightboxSrc" :src="lightboxSrc" alt="事件图片" @close="lightboxSrc = ''" />
  </Teleport>
</template>

<style scoped>
.event-overlay {
  position: fixed; inset: 0; z-index: 9000;
  display: flex; align-items: center; justify-content: center;
  padding: 16px; box-sizing: border-box;
  background: rgba(0, 0, 0, .45);
  animation: overlay-in .18s ease;
}
.event-panel {
  display: flex; flex-direction: column;
  width: 100%; max-width: 560px; height: 80vh;
  overflow: hidden; background: #fff; border-radius: 12px;
  box-shadow: 0 12px 40px rgba(25, 38, 32, .2); color: #333;
  animation: panel-in .28s cubic-bezier(.2,.8,.35,1.18);
}
.event-header {
  display: flex; align-items: center; justify-content: space-between;
  gap: 12px; padding: 16px 20px; border-bottom: 1px solid #d9dedb;
}
.event-header h2 { margin: 0; font-size: 18px; overflow-wrap: anywhere; }
.event-close {
  flex-shrink: 0; width: 32px; height: 32px; padding: 0;
  border: 1px solid #d9dedb; border-radius: 50%; background: #fff;
  color: #69736e; font-size: 18px; cursor: pointer;
}
.event-messages {
  flex: 1; min-height: 0; overflow-y: auto; overscroll-behavior: contain;
  display: flex; flex-direction: column; gap: 20px; padding: 20px 16px;
}
.event-empty { margin: auto; color: #69736e; text-align: center; }
.message-group { display: flex; gap: 10px; flex-shrink: 0; animation: message-in .2s ease-out; }
.message-group.player { flex-direction: row-reverse; }
.message-avatar {
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
  width: 36px; height: 36px; overflow: hidden; border-radius: 8px;
  background: #f5f6f4; border: 1px solid #d9dedb; font-size: 22px;
}
.message-avatar img { width: 100%; height: 100%; object-fit: cover; }
.message-content { display: flex; flex-direction: column; align-items: flex-start; gap: 6px; min-width: 0; max-width: 78%; }
.player .message-content { align-items: flex-end; }
.message-name { font-size: 12px; color: #69736e; overflow-wrap: anywhere; max-width: 100%; }
.message-bubble {
  box-sizing: border-box; max-width: 100%; padding: 10px 14px;
  border: 1px solid #d9dedb; border-radius: 12px; background: #f5f6f4;
  font-size: 14px; line-height: 1.6; white-space: pre-wrap; overflow-wrap: anywhere;
  box-shadow: 0 2px 8px rgba(25, 38, 32, .08);
  animation: bubble-in .26s cubic-bezier(.2,.8,.35,1.18) backwards;
}
.player .message-bubble { background: #237a57; border-color: #237a57; color: #fff; }
.message-image { display: block; max-width: 100%; padding: 0; margin-top: 6px; border: 0; background: transparent; cursor: zoom-in; }
.message-image img { display: block; width: 200px; max-width: 100%; max-height: 180px; object-fit: contain; border-radius: 8px; }
.event-footer { flex-shrink: 0; padding: 12px 20px 16px; border-top: 1px solid #d9dedb; text-align: center; max-height: 35%; overflow-y: auto; }
.event-options { display: flex; flex-direction: column; gap: 8px; }
.option-button, .primary-button, .continue-button { font: inherit; font-size: 14px; border-radius: 8px; padding: 10px 16px; cursor: pointer; transition: transform .12s ease, background .18s, border-color .18s; }
.option-button { border: 1px solid #d9dedb; background: #f5f6f4; color: #237a57; text-align: left; overflow-wrap: anywhere; animation: option-in .3s cubic-bezier(.2,.8,.35,1.18) backwards; }
.option-button:hover { border-color: #237a57; }
.option-button:active { transform: scale(.98); }
.option-number { font-weight: 600; }
.primary-button { border: 1px solid #237a57; background: #237a57; color: #fff; min-width: 100px; }
.primary-button:active { transform: scale(.97); }
.continue-button { border: 0; background: transparent; color: #69736e; width: 100%; }
.continue-button:hover { color: #237a57; }
.continue-button:active { transform: scale(.98); }
.event-close { transition: transform .12s ease, background .18s; }
.event-close:active { transform: scale(.9); }
.event-ending { margin: 0 0 10px; color: #69736e; font-size: 13px; }
button:focus-visible { outline: 2px solid #237a57; outline-offset: 2px; }
@keyframes message-in { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
@keyframes bubble-in { from { opacity: 0; transform: translateY(10px) scale(.95); } 60% { opacity: 1; transform: translateY(-2px) scale(1.015); } to { opacity: 1; transform: none; } }
@keyframes option-in { from { opacity: 0; transform: translateY(8px) scale(.97); } to { opacity: 1; transform: none; } }
@keyframes overlay-in { from { opacity: 0; } }
@keyframes panel-in { from { opacity: 0; transform: translateY(16px) scale(.98); } to { opacity: 1; transform: none; } }
@media (prefers-reduced-motion: reduce) {
  .message-group, .message-bubble, .option-button, .event-overlay, .event-panel { animation: none; }
  .option-button, .primary-button, .continue-button, .event-close { transition: none; }
}
</style>
