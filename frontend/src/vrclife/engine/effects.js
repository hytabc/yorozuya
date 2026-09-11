/**
 * apply_effects + derive_tags 移植。
 */

/**
 * 自动标签（PRD §3.5）。
 * @param {object} st
 */
export function deriveTags(st) {
  const add = (t) => { if (!st.tags.includes(t)) st.tags.push(t); };
  const rm = (t) => { const i = st.tags.indexOf(t); if (i >= 0) st.tags.splice(i, 1); };

  if (st.hours >= 50) rm('萌新');
  if (st.friends < 5 && st.hours > 100) add('独行侠');
  if (st.mood <= 14) add('退坑边缘');
  else if (st.mood >= 30) rm('退坑边缘');
}

/**
 * 应用 effects DSL。
 * @param {object} st
 * @param {object|null|undefined} fx
 */
export function applyEffects(st, fx) {
  if (!fx) return;

  // 心情：正向收益在 70 以上递减（软上限）。
  let md = fx.mood || 0;
  if (md > 0) {
    md *= Math.min(1.0, Math.max(0.0, (100 - st.mood) / 30.0));
  } else if (md < -20) {
    md = -20; // 单事件情绪悬崖封顶
  }
  st.mood = Math.max(0, Math.min(100, st.mood + md));

  st.friends = Math.max(0, Math.min(999, st.friends + (fx.friends || 0)));
  st.fame = Math.max(0, Math.min(100, st.fame + (fx.fame || 0)));
  st.avatars = Math.max(0, st.avatars + (fx.avatars || 0));
  st.assets += fx.assets || 0; // 不夹取，可为负
  st.sugarCount += fx.sugarCount || 0;
  st.breakupCount += fx.breakupCount || 0;
  st.hours += fx.hoursBonus || 0;

  const skills = fx.skills;
  if (skills) {
    for (const k of Object.keys(skills)) {
      st.skills[k] = Math.max(0, Math.min(100, (st.skills[k] || 0) + skills[k]));
    }
  }
  const circles = fx.circles;
  if (circles) {
    for (const c of (circles.add || [])) {
      if (!st.circles.includes(c)) st.circles.push(c);
    }
    for (const c of (circles.remove || [])) {
      const i = st.circles.indexOf(c);
      if (i >= 0) st.circles.splice(i, 1);
    }
  }
  const tags = fx.tags;
  if (tags) {
    for (const t of (tags.add || [])) {
      if (!st.tags.includes(t)) st.tags.push(t);
    }
    for (const t of (tags.remove || [])) {
      const i = st.tags.indexOf(t);
      if (i >= 0) st.tags.splice(i, 1);
    }
  }
  const flags = fx.flags;
  if (flags) {
    for (const f of (flags.add || [])) {
      if (!st.flags.includes(f)) st.flags.push(f);
    }
    for (const f of (flags.remove || [])) {
      const i = st.flags.indexOf(f);
      if (i >= 0) st.flags.splice(i, 1);
    }
  }
  const counters = fx.counters;
  if (counters) {
    for (const k of Object.keys(counters)) {
      st.counters[k] = (st.counters[k] || 0) + counters[k];
    }
  }

  deriveTags(st);
}