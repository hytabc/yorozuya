<script setup>
/**
 * 结果弹层：结果文案 + 非零数值浮动。
 */
import { computed, watch, onBeforeUnmount } from 'vue';

const props = defineProps({
  result: { type: Object, default: null },
});

const emit = defineEmits(['close']);

const tier = computed(() => {
  const r = props.result;
  if (!r) return 'normal';
  return (r.outcome && r.outcome.tier) || (r.entry && r.entry.outcomeTier) || 'normal';
});

const outcomeText = computed(() => (props.result && props.result.outcomeText) || '');

const deltas = computed(() => {
  const arr = (props.result && props.result.deltas) || [];
  return arr
    .map((d) => ({ label: d && d.label, diff: Math.round(Number(d && d.diff) || 0) }))
    .filter((d) => d.diff !== 0);
});

function close() {
  emit('close');
}

// PRD §9.2：弹层停留 1.5s 或玩家点击后淡出
let timer = null;
watch(
  () => props.result,
  (r) => {
    if (timer) { clearTimeout(timer); timer = null; }
    if (r) timer = setTimeout(close, 1500);
  },
  { immediate: true },
);
onBeforeUnmount(() => { if (timer) clearTimeout(timer); });
</script>

<template>
  <div v-if="result" class="vr-result" :class="`tier-${tier}`" @click="close">
    <div class="result-card">
      <span v-if="tier === 'extreme'" class="tier-tag extreme">极端转折</span>
      <span v-else-if="tier === 'rare'" class="tier-tag rare">稀有结果</span>

      <p class="result-text">{{ outcomeText }}</p>

      <div v-if="deltas.length" class="result-deltas">
        <span
          v-for="(d, i) in deltas"
          :key="`${d.label}-${i}`"
          class="delta"
          :class="d.diff > 0 ? 'pos' : 'neg'"
          :style="{ animationDelay: `${i * 70}ms` }"
        >
          {{ d.diff > 0 ? '+' : '' }}{{ d.diff }} {{ d.label }}
        </span>
      </div>

      <p class="result-hint">点击任意处继续</p>
    </div>
  </div>
</template>

<style scoped>
.vr-result {
  position: fixed;
  inset: 0;
  z-index: 60;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 32px;
  box-sizing: border-box;
  background: rgba(10, 6, 20, 0.62);
  backdrop-filter: blur(4px);
  animation: overlay-in 0.22s ease;
}

.result-card {
  position: relative;
  width: 100%;
  max-width: 520px;
  padding: 26px 26px 20px;
  border-radius: 16px;
  background: linear-gradient(165deg, rgba(26, 16, 51, 0.96), rgba(15, 10, 30, 0.96));
  border: 1px solid rgba(124, 58, 237, 0.5);
  box-shadow: 0 8px 32px rgba(124, 58, 237, 0.25);
  animation: card-in 0.28s cubic-bezier(0.22, 1, 0.36, 1);
}

.tier-rare .result-card {
  border-color: rgba(6, 182, 212, 0.75);
  box-shadow: 0 0 28px rgba(6, 182, 212, 0.3), 0 8px 32px rgba(0, 0, 0, 0.5);
}

.tier-extreme .result-card {
  border-color: rgba(236, 72, 153, 0.85);
  animation: card-in 0.28s cubic-bezier(0.22, 1, 0.36, 1), extreme-glow 1.6s ease-in-out infinite;
}

.tier-tag {
  display: inline-block;
  margin-bottom: 12px;
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 12px;
  letter-spacing: 1px;
}

.tier-tag.rare {
  color: #a5f3fc;
  background: rgba(6, 182, 212, 0.16);
  border: 1px solid rgba(6, 182, 212, 0.6);
}

.tier-tag.extreme {
  color: #f9a8d4;
  background: rgba(236, 72, 153, 0.16);
  border: 1px solid rgba(236, 72, 153, 0.7);
}

.result-text {
  margin: 0 0 18px;
  font-size: 16px;
  line-height: 1.85;
  color: #e9e4f5;
  white-space: pre-wrap;
}

.result-deltas {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}

.delta {
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 13px;
  font-variant-numeric: tabular-nums;
  animation: delta-float 0.7s cubic-bezier(0.22, 1, 0.36, 1) both;
}

.delta.pos {
  color: #10b981;
  background: rgba(16, 185, 129, 0.12);
  border: 1px solid rgba(16, 185, 129, 0.4);
}

.delta.neg {
  color: #f43f5e;
  background: rgba(244, 63, 94, 0.12);
  border: 1px solid rgba(244, 63, 94, 0.4);
}

.result-hint {
  margin: 0;
  font-size: 12px;
  color: #6f648c;
  text-align: right;
}

@keyframes overlay-in {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes card-in {
  from {
    opacity: 0;
    transform: translateY(14px) scale(0.98);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

@keyframes delta-float {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes extreme-glow {
  0%, 100% {
    box-shadow: 0 0 22px rgba(236, 72, 153, 0.28), 0 8px 32px rgba(0, 0, 0, 0.5);
  }
  50% {
    box-shadow: 0 0 44px rgba(236, 72, 153, 0.55), 0 8px 32px rgba(0, 0, 0, 0.5);
  }
}

/* =============== 窄屏（≤900px）：近全屏浮层 =============== */
@media (max-width: 900px) {
  .vr-result {
    padding: 12px;
  }

  .result-card {
    max-width: 100%;
    padding: 20px 18px 16px;
    border-radius: 14px;
  }

  .result-text {
    font-size: 15px;
    line-height: 1.75;
    margin-bottom: 14px;
    overflow-wrap: anywhere;
  }

  .result-deltas {
    gap: 6px;
    margin-bottom: 12px;
  }

  .delta {
    font-size: 12px;
    padding: 3px 9px;
  }

  .result-hint {
    font-size: 11px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .vr-result,
  .result-card,
  .delta,
  .tier-extreme .result-card {
    animation: none;
  }
}
</style>