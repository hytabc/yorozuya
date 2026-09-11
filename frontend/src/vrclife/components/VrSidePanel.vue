<script setup>
/**
 * 左侧属性面板：心态/声望/好感度、资源数字、情感关系、技能、标签云。
 */
import { computed, ref, watch, onMounted } from 'vue';
import { useVrclifeStore } from '../store/vrclifeStore.js';
import {
  formatNumber,
  moodTier,
  fameTier,
  skillTier,
  relationTone,
  percent,
} from '../utils/format.js';

const store = useVrclifeStore();

const FALLBACK_STATE = {
  mood: 0,
  fame: 0,
  friends: 0,
  avatars: 0,
  assets: 0,
  skills: {},
  tags: [],
  relation: null,
};

const st = computed(() => store.gameState || FALLBACK_STATE);
const vocab = computed(() => store.vocab || {});

const moodText = computed(() => moodTier(st.value.mood, vocab.value));
const fameText = computed(() => fameTier(st.value.fame, vocab.value));

/* ---- DLC1: 好感度 ---- */
const favorTiers = computed(() => {
  const tiers = vocab.value.favorTiers;
  return Array.isArray(tiers) ? tiers : [];
});

// favor 不存在或 favorTiers 缺失时整块不渲染。
const favorAvailable = computed(() => {
  const v = st.value.favor;
  if (typeof v !== 'number' || !Number.isFinite(v)) return false;
  return favorTiers.value.length > 0;
});

const favorValue = computed(() => Math.round(Number(st.value.favor) || 0));

const favorText = computed(() => {
  const tiers = favorTiers.value;
  if (!tiers.length) return '';
  const v = Number(st.value.favor);
  if (!Number.isFinite(v)) return '';
  let hit = null;
  for (const t of tiers) {
    if (typeof t.min === 'number' && v < t.min) continue;
    if (typeof t.max === 'number' && v > t.max) continue;
    hit = t;
  }
  if (!hit) return '';
  const label = hit.key !== undefined ? hit.key : hit.label;
  return label === undefined || label === null ? '' : String(label);
});
/* ---------------------- */

const REL_DIMS = [
  { key: 'intimacy', label: '亲密', color: '#ec4899' },
  { key: 'trust', label: '信任', color: '#06b6d4' },
  { key: 'freshness', label: '新鲜', color: '#7c3aed' },
  { key: 'dependence', label: '依赖', color: '#f59e0b' },
  { key: 'realPressure', label: '压力', color: '#f43f5e' },
];

const relTone = computed(() => relationTone(st.value.relation && st.value.relation.state));

const relDims = computed(() => {
  const r = st.value.relation;
  if (!r) return [];
  return REL_DIMS.map((d) => ({
    ...d,
    value: Math.round(Number(r[d.key]) || 0),
  }));
});

const skillList = computed(() => {
  const list = vocab.value.skills || [];
  const vals = st.value.skills || {};
  return list.map((s) => {
    const v = Math.round(Number(vals[s.key]) || 0);
    return {
      key: s.key,
      name: s.name || s.key,
      value: v,
      tier: skillTier(v, vocab.value),
    };
  });
});

const coreTags = computed(() => vocab.value.coreTags || []);

function isCore(tag) {
  return coreTags.value.includes(tag);
}

/* ---- 新标签高亮闪烁 ---- */
const flashing = ref({});
let prevTags = [];

function flashTags(tags) {
  if (!tags.length) return;
  const next = { ...flashing.value };
  for (const t of tags) next[t] = true;
  flashing.value = next;
  for (const t of tags) {
    setTimeout(() => {
      const m = { ...flashing.value };
      delete m[t];
      flashing.value = m;
    }, 1400);
  }
}

watch(
  () => (st.value.tags || []).join('|'),
  () => {
    const now = st.value.tags || [];
    const added = now.filter((t) => !prevTags.includes(t));
    if (added.length) flashTags(added);
    prevTags = [...now];
  },
);

onMounted(() => {
  prevTags = [...(st.value.tags || [])];
});
</script>

<template>
  <aside class="vr-side">
    <section class="panel">
      <div class="stat-head">
        <span class="stat-name">心态</span>
        <span class="stat-num">{{ Math.round(st.mood) }}</span>
        <span class="stat-tier">{{ moodText }}</span>
      </div>
      <div class="bar">
        <div class="bar-fill mood" :style="{ width: percent(st.mood) }"></div>
      </div>

      <div class="stat-head">
        <span class="stat-name">声望</span>
        <span class="stat-num">{{ Math.round(st.fame) }}</span>
        <span class="stat-tier">{{ fameText }}</span>
      </div>
      <div class="bar">
        <div class="bar-fill fame" :style="{ width: percent(st.fame) }"></div>
      </div>

      <template v-if="favorAvailable">
        <div class="stat-head">
          <span class="stat-name">好感度</span>
          <span class="stat-num">{{ favorValue }}</span>
          <span class="stat-tier">{{ favorText }}</span>
        </div>
        <div class="bar">
          <div class="bar-fill favor" :style="{ width: percent(favorValue) }"></div>
        </div>
      </template>

      <div class="nums">
        <div class="num-item">
          <span class="num-label">好友</span>
          <b class="num-value">{{ formatNumber(st.friends) }}</b>
        </div>
        <div class="num-item">
          <span class="num-label">模型</span>
          <b class="num-value">{{ formatNumber(st.avatars) }}</b>
        </div>
        <div class="num-item">
          <span class="num-label">资产</span>
          <b class="num-value">{{ formatNumber(st.assets) }}</b>
        </div>
      </div>
    </section>

    <section class="panel">
      <h3 class="panel-title">情感</h3>
      <p v-if="!st.relation" class="empty-text">
        还没有固定的人。世界里的关系，都还只是擦肩而过。
      </p>
      <div v-else class="relation" :class="`tone-${relTone}`">
        <div class="rel-head">
          <span class="rel-name">{{ st.relation.name }}</span>
          <span class="rel-state">{{ st.relation.state }}</span>
        </div>
        <div v-for="d in relDims" :key="d.key" class="mini-row">
          <span class="mini-label">{{ d.label }}</span>
          <div class="mini-bar">
            <div class="mini-fill" :style="{ width: percent(d.value), background: d.color }"></div>
          </div>
          <span class="mini-value">{{ d.value }}</span>
        </div>
      </div>
    </section>

    <section class="panel">
      <h3 class="panel-title">技能</h3>
      <div v-for="s in skillList" :key="s.key" class="skill-row">
        <span class="skill-name">{{ s.name }}</span>
        <div class="skill-bar">
          <div class="skill-fill" :style="{ width: percent(s.value) }"></div>
        </div>
        <span class="skill-tier">{{ s.tier }}</span>
      </div>
    </section>

    <section class="panel">
      <h3 class="panel-title">标签</h3>
      <div v-if="!(st.tags || []).length" class="empty-text">暂无标签</div>
      <div v-else class="tags">
        <span
          v-for="t in st.tags"
          :key="t"
          class="tag"
          :class="{ core: isCore(t), flash: flashing[t] }"
        >{{ t }}</span>
      </div>
    </section>
  </aside>
</template>

<style scoped>
.vr-side {
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow-y: auto;
  padding-right: 4px;
}

.panel {
  padding: 16px;
  border-radius: 16px;
  background: rgba(26, 16, 51, 0.55);
  border: 1px solid rgba(124, 58, 237, 0.24);
  box-shadow: 0 8px 32px rgba(124, 58, 237, 0.25);
  backdrop-filter: blur(12px);
}

.panel-title {
  margin: 0 0 12px;
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 2px;
  color: #8b7fa8;
}

.stat-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 6px;
}

.stat-name {
  font-size: 14px;
  color: #b9aede;
}

.stat-num {
  font-size: 18px;
  font-weight: 700;
  color: #e9e4f5;
  font-variant-numeric: tabular-nums;
  margin-left: auto;
}

.stat-tier {
  font-size: 12px;
  color: #06b6d4;
  min-width: 52px;
  text-align: right;
}

.bar {
  height: 7px;
  border-radius: 999px;
  background: rgba(124, 58, 237, 0.16);
  overflow: hidden;
  margin-bottom: 14px;
}

.bar:last-child {
  margin-bottom: 0;
}

.bar-fill {
  height: 100%;
  border-radius: 999px;
  transition: width 0.55s cubic-bezier(0.22, 1, 0.36, 1);
}

.bar-fill.mood {
  background: linear-gradient(90deg, #7c3aed, #06b6d4);
}

.bar-fill.fame {
  background: linear-gradient(90deg, #06b6d4, #ec4899);
}

.bar-fill.favor {
  background: linear-gradient(90deg, #ec4899, #7c3aed);
}

.nums {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid rgba(124, 58, 237, 0.18);
}

.num-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.num-label {
  font-size: 12px;
  color: #8b7fa8;
}

.num-value {
  font-size: 17px;
  color: #e9e4f5;
  font-variant-numeric: tabular-nums;
}

.empty-text {
  margin: 0;
  font-size: 13px;
  line-height: 1.7;
  color: #8b7fa8;
}

.relation {
  padding: 12px;
  border-radius: 12px;
  background: rgba(124, 58, 237, 0.08);
  border: 1px solid rgba(124, 58, 237, 0.22);
}

.relation.tone-sugar {
  background: rgba(236, 72, 153, 0.1);
  border-color: rgba(236, 72, 153, 0.45);
  box-shadow: 0 0 18px rgba(236, 72, 153, 0.18);
}

.relation.tone-bad {
  background: rgba(244, 63, 94, 0.08);
  border-color: rgba(244, 63, 94, 0.4);
}

.relation.tone-good {
  background: rgba(16, 185, 129, 0.08);
  border-color: rgba(16, 185, 129, 0.35);
}

.rel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.rel-name {
  font-size: 16px;
  font-weight: 600;
  color: #e9e4f5;
}

.rel-state {
  font-size: 12px;
  padding: 2px 10px;
  border-radius: 999px;
  border: 1px solid rgba(124, 58, 237, 0.5);
  color: #cbb8f5;
}

.tone-sugar .rel-state {
  border-color: rgba(236, 72, 153, 0.7);
  color: #f9a8d4;
}

.tone-bad .rel-state {
  border-color: rgba(244, 63, 94, 0.6);
  color: #fda4af;
}

.tone-good .rel-state {
  border-color: rgba(16, 185, 129, 0.6);
  color: #6ee7b7;
}

.mini-row {
  display: grid;
  grid-template-columns: 32px 1fr 26px;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.mini-row:last-child {
  margin-bottom: 0;
}

.mini-label {
  font-size: 12px;
  color: #8b7fa8;
}

.mini-bar {
  height: 5px;
  border-radius: 999px;
  background: rgba(124, 58, 237, 0.16);
  overflow: hidden;
}

.mini-fill {
  height: 100%;
  border-radius: 999px;
  transition: width 0.5s ease;
}

.mini-value {
  font-size: 12px;
  color: #b9aede;
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.skill-row {
  display: grid;
  grid-template-columns: 44px 1fr 40px;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.skill-row:last-child {
  margin-bottom: 0;
}

.skill-name {
  font-size: 13px;
  color: #b9aede;
}

.skill-bar {
  height: 5px;
  border-radius: 999px;
  background: rgba(124, 58, 237, 0.16);
  overflow: hidden;
}

.skill-fill {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, #7c3aed, #06b6d4);
  transition: width 0.5s ease;
}

.skill-tier {
  font-size: 11px;
  color: #8b7fa8;
  text-align: right;
}

.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.tag {
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 12px;
  color: #a99cc7;
  background: rgba(124, 58, 237, 0.12);
  border: 1px solid rgba(124, 58, 237, 0.22);
  transition: background 0.3s ease, border-color 0.3s ease;
}

.tag.core {
  color: #e9d5ff;
  background: rgba(124, 58, 237, 0.28);
  border-color: rgba(124, 58, 237, 0.65);
}

.tag.flash {
  animation: tag-flash 1.4s ease;
}

@keyframes tag-flash {
  0% {
    background: rgba(6, 182, 212, 0.85);
    border-color: #06b6d4;
    color: #04222b;
    box-shadow: 0 0 16px rgba(6, 182, 212, 0.85);
  }
  100% {
    background: rgba(124, 58, 237, 0.12);
    border-color: rgba(124, 58, 237, 0.22);
  }
}

@media (prefers-reduced-motion: reduce) {
  .bar-fill,
  .mini-fill,
  .skill-fill {
    transition: none;
  }
  .tag.flash {
    animation: none;
  }
}
</style>