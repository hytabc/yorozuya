<script setup>
import { computed, ref } from 'vue'
import { Snowflake } from 'lucide-vue-next'
import '../frost/frost.css'
import { useFrostGame } from '../frost/useFrostGame.js'
import { useAuthStore } from '../stores/auth'
import FrostChapterList from '../frost/components/FrostChapterList.vue'
import FrostBoard from '../frost/components/FrostBoard.vue'
import FrostMeters from '../frost/components/FrostMeters.vue'
import FrostInsightPanel from '../frost/components/FrostInsightPanel.vue'
import FrostHintDrawer from '../frost/components/FrostHintDrawer.vue'
import FrostButterflyOverlay from '../frost/components/FrostButterflyOverlay.vue'
import FrostEndingOverlay from '../frost/components/FrostEndingOverlay.vue'
import FrostGallery from '../frost/components/FrostGallery.vue'
import FrostAchievements from '../frost/components/FrostAchievements.vue'
import FrostCharacters from '../frost/components/FrostCharacters.vue'

const auth = useAuthStore()
const game = useFrostGame()
const {
  screen,
  chapters,
  progress,
  currentLevel,
  chain,
  chainFragments,
  draggable,
  phase,
  result,
  overlayVisible,
  endingAlreadySeen,
  globalEnding,
  butterfly,
  hintVisible,
  ruleVisible,
  toast,
  canEdit,
  canSubmit,
  coherence,
  valence,
  insights,
  failCount,
  hintTier,
  currentHint,
  ruleHint,
  achievements,
  achievementsList,
  achievementsPoints,
  achievementsTotalPoints,
  levelStates,
  gallery,
  globalGallery,
  characters,
  totalEndingsSeen,
  totalDesignEndings,
  enterLevel,
  showScreen,
  move,
  moveBy,
  moveToEdge,
  undo,
  submit,
  retry,
  keepEnding,
  closeGlobalEnding,
  backToChapters,
  dismissButterfly,
  openHint,
  closeHint,
  openRule,
  closeRule,
  toggleSettings,
  setFontScale,
  undoStack,
} = game

const { ready: saveReady, saving: saveSaving, dirty: saveDirty, error: saveError, conflict: saveConflict, savedAt, load: reloadSave } = game.save

const settingsVisible = ref(false)

const relationships = computed(() => [
  { from: 'Mio', to: 'Shiori', label: '砂糖（核心主轴）', bidirectional: true },
  { from: 'Rin', to: 'Shiori', label: '单向守护', bidirectional: false },
  { from: 'Shiori', to: 'Yu', label: '无意识的替代', bidirectional: false },
  { from: 'Mio', to: 'Yu', label: '镜像（非敌对）', bidirectional: true },
  { from: 'Rin', to: 'Observer', label: '世界建造者 → 观测者', bidirectional: false },
])

const chapterTitle = computed(() => {
  const chapter = chapters.find((c) => c.id === currentLevel.value?.chapter)
  return chapter?.title || ''
})

const hintHighlights = computed(() => (hintVisible.value && currentHint.value?.highlight ? currentHint.value.highlight : []))

const rootClasses = computed(() => {
  const settings = progress.value.settings
  return {
    'reduce-motion': settings.reduceMotion,
    'color-blind': settings.colorBlind,
    'high-contrast': settings.highContrast,
    [`font-${settings.fontScale}`]: true,
  }
})

const saveStatus = computed(() => {
  if (saveError.value) return '存档异常'
  if (!saveReady.value) return '正在读取存档…'
  if (saveSaving.value) return '正在保存…'
  if (saveDirty.value) return '有修改尚未保存'
  return '进度已同步'
})

const headerNote = computed(() => {
  if (saveConflict.value) return '冲突：另一页面已更新存档'
  if (saveError.value) return '读取/保存失败'
  return saveStatus.value
})
</script>

<template>
  <div class="page inner-page frost" :class="rootClasses">
    <header class="page-title">
      <div>
        <span class="eyebrow"><Snowflake :size="15" /> SUGAR FROST</span>
        <h1>糖霜世界</h1>
        <p>你是「观测者」——把被打散的聊天记录与回忆片段重新排序，修复（或亲手放开）一段段虚拟社交关系。</p>
      </div>
    </header>

    <div class="frost-toolbar">
      <div class="frost-tabs">
        <button type="button" class="frost-tab" :class="{ 'is-active': screen === 'chapters' }" @click="showScreen('chapters')">章节</button>
        <button type="button" class="frost-tab" :class="{ 'is-active': screen === 'gallery' }" @click="showScreen('gallery')">结局图鉴</button>
        <button type="button" class="frost-tab" :class="{ 'is-active': screen === 'achievements' }" @click="showScreen('achievements')">成就</button>
        <button type="button" class="frost-tab" :class="{ 'is-active': screen === 'characters' }" @click="showScreen('characters')">角色</button>
        <button type="button" class="frost-tab" @click="settingsVisible = true">设置</button>
      </div>
      <div class="frost-savebar">
        <span>{{ auth.user?.nickname || '登录用户' }}</span>
        <span :class="{ 'is-warn': saveError || saveConflict }">{{ headerNote }}</span>
        <span v-if="saveDirty || saveError || saveConflict">
          <button type="button" class="frost-tab" @click="reloadSave()">重新载入</button>
        </span>
        <span v-else-if="savedAt">已存档 {{ totalEndingsSeen }} / {{ totalDesignEndings }} 结局</span>
      </div>
    </div>

    <p v-if="saveError" class="frost-notice">{{ saveError }}</p>

    <!-- 章节 -->
    <FrostChapterList v-if="screen === 'chapters'" :chapters="levelStates" @enter="enterLevel" />

    <!-- 图鉴 -->
    <FrostGallery v-else-if="screen === 'gallery'" :gallery="gallery" :global-gallery="globalGallery" />

    <!-- 成就 -->
    <FrostAchievements
      v-else-if="screen === 'achievements'"
      :list="achievementsList"
      :unlocked="achievements"
      :points="achievementsPoints"
      :total-points="achievementsTotalPoints"
    />

    <!-- 角色 -->
    <FrostCharacters v-else-if="screen === 'characters'" :characters="characters" :relationships="relationships" />

    <!-- 关卡 -->
    <section v-else-if="screen === 'level' && currentLevel">
      <div class="frost-level-bar">
        <button type="button" class="frost-back" @click="backToChapters">← 返回</button>
        <span class="frost-chapter-tag">第 {{ currentLevel.chapter }} 章 · {{ chapterTitle }}</span>
        <h2>{{ currentLevel.id }} · {{ currentLevel.title }}</h2>
        <div class="frost-level-actions">
          <button type="button" class="frost-btn" @click="openHint">线索</button>
          <button type="button" class="frost-btn" @click="openRule">规则</button>
        </div>
      </div>

      <p v-if="currentLevel.epigraph" class="frost-chapter-epigraph">{{ currentLevel.epigraph }}</p>
      <p class="frost-intro">{{ currentLevel.intro }}</p>

      <div v-if="phase === 'settling'" class="frost-settling">
        <div class="frost-spinner" aria-hidden="true" />
        <p>因果稳定中……</p>
      </div>

      <div v-else class="frost-play-layout">
        <FrostBoard
          :chain="chain"
          :fragments="chainFragments"
          :draggable="draggable"
          :can-edit="canEdit"
          :can-submit="canSubmit"
          :can-undo="undoStack.length > 0"
          :highlight="hintHighlights"
          @move="move"
          @move-by="moveBy"
          @move-edge="moveToEdge"
          @undo="undo"
          @submit="submit"
        />
        <aside class="frost-side">
          <FrostMeters :coherence="coherence" :valence="valence" />
          <FrostInsightPanel :insights="insights" />
        </aside>
      </div>
    </section>

    <FrostHintDrawer
      :visible="hintVisible"
      :tier="hintTier"
      :hint="currentHint"
      :fail-count="failCount"
      :rule-hint="ruleHint"
      @close="closeHint"
      @show-rule="openRule"
    />

    <FrostButterflyOverlay v-if="butterfly" :butterfly="butterfly" @dismiss="dismissButterfly" />

    <FrostEndingOverlay
      v-if="overlayVisible && result"
      :ending="result.ending"
      :is-chaos="result.isChaos"
      :already-seen="endingAlreadySeen"
      :score="result.score"
      :coherence="result.coherence"
      :valence="result.valence"
      @keep="keepEnding"
      @retry="retry"
    />

    <FrostEndingOverlay v-if="globalEnding" :ending="globalEnding" is-global @close="closeGlobalEnding" />

    <!-- 规则说明 -->
    <div v-if="ruleVisible" class="frost-drawer-backdrop" @click.self="closeRule">
      <aside class="frost-drawer" role="dialog" aria-label="规则说明">
        <h3>规则说明</h3>
        <p class="frost-hint">{{ ruleHint }}</p>
        <div style="margin-top: 22px; display: flex; justify-content: flex-end">
          <button type="button" class="frost-btn is-primary" @click="closeRule">知道了</button>
        </div>
      </aside>
    </div>

    <!-- 设置 -->
    <div v-if="settingsVisible" class="frost-drawer-backdrop" @click.self="settingsVisible = false">
      <aside class="frost-drawer" role="dialog" aria-label="设置">
        <h3>设置</h3>
        <label class="frost-char-line" style="display: flex; gap: 8px; align-items: center">
          <input type="checkbox" :checked="progress.settings.reduceMotion" @change="toggleSettings('reduceMotion')" />
          减少动效
        </label>
        <label class="frost-char-line" style="display: flex; gap: 8px; align-items: center">
          <input type="checkbox" :checked="progress.settings.colorBlind" @change="toggleSettings('colorBlind')" />
          色盲模式（强化形状标识）
        </label>
        <label class="frost-char-line" style="display: flex; gap: 8px; align-items: center">
          <input type="checkbox" :checked="progress.settings.highContrast" @change="toggleSettings('highContrast')" />
          高对比度
        </label>
        <div class="frost-char-line" style="margin-top: 8px">
          字号：
          <button
            v-for="scale in ['small', 'medium', 'large']"
            :key="scale"
            type="button"
            class="frost-tab"
            :class="{ 'is-active': progress.settings.fontScale === scale }"
            @click="setFontScale(scale)"
          >
            {{ scale === 'small' ? '小' : scale === 'large' ? '大' : '中' }}
          </button>
        </div>
        <div style="margin-top: 22px; display: flex; justify-content: flex-end">
          <button type="button" class="frost-btn is-primary" @click="settingsVisible = false">完成</button>
        </div>
      </aside>
    </div>

    <p v-if="toast" class="frost-toast" role="status">{{ toast }}</p>
  </div>
</template>
