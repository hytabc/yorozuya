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

function playFirstAvailable(game) {
  let steps = 0;
  while (game.phase === 'playing' && steps < 400) {
    const current = game.current;
    if (!current) break;
    const available = current.options.filter((o) => o.available);
    if (available.length === 0) break;
    game.choose(available[0].id);
    steps++;
  }
  return game;
}

test('存档迁移：旧档只有单个 relation 时自动包成 relations[]', () => {
  const data = loadData();
  const g = createGame({ data, seed: '834271' });
  playFirstAvailable(g);
  const save = JSON.parse(JSON.stringify(g.serialize()));
  if (!save.relation) {
    save.relation = { name: '小满', state: '砂糖', intimacy: 60, trust: 50, freshness: 70, dependence: 10, realPressure: 5, metAt: 12 };
  }
  const legacy = { ...save, relations: undefined, focusId: undefined };
  const g2 = createGame.fromSave(legacy, data);
  const st = g2.state;
  assert.ok(Array.isArray(st.relations), '迁移后应有 relations[]');
  assert.equal(st.relations.length, 1);
  assert.equal(st.relations[0].name, save.relation.name);
  assert.equal(st.relation, st.relations[0], '焦点应指向数组里的同一个对象');
  assert.equal(st.focusId, 1, '旧的单个关系补上 id=1');
});
test('种子复现：两局逐字节相等，中途存档续跑一致', () => {
  const data = loadData();
  const seed = '834271';

  // 第一局
  const g1 = createGame({ data, seed });
  playFirstAvailable(g1);
  const s1 = JSON.stringify(g1.serialize());

  // 第二局
  const g2 = createGame({ data, seed });
  playFirstAvailable(g2);
  const s2 = JSON.stringify(g2.serialize());

  assert.equal(s1, s2, '相同种子两局最终序列化应逐字节相等');

  // 第三局：中途第 20 回合存档续跑
  const g3 = createGame({ data, seed });
  let steps = 0;
  while (g3.phase === 'playing' && steps < 20) {
    const current = g3.current;
    if (!current) break;
    const available = current.options.filter((o) => o.available);
    if (available.length === 0) break;
    g3.choose(available[0].id);
    steps++;
  }
  const save = g3.serialize();
  const g3restored = createGame.fromSave(save, data);
  playFirstAvailable(g3restored);
  const s3 = JSON.stringify(g3restored.serialize());

  assert.equal(s3, s1, '中途存档续跑后最终序列化应与不间断局一致');

  // history 快照中 renderedText 不为空
  const finalState = JSON.parse(s1);
  assert.ok(finalState.history.length > 0, '应有历史记录');
  for (const h of finalState.history) {
    assert.ok(
      h.renderedText && h.renderedText.length > 0,
      `renderedText 不应为空: ${JSON.stringify(h)}`
    );
  }
});