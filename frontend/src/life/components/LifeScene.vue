<script setup>
// 中央场景：位置标签、场景背景(包内 bg 或占位)、NPC 头像列表、对话浮层与回应面板。
// 样式从 LifeSimulator.vue 迁出，行为不变。
// 阶段 8a：气泡内图片缩略图 + 全屏灯箱（点击弹出、再点消失）。
import { ref, watch } from 'vue'
import LifeImageLightbox from './LifeImageLightbox.vue'
import LifeEventModal from './LifeEventModal.vue'
import { mergeEventChoices } from '../../composables/lifeEvents'
const props = defineProps({ game: { type: Object, required: true } })
const {
  currentWorld, currentRoom, currentWorldDef, sceneNpcs, npcListOpen, worldPopulation,
  currentNpcId, currentNpc, npcPortrait, tutorialDemo,
  dialogueVisible, speech, playback, replyTab, bondDelta,
  showChoices, currentDialogue, actionFeedback, actions,
  saveReady, saveConflict,
  roomEvents, activeEvent, openEvent, closeEvent, finishEvent, npcs,
  switchNpc, selectFriend, openHistory, chooseOption, actionState, performAction, portraitFor,
} = props.game
const lightboxSrc = ref('')
const pendingEventEffects = ref([])

function resolveEventSpeaker(speaker) {
  if (speaker?.npcId != null) {
    const npc = npcs.value.find(npc => npc.id === speaker.npcId)
    return npc ? { name: npc.name, portrait: portraitFor(speaker.npcId) } : { name: '未知', portrait: '?' }
  }
  return { name: speaker?.name, portrait: speaker?.avatar || '' }
}

// 选项只暂存，完整看完事件后才统一结算。
function onEventChoice(effects) {
  pendingEventEffects.value.push(effects || {})
}

function onEventFinish() {
  const merged = mergeEventChoices(pendingEventEffects.value)
  finishEvent(merged)
  pendingEventEffects.value = []
}

// 同步清空关闭或切换事件的暂存，外部切房间、切人物也不会遗留效果。
watch(activeEvent, () => {
  pendingEventEffects.value = []
}, { flush: 'sync' })
</script>

<template>
  <main class="scene-container">
    <div class="scene-box">
      <span class="location-tag">📍 {{ currentWorld }} · {{ currentRoom?.label }}</span>

      <!-- 房间事件入口放在位置标签下方，右侧留给人物列表。 -->
      <div v-if="roomEvents?.length" class="room-events" role="group" aria-label="房间事件">
        <button v-for="event in roomEvents" :key="event.id" class="room-event-btn" type="button"
                :disabled="event.done" :title="event.done ? '今天已经看过了，明天再来吧' : event.title"
                @click="openEvent(event.id)">
          {{ event.icon }} {{ event.title }}{{ event.done ? ' ✓' : '' }}
        </button>
      </div>

      <!-- 场景背景:包内配置了 bg 用背景图,否则保持占位 -->
      <div class="scene-bg">
        <img v-if="currentWorldDef?.bg" class="scene-bg-img" :src="currentWorldDef.bg" :alt="currentWorldDef.name + ' 场景背景'" />
        <template v-else>
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
            <circle cx="8.5" cy="8.5" r="1.5"/>
            <polyline points="21 15 16 10 5 21"/>
          </svg>
          <h3>场景画面 · 占位</h3>
          <p>{{ currentWorld }} · 场景插画位</p>
          <small v-if="sceneNpcs.length === 0">当前房间暂无可交谈人物，请从世界探索选择其他有人房间。</small>
        </template>
      </div>

      <!-- NPC 头像列表(浮在场景右侧边缘) -->
      <div class="npc-avatars">
        <button class="population-toggle" @click="npcListOpen = !npcListOpen" :aria-expanded="npcListOpen" aria-controls="life-world-avatars" :title="'当前房间 ' + worldPopulation + ' 人（含你）'">
          {{ worldPopulation }} 人 {{ npcListOpen ? '▴' : '▾' }}
        </button>
        <div v-show="npcListOpen" id="life-world-avatars" class="avatar-list">
        <div v-for="npc in sceneNpcs" :key="npc.id" class="avatar-anchor">
          <button :class="['npc-avatar-btn', { active: npc.id === currentNpcId }]"
                  @click="switchNpc(npc.id)" :title="npc.name" :aria-label="'与' + npc.name + '对话'"
                  :aria-pressed="npc.id === currentNpcId">
            <img :src="portraitFor(npc.id)" :alt="npc.name" />
          </button>
          <button class="scene-info" @click="selectFriend(npc.id)" :aria-label="'查看' + npc.name + '资料'">资料</button>
        </div>
        </div>
        <button class="history-icon-btn" @click="openHistory" title="对话历史">📜</button>
      </div>

      <div v-if="tutorialDemo" class="tutorial-demo">
        <small>教学示意 · 不写入存档</small>
        <div class="tutorial-demo-talk"><b>你</b><span>你好，很高兴认识你。<br>NPC：欢迎来这里一起看看风景。</span><b>NPC</b></div>
        <div>对话：一起拍照 ｜ 安静看海</div>
        <div>动作：摸摸头 +2 ｜ 戳戳脸 +1 ｜ 亲亲（好感≥30）</div>
      </div>
      <!-- 场景中仅保留头像旁的当前一句话；完整记录在历史抽屉中 -->
      <div v-if="dialogueVisible" class="dialogue-overlay">
        <div class="participants-row" :class="speech.from">
          <span class="participant-avatar player-participant" role="img" aria-label="白昼梦的头像">白</span>
          <button class="current-speech" @click="playback.complete" :aria-label="speech.typing ? '显示完整发言' : '当前发言'">
            <span>{{ speech.text || '…' }}</span>
            <img v-if="speech.image && !speech.typing" :src="speech.image" class="speech-thumb" alt="对话图片" @click.stop="lightboxSrc = speech.image" />
            <small v-if="speech.typing">点击显示全文</small>
          </button>
          <div class="npc-identity">
            <span class="npc-bond">{{ currentNpc.name }}</span>
            <img class="participant-avatar npc-participant" :src="npcPortrait" :alt="currentNpc.name" />
          </div>
        </div>

        <!-- 选项按钮 -->
        <section class="reply-panel" aria-label="回应方式">
          <div class="reply-tabs" role="tablist" aria-label="对话或动作">
            <button id="reply-dialogue-tab" role="tab" :aria-selected="replyTab === 'dialogue'" aria-controls="reply-dialogue" :class="{ active: replyTab === 'dialogue' }" @click="replyTab = 'dialogue'">对话</button>
            <button id="reply-actions-tab" role="tab" :aria-selected="replyTab === 'actions'" aria-controls="reply-actions" :class="{ active: replyTab === 'actions' }" @click="replyTab = 'actions'">动作</button>
            <small v-if="bondDelta > 0" class="bond-gain" role="status">好感 +{{ bondDelta }}</small>
          </div>
          <div v-if="replyTab === 'dialogue'" id="reply-dialogue" role="tabpanel" aria-labelledby="reply-dialogue-tab" class="reply-content">
            <div v-if="showChoices && currentDialogue?.choices" class="reply-options">
              <button v-for="(choice, i) in currentDialogue.choices" :key="i" class="reply-option" :disabled="!saveReady || saveConflict || speech.playing" @click="chooseOption(choice)">
                <span class="option-index">{{ String(i + 1).padStart(2, '0') }}</span><span>{{ choice.label }}</span><span class="option-arrow">↗</span>
              </button>
            </div>
            <p v-else class="reply-hint">{{ speech.playing ? '交谈中 · 点击气泡显示全文' : '对话结束 · 可切换动作' }}</p>
          </div>
          <div v-else id="reply-actions" role="tabpanel" aria-labelledby="reply-actions-tab" class="reply-content">
            <div class="action-options">
              <button v-for="action in actions" :key="action.id" class="action-option" :disabled="!saveReady || saveConflict || speech.playing || !actionState(action).allowed" :title="!actionState(action).allowed ? actionState(action).reason : actionState(action).repeated ? '今日已领取奖励，再次互动不增加好感' : '今日首次互动奖励好感 +' + action.reward" @click="performAction(action)">
                <strong>{{ action.label }}</strong>
                <small>{{ !actionState(action).allowed ? '好感 ≥ ' + action.threshold + ' 解锁' : actionState(action).repeated ? '今日已奖励' : '首次好感 +' + action.reward }}</small>
              </button>
            </div>
            <p v-if="actionFeedback" class="reply-hint action-result" role="status" :title="actionFeedback">{{ actionFeedback }}</p>
          </div>
        </section>
      </div>
    </div>
    <LifeEventModal v-if="activeEvent" :script="activeEvent.script" :title="activeEvent.event.title" :icon="activeEvent.event.icon"
                    :resolve-speaker="resolveEventSpeaker" player-name="白昼梦"
                    @choice="onEventChoice" @finish="onEventFinish" @close="closeEvent" />
    <LifeImageLightbox v-if="lightboxSrc" :src="lightboxSrc" alt="对话图片" @close="lightboxSrc = ''" />
  </main>
</template>

<style scoped>
/* ========== 中央场景(大空间) ========== */
.scene-container { display: flex; }
.scene-box {
  position: relative;
  flex: 1;
  background: #fff;
  border: 1px solid #d9dedb;
  border-radius: 12px;
  overflow: hidden;
  min-height: 600px;
}
.location-tag {
  position: absolute; top: 16px; left: 16px;
  padding: 6px 12px;
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid #d9dedb; border-radius: 999px;
  font-size: 12px; color: #69736e; z-index: 2;
}
/* 事件入口横向滚动，避免多事件挤占下方对话区域。 */
.room-events {
  position: absolute; top: 58px; left: 16px; right: 100px; z-index: 2;
  display: flex; gap: 8px; overflow-x: auto; padding: 4px 2px 8px;
}
.room-event-btn {
  flex-shrink: 0; padding: 6px 12px;
  background: #fff; border: 1px solid #d9dedb; border-radius: 999px;
  color: #237a57; font-size: 12px; cursor: pointer;
  box-shadow: 0 2px 8px rgba(25, 38, 32, .08);
}
.room-event-btn:hover:not(:disabled) { border-color: #237a57; }
.room-event-btn:disabled { color: #69736e; opacity: .55; cursor: default; }
.room-event-btn:focus-visible { outline: 2px solid #237a57; outline-offset: 2px; }
.scene-bg {
  position: absolute; inset: 0;
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  gap: 12px;
  background: linear-gradient(145deg, #f0f2f0, #e8eae8);
  color: #9a9fa0;
}
.scene-bg svg { opacity: 0.4; }
.scene-bg h3 { margin: 0; font-size: 16px; font-weight: 500; }
.scene-bg p { margin: 0; font-size: 12px; }
.scene-bg-img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }

/* NPC 头像列表(浮在场景右侧边缘) */
.speech-thumb {
  display: block;
  max-width: 180px;
  max-height: 120px;
  border-radius: 8px;
  margin-top: 6px;
  cursor: zoom-in;
  border: 1px solid #d9dedb;
}
.npc-avatars {
  position: absolute;
  top: 50%; right: 20px;
  transform: translateY(-50%);
  display: flex; flex-direction: column; gap: 12px;
  z-index: 3;
}
.npc-avatar-btn {
  width: 40px; height: 40px; padding: 0; overflow: hidden; border-radius: 50%;
  background: rgba(255, 255, 255, 0.9);
  border: 2px solid #d9dedb;
  display: grid; place-items: center;
  font-size: 24px; cursor: pointer;
  transition: all 0.2s;
  box-shadow: 0 2px 8px rgba(25, 38, 32, 0.1);
}
.avatar-anchor { position: relative; width: 40px; height: 40px; }
.npc-avatar-btn img { display: block; width: 100%; height: 100%; object-fit: cover; }
.avatar-speech {
  position: absolute; right: 54px; bottom: 22px;
  width: max-content; max-width: min(260px, calc(100vw - 160px));
  padding: 12px 16px; border: 1px solid #d9dedb; border-radius: 14px 14px 3px 14px;
  background: rgba(255,255,255,.97); color: #18201d;
  font-size: 13px; line-height: 1.7; overflow-wrap: anywhere;
  box-shadow: 0 3px 12px rgba(25,38,32,.09); pointer-events: none;
}
.avatar-speech::after {
  content: ''; position: absolute; right: -6px; bottom: 8px;
  width: 10px; height: 10px; transform: rotate(45deg);
  background: #fff; border-top: 1px solid #d9dedb; border-right: 1px solid #d9dedb;
}
.npc-avatar-btn:hover {
  border-color: #237a57;
  transform: scale(1.05);
}
.npc-avatar-btn.active {
  border-color: #237a57;
  background: #e5f3eb;
  box-shadow: 0 0 0 3px rgba(35, 122, 87, 0.2);
}
.history-icon-btn {
  width: 48px; height: 48px; border-radius: 50%;
  background: rgba(35, 122, 87, 0.9);
  border: 2px solid #237a57;
  color: #fff;
  display: grid; place-items: center;
  font-size: 18px; cursor: pointer;
  margin-top: 8px;
  box-shadow: 0 2px 8px rgba(35, 122, 87, 0.3);
}

/* 当前 NPC 立绘(场景中央) */
.npc-sprite {
  position: absolute;
  left: 50%; top: 45%;
  transform: translate(-50%, -50%);
  display: flex; flex-direction: column;
  align-items: center; gap: 12px;
  z-index: 2;
}
.npc-icon {
  width: 120px; height: 120px; border-radius: 50%;
  background: linear-gradient(145deg, #fff, #f0f2f0);
  border: 3px solid #d9dedb;
  display: grid; place-items: center;
  font-size: 48px;
  box-shadow: 0 8px 24px rgba(25, 38, 32, 0.15);
}
.npc-name-tag {
  padding: 6px 16px;
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid #d9dedb; border-radius: 6px;
  font-size: 13px; font-weight: 600; color: #18201d;
}

/* 对话气泡(浮在场景中央偏下) */
.dialogue-overlay {
  position: absolute;
  left: 50%; bottom: 40px;
  transform: translateX(-50%);
  width: min(600px, 85%);
  z-index: 4;
}
.dialogue-messages {
  display: flex; flex-direction: column; gap: 10px;
  margin-bottom: 16px;
  max-height: 200px; overflow-y: auto;
}
.message-bubble {
  display: flex;
}
.message-bubble.npc { justify-content: flex-start; }
.message-bubble.player { justify-content: flex-end; }
.bubble-text {
  max-width: 75%;
  padding: 12px 16px;
  border-radius: 16px;
  font-size: 14px; line-height: 1.6;
  word-break: break-word;
  box-shadow: 0 2px 8px rgba(25, 38, 32, 0.08);
}
.message-bubble.npc .bubble-text {
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid #d9dedb;
  color: #18201d;
}
.message-bubble.player .bubble-text {
  background: rgba(35, 122, 87, 0.95);
  color: #fff;
}

.dialogue-choices {
  display: flex; flex-direction: column; gap: 8px;
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid #d9dedb;
  border-radius: 12px;
  padding: 12px;
  box-shadow: 0 4px 16px rgba(25, 38, 32, 0.1);
}
.choice-btn {
  padding: 12px 16px;
  border-radius: 8px;
  border: 1px solid #d9dedb;
  background: #fff; color: #18201d;
  font-size: 13px; cursor: pointer;
  transition: all 0.2s;
  text-align: left;
}
.choice-btn:hover { border-color: #237a57; transform: translateX(-2px); }
.choice-btn.primary {
  background: #237a57; color: #fff;
  border-color: #237a57; font-weight: 600;
}
.choice-btn.primary:hover { background: #1e6b4c; }

/* Local dialogue stage: two participants, one bubble, no scrolling transcript. */
.dialogue-overlay { left: 18px; right: 18px; bottom: 22px; width: auto; transform: none; }
.participants-row { display: grid; grid-template-columns: 42px minmax(0, 1fr) 42px; gap: 12px; align-items: end; margin-bottom: 12px; }
.participant-avatar { width: 42px; height: 42px; object-fit: cover; border-radius: 50%; border: 2px solid #fff; box-shadow: 0 2px 8px #18201d18; }
.player-participant { display: grid; place-items: center; background: #e5f3eb; color: #237a57; font-size: 16px; font-weight: 700; }
.current-speech { position: relative; justify-self: start; max-width: 100%; min-width: 44px; padding: 11px 14px; border: 1px solid #d9dedb; border-radius: 14px 14px 14px 3px; background: rgba(255,255,255,.97); color: #18201d; font-size: 13px; line-height: 1.65; text-align: left; overflow-wrap: anywhere; box-shadow: 0 2px 8px #18201d14; }
.current-speech::before { content: ''; position: absolute; left: -6px; bottom: 13px; width: 10px; height: 10px; transform: rotate(45deg); background: #fff; border-left: 1px solid #d9dedb; border-bottom: 1px solid #d9dedb; }
.current-speech small { display: block; font-size: 10px; opacity: .65; margin-top: 4px; }
.participants-row.npc .current-speech { justify-self: end; border-radius: 14px 14px 3px 14px; }
.participants-row.npc .current-speech::before { left: auto; right: -6px; border: 0; border-top: 1px solid #d9dedb; border-right: 1px solid #d9dedb; }
.participants-row.player .current-speech { justify-self: start; background: #237a57; color: #fff; border-color: #237a57; border-radius: 14px 14px 14px 3px; }
.participants-row.player .current-speech::before { left: -6px; right: auto; background: #237a57; border: 0; }
.population-toggle { padding: 7px 9px; border: 1px solid #d9dedb; border-radius: 18px; background: rgba(255,255,255,.95); color: #237a57; font-size: 12px; cursor: pointer; white-space: nowrap; }
.avatar-list { display: flex; flex-direction: column; align-items: center; gap: 12px; }
.npc-avatars { top: 65px; transform: none; align-items: center; }
.population-toggle:focus-visible { outline: 2px solid #237a57; outline-offset: 3px; }
.dialogue-choices { background: transparent; border: 0; box-shadow: none; padding: 0 54px; }
.choice-btn:disabled { opacity: .55; cursor: default; }
.current-speech:focus-visible, .npc-avatar-btn:focus-visible { outline: 2px solid #237a57; outline-offset: 3px; }
@media (prefers-reduced-motion: reduce) { .npc-avatar-btn, .choice-btn { transition: none; } }

/* Warm paper reply selector; visual presentation stays inside the scene. */
.reply-panel { margin: 12px 54px 0; background: rgba(255,254,250,.97); border: 1px solid #d9e3db; border-radius: 12px; box-shadow: 0 5px 20px #2549320d; overflow: hidden; }
.reply-tabs { display: flex; gap: 6px; align-items: center; padding: 8px 10px; border-bottom: 1px solid #e7ebe5; background: #f6f8f2; }
.reply-tabs button { border: 0; border-radius: 6px; padding: 7px 15px; color: #69736e; background: transparent; font-size: 12px; cursor: pointer; }
.reply-tabs button.active { background: #237a57; color: #fff; }
.reply-tabs small { margin-left: auto; font-size: 10px; color: #69736e; }
.reply-content { padding: 10px; }
.reply-options { display: grid; gap: 6px; }
.reply-option { display: flex; align-items: center; gap: 10px; padding: 10px 12px; border: 1px solid #e0e6de; border-radius: 7px; background: #fffefa; color: #263b30; text-align: left; font-size: 12px; cursor: pointer; }
.reply-option:hover:not(:disabled) { background: #eaf3e9; border-color: #80ae93; }
.option-index { font-size: 10px; color: #7e9986; }
.option-arrow { margin-left: auto; color: #237a57; }
.action-options { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 8px; }
.action-option { padding: 12px 5px; border: 1px solid #dbe5d9; border-radius: 8px; background: #f4f8ef; color: #237a57; cursor: pointer; }
.action-option strong, .action-option small { display: block; }
.action-option strong { font-size: 13px; font-weight: 600; }
.action-option small { margin-top: 6px; font-size: 10px; color: #788576; }
.action-option:hover:not(:disabled) { background: #e5f3eb; border-color: #237a57; }
.action-option:disabled, .reply-option:disabled { opacity: .5; cursor: not-allowed; }
.reply-hint { margin: 8px 2px 2px; font-size: 11px; color: #788576; line-height: 1.6; }
.reply-panel button:focus-visible { outline: 2px solid #237a57; outline-offset: -2px; }
@media (max-width: 1200px) { .reply-panel { margin-left: 0; margin-right: 0; } .reply-tabs small { max-width: 45%; } }

/* Compact in-scene replies and acquaintance drawer. */
.reply-panel { width: min(100%, 420px); margin: 5px auto 0; border-radius: 9px; }
.reply-tabs { padding: 3px 6px; gap: 3px; }
.reply-tabs button { padding: 4px 10px; font-size: 11px; }
.reply-tabs small { max-width: none; white-space: nowrap; }
.reply-content { padding: 5px 6px; }
.reply-options { grid-template-columns: repeat(auto-fit, minmax(min(165px, 100%), 1fr)); gap: 4px; }
.reply-option { min-width: 0; padding: 5px 7px; gap: 5px; line-height: 1.35; font-size: 11px; }
.action-options { gap: 4px; }
.action-option { padding: 5px 3px; border-radius: 6px; }
.action-option strong { font-size: 12px; }
.action-option small { margin-top: 2px; font-size: 10px; }
.reply-hint { margin: 2px 0; line-height: 1.4; font-size: 10px; }
.action-result { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bond-gain { color: #237a57; padding-left: 4px; }
.npc-identity { position: relative; width: 42px; height: 42px; }
.npc-bond { position: absolute; bottom: calc(100% + 5px); right: 0; width: max-content; max-width: 210px; padding: 3px 7px; border-radius: 9px; background: #edf7ef; color: #285c40; font-size: 10px; line-height: 1.4; box-shadow: 0 1px 5px #18201d12; }
.npc-bond b { color: #138549; margin-left: 3px; }

.scene-info { display: block; margin: 3px auto 0; padding: 2px 5px; border: 0; background: #edf7ef; color: #237a57; font-size: 10px; cursor: pointer; border-radius: 4px; }

.tutorial-demo { position:absolute; left:18px; right:18px; bottom:22px; z-index:20; padding:14px; border:1px solid #9bc6a4; border-radius:12px; background:#fffdf4; color:#30533a; font-size:12px; line-height:1.8; }
.tutorial-demo-talk { display:flex; align-items:center; justify-content:space-between; gap:12px; margin:8px 0; }
.tutorial-demo-talk b { padding:9px; border-radius:50%; background:#e2f0df; }
.tutorial-demo-talk span { flex:1; border-radius:10px; padding:8px;background:#eff6ea; }

@media (max-width: 900px) {
  .scene-box { min-height: 500px; }
}
</style>
