/**
 * 事件池与打分 —— pick_event + score 移植（含导演系统规则）。
 */
import { match } from './conditions.js';

/**
 * 按 vocab.stages 的 [minHours, maxHours) 判定当前阶段，超出返回「传奇」。
 * @param {number} hours
 * @param {object} vocab
 * @returns {string}
 */
export function stageOf(hours, vocab) {
  const stages = vocab.stages || [];
  for (let i = 0; i < stages.length; i++) {
    const s = stages[i];
    if (hours >= s.minHours && hours < s.maxHours) return s.key;
  }
  return '传奇';
}

/**
 * 事件打分（simulate.py 的 score 逐项照抄）。
 * @param {object} e
 * @param {object} st
 * @param {object} rng
 * @param {object} vocab
 * @returns {number}
 */
export function score(e, st, rng, vocab) {
  let w = e.weight === undefined ? 10 : e.weight;
  if (e.stage === stageOf(st.hours, vocab)) w *= 1.5;
  else w *= 0.6;

  const tg = e.tags || [];
  const has = (t) => tg.includes(t);

  if (st.mood < 30 && has('正面')) w *= 0.7;
  if (st.mood < 30 && has('负面')) w *= 1.3;
  if (st.mood > 75 && has('负面')) w *= 0.7;
  if (st.fame > 60 && has('技能')) w *= 1.4;
  if (st.friends < 3 && has('社交')) w *= 0.6;

  // 导演：情绪回弹
  if (st.negStreak >= 3 && has('正面')) w *= 2.5;
  if (st.negStreak >= 3 && has('负面')) w *= 0.4;
  // 「好日子该过去了」——收到 1.4 以免成为趋势
  if (st.posStreak >= 4 && has('负面')) w *= 1.4;

  // 低迷期
  if (st.tags.includes('失恋')) {
    if (has('孤独') || has('回忆')) w *= 3.0;
    if (has('正面')) w *= 0.4;
  }

  // 防连发
  for (let i = 0; i < tg.length; i++) {
    if (st.recentTags.includes(tg[i])) { w *= 0.3; break; }
  }
  if (st.lastEvents.includes(e.id)) w *= 0.2;

  w *= 0.8 + rng.next() * 0.4;
  return w;
}

/**
 * 事件抽取主流程。
 * @param {object} st
 * @param {Array} sched 可变的 scheduled 数组
 * @param {{
 *   byId: object,
 *   vocab: object,
 *   rng: object,
 *   eventPool: object[],
 *   pityPool: object[],
 *   keyEvents: object[],
 *   keyIds: Set<string>
 * }} ctx
 * @returns {object|null}
 */
export function pickEvent(st, sched, ctx) {
  const { byId, vocab, rng, eventPool, pityPool, keyEvents, keyIds } = ctx;

  // 1) 到期的连锁事件
  const due = sched.filter((s) => s.at <= st.hours).sort((a, b) => a.at - b.at);
  for (const s of due) {
    const idx = sched.indexOf(s);
    if (idx >= 0) sched.splice(idx, 1);
    if (rng.next() < s.chance) {
      const ev = byId[s.eventId];
      if (ev && match(ev.condition, st, rng)) return ev;
    }
  }

  // 2) 关键事件 —— 但不允许连续两个 key
  const lastWasKey = st.lastEvents.length > 0 && keyIds.has(st.lastEvents[0]);
  if (!lastWasKey) {
    const inWin = [];
    const expired = [];
    for (const e of keyEvents) {
      if (st.usedEvents.includes(e.id)) continue;
      const hr = e.hoursRange;
      if (hr[0] > st.hours) continue;
      if (!match(e.condition, st, rng)) continue;
      if (st.hours <= hr[1]) inWin.push(e);
      else expired.push(e);
    }
    let keys = inWin;
    if (keys.length === 0 && expired.length > 0 && rng.next() < 0.45) {
      keys = expired;
    }
    if (keys.length > 0) {
      let base = Infinity;
      for (const e of keys) if (e.hoursRange[0] < base) base = e.hoursRange[0];
      const w = keys.map((e) => 1.0 / (1.0 + (e.hoursRange[0] - base) / 25.0));
      return rng.weightedPick(keys, w);
    }
  }

  // 3) 加权随机
  const pool = [];
  for (const e of eventPool) {
    if (e.once && st.usedEvents.includes(e.id)) continue;
    const cd = e.cooldown || 0;
    if (cd) {
      const seen = Object.prototype.hasOwnProperty.call(st.lastSeen, e.id)
        ? st.lastSeen[e.id] : -99999;
      if (st.hours - seen < cd) continue;
    }
    if (!match(e.condition, st, rng)) continue;
    const w = score(e, st, rng, vocab);
    if (w > 0) pool.push([e, w]);
  }
  if (pool.length > 0) {
    let total = 0;
    for (let i = 0; i < pool.length; i++) total += pool[i][1];
    const x = rng.next() * total;
    let acc = 0;
    for (let i = 0; i < pool.length; i++) {
      acc += pool[i][1];
      if (x <= acc) return pool[i][0];
    }
    return pool[pool.length - 1][0];
  }

  // 4) 保底
  const pity = [];
  const pityW = [];
  for (const e of pityPool) {
    if (match(e.condition, st, rng)) {
      pity.push(e);
      pityW.push(e.weight === undefined ? 1 : e.weight);
    }
  }
  if (pity.length > 0) return rng.weightedPick(pity, pityW);
  return null;
}