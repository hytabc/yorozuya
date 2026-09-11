/**
 * 纯函数格式化 / 档位计算工具。
 * 不依赖任何运行时状态，方便在组件与 store 中共用。
 */

/** 数值夹取（非法值回落到 min） */
export function clamp(value, min, max) {
  const n = Number(value);
  if (!Number.isFinite(n)) return min;
  return Math.min(max, Math.max(min, n));
}

function trimOne(v) {
  return String(Number(v.toFixed(1)));
}

/**
 * 千分位缩写：3200 → '3.2k'，1200000 → '1.2M'，950 → '950'
 */
export function formatNumber(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '0';
  const abs = Math.abs(n);
  const sign = n < 0 ? '-' : '';
  if (abs >= 1e6) return `${sign}${trimOne(abs / 1e6)}M`;
  if (abs >= 1e3) return `${sign}${trimOne(abs / 1e3)}k`;
  return `${sign}${Math.round(abs)}`;
}

/**
 * 通用档位查找：tiers 形如 [{min,max,name|key}]。
 */
export function tierOf(value, tiers) {
  const n = Number(value);
  if (!Array.isArray(tiers) || tiers.length === 0) return '';
  for (const t of tiers) {
    const min = t.min === undefined ? -Infinity : t.min;
    const max = t.max === undefined ? Infinity : t.max;
    if (n >= min && n <= max) return t.name || t.key || '';
  }
  return '';
}

export function moodTier(value, vocab) {
  return tierOf(value, vocab && vocab.moodTiers);
}

export function fameTier(value, vocab) {
  return tierOf(value, vocab && vocab.fameTiers);
}

export function skillTier(value, vocab) {
  return tierOf(value, vocab && vocab.skillTiers);
}

/**
 * 按小时数取阶段名（vocab.stages 用的是 minHours / maxHours 半开区间）。
 */
export function stageOf(hours, vocab) {
  const n = Number(hours) || 0;
  const stages = (vocab && vocab.stages) || [];
  for (const s of stages) {
    const min = s.minHours === undefined ? 0 : s.minHours;
    const max = s.maxHours === undefined ? Infinity : s.maxHours;
    if (n >= min && n < max) return s.key;
  }
  return stages.length ? stages[stages.length - 1].key : '';
}

/** 进度条百分比字符串 */
export function percent(value, max = 100) {
  return `${clamp((Number(value) || 0) / max * 100, 0, 100)}%`;
}

const SUGAR_STATES = ['暧昧', '砂糖'];
const BAD_STATES = ['矛盾', '结束', '低迷'];
const GOOD_STATES = ['稳定', '恢复'];

/**
 * 关系状态的语义色，用于侧栏徽章 / 边框。
 * @returns {'sugar'|'bad'|'good'|'plain'}
 */
export function relationTone(state) {
  const s = String(state || '');
  if (SUGAR_STATES.includes(s)) return 'sugar';
  if (BAD_STATES.includes(s)) return 'bad';
  if (GOOD_STATES.includes(s)) return 'good';
  return 'plain';
}

const RARITY_LABELS = {
  common: '常见',
  uncommon: '少见',
  rare: '稀有',
  legendary: '传说',
};

export function rarityLabel(rarity) {
  return RARITY_LABELS[rarity] || rarity || '';
}

/**
 * 找出数值最高的技能。
 * @returns {{key:string,name:string,value:number}}
 */
export function maxSkill(skills, vocab) {
  const list = (vocab && vocab.skills) || [];
  if (!list.length) return { key: '', name: '—', value: 0 };
  const vals = skills || {};
  let best = {
    key: list[0].key,
    name: list[0].name || list[0].key,
    value: Number(vals[list[0].key]) || 0,
  };
  for (const s of list) {
    const v = Number(vals[s.key]) || 0;
    if (v > best.value) best = { key: s.key, name: s.name || s.key, value: v };
  }
  return best;
}

/** 压缩空白并截断 */
export function shorten(text, max = 40) {
  const s = String(text == null ? '' : text).replace(/\s+/g, ' ').trim();
  if (s.length <= max) return s;
  return `${s.slice(0, max)}…`;
}

/** 取第一句话（用于分享卡片），过长再截断 */
export function firstSentence(text, max = 60) {
  const s = String(text == null ? '' : text).replace(/\s+/g, ' ').trim();
  if (!s) return '';
  const m = s.match(/^[^。！？!?]*[。！？!?]/);
  const out = m ? m[0] : s;
  if (out.length <= max) return out;
  return `${out.slice(0, max)}…`;
}

/** 小时数展示 */
export function formatHours(hours) {
  const n = Math.round(Number(hours) || 0);
  return `${n}h`;
}