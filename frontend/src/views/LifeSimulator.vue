<script setup>
import { ref, computed, onBeforeUnmount } from 'vue'
import LifeTutorial from '../components/LifeTutorial.vue'
import { useAuthStore } from '../stores/auth'
import { useLifeSave } from '../composables/lifeSave'
import { createLifePlayback } from '../composables/lifePlayback'
import { LIFE_ACTIONS, resolveLifeAction } from '../composables/lifeActions'
import { presenceFor, STATUS_LABELS, sceneRoster, canInteract, planJoin, WORLDS, ROOMS, roomFor, worldFor, roomDecision, migrateSocialState, friendshipDecision } from '../composables/lifePresence'

const avatarPaths = [
  '/life-assets/avatars/f1fcd71500345a67eb47b4a349339cfc_720.jpg',
  '/life-assets/avatars/850069447b371c8856317390362a550a_720.jpg',
  '/life-assets/avatars/e125eb534d189bfc005f4e1e3dac13da_720.jpg',
  '/life-assets/avatars/f134ae516db4415316fbf09384ed62b9_720.jpg',
]

// ==== 玩家人生数据 ====
const day = ref(7)
const npcListOpen = ref(false)
const tutorial = ref(null)
const auth = useAuthStore()
const tutorialDemo = ref(false)
let tutorialUi = null
function prepareTutorial(view) {
  if (!tutorialUi) tutorialUi = { panel: panel.value, npcListOpen: npcListOpen.value, showHistory: showHistory.value, profileId: profileId.value, selectedWorldId: selectedWorldId.value }
  // Presentation only: never call switchNpc, choices, actions, travel or save.
  panel.value = ''; showHistory.value = false; tutorialDemo.value = false
  if (view === 'roster') npcListOpen.value = true
  if (view === 'demo') { tutorialDemo.value = true }
  if (view === 'history') showHistory.value = true
  if (['worlds','friends','diary'].includes(view)) panel.value = view
  if (view === 'rooms') { selectedWorldId.value = currentRoom.value?.worldId || 'beach'; panel.value = 'rooms' }
  if (view === 'profile') { profileId.value = sceneNpcs.value[0]?.id || npcs.value[0]?.id; panel.value = 'profile' }
}
function closeTutorial() {
  tutorialDemo.value = false
  if (!tutorialUi) return
  panel.value = tutorialUi.panel; npcListOpen.value = tutorialUi.npcListOpen
  showHistory.value = tutorialUi.showHistory; profileId.value = tutorialUi.profileId; selectedWorldId.value = tutorialUi.selectedWorldId
  tutorialUi = null
}
const currentRoomId = ref('beach-1024')
const friendIds = ref([])
const interactedNpcIds = ref([])
const friends = computed(() => npcs.value.filter(n => friendIds.value.includes(n.id)))
const sceneNpcs = computed(() => sceneRoster(npcs.value, currentRoomId.value))
const worldPopulation = computed(() => (roomFor(currentRoomId.value)?.occupants || 0) + 1)
const currentRoom = computed(() => roomFor(currentRoomId.value))
const stats = ref({ mood: 72, energy: 66, social: 34, explore: 28 })
const labels = { mood: '心情', energy: '精力', social: '社交', explore: '探索' }
const tags = ref(['慢热', '喜欢拍照', '夜猫子'])
const currentWorld = ref('潮汐之后 · 黄昏')
const unlockedWorlds = ref(8)

// ==== 当前世界人物 ====
const npcs = ref([
  { id: 'ache', name: '阿澈', role: '摄影爱好者', avatar: '📷', status: '正在看着海面', bond: 12 },
  { id: 'xiaomi', name: '小弥', role: '舞蹈玩家', avatar: '💃', status: '在海边散步', bond: 6 },
  { id: 'maoyou', name: '猫又', role: '模型改装师', avatar: '⚙️', status: '在调试设备', bond: 2 },
  { id: 'yu', name: '小宇', role: '世界探索者', avatar: '🧭', status: '刚到达这个世界', bond: 0 },
])

const currentNpcId = ref('ache')
const currentNpc = computed(() => npcs.value.find(n => n.id === currentNpcId.value))

// ==== 对话历史(每个 NPC 独立保存) ====
const conversations = ref({
  ache: [
    { from: 'npc', text: '你第一次来到这个世界吗？', day: 7, time: '18:20' },
  ],
  xiaomi: [
    { from: 'npc', text: '你好呀，我叫小弥，平时喜欢在这里练舞。', day: 7, time: '18:15' },
  ],
  maoyou: [
    { from: 'npc', text: '……嗯？你也是来拍照的吗？', day: 7, time: '18:10' },
  ],
  yu: [
    { from: 'npc', text: '哇，这里好美！你也是玩家吗？', day: 7, time: '18:05' },
  ],
})

// ==== 当前对话剧本 ====
const dialogueScripts = {
  ache: {
    npcLine: { from: 'npc', text: '这里的日落每天都不太一样。要不要一起拍张照？就当是今天认识的纪念。', day: 7, time: '18:20' },
    choices: [
      { label: '好啊，一起拍吧', effect: '好感 +2 · 心情 +2', delta: { social: 2, mood: 2 }, npcReply: '太好了！那我调整一下角度……好了，笑一个！', next: 'continue' },
      { label: '我来帮你拍一张', effect: '好感 +3 · 表达 +2', delta: { social: 3, energy: -2 }, npcReply: '欸？可以吗？那就麻烦你了……这张照片我会好好保存的。', next: 'continue' },
      { label: '想先安静看一会儿海', effect: '心情 +4 · 探索 +1', delta: { mood: 4, explore: 1 }, npcReply: '嗯，海边确实很适合发呆。那我就先去拍别处了，回头见！', next: 'end' },
    ],
  },
  xiaomi: {
    npcLine: { from: 'npc', text: '今天也想跳一会儿舞呢。你要不要一起来？', day: 7, time: '18:15' },
    choices: [
      { label: '好啊，一起跳', effect: '社交 +3 · 精力 -4', delta: { social: 3, energy: -4 }, npcReply: '哈哈，你的动作好可爱！', next: 'continue' },
      { label: '我在旁边看就好', effect: '心情 +2', delta: { mood: 2 }, npcReply: '没问题！那我就开始了哦。', next: 'continue' },
    ],
  },
  maoyou: {
    npcLine: { from: 'npc', text: '……这个模型的骨架好像有点问题。你会改模型吗？', day: 7, time: '18:10' },
    choices: [
      { label: '我可以试试', effect: '社交 +2 · 好感 +2', delta: { social: 2, energy: -3 }, npcReply: '太好了！那就拜托你了。', next: 'continue' },
      { label: '我不会诶', effect: '', delta: {}, npcReply: '啊……没关系，我再想想办法。', next: 'continue' },
    ],
  },
  yu: {
    npcLine: { from: 'npc', text: '你经常来这个世界吗？我第一次来，感觉好棒！', day: 7, time: '18:05' },
    choices: [
      { label: '我也是第一次来', effect: '好感 +1 · 心情 +1', delta: { social: 1, mood: 1 }, npcReply: '哈哈，那我们算是同好了！', next: 'continue' },
      { label: '偶尔来，这里很放松', effect: '表达 +2', delta: { social: 2 }, npcReply: '嗯嗯，我也是这样觉得的。', next: 'continue' },
    ],
  },
}

const currentDialogue = computed(() => dialogueScripts[currentNpcId.value])
const currentConversation = computed(() => conversations.value[currentNpcId.value] || [])

const completed = ref({})
const actionLedger = ref({})
const replyTab = ref('dialogue')
const actionFeedback = ref('')
const bondDelta = ref(0)
let bondFeedbackTimer
function showBondGain(delta) {
  clearTimeout(bondFeedbackTimer)
  bondDelta.value = delta
  if (delta > 0) bondFeedbackTimer = setTimeout(() => { bondDelta.value = 0 }, 4000)
}
const portraitFor = npcId => avatarPaths[['ache', 'xiaomi', 'maoyou', 'yu'].indexOf(npcId)]
function actionState(action) {
  return resolveLifeAction({ ledger: actionLedger.value, day: day.value, npcId: currentNpcId.value, bond: currentNpc.value.bond, actionId: action.id })
}
function performAction(action) {
  if (!saveReady.value || saveConflict.value || speech.value.playing || !dialogueVisible.value || !canInteract(currentNpcId.value, currentRoomId.value)) return
  const result = actionState(action)
  if (!result.allowed) return
  const npc = currentNpc.value
  if (!interactedNpcIds.value.includes(npc.id)) interactedNpcIds.value.push(npc.id)
  npc.bond = result.bond
  showBondGain(result.reward)
  actionLedger.value = result.ledger
  const text = `（对${npc.name}${action.label}）`
  const reply = `${npc.name}${action.reply}`
  conversations.value[npc.id].push(
    { from: 'player', text, day: day.value, time: '18:20' },
    { from: 'npc', text: reply, day: day.value, time: '18:20' },
  )
  actionFeedback.value = result.repeated ? '今天已获得该动作奖励，本次仍可互动，好感不再增加。' :
    result.reward ? `今日首次${action.label} · 好感 +${result.reward}` : '今日首次互动已记录 · 好感已达上限 100'
  diaryHistory.value.unshift({ day: day.value, text: `${text} ${actionFeedback.value}`, mood: '亲近' })
  markChanged()
  playback.play([{ from: 'player', text }, { from: 'npc', text: reply }])
}
const pending = ref({})
const dialogueVisible = ref(false)
const speech = ref({ from: 'npc', text: '', typing: false, playing: false })
const playback = createLifePlayback(value => { speech.value = value }, {
  reducedMotion: () => window.matchMedia('(prefers-reduced-motion: reduce)').matches,
})
const npcPortrait = computed(() => avatarPaths[['ache', 'xiaomi', 'maoyou', 'yu'].indexOf(currentNpcId.value)])
const showChoices = computed(() => dialogueVisible.value && !speech.value.playing && !completed.value[currentNpcId.value] && !pending.value[currentNpcId.value])
function cancelPresentation() {
  playback.stop()
  showBondGain(0)
  dialogueVisible.value = false
}
let toastTimer
onBeforeUnmount(() => {
  cancelPresentation()
  clearTimeout(toastTimer)
})
const toast = ref('')

function showToast(msg) {
  toast.value = msg
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => { toast.value = '' }, 2000)
}

function switchNpc(npcId) {
  if (!saveReady.value || saveConflict.value || !canInteract(npcId, currentRoomId.value)) return
  cancelPresentation()
  currentNpcId.value = npcId
  actionFeedback.value = ''
  const conv = conversations.value[npcId]
  if (conv.length === 1) {
    conv.push({ ...dialogueScripts[npcId].npcLine, day: day.value })
  }
  dialogueVisible.value = true
  const latest = [...conv].reverse().find(msg => msg.from === 'npc')
  if (latest) playback.play([latest])
  markChanged()
}

function chooseOption(choice) {
  if (!saveReady.value || saveConflict.value || !showChoices.value || !canInteract(currentNpcId.value, currentRoomId.value)) return
  const npcId = currentNpcId.value
  if (!interactedNpcIds.value.includes(npcId)) interactedNpcIds.value.push(npcId)
  const sentDay = day.value
  pending.value[npcId] = true
  conversations.value[npcId].push({
    from: 'player',
    text: choice.label,
    day: day.value,
    time: '18:20',
  })

  if (choice.delta) {
    for (const [k, v] of Object.entries(choice.delta)) {
      stats.value[k] = Math.max(0, Math.min(100, stats.value[k] + v))
    }
  }

  const bondGain = Number(choice.effect.match(/好感 \+(\d+)/)?.[1] || 0)
  const npc = npcs.value.find(n => n.id === npcId)
  if (npc) {
    const previousBond = npc.bond
    npc.bond = Math.min(100, npc.bond + bondGain)
    showBondGain(npc.bond - previousBond)
  }
  showToast('✦ ' + (choice.effect || '已记录'))

  // Store the complete turn atomically; no delayed reply can be lost on navigation.
  conversations.value[npcId].push({
    from: 'npc', text: choice.npcReply, day: sentDay, time: '18:20',
  })
  pending.value[npcId] = false
  completed.value[npcId] = true
  diaryHistory.value.unshift({ day: sentDay, text: `${currentNpc.value.name}：${choice.label}`, mood: '日常' })
  markChanged()
  playback.play([{ from: 'player', text: choice.label }, { from: 'npc', text: choice.npcReply }])
}

// ==== 对话历史记录 ====
const showHistory = ref(false)
const historyNpcId = ref('ache')
const historyConversation = computed(() => conversations.value[historyNpcId.value] || [])

function openHistory() {
  historyNpcId.value = currentNpcId.value
  showHistory.value = true
}

// ==== 世界/手记面板 ====
const panel = ref('')
const profileId = ref('')
const profileNpc = computed(() => npcs.value.find(npc => npc.id === profileId.value))
const profilePresence = computed(() => presenceFor(profileId.value))
const profileJoin = computed(() => friendIds.value.includes(profileId.value) ? planJoin(profileId.value) : { allowed: false, reason: '添加好友后才能通过资料跟随加入' })
const profileRoom = computed(() => roomFor(profilePresence.value.roomId))
const profileAdd = computed(() => friendshipDecision(profileId.value, profileNpc.value?.bond || 0, interactedNpcIds.value, friendIds.value))
const selectedWorldId = ref('beach')
const selectedWorld = computed(() => worldFor(selectedWorldId.value))
const visibleRooms = computed(() => ROOMS.filter(r => r.worldId === selectedWorldId.value))
function addFriend() {
  if (!saveReady.value || saveConflict.value || !profileAdd.value.allowed) return
  friendIds.value.push(profileId.value)
  markChanged()
  showToast(profileNpc.value.name + '已接受好友申请')
}
function selectFriend(npcId) {
  profileId.value = npcId
  panel.value = 'profile'
}
function joinFriend() {
  if (!profileJoin.value.allowed) return
  enterRoom(profileJoin.value.roomId)
}
const worlds = WORLDS
function exploreWorld(world) {
  selectedWorldId.value = world.id
  panel.value = 'rooms'
}
function enterRoom(roomId) {
  if (!saveReady.value || saveConflict.value) return
  const access = roomDecision(roomFor(roomId))
  if (!access.allowed) { showToast(access.reason); return }
  cancelPresentation()
  currentRoomId.value = roomId
  currentWorld.value = access.world
  panel.value = ''
  npcListOpen.value = false
  actionFeedback.value = ''
  markChanged()
  showToast('已进入' + access.world + ' ' + roomFor(roomId).label + '，点击房间人物交谈')
}

const diaryHistory = ref([
  { day: 6, text: '"原来不说话的时候，也可以和别人共享一段风景。"', mood: '平静' },
  { day: 5, text: '"咖啡杯是热的，但手心里更暖的是有人记得你的名字。"', mood: '安心' },
  { day: 3, text: '"第一次主动开口，声音轻得像羽毛。"', mood: '紧张' },
])

function snapshot() {
  return JSON.parse(JSON.stringify({
    schemaVersion: 1, day: day.value, stats: stats.value, tags: tags.value,
    currentWorld: currentWorld.value, unlockedWorlds: unlockedWorlds.value,
    currentNpcId: currentNpcId.value, npcs: npcs.value,
    conversations: conversations.value, diary: diaryHistory.value, completed: completed.value,
    actionLedger: actionLedger.value,
    currentRoomId: currentRoomId.value, friendIds: friendIds.value, interactedNpcIds: interactedNpcIds.value,
  }))
}
function hydrate(state) {
  cancelPresentation()
  if (state.schemaVersion !== 1 || !state.npcs?.length ||
      state.npcs.some(n => !dialogueScripts[n.id]) ||
      !state.npcs.some(n => n.id === state.currentNpcId)) throw new Error('存档版本或人物不兼容')
  day.value = state.day
  stats.value = state.stats
  tags.value = state.tags
  const social = migrateSocialState(state)
  currentRoomId.value = social.currentRoomId
  friendIds.value = social.friendIds
  interactedNpcIds.value = social.interactedNpcIds
  currentWorld.value = worldFor(roomFor(currentRoomId.value).worldId).name
  unlockedWorlds.value = state.unlockedWorlds
  currentNpcId.value = state.currentNpcId
  npcs.value = state.npcs
  conversations.value = state.conversations
  diaryHistory.value = state.diary
  completed.value = state.completed
  actionLedger.value = state.actionLedger || {}
  actionFeedback.value = ''
  pending.value = {}
}
const {
  ready: saveReady, saving: saveBusy, dirty: saveDirty, error: saveError,
  conflict: saveConflict, savedAt, changed: markChanged, flush: flushSave, load: reloadSave,
} = useLifeSave(snapshot, hydrate)
async function save() {
  if (!saveReady.value || saveConflict.value) return
  markChanged()
  if (await flushSave()) showToast('存档已保存到服务器')
}
function reloadConfirmed() {
  if (!saveDirty.value || window.confirm('重新载入会丢弃尚未保存的本地修改，继续吗？')) reloadSave()
}

function nextDay() {
  if (!saveReady.value || saveConflict.value) return
  day.value += 1
  stats.value.energy = Math.min(100, stats.value.energy + 10)
  cancelPresentation()
  pending.value = {}
  completed.value = {}
  for (const npcId in conversations.value) {
    conversations.value[npcId].push({ ...dialogueScripts[npcId].npcLine, day: day.value })
  }
  markChanged()
  showToast('新的一天开始了，精力恢复了 10 点')
}
</script>

<template>
  <div class="life-page">
    <!-- 顶部信息栏 -->
    <header class="life-header">
      <div class="brand">
        <span class="brand-mark">万</span>
        <div class="brand-text">
          <strong>万事屋 · 虚拟人生</strong>
          <small>在另一个世界，慢慢成为自己。</small>
        </div>
      </div>
      <div class="status-pills">
        <span>📅 第 {{ day }} 天</span>
        <span>⏰ 18:20</span>
        <span>♥ 心情 {{ stats.mood }}</span>
        <span>⚡ 精力 {{ stats.energy }}</span>
      </div>
      <div class="header-actions">
        <button :disabled="!saveReady || saveConflict" @click="tutorial?.start()">新手指引</button>
        <button class="icon-btn" title="设置">⚙</button>
        <button class="icon-btn" title="返回" @click="$router.back()">↩</button>
      </div>
    </header>

    <div class="save-status" role="status" aria-live="polite">
      <span v-if="saveError">{{ saveError }}</span>
      <span v-else>{{ !saveReady ? '正在读取个人存档…' : saveBusy ? '正在保存…' : saveDirty ? '有修改尚未保存' : savedAt ? '个人存档已同步' : '尚无存档，请开始游戏或手动保存' }}</span>
      <button v-if="saveError && saveReady && !saveConflict" @click="save" :disabled="saveBusy">重试保存</button>
      <button v-if="saveError" @click="reloadConfirmed" :disabled="saveBusy">重新载入</button>
    </div>
    <!-- 主内容三栏 -->
    <div class="life-layout" :inert="!saveReady || saveConflict">
      <!-- 左侧角色 -->
      <aside class="char-panel">
        <div class="section-title">01 角色</div>
        <div class="char-card">
          <div class="avatar">☺</div>
          <div class="char-info">
            <h2>白昼梦</h2>
            <p>新人探索者</p>
            <div class="tags">
              <span v-for="t in tags" :key="t">{{ t }}</span>
            </div>
          </div>
        </div>
        <div class="stats-bars">
          <div v-for="(val, key) in stats" :key="key" class="stat-row">
            <span>{{ labels[key] }}</span>
            <div class="bar"><b :style="{ width: val + '%' }"></b></div>
            <strong>{{ val }}</strong>
          </div>
        </div>
        <div class="prompt-text">今天，想去哪里看看？</div>
      </aside>

      <!-- 中央场景(大空间,UI 浮在上面) -->
      <main class="scene-container">
        <div class="scene-box">
          <span class="location-tag">📍 {{ currentWorld }} · {{ currentRoom?.label }}</span>
          
          <!-- 场景背景占位 -->
          <div class="scene-bg">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
              <circle cx="8.5" cy="8.5" r="1.5"/>
              <polyline points="21 15 16 10 5 21"/>
            </svg>
            <h3>场景画面 · 占位</h3>
            <p>{{ currentWorld }} · 场景插画位</p>
            <small v-if="sceneNpcs.length === 0">当前房间暂无可交谈人物，请从世界探索选择其他有人房间。</small>
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
                <div v-if="showChoices && currentDialogue.choices" class="reply-options">
                  <button v-for="(choice, i) in currentDialogue.choices" :key="i" class="reply-option" :disabled="!saveReady || saveConflict || speech.playing" @click="chooseOption(choice)">
                    <span class="option-index">{{ String(i + 1).padStart(2, '0') }}</span><span>{{ choice.label }}</span><span class="option-arrow">↗</span>
                  </button>
                </div>
                <p v-else class="reply-hint">{{ speech.playing ? '交谈中 · 点击气泡显示全文' : '对话结束 · 可切换动作' }}</p>
              </div>
              <div v-else id="reply-actions" role="tabpanel" aria-labelledby="reply-actions-tab" class="reply-content">
                <div class="action-options">
                  <button v-for="action in LIFE_ACTIONS" :key="action.id" class="action-option" :disabled="!saveReady || saveConflict || speech.playing || !actionState(action).allowed" :title="!actionState(action).allowed ? actionState(action).reason : actionState(action).repeated ? '今日已领取奖励，再次互动不增加好感' : '今日首次互动奖励好感 +' + action.reward" @click="performAction(action)">
                    <strong>{{ action.label }}</strong>
                    <small>{{ !actionState(action).allowed ? '好感 ≥ ' + action.threshold + ' 解锁' : actionState(action).repeated ? '今日已奖励' : '首次好感 +' + action.reward }}</small>
                  </button>
                </div>
                <p v-if="actionFeedback" class="reply-hint action-result" role="status" :title="actionFeedback">{{ actionFeedback }}</p>
              </div>
            </section>
          </div>
        </div>
      </main>

      <!-- 右侧功能入口 -->
      <aside class="menu-panel">
        <div class="section-title">02 功能入口</div>
        <button data-life-guide="worlds" class="menu-item" @click="panel='worlds'">
          <div class="menu-icon">🌍</div>
          <div class="menu-text">
            <strong>世界探索</strong>
            <small>已发现地点 {{ unlockedWorlds }} / 30</small>
          </div>
          <span class="arrow">→</span>
        </button>
        <button class="menu-item" @click="panel='friends'">
          <div class="menu-icon">♡</div>
          <div class="menu-text"><strong>好友</strong><small>已添加 {{ friends.length }} 位好友</small></div>
          <span class="arrow">→</span>
        </button>
        <button class="menu-item" @click="panel='diary'">
          <div class="menu-icon">📖</div>
          <div class="menu-text">
            <strong>人生手记</strong>
            <small>{{ diaryHistory.length }} 篇记录</small>
          </div>
          <span class="arrow">→</span>
        </button>
      </aside>
    </div>

    <!-- 底部操作 -->
    <footer class="life-footer">
      <button @click="save" :disabled="!saveReady || saveConflict || saveBusy">存档</button>
      <button @click="nextDay" :disabled="!saveReady || saveConflict">下一天</button>
      <small>对话将写入今天的手记</small>
    </footer>

    <!-- 对话历史抽屉 -->
    <transition name="slide">
      <div v-if="showHistory" class="drawer" @click.self="showHistory = false">
        <div class="drawer-content history-drawer">
          <button class="drawer-close" @click="showHistory = false">✕</button>
          <h2>对话历史</h2>
          <div class="history-npc-tabs">
            <button v-for="npc in npcs" :key="npc.id"
                    :class="['history-tab', { active: npc.id === historyNpcId }]"
                    @click="historyNpcId = npc.id">
              {{ npc.name }}
            </button>
          </div>
          <div class="history-messages">
            <div v-for="(msg, i) in historyConversation" :key="i"
                 :class="['history-bubble', msg.from]">
              <div class="bubble-text">{{ msg.text }}</div>
              <div class="bubble-time">第 {{ msg.day }} 天 · {{ msg.time }}</div>
            </div>
          </div>
        </div>
      </div>
    </transition>

    <!-- 功能抽屉 -->
    <transition name="slide">
      <div v-if="panel" class="drawer" @click.self="panel = ''">
        <div class="drawer-content">
          <button class="drawer-close" @click="panel = ''">✕</button>

          <section v-if="panel === 'worlds'" class="drawer-body">
            <h2>世界探索 <small>{{ unlockedWorlds }} / 30</small></h2>
            <p class="reply-hint">选择地图查看房间，只能加入有人、未满的非私密房间。</p>
            <div v-for="w in worlds" :key="w.name" class="world-line">
              <div class="world-thumb" :style="{ background: 'linear-gradient(145deg,' + w.color + ',#e8e6e0)' }"><span>WORLD</span></div>
              <div><strong>{{ w.name }}</strong><small>{{ w.vibe }}</small></div>
              <div class="world-entry">
                <button @click="exploreWorld(w)">查看房间</button>
              </div>
            </div>
          </section>

          <section v-else-if="panel === 'rooms'" class="drawer-body">
            <button class="profile-back" @click="panel = 'worlds'">← 世界列表</button>
            <h2>{{ selectedWorld?.name }} · 房间</h2>
            <p class="reply-hint">人数为模拟人物与背景访客；无创建房间功能。</p>
            <div v-for="room in visibleRooms" :key="room.id" class="world-line">
              <div><strong>{{ room.label }} · {{ room.private ? '私密' : '公开' }}</strong><small>{{ room.occupants + (currentRoomId === room.id ? 1 : 0) }}/{{ room.capacity }} 人{{ currentRoomId === room.id ? ' · 你在这里' : '' }}</small></div>
              <div class="world-entry"><button :disabled="!saveReady || saveConflict || !roomDecision(room).allowed" @click="enterRoom(room.id)">{{ currentRoomId === room.id ? '返回房间' : '加入' }}</button><small v-if="!roomDecision(room).allowed">{{ roomDecision(room).reason }}</small></div>
            </div>
          </section>
          <section v-else-if="panel === 'friends'" class="drawer-body">
            <h2>好友 <small>{{ friends.length }} 位</small></h2>
            <p v-if="!friends.length" class="reply-hint">还没有好友。先在房间中互动至少一次，好感达到 10 后，从人物资料主动添加。</p>
            <div class="friend-list">
              <div v-for="npc in friends" :key="npc.id" class="friend-row">
                <button class="profile-avatar" @click="selectFriend(npc.id)" :aria-label="'查看' + npc.name + '的资料'"><img :src="portraitFor(npc.id)" :alt="npc.name" /></button>
                <span class="friend-detail"><strong>{{ npc.name }}</strong></span>
                <span class="presence-label" :class="presenceFor(npc.id).status">● {{ STATUS_LABELS[presenceFor(npc.id).status] }}</span>
              </div>
            </div>
          </section>
          <section v-else-if="panel === 'profile' && profileNpc" class="drawer-body profile-body">
            <button class="profile-back" @click="panel = 'friends'">← 好友列表</button>
            <div class="profile-heading"><img :src="portraitFor(profileNpc.id)" :alt="profileNpc.name" /><h2>{{ profileNpc.name }}</h2></div>
            <p class="presence-label" :class="profilePresence.status">● {{ STATUS_LABELS[profilePresence.status] }}</p>
            <p>{{ profileNpc.role }} · {{ profilePresence.intro }}</p>
            <p>所在世界：{{ profileRoom ? worldFor(profileRoom.worldId).name + ' · ' + profileRoom.label : '离线 · 暂无房间' }}</p>
            <div class="profile-affection"><strong>好感 {{ profileNpc.bond }}/100</strong><span class="friend-meter"><i :style="{ width: profileNpc.bond + '%' }"></i></span></div>
            <button class="profile-join" :disabled="!saveReady || saveConflict || !profileAdd.allowed" @click="addFriend">{{ friendIds.includes(profileId) ? '已是好友' : '添加好友' }}</button>
            <p class="reply-hint" role="status">{{ profileAdd.reason }}</p>
            <button v-if="friendIds.includes(profileId)" class="profile-join" :disabled="!saveReady || saveConflict || !profileJoin.allowed" @click="joinFriend">加入所在房间</button>
            <p class="reply-hint">{{ profileJoin.allowed ? '加入后，请点击场景内人物头像交谈。' : profileJoin.reason }}</p>
            <small class="profile-mock">模拟好友状态与世界，尚未连接真实 VRC。</small>
          </section>
          <section v-else-if="panel === 'diary'" class="drawer-body">
            <h2>人生手记</h2>
            <blockquote v-for="h in diaryHistory" :key="h.day">
              <p>{{ h.text }}</p>
              <small>第 {{ h.day }} 天 · {{ h.mood }}</small>
            </blockquote>
          </section>
        </div>
      </div>
    </transition>

    <LifeTutorial ref="tutorial" :ready="saveReady && !saveConflict" :user-id="auth.user?.id" @prepare="prepareTutorial" @close="closeTutorial" />
    <!-- Toast 提示 -->
    <transition name="fade">
      <div v-if="toast" class="toast">{{ toast }}</div>
    </transition>
  </div>
</template>

<style scoped>
.tutorial-demo { position:absolute; left:18px; right:18px; bottom:22px; z-index:20; padding:14px; border:1px solid #9bc6a4; border-radius:12px; background:#fffdf4; color:#30533a; font-size:12px; line-height:1.8; }
.tutorial-demo-talk { display:flex; align-items:center; justify-content:space-between; gap:12px; margin:8px 0; }
.tutorial-demo-talk b { padding:9px; border-radius:50%; background:#e2f0df; }
.tutorial-demo-talk span { flex:1; border-radius:10px; padding:8px;background:#eff6ea; }
.life-page {
  min-height: calc(100vh - 72px);
  background: #f5f6f4;
  color: #18201d;
  padding: 24px 32px 40px;
  font-family: Inter, 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

/* ========== 顶部信息栏 ========== */
.life-header {
  display: flex; align-items: center; gap: 24px;
  margin-bottom: 28px; padding-bottom: 20px;
  border-bottom: 1px solid #d9dedb;
}
.brand { display: flex; align-items: center; gap: 12px; }
.brand-mark {
  display: grid; place-items: center;
  width: 44px; height: 44px;
  background: #18201d; color: white;
  font-family: Georgia, serif; font-size: 22px; font-weight: 700;
  transform: rotate(-3deg);
}
.brand-text strong { display: block; font-size: 18px; }
.brand-text small { display: block; margin-top: 2px; color: #69736e; font-size: 11px; }
.status-pills { display: flex; gap: 16px; margin-left: auto; }
.status-pills span {
  padding: 6px 12px; border-radius: 999px;
  background: #fff; border: 1px solid #d9dedb;
  font-size: 12px; color: #69736e;
}
.header-actions { display: flex; gap: 8px; }
.icon-btn {
  width: 36px; height: 36px;
  border: 1px solid #d9dedb; border-radius: 6px;
  background: #fff; color: #69736e;
  cursor: pointer;
}

/* ========== 三栏布局 ========== */
.life-layout {
  display: grid;
  grid-template-columns: 280px 1fr 280px;
  gap: 24px;
  margin-bottom: 28px;
}
.section-title {
  font-size: 12px; font-weight: 700; color: #237a57;
  margin-bottom: 12px; letter-spacing: 0.05em;
}

/* 左侧角色面板 */
.char-panel { display: flex; flex-direction: column; }
.char-card {
  display: flex; align-items: center; gap: 16px;
  padding: 20px; background: #fff;
  border: 1px solid #d9dedb; border-radius: 8px;
  margin-bottom: 20px;
}
.avatar {
  width: 64px; height: 64px; border-radius: 50%;
  background: linear-gradient(145deg, #e5f3eb, #c8e6d4);
  display: grid; place-items: center;
  font-size: 28px; border: 2px solid #fff;
  box-shadow: 0 2px 8px rgba(25, 38, 32, 0.08);
}
.char-info h2 { margin: 0 0 4px; font-size: 20px; font-family: Georgia, serif; }
.char-info p { margin: 0 0 8px; color: #69736e; font-size: 12px; }
.tags { display: flex; gap: 6px; flex-wrap: wrap; }
.tags span {
  padding: 4px 8px; border-radius: 4px;
  background: #e5f3eb; color: #237a57;
  font-size: 10px; font-weight: 600;
}
.stats-bars {
  background: #fff; border: 1px solid #d9dedb;
  border-radius: 8px; padding: 20px; margin-bottom: 16px;
}
.stat-row {
  display: grid; grid-template-columns: 40px 1fr 32px;
  align-items: center; gap: 12px; margin-bottom: 12px;
}
.stat-row:last-child { margin-bottom: 0; }
.stat-row span { font-size: 12px; color: #69736e; }
.stat-row strong { font-size: 13px; color: #18201d; text-align: right; }
.bar { height: 6px; border-radius: 3px; background: #e5e8e5; overflow: hidden; }
.bar b { display: block; height: 100%; background: #237a57; border-radius: inherit; transition: width 0.3s ease; }
.prompt-text {
  padding: 16px 20px; background: #e5f3eb; border-radius: 8px;
  color: #237a57; font-size: 13px; font-style: italic;
}

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

/* NPC 头像列表(浮在场景右侧边缘) */
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
.friend-list { display: grid; gap: 9px; }
.friend-row { display: flex; align-items: center; gap: 12px; width: 100%; padding: 11px; border: 1px solid #dfe6df; border-radius: 9px; background: #fffefa; color: #263b30; text-align: left; cursor: pointer; }
.friend-row.selected { background: #edf5ed; border-color: #89b297; }
.friend-row:hover:not(:disabled) { border-color: #237a57; }
.friend-row:disabled { opacity: .55; cursor: not-allowed; }
.friend-row:focus-visible { outline: 2px solid #237a57; outline-offset: 2px; }
.friend-row img { width: 38px; height: 38px; object-fit: cover; border-radius: 50%; }
.friend-detail { flex: 1; min-width: 0; }
.friend-detail strong { font-size: 13px; }
.friend-detail small { margin-left: 5px; font-size: 10px; color: #69836f; font-weight: 400; }
.friend-meter { display: block; height: 4px; margin-top: 8px; border-radius: 4px; background: #dce7dc; overflow: hidden; }
.friend-meter i { display: block; height: 100%; background: #4d9670; }
.friend-bond { color: #237a57; font-size: 12px; white-space: nowrap; }
.friend-bond small { display: block; color: #788576; font-size: 10px; margin-top: 4px; }

.profile-avatar { padding: 0; border: 0; background: transparent; border-radius: 50%; cursor: pointer; }
.scene-info { display: block; margin: 3px auto 0; padding: 2px 5px; border: 0; background: #edf7ef; color: #237a57; font-size: 10px; cursor: pointer; border-radius: 4px; }
.profile-avatar img { display: block; }
.profile-avatar:focus-visible { outline: 2px solid #237a57; outline-offset: 3px; }
.friend-row { cursor: default; }
.presence-label { font-size: 12px; color: #7a827e; }
.presence-label.green { color: #237a57; }
.presence-label.orange { color: #b77427; }
.presence-label.red { color: #b84949; }
.profile-back { border: 0; background: transparent; color: #237a57; cursor: pointer; padding: 8px 0; }
.profile-heading { display: flex; align-items: center; gap: 14px; margin-top: 12px; }
.profile-heading img { width: 64px; height: 64px; object-fit: cover; border-radius: 50%; }
.profile-heading h2 { margin: 0; }
.profile-body p { font-size: 13px; line-height: 1.7; }
.profile-affection { padding: 16px 0; color: #237a57; font-size: 13px; }
.profile-join { padding: 10px 18px; background: #237a57; color: #fff; border: 0; border-radius: 8px; cursor: pointer; }
.profile-join:disabled { background: #dce2dc; color: #788576; cursor: not-allowed; }
.profile-mock { display: block; margin-top: 20px; color: #788576; font-size: 10px; }

/* ========== 右侧功能入口 ========== */
.menu-panel { display: flex; flex-direction: column; }
.menu-item {
  display: flex; align-items: center; gap: 12px;
  padding: 16px; background: #fff;
  border: 1px solid #d9dedb; border-radius: 8px;
  margin-bottom: 12px; cursor: pointer;
  transition: all 0.2s; text-align: left;
}
.menu-item:hover { border-color: #237a57; box-shadow: 0 2px 8px rgba(35, 122, 87, 0.1); }
.menu-icon {
  width: 40px; height: 40px; border-radius: 8px;
  background: #e5f3eb;
  display: grid; place-items: center;
  font-size: 20px;
}
.menu-text { flex: 1; }
.menu-text strong { display: block; font-size: 14px; margin-bottom: 2px; }
.menu-text small { color: #69736e; font-size: 11px; }
.arrow { color: #237a57; font-size: 16px; }

/* ========== 底部操作 ========== */
.life-footer {
  display: flex; align-items: center; gap: 24px;
  padding-top: 20px;
  border-top: 1px solid #d9dedb;
}
.life-footer button {
  padding: 8px 16px;
  background: transparent; border: 1px solid #d9dedb;
  border-radius: 6px; color: #69736e;
  font-size: 12px; cursor: pointer;
  transition: all 0.2s;
}
.life-footer button:hover { border-color: #237a57; color: #237a57; }
.life-footer small {
  margin-left: auto;
  color: #9a9fa0; font-size: 11px;
}

/* ========== 抽屉 ========== */
.drawer {
  position: fixed; inset: 0;
  background: rgba(24, 32, 29, 0.3);
  z-index: 1000;
  display: flex; justify-content: flex-end;
}
.drawer-content {
  position: relative;
  width: 400px; height: 100%;
  background: #fff;
  border-left: 1px solid #d9dedb;
  padding: 32px 24px;
  overflow-y: auto;
}
.drawer-close {
  position: absolute; top: 16px; right: 16px;
  width: 32px; height: 32px; border: 0;
  border-radius: 50%; background: #f0f2f0;
  color: #69736e; cursor: pointer;
}

/* 对话历史抽屉 */
.history-drawer { width: 450px; }
.history-drawer h2 { margin-bottom: 20px; font-size: 18px; }
.history-npc-tabs {
  display: flex; gap: 8px;
  margin-bottom: 20px;
  padding-bottom: 12px;
  border-bottom: 1px solid #f0f2f0;
}
.history-tab {
  padding: 8px 16px;
  background: #fff; border: 1px solid #d9dedb;
  border-radius: 6px; color: #69736e;
  font-size: 13px; cursor: pointer;
  transition: all 0.2s;
}
.history-tab:hover { border-color: #237a57; }
.history-tab.active {
  background: #237a57; color: #fff;
  border-color: #237a57;
}
.history-messages {
  display: flex; flex-direction: column; gap: 12px;
}
.history-bubble {
  padding: 10px 14px;
  border-radius: 12px;
  font-size: 13px; line-height: 1.6;
}
.history-bubble.npc {
  background: #f5f6f4;
  border: 1px solid #e5e8e5;
  align-self: flex-start;
}
.history-bubble.player {
  background: #237a57; color: #fff;
  align-self: flex-end;
}
.history-bubble .bubble-time {
  margin-top: 4px;
  font-size: 9px; color: #9a9fa0;
}

/* 功能抽屉 */
.drawer-body h2 {
  display: flex; align-items: baseline; gap: 10px;
  margin-bottom: 20px; font-size: 18px;
}
.drawer-body h2 small { color: #69736e; font-size: 11px; }
.world-line {
  display: grid;
  grid-template-columns: 56px 1fr auto;
  align-items: center; gap: 12px;
  padding: 12px 0;
  border-top: 1px solid #f0f2f0;
}
.world-thumb {
  height: 44px; border-radius: 6px;
  overflow: hidden; position: relative;
}
.world-thumb span {
  position: absolute; bottom: 4px; left: 6px;
  font-size: 7px; letter-spacing: 0.1em;
  color: rgba(255, 255, 255, 0.8);
}
.world-line strong, .world-line small { display: block; }
.world-line strong { font-size: 13px; }
.world-line small { margin-top: 3px; color: #69736e; font-size: 10px; }
.world-line > b { color: #9a9fa0; font-size: 10px; font-weight: 400; }
.world-entry { margin-left: auto; flex-shrink: 0; text-align: right; max-width: 125px; }
.world-entry button { border: 1px solid #237a57; border-radius: 7px; padding: 7px 13px; background: #237a57; color: #fff; cursor: pointer; }
.world-entry button:disabled { background: #e3e8e2; border-color: #d9dedb; color: #788576; cursor: not-allowed; }
.world-entry button:focus-visible { outline: 2px solid #237a57; outline-offset: 3px; }
blockquote {
  margin: 0 0 14px;
  padding: 14px 16px;
  border-left: 2px solid #237a57;
  background: #f8f9f8;
}
blockquote p { margin: 0 0 6px; font-size: 13px; line-height: 1.6; }
blockquote small { color: #69736e; font-size: 10px; }

.slide-enter-active, .slide-leave-active { transition: opacity 0.3s; }
.slide-enter-from, .slide-leave-to { opacity: 0; }
.slide-enter-active .drawer-content { transition: transform 0.3s; }
.slide-enter-from .drawer-content { transform: translateX(100%); }

/* ========== Toast ========== */
.toast {
  position: fixed; top: 90px; left: 50%;
  transform: translateX(-50%);
  padding: 10px 20px;
  background: #18201d; color: #fff;
  border-radius: 999px; font-size: 13px;
  z-index: 2000;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}
.fade-enter-active, .fade-leave-active { transition: opacity 0.3s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

/* ========== 响应式 ========== */
@media (max-width: 1200px) {
  .life-layout { grid-template-columns: 260px 1fr 260px; gap: 16px; }
}
@media (max-width: 900px) {
  .life-page { padding: 16px 20px 32px; }
  .life-header { flex-wrap: wrap; gap: 12px; }
  .status-pills { order: 3; width: 100%; }
  .life-layout { grid-template-columns: 1fr; gap: 20px; }
  .scene-box { min-height: 500px; }
  .drawer-content { width: min(340px, 90vw); }
  .history-drawer { width: min(400px, 90vw); }
}
</style>
