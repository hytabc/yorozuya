<script setup>
/**
 * VrLife —— 「VRChat 玩家历程模拟器」主视图。
 *
 * 职责：
 *  1. onMounted 触发 store.init()（数据尚未加载时）；
 *  2. 按 store.phase 做界面路由：loading / error / start / opening / playing / ended；
 *  3. playing 阶段组装三栏布局（左：属性面板，中：事件卡，右：时间线）；
 *  4. 监听数字键 1-4，映射到当前可用选项（仅 playing 且无任何弹层时）；
 *  5. 承载「完整时间线」弹层（由顶部栏 / 结局页的 show-timeline 事件触发）。
 */
import { ref, computed, onMounted, onBeforeUnmount } from 'vue';
import { useVrclifeStore } from '../vrclife/store/vrclifeStore.js';
import { rarityLabel } from '../vrclife/utils/format.js';

import VrStartScreen from '../vrclife/components/VrStartScreen.vue';
import VrTopBar from '../vrclife/components/VrTopBar.vue';
import VrSidePanel from '../vrclife/components/VrSidePanel.vue';
import VrTimeline from '../vrclife/components/VrTimeline.vue';
import VrEventCard from '../vrclife/components/VrEventCard.vue';
import VrResultOverlay from '../vrclife/components/VrResultOverlay.vue';
import VrEndingScreen from '../vrclife/components/VrEndingScreen.vue';

/** 站点未提供统一的 title 管理，直接用 document.title */
const PAGE_TITLE = '虚拟人生 · VRChat 玩家历程模拟器';

const store = useVrclifeStore();

/** 完整时间线弹层开关 */
const showTimeline = ref(false);

const phase = computed(() => store.phase);

/* ---- 开场卡展示数据 ---- */
const openingArch = computed(() => store.startArch || null);
const openingName = computed(() => (openingArch.value && openingArch.value.name) || '未知开局');
const openingRarity = computed(() => {
  const r = openingArch.value && openingArch.value.rarity;
  return r ? rarityLabel(r) : '';
});
const openingText = computed(() => {
  if (store.startText) return store.startText;
  return (openingArch.value && openingArch.value.desc) || '';
});

/** error 阶段重试 */
function retry() {
  store.init();
}

/** 开场卡 → 正式回合 */
function beginPlay() {
  store.begin();
}

/** 事件卡选项点击 */
function onChoose(optionId) {
  if (!optionId) return;
  store.choose(optionId);
}

/** 关闭结果弹层：store 未提供 clearResult，直接写 state 即可 */
function closeResult() {
  store.result = null;
}

/**
 * 数字键 1-4 → 当前「可用」选项。
 * 仅在 playing 阶段、且没有结果弹层 / 时间线弹层时生效。
 */
function handleKeydown(e) {
  if (store.phase !== 'playing') return;
  if (store.result) return;
  if (showTimeline.value) return;
  if (e.ctrlKey || e.metaKey || e.altKey) return;

  const t = e.target;
  if (t && (
    t.isContentEditable
    || t.tagName === 'INPUT'
    || t.tagName === 'TEXTAREA'
    || t.tagName === 'SELECT'
  )) return;

  const m = /^[1-4]$/.exec(e.key || '');
  if (!m) return;

  const idx = Number(m[0]) - 1;
  const cur = store.currentEvent;
  if (!cur || !Array.isArray(cur.options)) return;

  const available = cur.options.filter((o) => o && o.available);
  const opt = available[idx];
  if (!opt) return;

  e.preventDefault();
  store.choose(opt.id);
}

onMounted(() => {
  if (typeof document !== 'undefined') {
    document.title = PAGE_TITLE;
    document.addEventListener('keydown', handleKeydown);
  }
  // 数据未加载时（首次进入）才初始化，避免页面重挂载时把进行中的一局重置掉
  if (!store.data) store.init();
});

onBeforeUnmount(() => {
  if (typeof document !== 'undefined') {
    document.removeEventListener('keydown', handleKeydown);
  }
});
</script>

<template>
  <div class="vr-life">
    <!-- ============ loading ============ -->
    <div v-if="phase === 'loading'" class="phase-center">
      <div class="spinner" aria-hidden="true"></div>
      <p class="phase-text">正在载入人生数据…</p>
    </div>

    <!-- ============ error ============ -->
    <div v-else-if="phase === 'error'" class="phase-center">
      <div class="error-card">
        <p class="error-eyebrow">加载失败</p>
        <p class="error-text">{{ store.errorMsg || '数据加载失败，请稍后再试。' }}</p>
        <button type="button" class="btn primary" @click="retry">重试</button>
      </div>
    </div>

    <!-- ============ start ============ -->
    <VrStartScreen v-else-if="phase === 'start'" />

    <!-- ============ opening ============ -->
    <div v-else-if="phase === 'opening'" class="phase-center">
      <div class="opening-card">
        <p class="opening-eyebrow">出 生</p>
        <h1 class="opening-name">{{ openingName }}</h1>
        <p v-if="openingRarity" class="opening-rarity">{{ openingRarity }}</p>
        <p class="opening-text">{{ openingText }}</p>
        <button type="button" class="btn primary" @click="beginPlay">开始</button>
      </div>
    </div>

    <!-- ============ playing（三栏） ============ -->
    <div v-else-if="phase === 'playing'" class="play-shell">
      <VrTopBar @show-timeline="showTimeline = true" />

      <div class="play-body">
        <VrSidePanel class="col col-left" />

        <VrEventCard
          class="col col-center"
          :current="store.currentEvent"
          @choose="onChoose"
        />

        <VrTimeline class="col col-right" />
      </div>
    </div>

    <!-- ============ ended ============ -->
    <VrEndingScreen
      v-else-if="phase === 'ended'"
      @show-timeline="showTimeline = true"
    />

    <!-- ============ 结果弹层 ============ -->
    <VrResultOverlay
      v-if="store.result"
      :result="store.result"
      @close="closeResult"
    />

    <!-- ============ 完整时间线弹层 ============ -->
    <div v-if="showTimeline" class="tl-modal" @click.self="showTimeline = false">
      <div class="tl-modal-panel">
        <header class="tl-modal-head">
          <h2 class="tl-modal-title">完整时间线</h2>
          <button
            type="button"
            class="tl-modal-close"
            aria-label="关闭"
            @click="showTimeline = false"
          >×</button>
        </header>
        <div class="tl-modal-body">
          <VrTimeline class="tl-modal-timeline" :force-expand="true" />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.vr-life {
  min-height: 100vh;
  color: #e9e4f5;
  background:
    radial-gradient(1100px 720px at 12% -8%, rgba(124, 58, 237, 0.26), transparent 60%),
    radial-gradient(900px 660px at 88% 108%, rgba(6, 182, 212, 0.18), transparent 62%),
    radial-gradient(900px 640px at 76% 12%, rgba(236, 72, 153, 0.12), transparent 58%),
    linear-gradient(165deg, #1a1033 0%, #0f0a1e 100%);
  background-attachment: fixed;
}

/* =============== 通用居中舞台（loading / error / opening） =============== */
.phase-center {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 20px;
  padding: 48px 24px;
  box-sizing: border-box;
}

.phase-text {
  margin: 0;
  font-size: 15px;
  letter-spacing: 2px;
  color: #8b7fa8;
}

.spinner {
  width: 52px;
  height: 52px;
  border-radius: 50%;
  border: 3px solid rgba(124, 58, 237, 0.22);
  border-top-color: #7c3aed;
  border-right-color: #06b6d4;
  animation: vr-spin 0.9s linear infinite;
}

@keyframes vr-spin {
  to { transform: rotate(360deg); }
}

/* =============== 错误卡片 =============== */
.error-card {
  width: 100%;
  max-width: 460px;
  padding: 30px 28px 26px;
  border-radius: 16px;
  text-align: center;
  background: linear-gradient(160deg, rgba(236, 72, 153, 0.14), rgba(15, 10, 30, 0.78));
  border: 1px solid rgba(236, 72, 153, 0.42);
  box-shadow: 0 8px 32px rgba(236, 72, 153, 0.22);
  backdrop-filter: blur(14px);
}

.error-eyebrow {
  margin: 0 0 10px;
  font-size: 13px;
  letter-spacing: 4px;
  color: #f9a8d4;
}

.error-text {
  margin: 0 0 22px;
  font-size: 15px;
  line-height: 1.8;
  color: #cfc6e8;
  word-break: break-word;
}

/* =============== 开场卡 =============== */
.opening-card {
  width: 100%;
  max-width: 520px;
  padding: 36px 32px 30px;
  border-radius: 16px;
  text-align: center;
  background: linear-gradient(160deg, rgba(124, 58, 237, 0.18), rgba(15, 10, 30, 0.78));
  border: 1px solid rgba(124, 58, 237, 0.42);
  box-shadow: 0 8px 32px rgba(124, 58, 237, 0.25);
  backdrop-filter: blur(14px);
  animation: vr-opening-in 0.42s cubic-bezier(0.22, 1, 0.36, 1);
}

.opening-eyebrow {
  margin: 0 0 12px;
  font-size: 13px;
  letter-spacing: 6px;
  color: #06b6d4;
}

.opening-name {
  margin: 0 0 10px;
  font-size: 30px;
  font-weight: 700;
  line-height: 1.3;
  background: linear-gradient(100deg, #e9e4f5 10%, #7c3aed 55%, #06b6d4 95%);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}

.opening-rarity {
  display: inline-block;
  margin: 0 0 18px;
  padding: 2px 12px;
  border-radius: 999px;
  font-size: 12px;
  letter-spacing: 1px;
  color: #b79cf0;
  border: 1px solid rgba(124, 58, 237, 0.55);
  background: rgba(124, 58, 237, 0.1);
}

.opening-text {
  margin: 0 0 28px;
  font-size: 16px;
  line-height: 1.95;
  color: #b9aede;
  font-style: italic;
  white-space: pre-wrap;
}

@keyframes vr-opening-in {
  from {
    opacity: 0;
    transform: translateY(14px) scale(0.985);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

/* =============== 主游戏三栏 =============== */
.play-shell {
  display: flex;
  flex-direction: column;
  height: 100vh;
  box-sizing: border-box;
  overflow: hidden;
}

.play-body {
  flex: 1 1 auto;
  min-height: 0;
  display: grid;
  grid-template-columns: 300px minmax(0, 1fr) 360px;
  grid-template-rows: minmax(0, 1fr);
  gap: 16px;
  padding: 16px 20px 20px;
  box-sizing: border-box;
  overflow: hidden;
}

/* 三个列容器都需要 min-height:0，内部才能各自滚动 */
.col {
  min-width: 0;
  min-height: 0;
}

/* 事件卡区域自身滚动（短内容时不受影响） */
.col-center {
  overflow-y: auto;
}

/* =============== 通用按钮 =============== */
.btn {
  padding: 11px 24px;
  border-radius: 10px;
  border: 1px solid transparent;
  font-size: 16px;
  font-family: inherit;
  cursor: pointer;
  transition: transform 0.15s ease, box-shadow 0.2s ease, background 0.2s ease;
}

.btn:active {
  transform: translateY(1px);
}

.btn.primary {
  background: linear-gradient(120deg, #7c3aed, #06b6d4);
  color: #fff;
  box-shadow: 0 6px 22px rgba(124, 58, 237, 0.4);
}

.btn.primary:hover {
  box-shadow: 0 8px 28px rgba(124, 58, 237, 0.55);
}

/* =============== 完整时间线弹层 =============== */
.tl-modal {
  position: fixed;
  inset: 0;
  z-index: 80;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 24px;
  box-sizing: border-box;
  background: rgba(10, 6, 20, 0.68);
  backdrop-filter: blur(6px);
  animation: vr-modal-in 0.2s ease;
}

.tl-modal-panel {
  display: flex;
  flex-direction: column;
  width: 100%;
  max-width: 760px;
  max-height: 84vh;
  border-radius: 16px;
  background: linear-gradient(165deg, rgba(26, 16, 51, 0.96), rgba(15, 10, 30, 0.96));
  border: 1px solid rgba(124, 58, 237, 0.5);
  box-shadow: 0 8px 32px rgba(124, 58, 237, 0.25), 0 18px 48px rgba(0, 0, 0, 0.55);
  overflow: hidden;
  animation: vr-panel-in 0.26s cubic-bezier(0.22, 1, 0.36, 1);
}

.tl-modal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 20px;
  border-bottom: 1px solid rgba(124, 58, 237, 0.24);
}

.tl-modal-title {
  margin: 0;
  font-size: 17px;
  font-weight: 600;
  letter-spacing: 2px;
  color: #e9e4f5;
}

.tl-modal-close {
  width: 30px;
  height: 30px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  border: 1px solid rgba(124, 58, 237, 0.4);
  background: rgba(124, 58, 237, 0.1);
  color: #cbb8f5;
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
  transition: background 0.18s ease;
}

.tl-modal-close:hover {
  background: rgba(124, 58, 237, 0.26);
}

.tl-modal-body {
  flex: 1 1 auto;
  min-height: 0;
  padding: 16px 18px 20px;
  box-sizing: border-box;
  display: flex;
}

/* 时间线自身滚动，撑满弹层主体 */
.tl-modal-timeline {
  flex: 1 1 auto;
  min-height: 0;
  height: 100%;
}

@keyframes vr-modal-in {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes vr-panel-in {
  from {
    opacity: 0;
    transform: translateY(14px) scale(0.985);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

/* =============== 响应式 =============== */
@media (max-width: 1100px) {
  .play-shell {
    height: auto;
    min-height: 100vh;
    overflow: visible;
  }

  .play-body {
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: auto;
    overflow: visible;
  }

  .col-center {
    overflow: visible;
  }
}

@media (prefers-reduced-motion: reduce) {
  .spinner {
    animation-duration: 1.6s;
  }
  .opening-card,
  .tl-modal,
  .tl-modal-panel {
    animation: none;
  }
  .btn {
    transition: none;
  }
}
</style>
