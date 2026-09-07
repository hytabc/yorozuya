<script setup>
import { ref, computed, onBeforeUnmount } from 'vue'

const avatarPaths = [
  '/life-assets/avatars/f1fcd71500345a67eb47b4a349339cfc_720.jpg',
  '/life-assets/avatars/850069447b371c8856317390362a550a_720.jpg',
  '/life-assets/avatars/e125eb534d189bfc005f4e1e3dac13da_720.jpg',
  '/life-assets/avatars/f134ae516db4415316fbf09384ed62b9_720.jpg',
]

// ==== 玩家人生数据 ====
const day = ref(7)
const stats = ref({ mood: 72, energy: 66, social: 34, explore: 28 })
const labels = { mood: '心情', energy: '精力', social: '社交', explore: '探索' }
const tags = ['慢热', '喜欢拍照', '夜猫子']
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
const pending = ref({})
const showChoices = computed(() => !completed.value[currentNpcId.value] && !pending.value[currentNpcId.value])
const latestNpcLine = computed(() => [...currentConversation.value].reverse().find(msg => msg.from === 'npc')?.text || '')
const replyTimers = new Set()
let toastTimer
onBeforeUnmount(() => {
  replyTimers.forEach(clearTimeout)
  clearTimeout(toastTimer)
})
const toast = ref('')

function showToast(msg) {
  toast.value = msg
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => { toast.value = '' }, 2000)
}

function switchNpc(npcId) {
  currentNpcId.value = npcId
  const conv = conversations.value[npcId]
  if (conv.length === 1) {
    conv.push({ ...dialogueScripts[npcId].npcLine })
  }
}

function chooseOption(choice) {
  if (!showChoices.value) return
  const npcId = currentNpcId.value
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

  showToast('✦ ' + (choice.effect || '已记录'))

  const timer = setTimeout(() => {
    conversations.value[npcId].push({
      from: 'npc', text: choice.npcReply, day: sentDay, time: '18:20',
    })
    pending.value[npcId] = false
    completed.value[npcId] = true
    replyTimers.delete(timer)
  }, 500)
  replyTimers.add(timer)
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

const worlds = [
  { name: '潮汐之后', vibe: '安静 · 适合独处和拍照', color: '#3f7777', day: '昨晚' },
  { name: '小小咖啡馆', vibe: '轻松 · 遇见 2 位新朋友', color: '#9a7563', day: '第 5 天' },
  { name: '夜间聚会大厅', vibe: '热闹 · 认识阿澈', color: '#576c80', day: '现在' },
]

const diaryHistory = ref([
  { day: 6, text: '"原来不说话的时候，也可以和别人共享一段风景。"', mood: '平静' },
  { day: 5, text: '"咖啡杯是热的，但手心里更暖的是有人记得你的名字。"', mood: '安心' },
  { day: 3, text: '"第一次主动开口，声音轻得像羽毛。"', mood: '紧张' },
])

function save() {
  diaryHistory.value.unshift({ day: day.value, text: '手动存档：今天的人生进度已保存。', mood: '安心' })
  showToast('存档成功')
}

function nextDay() {
  day.value += 1
  stats.value.energy = Math.min(100, stats.value.energy + 10)
  replyTimers.forEach(clearTimeout)
  replyTimers.clear()
  pending.value = {}
  completed.value = {}
  for (const npcId in conversations.value) {
    conversations.value[npcId].push({ ...dialogueScripts[npcId].npcLine, day: day.value })
  }
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
        <button class="icon-btn" title="设置">⚙</button>
        <button class="icon-btn" title="返回" @click="$router.back()">↩</button>
      </div>
    </header>

    <!-- 主内容三栏 -->
    <div class="life-layout">
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
          <span class="location-tag">📍 潮汐之后 · 黄昏</span>
          
          <!-- 场景背景占位 -->
          <div class="scene-bg">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
              <circle cx="8.5" cy="8.5" r="1.5"/>
              <polyline points="21 15 16 10 5 21"/>
            </svg>
            <h3>场景画面 · 占位</h3>
            <p>黄昏海边社交空间插画位</p>
          </div>

          <!-- NPC 头像列表(浮在场景右侧边缘) -->
          <div class="npc-avatars">
            <div v-for="(npc, index) in npcs" :key="npc.id" class="avatar-anchor">
              <button :class="['npc-avatar-btn', { active: npc.id === currentNpcId }]"
                      @click="switchNpc(npc.id)" :title="npc.name" :aria-label="'与' + npc.name + '对话'"
                      :aria-pressed="npc.id === currentNpcId">
                <img :src="avatarPaths[index]" :alt="npc.name" />
              </button>
              <Transition name="fade">
                <div v-if="npc.id === currentNpcId" class="avatar-speech" role="status" aria-live="polite">
                  {{ pending[npc.id] ? '……' : latestNpcLine }}
                </div>
              </Transition>
            </div>
            <button class="history-icon-btn" @click="openHistory" title="对话历史">📜</button>
          </div>

          <!-- 场景中仅保留头像旁的当前一句话；完整记录在历史抽屉中 -->
          <div class="dialogue-overlay">
            
            <!-- 选项按钮 -->
            <div v-if="showChoices && currentDialogue.choices" class="dialogue-choices">
              <button v-for="(choice, i) in currentDialogue.choices" :key="i"
                      :class="['choice-btn', { primary: i === 0 }]"
                      @click="chooseOption(choice)">
                {{ choice.label }}
              </button>
            </div>
          </div>
        </div>
      </main>

      <!-- 右侧功能入口 -->
      <aside class="menu-panel">
        <div class="section-title">02 功能入口</div>
        <button class="menu-item" @click="panel='worlds'">
          <div class="menu-icon">🌍</div>
          <div class="menu-text">
            <strong>世界探索</strong>
            <small>已发现地点 {{ unlockedWorlds }} / 30</small>
          </div>
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
      <button @click="save">存档</button>
      <button @click="nextDay">下一天</button>
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
            <div v-for="w in worlds" :key="w.name" class="world-line">
              <div class="world-thumb" :style="{ background: 'linear-gradient(145deg,' + w.color + ',#e8e6e0)' }"><span>WORLD</span></div>
              <div><strong>{{ w.name }}</strong><small>{{ w.vibe }}</small></div>
              <b>{{ w.day }}</b>
            </div>
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

    <!-- Toast 提示 -->
    <transition name="fade">
      <div v-if="toast" class="toast">{{ toast }}</div>
    </transition>
  </div>
</template>

<style scoped>
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
