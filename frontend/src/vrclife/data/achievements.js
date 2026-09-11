/**
 * 成就定义（纯数据 + 判定函数）。
 *
 * - IN_RUN_ACHIEVEMENTS：本局结束时按最终状态判定，check(ctx) 返回布尔。
 * - CROSS_RUN_ACHIEVEMENTS：跨局累计，value(ctx)/target(ctx) 给出进度。
 * - ctx = { st, ending, insights, vocab, data, meta }
 *
 * 判定函数一律防御取值：老存档、测试桩缺字段时返回 false / 0，不得抛错。
 */

const INACTIVE_STATES = ['结束', '低迷', '恢复'];

function num(v) {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

/** 全部关系（含已结束）；兼容只有单个 relation 的旧状态。 */
function allRels(st) {
  if (!st) return [];
  return Array.isArray(st.relations) ? st.relations.filter(Boolean) : (st.relation ? [st.relation] : []);
}

/** 活跃关系（同时多段用）。 */
function activeRels(st) {
  return allRels(st).filter((r) => !INACTIVE_STATES.includes(r.state));
}

function arr(v) {
  return Array.isArray(v) ? v : [];
}

function maxSkill(st) {
  let m = 0;
  for (const v of Object.values((st && st.skills) || {})) {
    const n = num(v);
    if (n > m) m = n;
  }
  return m;
}

function countSkillsAtLeast(st, threshold) {
  let c = 0;
  for (const v of Object.values((st && st.skills) || {})) if (num(v) >= threshold) c += 1;
  return c;
}

function ctxList(ctx, key, fallback) {
  const n = arr(ctx && ctx.data && ctx.data[key]).length;
  return n || fallback;
}

/** 本局成就：按终局状态判定 */
export const IN_RUN_ACHIEVEMENTS = [
  { id: 'favor_80', name: '挚友', icon: '💗', tier: 'gold', desc: '好感度达到 80', check: (c) => num(c.st.favor) >= 80 },
  { id: 'favor_95', name: '手心的温度', icon: '💞', tier: 'gold', desc: '好感度达到 95', check: (c) => num(c.st.favor) >= 95 },
  { id: 'friends_50', name: '社交花蝴蝶', icon: '🦋', tier: 'silver', desc: '好友数达到 50', check: (c) => num(c.st.friends) >= 50 },
  { id: 'fame_90', name: '万人迷', icon: '⭐', tier: 'gold', desc: '声望达到 90', check: (c) => num(c.st.fame) >= 90 },
  { id: 'skill_90', name: '专精大师', icon: '🎯', tier: 'gold', desc: '任一技能达到 90', check: (c) => maxSkill(c.st) >= 90 },
  { id: 'skill_allround', name: '五项全能', icon: '🧩', tier: 'silver', desc: '5 项技能达到 60', check: (c) => countSkillsAtLeast(c.st, 60) >= 5 },
  { id: 'circles_5', name: '圈子浪人', icon: '🌀', tier: 'silver', desc: '混迹 5 个圈子', check: (c) => arr(c.st.circles).length >= 5 },
  { id: 'sugar_3', name: '砂糖成瘾', icon: '🍬', tier: 'silver', desc: '经历 3 段砂糖关系', check: (c) => num(c.st.sugarCount) >= 3 },
  { id: 'breakup_3', name: '心碎收藏家', icon: '💔', tier: 'bronze', desc: '经历 3 次关系破裂', check: (c) => num(c.st.breakupCount) >= 3 },
  { id: 'hours_1000', name: '长跑者', icon: '⏳', tier: 'gold', desc: '累计 1000 小时', check: (c) => num(c.st.hours) >= 1000 },
  { id: 'avatars_10', name: '模型收藏家', icon: '👗', tier: 'bronze', desc: '换过 10 个模型', check: (c) => num(c.st.avatars) >= 10 },
  { id: 'assets_100000', name: '资产自由', icon: '💰', tier: 'silver', desc: '资产达到 10 万', check: (c) => num(c.st.assets) >= 100000 },
  { id: 'lone_wolf', name: '独行侠', icon: '🌙', tier: 'bronze', desc: '200 小时以上，好友不超过 3 人', check: (c) => num(c.st.hours) >= 200 && num(c.st.friends) <= 3 },
  { id: 'relation_any', name: '名分已定', icon: '🤝', tier: 'silver', desc: '建立过一段关系', check: (c) => allRels(c.st).length > 0 },
  { id: 'relation_stable', name: '稳定关系', icon: '🏡', tier: 'gold', desc: '把一段关系走到「稳定」', check: (c) => allRels(c.st).some((r) => r.state === '稳定') },
  { id: 'parallel_line', name: '两条线', icon: '🎭', tier: 'silver', desc: '同时维系 2 段关系', check: (c) => activeRels(c.st).length >= 2 },
  { id: 'parallel_sugar', name: '两边都是真的', icon: '💞', tier: 'gold', desc: '同时维持 2 段砂糖关系', check: (c) => activeRels(c.st).filter((r) => r.state === '砂糖').length >= 2 },
  { id: 'parallel_three', name: '三线并行', icon: '🕸️', tier: 'gold', desc: '同时维持 3 段活跃关系', check: (c) => activeRels(c.st).length >= 3 },
  { id: 'rebound', name: '触底反弹', icon: '🌈', tier: 'silver', desc: '心态跌破 15 后又回到 60 以上', check: (c) => num(c.insights && c.insights.mood && c.insights.mood.min && c.insights.mood.min.value) <= 15 && num(c.st.mood) >= 60 },
  { id: 'rare_ending', name: '难得一见', icon: '🏅', tier: 'gold', desc: '达成一个稀有结局', check: (c) => c.ending.rarity === 'rare' },
  { id: 'burnout_ending', name: '燃尽', icon: '🕯️', tier: 'bronze', desc: '达成结局「燃尽」', check: (c) => c.ending.id === 'end_burnout' },
];

/** 跨局成就：跨存档累计（meta） */
export const CROSS_RUN_ACHIEVEMENTS = [
  { id: 'first_run', name: '初次下场', icon: '🌱', tier: 'bronze', desc: '完成第一局', value: (c) => num(c.meta.playCount), target: () => 1 },
  { id: 'runs_10', name: '十局老手', icon: '🎮', tier: 'silver', desc: '完成 10 局', value: (c) => num(c.meta.playCount), target: () => 10 },
  { id: 'endings_5', name: '结局见闻', icon: '📖', tier: 'bronze', desc: '解锁 5 个结局', value: (c) => arr(c.meta.unlockedEndings).length, target: () => 5 },
  { id: 'endings_10', name: '结局收藏', icon: '📚', tier: 'silver', desc: '解锁 10 个结局', value: (c) => arr(c.meta.unlockedEndings).length, target: () => 10 },
  { id: 'endings_all', name: '结局全收集', icon: '🏆', tier: 'gold', desc: '解锁全部结局', value: (c) => arr(c.meta.unlockedEndings).length, target: (c) => ctxList(c, 'endings', 23) },
  { id: 'events_100', name: '见闻者', icon: '👀', tier: 'bronze', desc: '见过 100 个事件', value: (c) => arr(c.meta.seenEvents).length, target: () => 100 },
  { id: 'events_all', name: '活字典', icon: '🗂️', tier: 'gold', desc: '见过全部事件', value: (c) => arr(c.meta.seenEvents).length, target: (c) => ctxList(c, 'events', 355) },
  { id: 'archetypes_all', name: '全出生体验', icon: '🎭', tier: 'gold', desc: '体验全部出生', value: (c) => arr(c.meta.unlockedArchetypes).length, target: (c) => ctxList(c, 'archetypes', 14) },
];

export default { IN_RUN_ACHIEVEMENTS, CROSS_RUN_ACHIEVEMENTS };
