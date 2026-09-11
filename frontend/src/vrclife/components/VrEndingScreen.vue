<script setup>
/**
 * 结局页：称号 / 描述 / 关键数值 / 雷达图 / 关键选择回放 / 重开·分享·时间线。
 */
import { ref, computed } from 'vue';
import { useVrclifeStore } from '../store/vrclifeStore.js';
import VrRadarChart from './VrRadarChart.vue';
import VrShareCard from './VrShareCard.vue';
import {
  clamp,
  fameTier,
  maxSkill,
  skillTier,
  firstSentence,
  shorten,
} from '../utils/format.js';

const emit = defineEmits(['show-timeline']);
const store = useVrclifeStore();

const confirmRestart = ref(false);
const showShare = ref(false);

const ending = computed(() => store.ending || {});
const st = computed(() => store.gameState || {});
const vocab = computed(() => store.vocab || {});

const accent = computed(() => ending.value.color || '#7c3aed');
const title = computed(() => ending.value.title || '普通玩家');
const desc = computed(() => ending.value.desc || '');
const summary = computed(() => ending.value.summary || '');

const bestSkill = computed(() => maxSkill(st.value.skills || {}, vocab.value));

const radarLabels = ['社交', '技能', '声望', '情感', '心态', '投入'];

const radarValues = computed(() => {
  const s = st.value;
  return [
    clamp(s.friends || 0, 0, 100),
    clamp(bestSkill.value.value || 0, 0, 100),
    clamp(s.fame || 0, 0, 100),
    clamp((s.sugarCount || 0) * 20 + (s.breakupCount || 0) * 10, 0, 100),
    clamp(s.mood || 0, 0, 100),
    clamp((s.hours || 0) / 10, 0, 100),
  ];
});

const statRows = computed(() => {
  const s = st.value;
  return [
    { label: '总时长', value: `${Math.round(s.hours || 0)}h` },
    { label: '好友', value: String(Math.round(s.friends || 0)) },
    { label: '砂糖关系', value: String(s.sugarCount || 0) },
    { label: '关系破裂', value: String(s.breakupCount || 0) },
    {
      label: '最高技能',
      value: `${bestSkill.value.name}（${bestSkill.value.value} · ${skillTier(bestSkill.value.value, vocab.value)}）`,
    },
    {
      label: '声望档位',
      value: `${Math.round(s.fame || 0)} · ${fameTier(s.fame || 0, vocab.value)}`,
    },
  ];
});

const replay = computed(() => {
  const h = (st.value.history || []).filter((e) => e.isTurnPoint);
  const tail = h.slice(-8);
  return tail.map((e) => ({
    turn: e.turn,
    hours: e.hoursAfter,
    optionText: e.optionText,
    brief: shorten(e.outcomeText || '', 34),
  }));
});

const shareStats = computed(() => ({
  hours: st.value.hours || 0,
  friends: st.value.friends || 0,
  sugarCount: st.value.sugarCount || 0,
  breakupCount: st.value.breakupCount || 0,
  fame: st.value.fame || 0,
}));

const shareSummary = computed(() => firstSentence(summary.value || desc.value, 46));

function doRestart() {
  confirmRestart.value = false;
  store.restart();
}
</script>

<template>
  <div class="vr-ending" :style="{ '--accent': accent }">
    <div class="ending-card">
      <p class="ending-eyebrow">{{ ending.rarity === 'legendary' ? '传说结局' : '结局' }}</p>
      <h1 class="ending-title">{{ title }}</h1>
      <p v-if="desc" class="ending-desc">{{ desc }}</p>
      <p v-if="summary" class="ending-summary">{{ summary }}</p>

      <div class="ending-grid">
        <div class="stats-box">
          <h3 class="box-title">关键数值</h3>
          <dl class="stat-list">
            <div v-for="row in statRows" :key="row.label" class="stat-row">
              <dt>{{ row.label }}</dt>
              <dd>{{ row.value }}</dd>
            </div>
          </dl>
        </div>

        <div class="radar-box">
          <h3 class="box-title">能力雷达</h3>
          <VrRadarChart
            :values="radarValues"
            :labels="radarLabels"
            :size="248"
            :stroke-color="accent"
          />
        </div>
      </div>

      <section v-if="replay.length" class="replay">
        <h3 class="box-title">关键选择回放</h3>
        <ul class="replay-list">
          <li v-for="r in replay" :key="r.turn" class="replay-item">
            <span class="replay-hours">{{ r.hours }}h</span>
            <span class="replay-option">{{ r.optionText }}</span>
            <span class="replay-arrow">→</span>
            <span class="replay-brief">{{ r.brief }}</span>
          </li>
        </ul>
      </section>

      <div class="ending-actions">
        <button type="button" class="btn primary" @click="confirmRestart = true">重开一局</button>
        <button type="button" class="btn ghost" @click="showShare = !showShare">
          {{ showShare ? '收起分享卡片' : '分享卡片' }}
        </button>
        <button type="button" class="btn ghost" @click="emit('show-timeline')">查看完整时间线</button>
      </div>

      <div v-if="showShare" class="share-wrap">
        <VrShareCard
          :ending="ending"
          :stats="shareStats"
          :radar="radarValues"
          :labels="radarLabels"
          :seed="store.seedStr"
          :summary="shareSummary"
        />
      </div>

      <footer class="ending-footer">种子 {{ store.seedStr }}</footer>
    </div>

    <div v-if="confirmRestart" class="ending-confirm" @click.self="confirmRestart = false">
      <div class="confirm-box">
        <p>确定要重新开始吗？本局记录不会保留。</p>
        <div class="confirm-actions">
          <button type="button" class="btn ghost" @click="confirmRestart = false">取消</button>
          <button type="button" class="btn primary" @click="doRestart">确定</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.vr-ending {
  min-height: 100vh;
  min-height: 100dvh;
  display: flex;
  justify-content: center;
  padding: 48px 24px 64px;
  box-sizing: border-box;
}

.ending-card {
  width: 100%;
  max-width: 860px;
  padding: 36px 32px 28px;
  border-radius: 16px;
  background: linear-gradient(165deg, rgba(26, 16, 51, 0.82), rgba(15, 10, 30, 0.82));
  border: 1px solid color-mix(in srgb, var(--accent) 55%, transparent);
  box-shadow: 0 8px 32px rgba(124, 58, 237, 0.25);
  backdrop-filter: blur(14px);
}

.ending-eyebrow {
  margin: 0 0 10px;
  font-size: 13px;
  letter-spacing: 5px;
  color: var(--accent);
}

.ending-title {
  margin: 0 0 14px;
  font-size: 40px;
  font-weight: 700;
  line-height: 1.25;
  color: var(--accent);
  text-shadow: 0 0 26px color-mix(in srgb, var(--accent) 45%, transparent);
}

.ending-desc {
  margin: 0 0 12px;
  font-size: 16px;
  line-height: 1.85;
  color: #b9aede;
}

.ending-summary {
  margin: 0 0 28px;
  padding: 16px 18px;
  border-radius: 12px;
  background: rgba(124, 58, 237, 0.1);
  border-left: 3px solid var(--accent);
  font-size: 16px;
  line-height: 1.9;
  color: #e9e4f5;
  white-space: pre-wrap;
}

.ending-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 24px;
  margin-bottom: 24px;
}

.box-title {
  margin: 0 0 12px;
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 2px;
  color: #8b7fa8;
}

.stat-list {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.stat-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 7px;
  border-bottom: 1px solid rgba(124, 58, 237, 0.16);
}

.stat-row dt {
  font-size: 14px;
  color: #8b7fa8;
}

.stat-row dd {
  margin: 0;
  font-size: 15px;
  color: #e9e4f5;
  font-variant-numeric: tabular-nums;
  text-align: right;
  min-width: 0;
  overflow-wrap: anywhere;
}

.radar-box {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.replay {
  margin-bottom: 24px;
}

.replay-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.replay-item {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 8px;
  padding: 9px 12px;
  border-radius: 10px;
  background: rgba(124, 58, 237, 0.08);
  font-size: 14px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.replay-hours {
  color: #06b6d4;
  font-variant-numeric: tabular-nums;
}

.replay-option {
  color: #cbb8f5;
}

.replay-arrow {
  color: #6f648c;
}

.replay-brief {
  color: #8b7fa8;
  flex: 1 1 auto;
  min-width: 0;
}

.ending-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.btn {
  padding: 11px 22px;
  border-radius: 10px;
  border: 1px solid transparent;
  font-size: 15px;
  font-family: inherit;
  cursor: pointer;
  transition: background 0.18s ease, box-shadow 0.2s ease;
}

.btn.primary {
  background: linear-gradient(120deg, var(--accent), #7c3aed);
  color: #fff;
  box-shadow: 0 6px 22px color-mix(in srgb, var(--accent) 45%, transparent);
}

.btn.ghost {
  background: rgba(124, 58, 237, 0.1);
  border-color: rgba(124, 58, 237, 0.45);
  color: #cbb8f5;
}

.btn.ghost:hover {
  background: rgba(124, 58, 237, 0.22);
}

.share-wrap {
  margin-top: 24px;
  display: flex;
  justify-content: center;
}

.ending-footer {
  margin-top: 28px;
  padding-top: 14px;
  border-top: 1px solid rgba(124, 58, 237, 0.2);
  font-size: 12px;
  color: #6f648c;
  text-align: center;
  font-variant-numeric: tabular-nums;
}

.ending-confirm {
  position: fixed;
  inset: 0;
  z-index: 70;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  box-sizing: border-box;
  background: rgba(10, 6, 20, 0.66);
  backdrop-filter: blur(3px);
}

.confirm-box {
  width: 320px;
  max-width: 100%;
  padding: 22px;
  border-radius: 14px;
  background: rgba(22, 15, 42, 0.98);
  border: 1px solid rgba(236, 72, 153, 0.5);
  box-shadow: 0 12px 36px rgba(0, 0, 0, 0.6);
}

.confirm-box p {
  margin: 0 0 16px;
  font-size: 15px;
  line-height: 1.7;
  color: #e9e4f5;
}

.confirm-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

/* =============== 窄屏（≤900px） =============== */
@media (max-width: 900px) {
  .vr-ending {
    padding: 24px 12px 40px;
  }

  .ending-card {
    padding: 24px 16px 22px;
    border-radius: 14px;
  }

  .ending-title {
    font-size: 28px;
    line-height: 1.3;
  }

  .ending-desc {
    font-size: 15px;
    line-height: 1.8;
  }

  .ending-summary {
    font-size: 15px;
    line-height: 1.85;
    padding: 14px 14px;
    margin-bottom: 20px;
  }

  .ending-grid {
    grid-template-columns: minmax(0, 1fr);
    gap: 18px;
    margin-bottom: 20px;
  }

  /* 关键数值：2 列网格 */
  .stat-list {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px 12px;
  }

  .stat-row {
    flex-direction: column;
    align-items: flex-start;
    gap: 2px;
  }

  .stat-row dd {
    text-align: left;
    font-size: 14px;
  }

  .stat-row dt {
    font-size: 12px;
  }

  .radar-box {
    align-items: stretch;
  }

  .replay-item {
    font-size: 13px;
    padding: 8px 10px;
    gap: 6px;
  }

  .replay-brief {
    flex-basis: 100%;
  }

  .ending-actions {
    flex-direction: column;
    gap: 10px;
  }

  .ending-actions .btn {
    width: 100%;
    min-height: 46px;
  }

  .share-wrap {
    margin-top: 18px;
  }

  .confirm-actions {
    flex-direction: column-reverse;
  }

  .confirm-actions .btn {
    width: 100%;
    min-height: 44px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .btn {
    transition: none;
  }
}
</style>