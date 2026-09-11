import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { createGame } from '../src/vrclife/engine/engine.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const dataDir = join(__dirname, '../../vrclife/data');

function loadData() {
  const eventsIndex = JSON.parse(readFileSync(join(dataDir, 'events.index.json'), 'utf8'));
  const endingsData = JSON.parse(readFileSync(join(dataDir, 'endings.json'), 'utf8'));
  const archetypesData = JSON.parse(readFileSync(join(dataDir, 'archetypes.json'), 'utf8'));
  const vocab = JSON.parse(readFileSync(join(dataDir, 'vocab.json'), 'utf8'));
  return {
    events: eventsIndex.events,
    byId: eventsIndex.byId,
    vocab,
    endings: endingsData.endings,
    endingsRaw: endingsData,
    archetypes: archetypesData.archetypes,
  };
}

function playRandom(game) {
  let steps = 0;
  while (game.phase === 'playing' && steps < 400) {
    const current = game.current;
    if (!current) break;
    const available = current.options.filter((o) => o.available);
    if (available.length === 0) break;
    const idx = Math.floor(game._rng.next() * available.length);
    const opt = available[Math.min(idx, available.length - 1)];
    game.choose(opt.id);
    steps++;
  }
  return game;
}

test('50 局随机模拟：无错误、事件数 >= 30、无非法转移、至少一局砂糖→失恋', () => {
  const data = loadData();
  const results = [];

  for (let i = 0; i < 50; i++) {
    const seed = `sim-${i}`;
    const game = createGame({ data, seed });
    playRandom(game);

    assert.equal(game.error, null, `第 ${i} 局不应有 error`);
    assert.ok(
      game._fired.length >= 30,
      `第 ${i} 局事件数应 >= 30，实际 ${game._fired.length}`
    );
    assert.equal(game.state.illegal, 0, `第 ${i} 局不应有非法状态转移`);

    // 数值越界由内部 assertRanges 抛出，若未抛出则说明未越界
    results.push({
      sugarCount: game.state.sugarCount,
      breakupCount: game.state.breakupCount,
    });
  }

  const hasSugarBreakup = results.some(
    (r) => r.sugarCount >= 1 && r.breakupCount >= 1
  );
  assert.ok(hasSugarBreakup, '至少应有一局完成砂糖→失恋循环');
});