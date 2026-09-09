<script setup>
// 事件剧本是七天的线性序列；选项回复复用消息组面板，不提供嵌套选项入口。
import { computed, nextTick, reactive, ref, watch } from 'vue'
import {
  adminState, npcById, LIFE_DIALOGUE_DAYS, addEvent, removeEvent,
  addEventMessage, addEventChoice, removeEventItem,
} from './useLifeAdmin'
import AdminImageField from './AdminImageField.vue'

const content = computed(() => adminState.content)
const events = computed(() => content.value?.events || [])
const selectedId = ref('')
const editorRef = ref(null)
const activeDay = ref(1)
const selected = computed(() => events.value.find(e => e.id === selectedId.value) || events.value[0])
const script = computed(() => selected.value?.scripts[activeDay.value - 1])
const dayTabs = Array.from({ length: LIFE_DIALOGUE_DAYS }, (_, i) => i + 1)
const stats = [
  { key: 'mood', label: '心情' }, { key: 'energy', label: '精力' },
  { key: 'social', label: '社交' }, { key: 'explore', label: '探索' },
]
// 非法路径只留在界面草稿里，不写进待保存的内容包。
const imageDrafts = reactive(new Map())
const avatarDrafts = reactive(new Map())
watch(content, () => {
  selectedId.value = ''
  activeDay.value = 1
  imageDrafts.clear()
  avatarDrafts.clear()
})
watch(() => selected.value?.id, () => { activeDay.value = 1 })

function roomLabel(room) {
  const world = content.value.worlds.find(w => w.id === room.worldId)
  return `${room.label} · ${world?.name || room.worldId}`
}
async function selectEvent(id) {
  selectedId.value = id
  // 等待选中事件的编辑器渲染完成，再滚动到剧本区域。
  await nextTick()
  editorRef.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
function createEvent(roomId = content.value.rooms[0]?.id) {
  const id = addEvent(content.value, roomId)
  if (id) selectEvent(id)
}
function deleteEvent(event) {
  if (window.confirm(`删除事件「${event.title}」及其七天剧本？`)) removeEvent(content.value, event.id)
}
function moveItem(index, offset) {
  const items = script.value.messages
  const target = index + offset
  if (target < 0 || target >= items.length) return
  items.splice(target, 0, items.splice(index, 1)[0])
}
function entries(item) {
  return item.choice
    ? item.choice.options.map(option => ({ option, messages: option.reply }))
    : [{ option: null, messages: [item] }]
}
function addOption(item) {
  const day = { messages: [] }
  addEventChoice(day)
  item.choice.options.push(day.messages[0].choice.options[0])
}
function addReply(option) {
  addEventMessage({ messages: option.reply })
}
function setSpeaker(message, event) {
  const id = event.target.value
  message.speaker = content.value.npcIds.includes(id) ? { npcId: id } : { name: '路人' }
}
function setText(target, key, event, fallback) {
  target[key] = event.target.value.trim() ? event.target.value : fallback
}
function setName(message, event) {
  setText(message.speaker, 'name', event, '路人')
}
function uploadPath(value) {
  return /^\/uploads\/[^\s?#]+$/.test(value)
}
function validAvatar(value) {
  return !value || uploadPath(value) || /^(?=.*\p{Extended_Pictographic})[\p{Extended_Pictographic}\p{Emoji_Component}\u200d\ufe0f]+$/u.test(value)
}
function setAvatar(message, value) {
  avatarDrafts.set(message.speaker, value)
  if (!validAvatar(value)) return
  if (value) message.speaker.avatar = value
  else delete message.speaker.avatar
}
function setImage(message, value) {
  imageDrafts.set(message, value)
  if (!value || uploadPath(value)) message.image = value || null
}
function setStat(option, key, event) {
  // 不依赖 number 输入框的 min/max：空值删除，有限数截断并限幅。
  const raw = event.target.value
  const next = { ...option.effects?.stats }
  if (raw === '' || !Number.isFinite(Number(raw))) delete next[key]
  else next[key] = Math.max(-100, Math.min(100, Math.trunc(Number(raw))))
  option.effects = { ...option.effects, stats: Object.fromEntries(stats.filter(s => Number.isInteger(next[s.key])).map(s => [s.key, Math.max(-100, Math.min(100, next[s.key]))])) }
  event.target.value = option.effects.stats[key] ?? ''
}
function setBondNpc(option, event) {
  const npcId = event.target.value
  option.effects ||= {}
  if (!content.value.npcIds.includes(npcId)) delete option.effects.bond
  else option.effects.bond = { npcId, value: option.effects.bond?.value ?? 0 }
}
function setBondValue(option, event) {
  // 与属性输入一致：清空删除，整数硬钳制，不留下不完整的 bond。
  const raw = event.target.value
  const npcId = option.effects?.bond?.npcId
  if (raw === '' || !Number.isFinite(Number(raw)) || !content.value.npcIds.includes(npcId)) {
    if (option.effects) delete option.effects.bond
  } else {
    option.effects.bond = { npcId, value: Math.max(-100, Math.min(100, Math.trunc(Number(raw)))) }
  }
  event.target.value = option.effects?.bond?.value ?? ''
}
</script>

<template>
  <section v-if="content" class="la-section la-events la-form">
    <h2>事件</h2>
    <p>按房间组织事件；第 1~7 天各一份线性剧本，无第八天。选项回复只包含消息组，播放完后继续后面的消息。</p>
    <p v-if="!content.rooms.length" class="la-hint">请先在「世界与房间」中新增房间。</p>
    <div v-for="room in content.rooms" :key="room.id" class="la-event-room">
      <div class="la-event-heading">
        <h3>{{ roomLabel(room) }}</h3>
        <button class="la-mini" @click="createEvent(room.id)">+ 新增事件</button>
      </div>
      <div v-for="event in events.filter(e => e.roomId === room.id)" :key="event.id"
           class="la-event-row" :class="{ selected: selected?.id === event.id }">
        <button class="la-mini" :aria-pressed="selected?.id === event.id" @click="selectEvent(event.id)">编辑剧本</button>
        <label>图标<input :value="event.icon" @input="setText(event, 'icon', $event, '❗')" type="text" class="la-event-icon" /></label>
        <label class="la-event-title">标题<input :value="event.title" @input="setText(event, 'title', $event, '新事件')" type="text" /></label>
        <label>房间<select v-model="event.roomId">
          <option v-for="target in content.rooms" :key="target.id" :value="target.id">{{ roomLabel(target) }}</option>
        </select></label>
        <button class="la-mini la-danger" @click="deleteEvent(event)">删除事件</button>
      </div>
    </div>
    <button class="la-mini" :disabled="!content.rooms.length" @click="createEvent()">+ 新增事件（首个房间）</button>

    <div v-if="selected && script" :key="selected.id" ref="editorRef" class="la-event-editor">
      <h3>{{ selected.icon }} {{ selected.title }} <small>{{ selected.id }}</small></h3>
      <nav class="la-npc-tabs" aria-label="事件天数">
        <button v-for="day in dayTabs" :key="day" :class="{ active: day === activeDay }"
                @click="activeDay = day">第 {{ day }} 天</button>
      </nav>
      <div :key="activeDay">
        <article v-for="(item, index) in script.messages" :key="index" class="la-node">
          <div class="la-node-head">
            <strong>{{ index + 1 }} · {{ item.choice ? '选项点' : '消息组' }}</strong>
            <button class="la-mini" :disabled="index === 0" @click="moveItem(index, -1)">上移</button>
            <button class="la-mini" :disabled="index === script.messages.length - 1" @click="moveItem(index, 1)">下移</button>
            <button class="la-mini la-danger" :disabled="script.messages.length <= 1" @click="removeEventItem(script, index)">{{ item.choice ? '删除此选项点' : '删除卡' }}</button>
          </div>
          <!-- 同一套消息组编辑字段用于正文与回复，回复没有选项点入口。 -->
          <div v-for="(entry, optionIndex) in entries(item)" :key="optionIndex" :class="{ 'la-choice-block': entry.option }">
            <div v-if="entry.option" class="la-event-option">
              <label class="la-event-title">选项文案<input :value="entry.option.label" @input="setText(entry.option, 'label', $event, '继续')" type="text" /></label>
              <label v-for="stat in stats" :key="stat.key">{{ stat.label }}
                <input type="number" min="-100" max="100" step="1" placeholder="0"
                       :value="entry.option.effects?.stats?.[stat.key] ?? ''"
                       @input="setStat(entry.option, stat.key, $event)" />
              </label>
              <div class="la-event-bond">
                <label>好感<select :value="entry.option.effects?.bond?.npcId ?? ''" @change="setBondNpc(entry.option, $event)">
                  <option value="">无</option>
                  <option v-for="id in content.npcIds" :key="id" :value="id">{{ npcById(id)?.name || id }}</option>
                </select></label>
                <label>好感变化<input type="number" min="-100" max="100" step="1" placeholder="0"
                       :disabled="!entry.option.effects?.bond"
                       :value="entry.option.effects?.bond?.value ?? ''"
                       @input="setBondValue(entry.option, $event)" /></label>
                <small>好感 -100~100 · 属性 -100~100</small>
              </div>
              <button class="la-mini la-danger" :disabled="item.choice.options.length <= 1"
                      @click="item.choice.options.splice(optionIndex, 1)">删选项</button>
            </div>
            <div v-for="(message, replyIndex) in entry.messages" :key="replyIndex" class="la-event-message">
              <div class="la-event-speaker">
                <span v-if="entry.option">回复 {{ replyIndex + 1 }}</span>
                <label>发言人<select :value="message.speaker.npcId || ''" @change="setSpeaker(message, $event)">
                  <option value="">路人</option>
                  <option v-for="id in content.npcIds" :key="id" :value="id">{{ npcById(id)?.name || id }}</option>
                </select></label>
                <template v-if="!message.speaker.npcId">
                  <label>姓名<input type="text" :value="message.speaker.name" @input="setName(message, $event)" /></label>
                  <label>头像（emoji 或 /uploads/ 图片）
                    <input type="text" :value="avatarDrafts.get(message.speaker) ?? message.speaker.avatar ?? ''"
                           @input="setAvatar(message, $event.target.value)" />
                    <span v-if="!validAvatar(avatarDrafts.get(message.speaker) ?? message.speaker.avatar ?? '')" class="la-missing">头像格式无效，尚未写入</span>
                  </label>
                </template>
                <button v-if="entry.option" class="la-mini la-danger" :disabled="entry.option.reply.length <= 1" @click="entry.option.reply.splice(replyIndex, 1)">删除回复消息</button>
              </div>
              <div v-for="(line, lineIndex) in message.lines" :key="lineIndex" class="la-line-row">
                <textarea :value="message.lines[lineIndex]" @input="setText(message.lines, lineIndex, $event, '……')" :aria-label="`第 ${lineIndex + 1} 句`" placeholder="台词（每项一句，依次播放）"></textarea>
                <button class="la-mini la-danger" :disabled="message.lines.length <= 1" @click="message.lines.splice(lineIndex, 1)">删</button>
              </div>
              <button class="la-mini" @click="message.lines.push('……')">+ 加一句</button>
              <AdminImageField :model-value="imageDrafts.get(message) ?? message.image ?? ''"
                               placeholder="可选图片（/uploads/ 路径）" @update:model-value="setImage(message, $event)" />
              <p v-if="imageDrafts.get(message) && !uploadPath(imageDrafts.get(message))" class="la-missing">图片须为 /uploads/ 路径；当前输入尚未写入。</p>
            </div>
            <button v-if="entry.option" class="la-mini" @click="addReply(entry.option)">+ 加回复消息</button>
          </div>
          <button v-if="item.choice" class="la-mini" @click="addOption(item)">+ 加选项</button>
        </article>
        <p v-if="!script.messages.length" class="la-hint">当天暂无消息，可在下方添加。</p>
        <div class="la-add-row">
          <button class="la-mini" @click="addEventMessage(script)">+ 加消息</button>
          <button class="la-mini" @click="addEventChoice(script)">+ 加选项点</button>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.la-event-room { margin-bottom: 14px; }
.la-event-heading, .la-event-row, .la-event-option, .la-event-speaker { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.la-event-heading { justify-content: space-between; }
.la-events h3 { font-size: 13px; margin: 12px 0; }
.la-events small { color: #69736e; font-weight: normal; }
.la-event-row { padding: 10px; margin-bottom: 6px; border: 1px solid #d9dedb; border-radius: 8px; }
.la-event-row.selected { border-color: #237a57; border-left: 4px solid #237a57; background: #f4f9f5; }
.la-event-icon { width: 56px; }
.la-event-title { flex: 1; min-width: 140px; }
.la-event-editor { margin-top: 20px; padding-top: 8px; border-top: 1px solid #d9dedb; }
.la-event-option { margin-bottom: 10px; align-items: end; }
.la-event-option input[type=number] { width: 64px; }
.la-event-bond { display: flex; align-items: end; gap: 10px; flex-wrap: wrap; flex-basis: 100%; }
.la-event-message { padding: 10px 0; }
.la-event-speaker { margin-bottom: 10px; }
.la-node-head { flex-wrap: wrap; }
.la-line-row textarea { min-width: 0; box-sizing: border-box; }
.la-event-message :deep(.la-img-cell) { margin-top: 8px; flex-wrap: wrap; }
</style>
