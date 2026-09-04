<script setup>
import { nextTick, ref } from 'vue'

const open = ref(true) // 默认展开,让看板娘更醒目(移动端仍隐藏)
const busy = ref(false)
const input = ref('')
const messages = ref([
  {
    role: 'assistant',
    content: '欢迎来万事屋~ 咱 VRC 群的互助站,发委托、接委托、逛砂糖社都在这儿。想问点什么?找我也行,陪聊也接(笑)。'
  }
])
const listEl = ref(null)

function scrollBottom() {
  nextTick(() => {
    if (listEl.value) listEl.value.scrollTop = listEl.value.scrollHeight
  })
}

async function send() {
  const text = input.value.trim()
  if (!text || busy.value) return

  input.value = ''
  messages.value.push({ role: 'user', content: text })
  busy.value = true
  scrollBottom()

  try {
    const token = localStorage.getItem('wsw_token')
    const headers = { 'content-type': 'application/json' }
    if (token) headers.authorization = `Bearer ${token}`
    const resp = await fetch('/api/mascot/chat', {
      method: 'POST',
      headers,
      body: JSON.stringify({ messages: messages.value.slice(-16) })
    })
    const data = await resp.json()
    if (data.reply) {
      messages.value.push({ role: 'assistant', content: data.reply })
    } else {
      messages.value.push({ role: 'assistant', content: '呜…我刚刚走神了，再问我一次好不好？' })
    }
  } catch {
    messages.value.push({ role: 'assistant', content: '呜…线路好像出问题了，稍后再来找我聊吧~' })
  } finally {
    busy.value = false
    scrollBottom()
  }
}
</script>

<template>
  <div class="kanban-niang">
    <Transition name="pop">
      <div v-if="open" class="panel">
        <div class="panel-header">
          <div class="header-avatar">白</div>
          <div class="header-title">
            <div class="header-name">看板娘 · 小白</div>
            <div class="header-status">
              <span class="status-dot" />
              <span>在线</span>
            </div>
          </div>
          <button class="header-close" @click="open = false" aria-label="关闭">×</button>
        </div>

        <div ref="listEl" class="message-list">
          <div
            v-for="(msg, index) in messages"
            :key="index"
            class="message-row"
            :class="{ user: msg.role === 'user' }"
          >
            <div class="message-bubble">
              {{ msg.content }}
            </div>
          </div>
          <div v-if="busy" class="message-row">
            <div class="message-bubble busy-bubble">
              <span class="typing-dot" />
              <span class="typing-dot" />
              <span class="typing-dot" />
            </div>
          </div>
        </div>

        <div class="input-bar">
          <input
            v-model="input"
            type="text"
            class="input-field"
            placeholder="想问点什么…"
            @keydown.enter="send"
          />
          <button class="send-btn" :disabled="!input.trim() || busy" @click="send">发送</button>
        </div>
      </div>
    </Transition>

    <button v-if="!open" class="fab" @click="open = true" aria-label="打开看板娘">
      <span class="fab-avatar">白</span>
      <span class="fab-name">小白</span>
      <span class="fab-dot" />
    </button>
  </div>
</template>

<style scoped>
.kanban-niang {
  position: fixed;
  top: 88px;
  left: 16px;
  z-index: 1000;
  font-family: Inter, 'PingFang SC', -apple-system, BlinkMacSystemFont, sans-serif;
  color: var(--ink, #18201d);
}

/* 折叠入口 */
.fab {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px 6px 6px;
  background: var(--paper, #ffffff);
  border: 1px solid var(--line, #d9dedb);
  border-radius: 6px;
  box-shadow: var(--shadow, 0 14px 40px rgba(25, 38, 32, .1));
  cursor: pointer;
  transition: border-color .2s ease, box-shadow .2s ease, transform .15s ease;
}

.fab:hover {
  border-color: var(--green, #237a57);
  box-shadow: 0 16px 44px rgba(25, 38, 32, .12);
  transform: translateY(-1px);
}

.fab:active {
  transform: translateY(0);
}

.fab-avatar {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  background: var(--green-soft, #e5f3eb);
  color: var(--green, #237a57);
  font-size: 13px;
  font-weight: 700;
  border-radius: 4px;
}

.fab-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--ink, #18201d);
  letter-spacing: .02em;
}

.fab-dot {
  width: 6px;
  height: 6px;
  background: var(--green, #237a57);
  border-radius: 50%;
  box-shadow: 0 0 0 2px var(--paper, #ffffff);
}

/* 聊天面板 */
.panel {
  width: 320px;
  max-height: calc(100vh - 104px);
  display: flex;
  flex-direction: column;
  background: var(--paper, #ffffff);
  border: 1px solid var(--line, #d9dedb);
  border-radius: 6px;
  box-shadow: var(--shadow, 0 14px 40px rgba(25, 38, 32, .1));
  overflow: hidden;
}

.panel-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--line, #d9dedb);
  background: var(--paper, #ffffff);
}

.header-avatar {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  background: var(--green-soft, #e5f3eb);
  color: var(--green, #237a57);
  font-size: 14px;
  font-weight: 700;
  border-radius: 4px;
  flex-shrink: 0;
}

.header-title {
  flex: 1;
  min-width: 0;
}

.header-name {
  font-family: Georgia, 'Songti SC', serif;
  font-size: 15px;
  font-weight: 600;
  color: var(--ink, #18201d);
  letter-spacing: .02em;
}

.header-status {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-top: 2px;
  font-size: 11px;
  color: var(--muted, #69736e);
}

.status-dot {
  width: 6px;
  height: 6px;
  background: var(--green, #237a57);
  border-radius: 50%;
}

.header-close {
  display: grid;
  place-items: center;
  width: 26px;
  height: 26px;
  padding: 0;
  background: transparent;
  border: none;
  color: var(--muted, #69736e);
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
  border-radius: 4px;
  transition: background .15s ease, color .15s ease;
}

.header-close:hover {
  background: var(--green-soft, #e5f3eb);
  color: var(--green, #237a57);
}

/* 消息列表 */
.message-list {
  flex: 1;
  min-height: 0;
  padding: 14px;
  overflow-y: auto;
  background: #f3f5f2;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.message-row {
  display: flex;
  justify-content: flex-start;
}

.message-row.user {
  justify-content: flex-end;
}

.message-bubble {
  max-width: 86%;
  padding: 9px 12px;
  font-size: 13px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
  border-radius: 6px;
  background: var(--paper, #ffffff);
  color: var(--ink, #18201d);
  border: 1px solid var(--line, #d9dedb);
}

.message-row.user .message-bubble {
  background: var(--green, #237a57);
  color: var(--paper, #ffffff);
  border-color: var(--green, #237a57);
}

.busy-bubble {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 14px 12px;
}

.typing-dot {
  width: 5px;
  height: 5px;
  background: var(--muted, #69736e);
  border-radius: 50%;
  animation: typing 1.2s infinite ease-in-out;
}

.typing-dot:nth-child(2) {
  animation-delay: .15s;
}

.typing-dot:nth-child(3) {
  animation-delay: .3s;
}

@keyframes typing {
  0%, 80%, 100% {
    transform: translateY(0);
    opacity: .5;
  }
  40% {
    transform: translateY(-3px);
    opacity: 1;
  }
}

/* 输入栏 */
.input-bar {
  display: flex;
  gap: 8px;
  padding: 10px 12px;
  background: var(--paper, #ffffff);
  border-top: 1px solid var(--line, #d9dedb);
}

.input-field {
  flex: 1;
  min-width: 0;
  padding: 8px 10px;
  font-size: 13px;
  color: var(--ink, #18201d);
  background: #f3f5f2;
  border: 1px solid var(--line, #d9dedb);
  border-radius: 4px;
  outline: none;
  transition: border-color .15s ease;
}

.input-field::placeholder {
  color: var(--muted, #69736e);
}

.input-field:focus {
  border-color: var(--green, #237a57);
}

.send-btn {
  padding: 0 14px;
  font-size: 13px;
  font-weight: 500;
  color: var(--paper, #ffffff);
  background: var(--green, #237a57);
  border: 1px solid var(--green, #237a57);
  border-radius: 4px;
  cursor: pointer;
  transition: background .15s ease, border-color .15s ease, opacity .15s ease;
}

.send-btn:hover:not(:disabled) {
  background: #1e684a;
  border-color: #1e684a;
}

.send-btn:disabled {
  opacity: .45;
  cursor: not-allowed;
}

/* 弹窗过渡 */
.pop-enter-active,
.pop-leave-active {
  transition: opacity .2s ease, transform .2s ease;
  transform-origin: top left;
}

.pop-enter-from,
.pop-leave-to {
  opacity: 0;
  transform: scale(.96);
}

/* 移动端隐藏 */
@media (max-width: 768px) {
  .kanban-niang {
    display: none;
  }
}
</style>
