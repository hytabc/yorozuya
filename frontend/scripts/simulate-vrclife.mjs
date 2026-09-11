#!/usr/bin/env node
/**
 * 1000 局无头模拟（对齐 simulate.py 的报表与验收）。
 *
 * 用法: node frontend/scripts/simulate-vrclife.mjs [局数] [--seed N] [--data 目录]
 *   --data 默认 vrclife/data（本体），DLC 验收用 --data vrclife/DLC1/build
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createGame, defaultChoicePolicy } from '../src/vrclife/engine/engine.js';
import { evaluateEnding } from '../src/vrclife/engine/ending.js';
import { stageOf } from '../src/vrclife/engine/pool.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND = path.resolve(__dirname, '..');
const REPO_ROOT = path.resolve(FRONTEND, '..');
const DATA_DIR_DEFAULT = path.join(REPO_ROOT, 'vrclife', 'data');

function loadData(dataDir) {
  const idx = JSON.parse(fs.readFileSync(path.join(dataDir, 'events.index.json'), 'utf-8'));
  const vocab = JSON.parse(fs.readFileSync(path.join(dataDir, 'vocab.json'), 'utf-8'));
  const endingsRaw = JSON.parse(fs.readFileSync(path.join(dataDir, 'endings.json'), 'utf-8'));
  const archetypesRaw = JSON.parse(fs.readFileSync(path.join(dataDir, 'archetypes.json'), 'utf-8'));
  return {
    events: idx.events || [],
    byId: idx.byId || {},
    vocab,
    endings: endingsRaw.endings || [],
    endingsRaw,
    archetypes: archetypesRaw.archetypes || [],
  };
}

function parseArgs(argv) {
  let n = 300;
  let seed0 = 1;
  let dataDir = DATA_DIR_DEFAULT;
  const args = argv.slice(2);
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--seed') {
      seed0 = parseInt(args[++i], 10);
    } else if (args[i] === '--data') {
      dataDir = path.resolve(REPO_ROOT, args[++i]);
    } else if (!args[i].startsWith('--')) {
      n = parseInt(args[i], 10);
    }
  }
  if (!Number.isFinite(n) || n <= 0) n = 300;
  if (!Number.isFinite(seed0)) seed0 = 1;
  return { n, seed0, dataDir };
}

function playOne(data, seed, stageStats) {
  const game = createGame({ data, seed, choicePolicy: null });
  let safety = 0;
  while (game.phase === 'playing' && safety < 10000) {
    const usable = game.current.options.filter((o) => o.available);
    if (usable.length === 0) {
      return { state: game.state, fired: game._fired, error: 'NO_OPTION', ending: null };
    }
    const chosen = defaultChoicePolicy(game.state, game.current.event, usable, game._rng);
    // 记录阶段统计（用回合开始前的 hours）
    const stageNow = stageOf(game.state.hours, data.vocab);
    const moodBefore = game.state.mood;
    const friendsBefore = game.state.friends;
    game.choose(chosen.id);
    const st = game.state;
    if (!stageStats[stageNow]) {
      stageStats[stageNow] = { events: 0, mood: [], friends: [], skillmax: [] };
    }
    const bucket = stageStats[stageNow];
    bucket.events += 1;
    bucket.mood.push(st.mood - moodBefore);
    bucket.friends.push(st.friends - friendsBefore);
    const skillVals = Object.values(st.skills);
    bucket.skillmax.push(skillVals.length ? Math.max(...skillVals) : 0);
    safety++;
  }
  return {
    state: game.state,
    fired: game._fired,
    error: game.error || (game.phase === 'ended' && !game.ending ? 'UNDEFINED' : null),
    ending: game.ending,
  };
}

function main() {
  const { n, seed0, dataDir } = parseArgs(process.argv);
  const data = loadData(dataDir);

  console.log(`运行 ${n} 局模拟…（数据：${path.relative(REPO_ROOT, dataDir)}）\n`);

  const hit = new Map();
  const endings = new Map();
  const errors = new Map();
  const eventsPerRun = [];
  const hoursPerRun = [];
  const favorEnd = [];
  const stageStats = {};
  let sugarLoops = 0;
  let illegalTotal = 0;
  const archUse = new Map();
  let lowRecovered = 0;
  let lowEntered = 0;
  let recoverEntered = 0;
  let multiSugar = 0;

  for (let i = 0; i < n; i++) {
    let r;
    try {
      r = playOne(data, seed0 + i, stageStats);
    } catch (e) {
      errors.set('THROW: ' + (e && e.message ? e.message : String(e)),
        (errors.get('THROW: ' + (e && e.message ? e.message : String(e))) || 0) + 1);
      continue;
    }
    const st = r.state;
    if (r.error) {
      errors.set(r.error, (errors.get(r.error) || 0) + 1);
      continue;
    }
    for (const eid of r.fired) hit.set(eid, (hit.get(eid) || 0) + 1);
    eventsPerRun.push(r.fired.length);
    hoursPerRun.push(st.hours);
    if (typeof st.favor === 'number') favorEnd.push(st.favor);
    archUse.set(st.arch.name, (archUse.get(st.arch.name) || 0) + 1);
    illegalTotal += st.illegal;

    const endId = evaluateEnding(st, data.vocab, data.endings);
    endings.set(endId, (endings.get(endId) || 0) + 1);

    if (st.sugarCount >= 2) multiSugar++;
    if (st.sawRecover) recoverEntered++;
    if (st.sugarCount >= 1 && st.breakupCount >= 1) sugarLoops++;
    if (st.sawLow) {
      lowEntered++;
      if (st.mood >= 40) lowRecovered++;
    }
  }

  const total = eventsPerRun.length;
  console.log('='.repeat(62));
  console.log('模拟结果');
  console.log('='.repeat(62));
  console.log(`\n成功完成局数  : ${total}/${n}`);
  if (errors.size > 0) {
    console.log(`异常          : ${JSON.stringify(Object.fromEntries(errors))}`);
  } else {
    console.log('异常          : 无 ✅');
  }
  const sumEv = eventsPerRun.reduce((a, b) => a + b, 0);
  const sumHr = hoursPerRun.reduce((a, b) => a + b, 0);
  const avgEv = sumEv / Math.max(1, total);
  console.log(`平均事件数/局 : ${avgEv.toFixed(1)}  (min ${Math.min(...eventsPerRun, 0)}, max ${Math.max(...eventsPerRun, 0)})`);
  console.log(`平均时长/局   : ${Math.round(sumHr / Math.max(1, total))}h  (min ${Math.min(...hoursPerRun, 0)}, max ${Math.max(...hoursPerRun, 0)})`);
  console.log(`非法状态转移  : ${illegalTotal}`);
  if (favorEnd.length) {
    const sumFav = favorEnd.reduce((a, b) => a + b, 0);
    console.log(`终局好感度    : 均值 ${(sumFav / favorEnd.length).toFixed(1)}  (min ${Math.min(...favorEnd).toFixed(0)}, max ${Math.max(...favorEnd).toFixed(0)})`);
  }

  console.log(`\n砂糖循环:`);
  console.log(`  至少 1 次砂糖并失恋 : ${sugarLoops}/${total} 局 (${(sugarLoops / Math.max(1, total) * 100).toFixed(1)}%)`);
  console.log(`  进入过低迷期        : ${lowEntered} 局，其中 mood 回升 ≥40 : ${lowRecovered} 局`);
  console.log(`  进入过恢复期        : ${recoverEntered} 局`);
  console.log(`  多次砂糖(≥2)        : ${multiSugar} 局 (${(multiSugar / Math.max(1, total) * 100).toFixed(1)}%)`);

  const firedIds = new Set(hit.keys());
  const dead = data.events.filter((e) => !firedIds.has(e.id)).map((e) => e.id);
  console.log(`\n事件触达:`);
  console.log(`  被触发过的事件 : ${firedIds.size}/${data.events.length}`);
  if (dead.length > 0) {
    console.log(`  ⚠️  未被触发(${dead.length}) : ${dead.slice(0, 25).join(', ')}`);
  } else {
    console.log('  ✅ 全部事件均被触发过（无死事件）');
  }

  const sortedHit = [...hit.entries()].sort((a, b) => b[1] - a[1]);
  console.log(`\n热点事件 Top10:`);
  for (const [eid, c] of sortedHit.slice(0, 10)) {
    console.log(`  ${eid.padEnd(16)} ${String(c).padStart(5)} 次`);
  }
  console.log(`\n冷门事件 Bottom10（已触发的）:`);
  for (const [eid, c] of sortedHit.slice().reverse().slice(0, 10)) {
    console.log(`  ${eid.padEnd(16)} ${String(c).padStart(5)} 次`);
  }

  console.log(`\n分阶段数值（每事件增量）:`);
  console.log(`  ${'阶段'.padEnd(10)} ${'事件数'.padStart(5)} ${'mood 均值'.padStart(9)} ${'mood 范围'.padStart(14)} ${'friends 均值'.padStart(11)} ${'技能上限'.padStart(10)}`);
  const stageNames = (data.vocab.stages || []).map((s) => s.key);
  for (const name of stageNames) {
    const s = stageStats[name];
    if (!s || !s.events) continue;
    const m = s.mood;
    const f = s.friends;
    const sk = s.skillmax;
    const moodAvg = m.reduce((a, b) => a + b, 0) / m.length;
    const moodMin = Math.min(...m);
    const moodMax = Math.max(...m);
    const friendAvg = f.reduce((a, b) => a + b, 0) / f.length;
    const skMin = Math.min(...sk);
    const skMax = Math.max(...sk);
    console.log(`  ${name.padEnd(10)} ${String(s.events).padStart(5)} ${(moodAvg >= 0 ? '+' : '') + moodAvg.toFixed(1).padStart(8)} ${((moodMin >= 0 ? '+' : '') + moodMin.toFixed(0) + ' ~ ' + (moodMax >= 0 ? '+' : '') + moodMax.toFixed(0)).padStart(14)} ${(friendAvg >= 0 ? '+' : '') + friendAvg.toFixed(1).padStart(11)} ${(skMin + '-' + skMax).padStart(10)}`);
  }

  const titles = new Map(data.endings.map((e) => [e.id, e.title || e.id]));
  const sortedEnd = [...endings.entries()].sort((a, b) => b[1] - a[1]);
  console.log(`\n结局分布:`);
  for (const [eid, c] of sortedEnd) {
    const title = titles.get(eid) || eid;
    console.log(`  ${title.padEnd(14)} ${String(c).padStart(4)} 局 (${(c / Math.max(1, total) * 100).toFixed(1).padStart(5)}%)`);
  }
  const unreachable = data.endings
    .filter((e) => !endings.has(e.id) && e.condition && Object.keys(e.condition).length > 0)
    .map((e) => e.id);
  if (unreachable.length > 0) {
    console.log(`  ⚠️  不可达结局(${unreachable.length}): ${unreachable.join(', ')}`);
  } else {
    console.log('  ✅ 全部结局均可达');
  }
  console.log();

  console.log('='.repeat(62));
  let ok = true;
  if (errors.size > 0) {
    console.log('❌ A. 存在运行时异常');
    ok = false;
  } else {
    console.log('✅ A. 无致命异常');
  }
  if (avgEv >= 30) {
    console.log(`✅ B. 平均事件数 ${avgEv.toFixed(1)} ≥ 30`);
  } else {
    console.log(`❌ B. 平均事件数 ${avgEv.toFixed(1)} < 30`);
    ok = false;
  }
  if (dead.length > 0) {
    console.log(`⚠️  D. 存在 ${dead.length} 个死事件`);
  } else {
    console.log('✅ D. 无死事件');
  }
  if (sugarLoops > 0) {
    console.log(`✅ E. 砂糖循环可完整走通（${sugarLoops} 局）`);
  } else {
    console.log('❌ E. 砂糖循环未能走通');
    ok = false;
  }
  if (illegalTotal === 0) {
    console.log('✅ H. 无数值越界 / 非法状态转移');
  } else {
    console.log(`⚠️  H. 非法状态转移 ${illegalTotal} 次`);
  }
  console.log('='.repeat(62));
  process.exit(ok ? 0 : 1);
}

main();