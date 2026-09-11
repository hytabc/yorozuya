/**
 * 关系系统 —— new_relation / apply_relation_op / drift_relation 移植。
 */
import { INACTIVE_REL_STATES } from './conditions.js';

/** 来源：simulate.py drift_relation 中 realPressure > 60 时排入的连锁事件。 */
export const DRIFT_CHAIN_END = 'sugar_b_k04';
/** 来源：simulate.py drift_relation 中 freshness < 30 且状态砂糖时排入的连锁事件。 */
export const DRIFT_CHAIN_CONFLICT = 'sugar_b_k02';

const SPAWN_COOLDOWN_HOURS = 120;
const DIM_KEYS = ['intimacy', 'trust', 'freshness', 'dependence', 'realPressure'];

/**
 * 开一段新关系。
 * @param {object} st
 * @param {{pick: Function}} rng
 * @param {object} vocab
 * @param {string} [stateStr]
 * @returns {object}
 */
export function newRelation(st, rng, vocab, stateStr = '认识') {
  const relStates = vocab.relationStates || [];
  let s = stateStr;
  if (!relStates.includes(s)) s = '认识';
  st.relation = {
    name: rng.pick(vocab.nicknamePool),
    state: s,
    intimacy: 0,
    trust: 0,
    freshness: 90,
    dependence: 0,
    realPressure: 0,
    metAt: st.hours,
  };
  if (s === '低迷') st.sawLow = true;
  else if (s === '恢复') st.sawRecover = true;
  return st.relation;
}

/**
 * 应用 relationOp。
 * @param {object} st
 * @param {object|null|undefined} rop
 * @param {object} rng
 * @param {object} vocab
 * @param {Array} [eventsLog]
 */
export function applyRelationOp(st, rop, rng, vocab, eventsLog) {
  if (!rop) return;
  const t = rop.type;
  let r = st.relation;

  if (t === 'spawn') {
    // 分手冷却（SCHEMA §5.2）：刚失恋的一段时间内不会立刻开始下一段，
    // 除非该 spawn 显式声明 "force": true。
    if (st.hours < st.spawnBlockUntil && !rop.force) return;
    if (!r || INACTIVE_REL_STATES.includes(r.state)) {
      r = newRelation(st, rng, vocab, rop.state || '认识');
    }
  } else if (t === 'end') {
    if (r && !INACTIVE_REL_STATES.includes(r.state)) {
      r.state = '结束';
      st.spawnBlockUntil = st.hours + SPAWN_COOLDOWN_HOURS;
      if (eventsLog) eventsLog.push(['state', '结束']);
    }
    // 忽略数值键
    return;
  } else if (t === 'renew') {
    if (r) {
      r.freshness = 90;
      r.realPressure = 0;
    }
    return;
  } else if (t === 'setState' && rop.state) {
    // 上一段已经结束却要把关系设成活跃状态：这不是状态转移，而是开始新的一段。
    if (r && INACTIVE_REL_STATES.includes(r.state)
        && !INACTIVE_REL_STATES.includes(rop.state)) {
      if (st.hours < st.spawnBlockUntil && !rop.force) return;
      r = newRelation(st, rng, vocab, rop.state);
    }
  }

  if (!st.relation) return;
  r = st.relation;

  // 1) init* 绝对赋值
  for (const d of DIM_KEYS) {
    const k = 'init' + d[0].toUpperCase() + d.slice(1);
    if (Object.prototype.hasOwnProperty.call(rop, k)) {
      r[d] = Math.max(0, Math.min(100, rop[k]));
    }
  }
  // 2) 裸名增量
  for (const d of DIM_KEYS) {
    if (Object.prototype.hasOwnProperty.call(rop, d)) {
      r[d] = Math.max(0, Math.min(100, r[d] + rop[d]));
    }
  }

  // 3) 状态转移（校验合法转移）
  if (t === 'setState' && rop.state) {
    const target = rop.state;
    const legal = (vocab.relationStateFlow || {})[r.state] || [];
    if (legal.includes(target) || target === r.state) {
      r.state = target;
      if (target === '低迷') st.sawLow = true;
      else if (target === '恢复') st.sawRecover = true;
      if (eventsLog) eventsLog.push(['state', target]);
    } else {
      st.illegal += 1;
      const key = `${r.state}->${target}`;
      st.illegalDetail[key] = (st.illegalDetail[key] || 0) + 1;
      if (eventsLog) eventsLog.push(['illegal_state', key]);
    }
  }
}

/**
 * 关系漂移。仅在关系活跃时执行。
 * @param {object} st
 * @param {object} rng
 * @param {Array} scheduled
 */
export function driftRelation(st, rng, scheduled) {
  const r = st.relation;
  if (!r || INACTIVE_REL_STATES.includes(r.state)) return;

  r.freshness = Math.max(0, r.freshness - 2);
  if (st.recentTags.includes('sugar')) {
    r.intimacy = Math.min(100, r.intimacy + 1);
  } else {
    r.intimacy = Math.max(0, r.intimacy - 1);
  }
  if (r.state === '砂糖' || r.state === '稳定') {
    r.dependence = Math.min(100, r.dependence + 0.5);
  }
  r.realPressure = Math.max(0, Math.min(100, r.realPressure + rng.randint(-3, 4)));

  if (r.realPressure > 60 && rng.next() < 0.08) {
    scheduled.push({
      eventId: DRIFT_CHAIN_END,
      at: st.hours + rng.randint(0, 40),
      chance: 1.0,
    });
  }
  if (r.freshness < 30 && r.state === '砂糖' && rng.next() < 0.1) {
    scheduled.push({
      eventId: DRIFT_CHAIN_CONFLICT,
      at: st.hours + rng.randint(10, 60),
      chance: 0.8,
    });
  }
  if (r.state === '砂糖' || r.state === '稳定') st.sugarPath.add('sugar');
  if (r.state === '矛盾') st.sugarPath.add('conflict');
  if (r.state === '低迷') st.sugarPath.add('low');
}