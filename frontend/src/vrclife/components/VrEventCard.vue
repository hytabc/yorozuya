<script setup>
/**
 * 当前事件卡：标题 / 正文 / 2-4 个选项。
 */
import { computed } from 'vue';

const props = defineProps({
  current: { type: Object, default: null },
});

const emit = defineEmits(['choose']);

const cardKey = computed(() => {
  const c = props.current;
  if (!c || !c.event) return 'empty';
  const ids = (c.options || []).map((o) => o.id).join(',');
  return `${c.event.id}:${ids}`;
});

const isKeyEvent = computed(() => {
  const c = props.current;
  return !!(c && c.event && c.event.category === 'key');
});

function pick(opt) {
  if (!opt || !opt.available) return;
  emit('choose', opt.id);
}
</script>

<template>
  <div v-if="current" :key="cardKey" class="vr-event">
    <header class="evt-head">
      <h2 class="evt-title">{{ current.event.title }}</h2>
      <span v-if="isKeyEvent" class="evt-key">关键</span>
    </header>

    <p class="evt-text">{{ current.text }}</p>

    <div class="evt-options">
      <button
        v-for="(opt, i) in current.options"
        :key="opt.id"
        type="button"
        class="opt"
        :class="{ locked: !opt.available }"
        :disabled="!opt.available"
        @click="pick(opt)"
      >
        <span class="opt-num">{{ i + 1 }}</span>
        <span class="opt-text">{{ opt.text }}</span>
        <span v-if="!opt.available" class="opt-lock">
          🔒 {{ opt.lockedHint || '条件未满足' }}
        </span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.vr-event {
  padding: 20px 22px 22px;
  border-radius: 16px;
  background: linear-gradient(165deg, rgba(124, 58, 237, 0.14), rgba(26, 16, 51, 0.72));
  border: 1px solid rgba(124, 58, 237, 0.42);
  box-shadow: 0 8px 32px rgba(124, 58, 237, 0.25);
  backdrop-filter: blur(14px);
  animation: evt-in 0.36s ease;
}

.evt-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.evt-title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: #e9e4f5;
}

.evt-key {
  font-size: 11px;
  padding: 2px 9px;
  border-radius: 999px;
  background: rgba(6, 182, 212, 0.2);
  border: 1px solid rgba(6, 182, 212, 0.65);
  color: #a5f3fc;
}

.evt-text {
  margin: 0 0 18px;
  font-size: 16px;
  line-height: 1.8;
  color: #cfc6e8;
  white-space: pre-wrap;
}

.evt-options {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.opt {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 13px 16px;
  border-radius: 12px;
  border: 1px solid rgba(124, 58, 237, 0.42);
  background: rgba(124, 58, 237, 0.1);
  color: #e9e4f5;
  font-size: 15px;
  line-height: 1.6;
  font-family: inherit;
  text-align: left;
  cursor: pointer;
  transition: background 0.18s ease, border-color 0.18s ease, transform 0.15s ease;
}

.opt:hover:not(:disabled) {
  background: rgba(124, 58, 237, 0.26);
  border-color: #7c3aed;
  transform: translateX(2px);
}

.opt:active:not(:disabled) {
  transform: translateX(0);
}

.opt:disabled,
.opt.locked {
  cursor: not-allowed;
  opacity: 0.5;
  border-color: rgba(139, 127, 168, 0.28);
  background: rgba(139, 127, 168, 0.08);
  color: #8b7fa8;
}

.opt-num {
  flex: 0 0 auto;
  width: 22px;
  height: 22px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  font-size: 12px;
  color: #a5f3fc;
  background: rgba(6, 182, 212, 0.14);
  border: 1px solid rgba(6, 182, 212, 0.35);
}

.opt-text {
  flex: 1 1 auto;
}

.opt-lock {
  flex: 0 0 auto;
  font-size: 12px;
  color: #8b7fa8;
}

@keyframes evt-in {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@media (prefers-reduced-motion: reduce) {
  .vr-event {
    animation: none;
  }
  .opt {
    transition: none;
  }
}
</style>