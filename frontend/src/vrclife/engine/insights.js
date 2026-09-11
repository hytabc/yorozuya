/**
 * 结局洞察（情感分析 / 成就评估）。
 *
 * 纯函数，只读 gameState + meta + data，不依赖 store 与组件，可直接单测。
 * 数据来源：history[].deltas（每回合各数值增减）、relationSnapshot、hints、meta。
 */

import { clamp } from '../utils/format.js';
import { IN_RUN_ACHIEVEMENTS, CROSS_RUN_ACHIEVEMENTS } from '../data/achievements.js';

const FAVOR_LABEL = '好感度';
const MOOD_LABEL = '心态';

function num(v) {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

function arr(v) {
  return Array.isArray(v) ? v : [];
}

function deltaDiff(entry, label) {
  const list = entry && entry.deltas;
  if (!Array.isArray(list)) return 0;
  for (const d of list) {
    if (d && d.label === label) return num(d.diff);
  }
  return 0;
}

/**
 * 由「终局值 + 每回合增量」反向重建曲线，老存档没有 deltas 时退化为一条水平线。
 * @returns {{x:number,y:number,turn:number,eventTitle:string}[]}
 */
export function buildSeries(history, finalValue, label) {
  const hs = arr(history).filter(Boolean);
  let sum = 0;
  for (const e of hs) sum += deltaDiff(e, label);
  let acc = num(finalValue) - sum;
  const points = [{ x: 0, y: clamp(acc, 0, 100), turn: -1, eventTitle: '开局' }];
  for (const e of hs) {
    acc += deltaDiff(e, label);
    const prevX = points[points.length - 1].x;
    const x = e.hoursAfter === undefined || e.hoursAfter === null ? prevX : num(e.hoursAfter);
    points.push({ x, y: clamp(acc, 0, 100), turn: num(e.turn), eventTitle: e.eventTitle || '' });
  }
  return points;
}

function peakOf(points, mode) {
  if (!points.length) return { value: 0, hours: 0, turn: -1, eventTitle: '' };
  let best = points[0];
  for (const p of points) {
    if (mode === 'max' ? p.y > best.y : p.y < best.y) best = p;
  }
  return { value: best.y, hours: best.x, turn: best.turn, eventTitle: best.eventTitle };
}

function pickExtremes(history, label, dir, count) {
  const hs = arr(history).filter(Boolean);
  const scored = [];
  for (const e of hs) {
    const diff = deltaDiff(e, label);
    if (diff !== 0) scored.push({ e, diff });
  }
  scored.sort((a, b) => (dir === 'up' ? b.diff - a.diff : a.diff - b.diff));
  return scored.slice(0, count).map((item) => ({
    turn: num(item.e.turn),
    hours: num(item.e.hoursAfter),
    eventTitle: item.e.eventTitle || '未命名事件',
    optionText: item.e.optionText || '',
    outcomeText: item.e.outcomeText || '',
    diff: Math.round(item.diff * 10) / 10,
  }));
}

function relationStats(history, st) {
  const hs = arr(history).filter(Boolean);
  const changes = [];
  let prev = null;
  for (const e of hs) {
    const snap = e.relationSnapshot;
    if (!snap) {
      if (prev) {
        changes.push({ from: prev, to: '结束', hours: num(e.hoursAfter) });
        prev = null;
      }
      continue;
    }
    const state = snap.state || '认识';
    if (prev === null) changes.push({ from: '陌生人', to: state, hours: num(e.hoursAfter) });
    else if (state !== prev) changes.push({ from: prev, to: state, hours: num(e.hoursAfter) });
    prev = state;
  }
  let lastSnap = null;
  for (let i = hs.length - 1; i >= 0; i -= 1) {
    if (hs[i].relationSnapshot) { lastSnap = hs[i].relationSnapshot; break; }
  }
  const final = (st && st.relation) || lastSnap || null;
  return { final, changes, hadRelation: !!final };
}

function pathLabel(path, endings) {
  const list = arr(endings);
  const exact = list.find((e) => e && e.id === 'end_' + path);
  if (exact && exact.title) return exact.title;
  const pref = list.find((e) => e && typeof e.id === 'string' && e.id.indexOf('end_' + path) === 0);
  return (pref && pref.title) || path;
}

function topPaths(st, endings) {
  const hints = (st && st.hints) || {};
  const list = Object.keys(hints)
    .map((key) => ({ key, score: num(hints[key]) }))
    .filter((x) => x.score > 0)
    .sort((a, b) => b.score - a.score);
  return list.slice(0, 3).map((x) => ({ key: x.key, label: pathLabel(x.key, endings), score: Math.round(x.score * 10) / 10 }));
}

function buildSummary(ins) {
  const parts = [];
  parts.push('你用 ' + Math.round(ins.hours) + ' 小时，把心态走成了一条从 ' + Math.round(ins.mood.start) + ' 到 ' + Math.round(ins.mood.end) + ' 的线（峰值 ' + Math.round(ins.mood.max.value) + '，谷底 ' + Math.round(ins.mood.min.value) + '）。');
  if (ins.mood.max.value - ins.mood.min.value >= 40) parts.push('这一局的情绪起伏很大，几乎不像同一个人走完的。');
  else if (ins.mood.max.value - ins.mood.min.value <= 10) parts.push('情绪几乎没有大起大落，你走得很稳。');
  parts.push('好感度最高到过 ' + Math.round(ins.favor.max.value) + '，最后停在 ' + Math.round(ins.favor.end) + '。');
  if (ins.relation && ins.relation.final && ins.relation.final.name) {
    const r = ins.relation.final;
    parts.push('唯一深交的是 ' + r.name + '，关系最终停在「' + (r.state || '朋友') + '」，中间换过 ' + Math.max(0, ins.relation.changes.length - 1) + ' 次状态。');
  } else {
    parts.push('一局下来，没有哪个名字留到了最后一回合。');
  }
  if (ins.circles.length) {
    const shown = ins.circles.slice(0, 4).join('、');
    parts.push('你混过 ' + ins.circles.length + ' 个圈子：' + shown + (ins.circles.length > 4 ? ' 等' : '') + '。');
  }
  if (ins.paths.length) parts.push('整局的走向，更像是奔着「' + ins.paths[0].label + '」去的。');
  return parts.join('');
}

/**
 * 汇总一局的“情感分析”数据。
 * @param {object} st gameState
 * @param {object} vocab
 * @param {object} data 数据包（endings / events / archetypes）
 */
export function buildInsights(st, vocab, data) {
  const state = st || {};
  const history = arr(state.history);
  const favorSeries = buildSeries(history, state.favor, FAVOR_LABEL);
  const moodSeries = buildSeries(history, state.mood, MOOD_LABEL);
  const endings = (data && data.endings) || [];

  const ins = {
    hours: num(state.hours),
    turns: history.length,
    favorSeries,
    moodSeries,
    favor: {
      start: favorSeries[0].y,
      end: num(state.favor),
      max: peakOf(favorSeries, 'max'),
      min: peakOf(favorSeries, 'min'),
    },
    mood: {
      start: moodSeries[0].y,
      end: num(state.mood),
      max: peakOf(moodSeries, 'max'),
      min: peakOf(moodSeries, 'min'),
    },
    relation: relationStats(history, state),
    highs: pickExtremes(history, MOOD_LABEL, 'up', 3),
    lows: pickExtremes(history, MOOD_LABEL, 'down', 3),
    favorHighs: pickExtremes(history, FAVOR_LABEL, 'up', 3),
    tags: arr(state.tags).slice(),
    circles: arr(state.circles).slice(),
    paths: topPaths(state, endings),
    summary: '',
  };
  ins.summary = buildSummary(ins);
  return ins;
}

/**
 * 评估全部成就。任何判定函数抛错都不影响整体（记未达成）。
 * @returns {{inRun:object[], crossRun:object[], earnedIds:string[]}}
 */
export function evaluateAchievements(ctx) {
  const safe = ctx || {};
  const base = {
    st: safe.st || {},
    ending: safe.ending || {},
    insights: safe.insights || {},
    vocab: safe.vocab || {},
    data: safe.data || {},
    meta: safe.meta || {},
  };

  const inRun = IN_RUN_ACHIEVEMENTS.map((def) => {
    let earned = false;
    try { earned = !!def.check(base); } catch (_e) { earned = false; }
    return { def, earned };
  });

  const crossRun = CROSS_RUN_ACHIEVEMENTS.map((def) => {
    let value = 0;
    let target = 1;
    try { value = num(def.value ? def.value(base) : 0); } catch (_e) { value = 0; }
    try { target = num(def.target ? def.target(base) : 1) || 1; } catch (_e) { target = 1; }
    return {
      def,
      value,
      target,
      earned: value >= target,
      ratio: clamp(value / target, 0, 1),
    };
  });

  const earnedIds = [];
  for (const a of inRun) if (a.earned) earnedIds.push(a.def.id);
  for (const a of crossRun) if (a.earned) earnedIds.push(a.def.id);

  return { inRun, crossRun, earnedIds };
}

export default { buildInsights, evaluateAchievements, buildSeries };
