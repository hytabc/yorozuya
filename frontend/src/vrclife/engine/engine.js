/**
 * GameEngine —— new_state / 回合流程 / 序列化。
 *
 * NOTE: 与 PRD §6.4 有出入，按 simulate.py 参考实现：
 *   step_hours 不乘出生 hourStepMod；不实现 applyArchetypeMod（出生权重修正）。
 */
import { createRng } from './rng.js';
import { match } from './conditions.js';
import { applyEffects } from './effects.js';
import { applyRelationOp, driftRelation } from './relation.js';
import { pickEvent, stageOf } from './pool.js';
import { stepHours } from './step.js';
import { evaluateEnding, canonicalHint } from './ending.js';
import { renderTemplate } from './template.js';

export const MAX_EVENTS_PER_RUN = 72;
export const MAX_TURNS = 400;
export const SPAWN_COOLDOWN_HOURS = 120;

/**
 * @param {object[]} events
 * @returns {{keyEvents:object[], eventPool:object[], pityPool:object[], keyIds:Set<string>}}
 */
function createPools(events) {
  const keyEvents = events.filter((e) => e.category === 'key');
  const eventPool = events.filter((e) => e.category !== 'key' && e.category !== 'chain');
  const pityPool = events.filter((e) => e.category === 'pity');
  const keyIds = new Set(keyEvents.map((e) => e.id));
  return { keyEvents, eventPool, pityPool, keyIds };
}

/**
 * @param {number|string} seed
 * @param {object} arch
 * @param {string} playerName
 * @param {object} vocab
 * @returns {object}
 */
function initState(seed, arch, playerName, vocab) {
  const skills = {};
  for (const s of vocab.skills || []) skills[s.key] = 0;

  const st = {
    seed,
    arch,
    playerName: playerName || '我',
    hours: 0,
    friends: 0,
    mood: 70,
    fame: 0,
    avatars: 1,
    assets: 0,
    sugarCount: 0,
    breakupCount: 0,
    skills,
    circles: [],
    tags: ['萌新'],
    flags: [],
    counters: {},
    relation: null,
    usedEvents: [],
    lastSeen: {},
    scheduled: [],
    recentTags: [],
    lastEvents: [],
    negStreak: 0,
    posStreak: 0,
    milestones: new Set(),
    history: [],
    sugarPath: new Set(),
    illegal: 0,
    illegalDetail: {},
    spawnBlockUntil: -1,
    sawLow: false,
    sawRecover: false,
    hints: {},
  };

  const init = arch.init || {};
  for (const k of Object.keys(init)) st[k] = init[k];
  const askills = arch.skills || {};
  for (const k of Object.keys(askills)) st.skills[k] = askills[k];
  st.tags = [...(arch.tags || ['萌新'])];
  st.flags = [...(((arch.flags || {}).add) || [])];
  return st;
}

function snapshotBefore(st) {
  return {
    mood: st.mood,
    friends: st.friends,
    fame: st.fame,
    avatars: st.avatars,
    assets: st.assets,
    skills: { ...st.skills },
    relation: st.relation ? { ...st.relation } : null,
    tags: [...st.tags],
    circles: [...st.circles],
  };
}

function computeDeltas(before, st, vocab) {
  const deltas = [];
  const push = (label, b, a) => {
    if (b !== a) deltas.push({ label, before: b, after: a, diff: a - b });
  };
  push('心态', before.mood, st.mood);
  push('好友', before.friends, st.friends);
  push('声望', before.fame, st.fame);
  push('模型', before.avatars, st.avatars);
  push('资产', before.assets, st.assets);
  for (const s of vocab.skills || []) {
    push(s.name, before.skills[s.key] || 0, st.skills[s.key] || 0);
  }
  const rb = before.relation;
  const ra = st.relation;
  if (rb && ra) {
    push('亲密度', rb.intimacy, ra.intimacy);
    push('信任', rb.trust, ra.trust);
    push('新鲜感', rb.freshness, ra.freshness);
    push('依赖度', rb.dependence, ra.dependence);
    push('现实压力', rb.realPressure, ra.realPressure);
  }
  return deltas;
}

function computeIsTurnPoint(before, st, ev, relationsBefore) {
  if (ev.category === 'key') return true;
  if (Math.abs(st.mood - before.mood) >= 15) return true;
  const rBefore = relationsBefore;
  const rAfter = st.relation;
  if (rAfter && rBefore && rAfter.state !== rBefore.state) return true;
  if (rAfter && !rBefore) return true;
  if (!rAfter && rBefore) return true;
  for (const t of st.tags) if (!before.tags.includes(t)) return true;
  for (const c of st.circles) if (!before.circles.includes(c)) return true;
  return false;
}

function assertRanges(st) {
  if (!(st.mood >= 0 && st.mood <= 100)) throw new Error(`mood 越界 ${st.mood}`);
  if (!(st.fame >= 0 && st.fame <= 100)) throw new Error(`fame 越界 ${st.fame}`);
  if (st.friends < 0) throw new Error('friends 为负');
  if (st.avatars < 0) throw new Error('avatars 为负');
  for (const k of Object.keys(st.skills)) {
    const v = st.skills[k];
    if (!(v >= 0 && v <= 100)) throw new Error(`技能 ${k} 越界 ${v}`);
  }
}

/**
 * @param {{
 *   rng: object,
 *   st: object,
 *   data: object,
 *   pools: object,
 *   fired: string[],
 *   phase: string,
 *   ending?: object|null,
 *   error?: string|null,
 *   choicePolicy?: Function|null
 * }} ctx
 * @returns {object}
 */
function makeGame(ctx) {
  const { rng, st, data, pools, fired } = ctx;
  const vocab = data.vocab;

  const game = {
    state: st,
    phase: ctx.phase || 'playing',
    current: null,
    ending: ctx.ending || null,
    error: ctx.error || null,
    _fired: fired,
    _choicePolicy: ctx.choicePolicy || null,
    _turnStartHours: ctx.turnStartHours || 0,
  };

  function checkEndConditions() {
    if (fired.length >= MAX_EVENTS_PER_RUN) return true;
    if (st.mood <= 0) return true;
    if (st.hours >= 5000) return true;
    return false;
  }

  function finalize() {
    const endId = evaluateEnding(st, vocab, data.endings);
    let def = data.endings.find((e) => e.id === endId);
    if (!def) def = data.endings.find((e) => e.id === 'end_default');
    if (!def) def = { id: 'end_default', title: '普通玩家' };
    let summary = '';
    try {
      summary = renderTemplate(def.summaryTemplate || '', st, rng, vocab);
    } catch (_e) {
      summary = '';
    }
    game.ending = { ...def, summary };
    game.phase = 'ended';
    game.current = null;
  }

  function startTurn() {
    game.current = null;
    if (checkEndConditions()) {
      finalize();
      return;
    }
    const ev = pickEvent(st, st.scheduled, {
      byId: data.byId,
      vocab,
      rng,
      eventPool: pools.eventPool,
      pityPool: pools.pityPool,
      keyEvents: pools.keyEvents,
      keyIds: pools.keyIds,
    });
    if (!ev) {
      game.phase = 'ended';
      game.error = 'EMPTY_POOL';
      return;
    }
    fired.push(ev.id);
    st.lastSeen[ev.id] = st.hours;
    game._turnStartHours = st.hours;

    const rendered = renderTemplate(ev.text || '', st, rng, vocab);
    const options = [];
    for (const o of ev.options) {
      const ok = match(o.condition, st, rng);
      if (ok) {
        options.push({ id: o.id, text: o.text, available: true, lockedHint: null });
      } else if (o.lockedHint) {
        options.push({ id: o.id, text: o.text, available: false, lockedHint: o.lockedHint });
      }
    }
    if (!options.some((o) => o.available)) {
      game.phase = 'ended';
      game.error = 'NO_OPTION';
      return;
    }
    game.current = { event: ev, text: rendered, options };
  }

  game._startTurn = startTurn;

  function choose(optionId) {
    if (game.phase !== 'playing' || !game.current) {
      throw new Error('没有进行中的回合');
    }
    const optView = game.current.options.find((o) => o.id === optionId);
    if (!optView) throw new Error(`未知选项 ${optionId}`);
    if (!optView.available) throw new Error(`选项不可用 ${optionId}`);

    const ev = game.current.event;
    const opt = ev.options.find((o) => o.id === optionId);

    const outs = opt.outcomes || [];
    let total = 0;
    for (const o of outs) total += o.weight;
    const x = rng.next() * total;
    let acc = 0;
    let chosen = outs[outs.length - 1];
    for (const o of outs) {
      acc += o.weight;
      if (x <= acc) { chosen = o; break; }
    }

    const before = snapshotBefore(st);
    const stageNow = stageOf(st.hours, vocab);

    applyEffects(st, chosen.effects);
    const fx = chosen.effects || {};
    applyRelationOp(st, fx.relationOp || chosen.relationOp, rng, vocab, null);

    const hint = chosen.endingHint || fx.endingHint;
    if (hint && hint.path) {
      const p = canonicalHint(hint.path, vocab);
      st.hints[p] = (st.hints[p] || 0) + (hint.score === undefined ? 1 : hint.score);
    }

    const negative = st.mood < before.mood;
    st.negStreak = negative ? st.negStreak + 1 : 0;
    st.posStreak = negative ? 0 : st.posStreak + 1;

    const tg = ev.tags || [];
    st.recentTags = [...tg, ...st.recentTags].slice(0, 3);
    st.lastEvents = [ev.id, ...st.lastEvents].slice(0, 5);

    if (ev.once) st.usedEvents.push(ev.id);

    for (const s of (chosen.schedule || [])) {
      const dh = s.delayHours === undefined ? [10, 60] : s.delayHours;
      const d = Array.isArray(dh) ? rng.randint(dh[0], dh[1]) : dh;
      st.scheduled.push({
        eventId: s.eventId,
        at: st.hours + d,
        chance: s.chance === undefined ? 1.0 : s.chance,
      });
    }

    st.hours += stepHours(st, rng, vocab);
    driftRelation(st, rng, st.scheduled);

    assertRanges(st);

    const outcomeText = renderTemplate(chosen.text || '', st, rng, vocab);
    const deltas = computeDeltas(before, st, vocab);
    const relationSnapshot = st.relation ? { ...st.relation } : null;
    const isKey = ev.category === 'key';
    const relBefore = before.relation;
    const isTurnPoint = computeIsTurnPoint(before, st, ev, relBefore);

    const entry = {
      turn: st.history.length,
      hoursAtStart: game._turnStartHours,
      hoursAfter: st.hours,
      eventId: ev.id,
      eventTitle: ev.title,
      renderedText: game.current.text,
      optionId,
      optionText: opt.text,
      outcomeText,
      outcomeTier: chosen.tier || 'normal',
      deltas,
      relationSnapshot,
      isKey,
      isTurnPoint,
      stage: stageNow,
      firedIndex: fired.length - 1,
    };
    st.history.push(entry);

    game.current = null;
    startTurn();

    return { outcome: chosen, outcomeText, deltas, entry };
  }

  game.choose = choose;

  game.quit = function () {
    if (game.phase !== 'playing') return;
    finalize();
  };

  game.serialize = function () {
    // 进行中的回合也要入档：事件已抽取、文案已渲染（rng 已消耗），
    // 恢复时必须原样还原而不是重新走 startTurn（否则 rng 序列分叉）。
    const cur = game.current
      ? {
          eventId: game.current.event.id,
          text: game.current.text,
          options: game.current.options.map((o) => ({ ...o })),
        }
      : null;
    return serializeState(st, rng, fired, game.phase, game.ending, game.error, cur, game._turnStartHours);
  };

  game._setChoicePolicy = function (fn) { game._choicePolicy = fn; };

  if (game.phase === 'playing') {
    // 恢复存档时若带有进行中的回合，直接还原，不再走 startTurn（避免重复消耗 rng）
    if (ctx.current) game.current = ctx.current;
    else startTurn();
  }
  return game;
}

function serializeState(st, rng, fired, phase, ending, error, current, turnStartHours) {
  return {
    seed: st.seed,
    arch: st.arch,
    playerName: st.playerName,
    hours: st.hours,
    friends: st.friends,
    mood: st.mood,
    fame: st.fame,
    avatars: st.avatars,
    assets: st.assets,
    sugarCount: st.sugarCount,
    breakupCount: st.breakupCount,
    skills: { ...st.skills },
    circles: [...st.circles],
    tags: [...st.tags],
    flags: [...st.flags],
    counters: { ...st.counters },
    relation: st.relation ? { ...st.relation } : null,
    usedEvents: [...st.usedEvents],
    lastSeen: { ...st.lastSeen },
    scheduled: st.scheduled.map((s) => ({ ...s })),
    recentTags: [...st.recentTags],
    lastEvents: [...st.lastEvents],
    negStreak: st.negStreak,
    posStreak: st.posStreak,
    milestones: [...st.milestones],
    history: st.history.map((h) => ({ ...h })),
    sugarPath: [...st.sugarPath],
    illegal: st.illegal,
    illegalDetail: { ...st.illegalDetail },
    spawnBlockUntil: st.spawnBlockUntil,
    sawLow: st.sawLow,
    sawRecover: st.sawRecover,
    hints: { ...st.hints },
    rngState: rng.getState(),
    fired: [...fired],
    current: current || null,
    turnStartHours: turnStartHours || 0,
    phase,
    ending: ending || null,
    error: error || null,
  };
}

function deserializeState(save) {
  const skills = { ...(save.skills || {}) };
  return {
    seed: save.seed,
    arch: save.arch,
    playerName: save.playerName || '我',
    hours: save.hours || 0,
    friends: save.friends || 0,
    mood: save.mood === undefined ? 70 : save.mood,
    fame: save.fame || 0,
    avatars: save.avatars === undefined ? 1 : save.avatars,
    assets: save.assets || 0,
    sugarCount: save.sugarCount || 0,
    breakupCount: save.breakupCount || 0,
    skills,
    circles: [...(save.circles || [])],
    tags: [...(save.tags || [])],
    flags: [...(save.flags || [])],
    counters: { ...(save.counters || {}) },
    relation: save.relation ? { ...save.relation } : null,
    usedEvents: [...(save.usedEvents || [])],
    lastSeen: { ...(save.lastSeen || {}) },
    scheduled: (save.scheduled || []).map((s) => ({ ...s })),
    recentTags: [...(save.recentTags || [])],
    lastEvents: [...(save.lastEvents || [])],
    negStreak: save.negStreak || 0,
    posStreak: save.posStreak || 0,
    milestones: new Set(save.milestones || []),
    history: (save.history || []).map((h) => ({ ...h })),
    sugarPath: new Set(save.sugarPath || []),
    illegal: save.illegal || 0,
    illegalDetail: { ...(save.illegalDetail || {}) },
    spawnBlockUntil: save.spawnBlockUntil === undefined ? -1 : save.spawnBlockUntil,
    sawLow: !!save.sawLow,
    sawRecover: !!save.sawRecover,
    hints: { ...(save.hints || {}) },
  };
}

/**
 * 默认选项策略：usable = 条件满足的选项（空则无条件选项），rng 均匀抽一。
 * @param {object} _state
 * @param {object} _event
 * @param {object[]} usableOptions
 * @param {object} rng
 * @returns {object}
 */
function defaultChoicePolicy(_state, _event, usableOptions, rng) {
  return usableOptions[Math.floor(rng.next() * usableOptions.length)];
}

/**
 * 创建游戏。
 * @param {{
 *   data: object,
 *   seed: string|number,
 *   playerName?: string,
 *   archetypeId?: string,
 *   choicePolicy?: Function
 * }} opts
 * @returns {object}
 */
export function createGame(opts) {
  const { data, seed, playerName, archetypeId, choicePolicy } = opts;
  const { events, vocab, archetypes } = data;
  const pools = createPools(events);
  const rng = createRng(seed);

  let arch;
  if (archetypeId) {
    arch = archetypes.find((a) => a.id === archetypeId);
    if (!arch) throw new Error(`未知 archetype: ${archetypeId}`);
  } else {
    arch = rng.weightedPick(archetypes, archetypes.map((a) => a.weight));
  }

  const st = initState(seed, arch, playerName, vocab);

  const game = makeGame({
    rng,
    st,
    data,
    pools,
    fired: [],
    phase: 'playing',
    choicePolicy: choicePolicy || null,
  });

  // 保存 _rng 供 fromSave / 序列化使用
  game._rng = rng;
  return game;
}

/**
 * 从存档恢复（含 rng 精确恢复）。
 * @param {string|object} saveJson
 * @param {object} data
 * @param {Function} [choicePolicy]
 * @returns {object}
 */
createGame.fromSave = function (saveJson, data, choicePolicy) {
  const save = typeof saveJson === 'string' ? JSON.parse(saveJson) : saveJson;
  const pools = createPools(data.events);
  const rng = createRng(0);
  rng.setState(save.rngState || 0);
  const st = deserializeState(save);

  // 还原进行中的回合；事件在数据中找不到时回退为重新 startTurn（数据已变更的兜底）
  let current = null;
  if (save.current && save.phase === 'playing') {
    const ev = (data.byId || {})[save.current.eventId];
    if (ev) {
      current = {
        event: ev,
        text: save.current.text,
        options: (save.current.options || []).map((o) => ({ ...o })),
      };
    }
  }

  const game = makeGame({
    rng,
    st,
    data,
    pools,
    fired: [...(save.fired || [])],
    phase: save.phase || 'playing',
    ending: save.ending || null,
    error: save.error || null,
    choicePolicy: choicePolicy || null,
    current,
    turnStartHours: save.turnStartHours || 0,
  });
  game._rng = rng;
  return game;
};

/**
 * 引擎内置默认策略，供外部调用模拟使用。
 */
export { defaultChoicePolicy };