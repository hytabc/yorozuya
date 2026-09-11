<script setup>
/**
 * 顶部栏：小时数（滚动动画）/ 阶段 / 种子（点击复制）/ 菜单。
 */
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue';
import { useVrclifeStore } from '../store/vrclifeStore.js';

const emit = defineEmits(['show-timeline']);
const store = useVrclifeStore();

const menuOpen = ref(false);
const confirmAction = ref(null);
const copied = ref(false);
const displayHours = ref(0);

let rafId = 0;
let copyTimer = 0;

const hours = computed(() => (store.gameState ? (store.gameState.hours || 0) : 0));
const stage = computed(() => store.currentStage);
const seed = computed(() => store.seedStr);

function prefersReducedMotion() {
  try {
    return typeof window !== 'undefined'
      && typeof window.matchMedia === 'function'
      && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  } catch (_e) {
    return false;
  }
}

function animateHours(to) {
  if (prefersReducedMotion()) {
    displayHours.value = to;
    return;
  }
  const from = displayHours.value;
  if (from === to) return;
  const duration = 460;
  const t0 = performance.now();
  if (rafId) cancelAnimationFrame(rafId);
  const step = (now) => {
    const p = Math.min(1, (now - t0) / duration);
    const eased = 1 - Math.pow(1 - p, 3);
    displayHours.value = Math.round(from + (to - from) * eased);
    if (p < 1) rafId = requestAnimationFrame(step);
    else rafId = 0;
  };
  rafId = requestAnimationFrame(step);
}

watch(hours, (v) => animateHours(v), { immediate: true });

async function copySeed() {
  const text = String(seed.value || '');
  if (!text) return;
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text);
    } else {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
    }
    copied.value = true;
    clearTimeout(copyTimer);
    copyTimer = setTimeout(() => { copied.value = false; }, 1400);
  } catch (_e) {
    copied.value = false;
  }
}

function closeMenu() {
  menuOpen.value = false;
}

function toggleMenu() {
  menuOpen.value = !menuOpen.value;
}

function askConfirm(kind) {
  confirmAction.value = kind;
  menuOpen.value = false;
}

function cancelConfirm() {
  confirmAction.value = null;
}

function doConfirm() {
  const kind = confirmAction.value;
  confirmAction.value = null;
  if (kind === 'restart') store.restart();
  else if (kind === 'quit') store.quitGame();
}

function onTimeline() {
  menuOpen.value = false;
  emit('show-timeline');
}

onMounted(() => {
  document.addEventListener('click', closeMenu);
});

onBeforeUnmount(() => {
  document.removeEventListener('click', closeMenu);
  if (rafId) cancelAnimationFrame(rafId);
  clearTimeout(copyTimer);
});
</script>

<template>
  <header class="vr-topbar">
    <div class="tb-left">
      <div class="tb-hours">
        <span class="hours-num">{{ displayHours }}</span>
        <span class="hours-unit">h</span>
      </div>
      <div class="tb-stage">
        <span class="stage-dot"></span>
        <span>{{ stage }}</span>
      </div>
    </div>

    <div class="tb-right">
      <button class="seed-btn" type="button" title="点击复制种子" @click.stop="copySeed">
        <span class="seed-label">种子</span>
        <span class="seed-value">{{ seed }}</span>
        <span v-if="copied" class="seed-copied">已复制</span>
      </button>

      <div class="menu-wrap" @click.stop>
        <button class="menu-btn" type="button" @click="toggleMenu">☰ 菜单</button>
        <div v-if="menuOpen" class="menu-panel">
          <button type="button" @click="onTimeline">查看完整时间线</button>
          <button type="button" @click="askConfirm('restart')">重开一局</button>
          <button type="button" class="danger" @click="askConfirm('quit')">主动结束</button>
        </div>
      </div>
    </div>

    <div v-if="confirmAction" class="tb-confirm" @click.stop>
      <p class="confirm-text">
        {{ confirmAction === 'restart'
          ? '确定要放弃当前进度，重新开始吗？'
          : '确定要主动结束这一局吗？会立即结算结局。' }}
      </p>
      <div class="confirm-actions">
        <button type="button" class="ghost" @click="cancelConfirm">取消</button>
        <button type="button" class="primary" @click="doConfirm">确定</button>
      </div>
    </div>
  </header>
</template>

<style scoped>
.vr-topbar {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  min-height: 64px;
  padding: 0 24px;
  box-sizing: border-box;
  background: linear-gradient(180deg, rgba(26, 16, 51, 0.92), rgba(15, 10, 30, 0.72));
  border-bottom: 1px solid rgba(124, 58, 237, 0.28);
  backdrop-filter: blur(12px);
  z-index: 20;
}

.tb-left {
  display: flex;
  align-items: baseline;
  gap: 18px;
}

.tb-hours {
  display: flex;
  align-items: baseline;
  gap: 2px;
}

.hours-num {
  font-size: 28px;
  font-weight: 700;
  color: #e9e4f5;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.5px;
}

.hours-unit {
  font-size: 14px;
  color: #8b7fa8;
}

.tb-stage {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  color: #b9aede;
}

.stage-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #06b6d4;
  box-shadow: 0 0 10px rgba(6, 182, 212, 0.9);
}

.tb-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.seed-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 14px;
  border-radius: 999px;
  border: 1px solid rgba(124, 58, 237, 0.45);
  background: rgba(124, 58, 237, 0.1);
  color: #cbb8f5;
  font-size: 13px;
  font-family: inherit;
  cursor: pointer;
  transition: background 0.18s ease;
}

.seed-btn:hover {
  background: rgba(124, 58, 237, 0.22);
}

.seed-label {
  color: #8b7fa8;
}

.seed-value {
  font-variant-numeric: tabular-nums;
  letter-spacing: 1px;
}

.seed-copied {
  color: #10b981;
  animation: fade-in 0.2s ease;
}

.menu-wrap {
  position: relative;
}

.menu-btn {
  padding: 8px 16px;
  border-radius: 10px;
  border: 1px solid rgba(6, 182, 212, 0.4);
  background: rgba(6, 182, 212, 0.1);
  color: #a5f3fc;
  font-size: 14px;
  font-family: inherit;
  cursor: pointer;
  transition: background 0.18s ease;
}

.menu-btn:hover {
  background: rgba(6, 182, 212, 0.22);
}

.menu-panel {
  position: absolute;
  right: 0;
  top: calc(100% + 8px);
  min-width: 172px;
  padding: 6px;
  border-radius: 12px;
  background: rgba(22, 15, 42, 0.97);
  border: 1px solid rgba(124, 58, 237, 0.4);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.55);
  display: flex;
  flex-direction: column;
  gap: 2px;
  z-index: 30;
}

.menu-panel button {
  padding: 9px 12px;
  text-align: left;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: #d9d0f2;
  font-size: 14px;
  font-family: inherit;
  cursor: pointer;
  transition: background 0.15s ease;
}

.menu-panel button:hover {
  background: rgba(124, 58, 237, 0.25);
}

.menu-panel button.danger {
  color: #f9a8d4;
}

.menu-panel button.danger:hover {
  background: rgba(236, 72, 153, 0.22);
}

.tb-confirm {
  position: absolute;
  right: 24px;
  top: calc(100% + 10px);
  width: 300px;
  padding: 16px;
  border-radius: 14px;
  background: rgba(22, 15, 42, 0.98);
  border: 1px solid rgba(236, 72, 153, 0.45);
  box-shadow: 0 12px 36px rgba(0, 0, 0, 0.6);
  z-index: 40;
}

.confirm-text {
  margin: 0 0 14px;
  font-size: 14px;
  line-height: 1.7;
  color: #e9e4f5;
}

.confirm-actions {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
}

.confirm-actions button {
  padding: 7px 16px;
  border-radius: 9px;
  font-size: 14px;
  font-family: inherit;
  cursor: pointer;
  border: 1px solid transparent;
}

.confirm-actions .ghost {
  background: transparent;
  border-color: rgba(139, 127, 168, 0.45);
  color: #b9aede;
}

.confirm-actions .primary {
  background: linear-gradient(120deg, #ec4899, #7c3aed);
  color: #fff;
}

@keyframes fade-in {
  from { opacity: 0; }
  to { opacity: 1; }
}

@media (prefers-reduced-motion: reduce) {
  .seed-copied {
    animation: none;
  }
}
</style>