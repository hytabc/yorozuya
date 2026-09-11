<script setup>
/**
 * 中部时间线：渲染 state.history，默认只展示最近 20 条。
 */
import { ref, computed, watch, nextTick } from 'vue';
import { useVrclifeStore } from '../store/vrclifeStore.js';

const props = defineProps({
  forceExpand: { type: Boolean, default: false },
});

const store = useVrclifeStore();

const COLLAPSED_COUNT = 20;
const MAX_RENDER = 100;

const expanded = ref(false);
const scroller = ref(null);

const history = computed(() => (store.gameState && store.gameState.history) || []);
const showAll = computed(() => props.forceExpand || expanded.value);

const visible = computed(() => {
  const all = history.value;
  if (showAll.value) {
    return all.length > MAX_RENDER ? all.slice(all.length - MAX_RENDER) : all;
  }
  return all.slice(-COLLAPSED_COUNT);
});

function tierClass(entry) {
  const t = entry && entry.outcomeTier;
  if (t === 'extreme') return 'tier-extreme';
  if (t === 'rare') return 'tier-rare';
  return '';
}

function scrollToBottom() {
  const el = scroller.value;
  if (!el) return;
  const last = el.querySelector('.tl-item:last-child');
  if (last && typeof last.scrollIntoView === 'function') {
    last.scrollIntoView({ behavior: 'smooth', block: 'end' });
  } else {
    el.scrollTop = el.scrollHeight;
  }
}

watch(
  () => history.value.length,
  async () => {
    await nextTick();
    scrollToBottom();
  },
);
</script>

<template>
  <div ref="scroller" class="vr-timeline">
    <div v-if="!visible.length" class="tl-empty">
      时间线还是空的。做出你的第一个选择吧。
    </div>

    <div v-else class="tl-list">
      <article
        v-for="e in visible"
        :key="e.turn"
        class="tl-item"
        :class="[tierClass(e), { 'is-key': e.isKey }]"
      >
        <header class="tl-head">
          <span class="tl-turn">#{{ (e.turn || 0) + 1 }}</span>
          <span class="tl-hours">{{ e.hoursAtStart }}h → {{ e.hoursAfter }}h</span>
          <span class="tl-title">{{ e.eventTitle }}</span>
          <span v-if="e.isKey" class="tl-badge">关键</span>
        </header>
        <p class="tl-choice">你选了：<em>{{ e.optionText }}</em></p>
        <p class="tl-outcome">{{ e.outcomeText }}</p>
      </article>
    </div>

    <div v-if="!forceExpand && history.length > COLLAPSED_COUNT" class="tl-more">
      <button v-if="!expanded" type="button" @click="expanded = true">
        展开全部（共 {{ history.length }} 条）
      </button>
      <button v-else type="button" @click="expanded = false">收起</button>
    </div>
  </div>
</template>

<style scoped>
.vr-timeline {
  overflow-y: auto;
  padding-right: 6px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.tl-empty {
  padding: 28px 20px;
  border-radius: 16px;
  border: 1px dashed rgba(124, 58, 237, 0.35);
  color: #8b7fa8;
  font-size: 14px;
  text-align: center;
}

.tl-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.tl-item {
  padding: 12px 14px;
  border-radius: 14px;
  background: rgba(26, 16, 51, 0.5);
  border: 1px solid rgba(124, 58, 237, 0.2);
  border-left: 3px solid rgba(124, 58, 237, 0.45);
  animation: tl-in 0.32s ease;
}

.tl-item.tier-rare {
  border-left-color: #06b6d4;
  box-shadow: 0 0 14px rgba(6, 182, 212, 0.16);
}

.tl-item.tier-extreme {
  border-left-color: #ec4899;
  box-shadow: 0 0 20px rgba(236, 72, 153, 0.28);
}

.tl-head {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 6px;
}

.tl-turn {
  font-size: 12px;
  color: #6f648c;
  font-variant-numeric: tabular-nums;
}

.tl-hours {
  font-size: 12px;
  color: #06b6d4;
  font-variant-numeric: tabular-nums;
}

.tl-title {
  font-size: 15px;
  font-weight: 600;
  color: #e9e4f5;
}

.tl-badge {
  font-size: 11px;
  padding: 1px 8px;
  border-radius: 999px;
  background: rgba(124, 58, 237, 0.32);
  border: 1px solid rgba(124, 58, 237, 0.65);
  color: #ddd0ff;
}

.tl-choice {
  margin: 0 0 4px;
  font-size: 13px;
  line-height: 1.7;
  color: #8b7fa8;
}

.tl-choice em {
  font-style: normal;
  color: #cbb8f5;
}

.tl-outcome {
  margin: 0;
  font-size: 14px;
  line-height: 1.75;
  color: #b9aede;
}

.tl-more {
  display: flex;
  justify-content: center;
  padding: 4px 0 10px;
}

.tl-more button {
  padding: 7px 18px;
  border-radius: 999px;
  border: 1px solid rgba(124, 58, 237, 0.42);
  background: rgba(124, 58, 237, 0.12);
  color: #cbb8f5;
  font-size: 13px;
  font-family: inherit;
  cursor: pointer;
  transition: background 0.18s ease;
}

.tl-more button:hover {
  background: rgba(124, 58, 237, 0.25);
}

@keyframes tl-in {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@media (prefers-reduced-motion: reduce) {
  .tl-item {
    animation: none;
  }
}
</style>