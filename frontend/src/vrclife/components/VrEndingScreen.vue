<script setup>
/**
 * 结局页：称号 / 描述 / 关键数值 / 雷达图 / 情感分析 / 成就 / 重开·分享·时间线。
 */
import { ref, computed } from 'vue';
import { useVrclifeStore } from '../store/vrclifeStore.js';
import VrRadarChart from './VrRadarChart.vue';
import VrShareCard from './VrShareCard.vue';
import VrMoodChart from './VrMoodChart.vue';
import { buildInsights, evaluateAchievements } from '../engine/insights.js';
import {
  clamp,
  fameTier,
  moodTier,
  maxSkill,
  skillTier,
  firstSentence,
  formatNumber,
  relationTone,
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

/** 关键数值：优先按结局自带的 keyStats 取项，缺省回落到固定六项 */
const STAT_ROWS = {
  hours: { label: '总时长', value: (s) => `${Math.round(s.hours || 0)}h` },
  friends: { label: '好友', value: (s) => String(Math.round(s.friends || 0)) },
  favor: { label: '好感度', value: (s) => String(Math.round(s.favor || 0)) },
  mood: { label: '心态', value: (s) => `${Math.round(s.mood || 0)} · ${moodTier(s.mood || 0, vocab.value)}` },
  fame: { label: '声望', value: (s) => `${Math.round(s.fame || 0)} · ${fameTier(s.fame || 0, vocab.value)}` },
  avatars: { label: '模型', value: (s) => String(Math.round(s.avatars || 0)) },
  assets: { label: '资产', value: (s) => formatNumber(s.assets || 0) },
  sugarCount: { label: '砂糖关系', value: (s) => String(s.sugarCount || 0) },
  breakupCount: { label: '关系破裂', value: (s) => String(s.breakupCount || 0) },
  'circle.count': { label: '圈子', value: (s) => String((s.circles || []).length) },
  'tag.count': { label: '标签', value: (s) => String((s.tags || []).length) },
  'skill.max': {
    label: '最高技能',
    value: () => `${bestSkill.value.name}（${bestSkill.value.value} · ${skillTier(bestSkill.value.value, vocab.value)}）`,
  },
};

const DEFAULT_STAT_KEYS = ['hours', 'friends', 'favor', 'sugarCount', 'skill.max', 'fame'];

const statRows = computed(() => {
  const s = st.value;
  const declared = Array.isArray(ending.value.keyStats)
    ? ending.value.keyStats.filter((k) => STAT_ROWS[k])
    : [];
  const keys = declared.length ? declared : DEFAULT_STAT_KEYS;
  return keys.map((k) => ({ label: STAT_ROWS[k].label, value: STAT_ROWS[k].value(s) }));
});

const shareStats = computed(() => ({
  hours: st.value.hours || 0,
  friends: st.value.friends || 0,
  sugarCount: st.value.sugarCount || 0,
  breakupCount: st.value.breakupCount || 0,
  fame: st.value.fame || 0,
}));

const shareSummary = computed(() => firstSentence(summary.value || desc.value, 46));

/* ---------- 情感分析 / 成就（纯函数计算，不额外持久化） ---------- */
const insights = computed(() => buildInsights(st.value, vocab.value, store.data));

const achResult = computed(() =>
  evaluateAchievements({
    st: st.value,
    ending: ending.value,
    insights: insights.value,
    vocab: vocab.value,
    data: store.data,
    meta: store.meta,
  }),
);

const inRun = computed(() => achResult.value.inRun);
const crossRun = computed(() => achResult.value.crossRun);
const earnedCount = computed(() => achResult.value.earnedIds.length);
const totalCount = computed(() => inRun.value.length + crossRun.value.length);
const inRunEarned = computed(() => inRun.value.filter((a) => a.earned));
const crossRunEarned = computed(() => crossRun.value.filter((a) => a.earned));
const freshIds = computed(
  () => new Set((store.endingAchievements && store.endingAchievements.newlyIds) || []),
);

function isFresh(id) {
  return freshIds.value.has(id);
}

const favorText = computed(() => {
  const v = insights.value.favor;
  return `开局 ${Math.round(v.start)} → 结束 ${Math.round(v.end)}｜峰值 ${Math.round(v.max.value)}`;
});

const moodText = computed(() => {
  const v = insights.value.mood;
  return `峰值 ${Math.round(v.max.value)}｜谷底 ${Math.round(v.min.value)}`;
});

/** 这一局牵过的所有关系（含已结束的） */
const relationList = computed(() => (insights.value.relation && insights.value.relation.all) || []);

const relationText = computed(() => {
  const list = relationList.value;
  if (!list.length) return '这一局没有留下关系';
  if (list.length === 1) {
    const r = insights.value.relation.final || list[0];
    return `${r.name}｜最终「${r.state || '朋友'}」｜变化 ${Math.max(0, insights.value.relation.changes.length - 1)} 次`;
  }
  return `同时牵过 ${list.length} 段关系`;
});

const tagText = computed(() => (insights.value.tags.length ? insights.value.tags.join(' · ') : '—'));
const circleText = computed(() => (insights.value.circles.length ? insights.value.circles.join('、') : '—'));
const pathText = computed(() => insights.value.paths.map((p) => p.label).join(' / '));

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

      <section v-if="insights.turns" class="insight">
        <h3 class="box-title">情感分析</h3>

        <div class="chart-row">
          <div class="chart-cell">
            <div class="chart-head">
              <span class="chart-name">好感度</span>
              <span class="chart-meta">{{ favorText }}</span>
            </div>
            <VrMoodChart :points="insights.favorSeries" color="#f472b6" />
          </div>
          <div class="chart-cell">
            <div class="chart-head">
              <span class="chart-name">心态</span>
              <span class="chart-meta">{{ moodText }}</span>
            </div>
            <VrMoodChart :points="insights.moodSeries" color="#22d3ee" />
          </div>
        </div>

        <p class="insight-summary">{{ insights.summary }}</p>

        <div class="peak-grid">
          <div class="peak-col">
            <h4 class="peak-title up">高光时刻</h4>
            <ul class="peak-list">
              <li v-for="h in insights.highs" :key="'hi-' + h.turn">
                <span class="peak-diff up">+{{ h.diff }}</span>
                <span class="peak-body">{{ h.eventTitle }} · {{ h.optionText }}</span>
              </li>
            </ul>
          </div>
          <div class="peak-col">
            <h4 class="peak-title down">低谷时刻</h4>
            <ul class="peak-list">
              <li v-for="l in insights.lows" :key="'lo-' + l.turn">
                <span class="peak-diff down">{{ l.diff }}</span>
                <span class="peak-body">{{ l.eventTitle }} · {{ l.optionText }}</span>
              </li>
            </ul>
          </div>
        </div>

        <div class="fact-grid">
          <div class="fact">
            <span class="fact-label">关系轨迹</span>
            <span class="fact-value">{{ relationText }}</span>
          </div>
          <div class="fact">
            <span class="fact-label">圈子</span>
            <span class="fact-value">{{ circleText }}</span>
          </div>
          <div class="fact">
            <span class="fact-label">社交标签</span>
            <span class="fact-value">{{ tagText }}</span>
          </div>
          <div v-if="insights.paths.length" class="fact">
            <span class="fact-label">路线倾向</span>
            <span class="fact-value">{{ pathText }}</span>
          </div>
        </div>

        <div v-if="relationList.length > 1" class="rel-chips">
          <span
            v-for="r in relationList"
            :key="r.id"
            class="rel-chip"
            :class="`tone-${relationTone(r.state)}`"
          >
            {{ r.name }} · {{ r.state }}
          </span>
        </div>
      </section>

      <section v-if="earnedCount" class="ach">
        <h3 class="box-title">成就<span class="ach-count">{{ earnedCount }} / {{ totalCount }}</span></h3>

        <template v-if="inRunEarned.length">
          <h4 class="ach-sub">本局</h4>
          <div class="ach-grid">
            <div
              v-for="a in inRunEarned"
              :key="a.def.id"
              class="ach-badge"
              :class="[a.def.tier, { fresh: isFresh(a.def.id) }]"
            >
              <span class="ach-icon">{{ a.def.icon }}</span>
              <span class="ach-name">{{ a.def.name }}</span>
              <span class="ach-desc">{{ a.def.desc }}</span>
            </div>
          </div>
        </template>

        <template v-if="crossRunEarned.length">
          <h4 class="ach-sub">生涯</h4>
          <div class="ach-grid">
            <div
              v-for="a in crossRunEarned"
              :key="a.def.id"
              class="ach-badge"
              :class="[a.def.tier, { fresh: isFresh(a.def.id) }]"
            >
              <span class="ach-icon">{{ a.def.icon }}</span>
              <span class="ach-name">{{ a.def.name }}</span>
              <span class="ach-desc">{{ a.def.desc }}</span>
            </div>
          </div>
        </template>
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

/* =============== 情感分析 =============== */
.insight {
  margin-bottom: 24px;
}

.chart-row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 14px;
}

.chart-cell {
  min-width: 0;
  padding: 10px 12px 6px;
  border-radius: 12px;
  background: rgba(124, 58, 237, 0.08);
  border: 1px solid rgba(124, 58, 237, 0.18);
}

.chart-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 4px;
}

.chart-name {
  font-size: 13px;
  color: #cbb8f5;
}

.chart-meta {
  font-size: 11px;
  color: #8b7fa8;
  font-variant-numeric: tabular-nums;
  overflow-wrap: anywhere;
}

.insight-summary {
  margin: 0 0 14px;
  padding: 12px 14px;
  border-radius: 10px;
  background: rgba(6, 182, 212, 0.08);
  border-left: 3px solid #22d3ee;
  font-size: 14px;
  line-height: 1.85;
  color: #cfe9f3;
  overflow-wrap: anywhere;
}

.peak-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  margin-bottom: 14px;
}

.peak-title {
  margin: 0 0 8px;
  font-size: 13px;
  font-weight: 600;
}

.peak-title.up {
  color: #34d399;
}

.peak-title.down {
  color: #fb7185;
}

.peak-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.peak-list li {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 7px 9px;
  border-radius: 9px;
  background: rgba(124, 58, 237, 0.08);
  font-size: 13px;
  line-height: 1.55;
  overflow-wrap: anywhere;
}

.peak-diff {
  flex: 0 0 auto;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.peak-diff.up {
  color: #34d399;
}

.peak-diff.down {
  color: #fb7185;
}

.peak-body {
  min-width: 0;
  color: #cbb8f5;
}

.fact-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px 14px;
}

.fact {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  min-width: 0;
  padding-bottom: 6px;
  border-bottom: 1px solid rgba(124, 58, 237, 0.16);
}

.fact-label {
  flex: 0 0 auto;
  font-size: 13px;
  color: #8b7fa8;
}

.fact-value {
  font-size: 13px;
  color: #e9e4f5;
  text-align: right;
  overflow-wrap: anywhere;
}

/* 结局页：多段关系的名字/状态标签 */
.rel-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}

.rel-chip {
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 12px;
  background: rgba(124, 58, 237, 0.12);
  border: 1px solid rgba(124, 58, 237, 0.35);
  color: #cbb8f5;
}

.rel-chip.tone-sugar {
  border-color: rgba(236, 72, 153, 0.5);
  background: rgba(236, 72, 153, 0.12);
}

.rel-chip.tone-bad {
  border-color: rgba(244, 63, 94, 0.45);
  background: rgba(244, 63, 94, 0.1);
}

.rel-chip.tone-good {
  border-color: rgba(16, 185, 129, 0.4);
  background: rgba(16, 185, 129, 0.1);
}

/* =============== 成就 =============== */
.ach {
  margin-bottom: 24px;
}

.ach-count {
  margin-left: 8px;
  color: var(--accent);
  font-variant-numeric: tabular-nums;
}

.ach-sub {
  margin: 0 0 8px;
  font-size: 12px;
  letter-spacing: 2px;
  color: #6f648c;
}

.ach-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 8px;
  margin-bottom: 14px;
}

.ach-badge {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  padding: 9px 10px;
  border-radius: 10px;
  border: 1px solid rgba(124, 58, 237, 0.45);
  background: rgba(124, 58, 237, 0.14);
}

.ach-badge.gold {
  border-color: rgba(245, 158, 11, 0.65);
  box-shadow: 0 0 14px rgba(245, 158, 11, 0.18);
}

.ach-badge.silver {
  border-color: rgba(148, 163, 184, 0.6);
}

.ach-badge.bronze {
  border-color: rgba(180, 120, 80, 0.6);
}

.ach-badge.fresh {
  animation: ach-pop 1.1s ease;
}

@keyframes ach-pop {
  0% {
    transform: scale(0.86);
  }
  45% {
    transform: scale(1.06);
    box-shadow: 0 0 22px rgba(244, 114, 182, 0.55);
  }
  100% {
    transform: scale(1);
  }
}

.ach-icon {
  font-size: 18px;
  line-height: 1;
}

.ach-name {
  font-size: 13px;
  color: #e9e4f5;
}

.ach-desc {
  font-size: 11px;
  line-height: 1.5;
  color: #8b7fa8;
}

@media (max-width: 900px) {
  .chart-row,
  .peak-grid {
    grid-template-columns: minmax(0, 1fr);
    gap: 10px;
  }

  .fact-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .ach-grid {
    grid-template-columns: repeat(auto-fill, minmax(118px, 1fr));
  }
}

@media (prefers-reduced-motion: reduce) {
  .ach-badge.fresh {
    animation: none;
  }
}
</style>