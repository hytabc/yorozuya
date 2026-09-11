/**
 * 文案模板渲染（PRD §5.8）。
 */

/**
 * 渲染模板字符串。会消耗 rng。
 * @param {string} text
 * @param {object} st
 * @param {object} rng
 * @param {object} vocab
 * @returns {string}
 */
export function renderTemplate(text, st, rng, vocab) {
  if (!text) return text;

  // 1) 随机组 \{([^{}|]+\|[^{}]*)\}
  let out = text.replace(/\{([^{}|]+\|[^{}]*)\}/g, (_m, group) => {
    const parts = group.split('|');
    return parts[Math.floor(rng.next() * parts.length)];
  });

  // 2) 变量替换
  out = out.replace(/\{([^{}]+)\}/g, (full, key) => {
    switch (key) {
      case 'ta':
        return st.relation ? st.relation.name : '那个陌生人';
      case '我':
        return st.playerName || '我';
      case '世界':
        return rng.pick(vocab.worldPool);
      case '中文吧':
        return '中文吧';
      case '圈子':
        return st.circles && st.circles.length > 0 ? rng.pick(st.circles) : '这里';
      case '技能': {
        const skillDefs = vocab.skills || [];
        if (skillDefs.length === 0) return '';
        let best = skillDefs[0];
        let bestVal = (st.skills && st.skills[best.key]) || 0;
        for (let i = 1; i < skillDefs.length; i++) {
          const v = (st.skills && st.skills[skillDefs[i].key]) || 0;
          if (v > bestVal) { best = skillDefs[i]; bestVal = v; }
        }
        return best.name;
      }
      case 'N':
        return String(rng.randint(1, 99));
      // —— 结局总结模板用的数值变量（endings.json 的 summaryTemplate）——
      case 'hours':
      case 'friends':
      case 'mood':
      case 'fame':
      case 'avatars':
      case 'assets':
      case 'sugarCount':
      case 'breakupCount': {
        const v = st[key];
        return String(typeof v === 'number' ? Math.round(v) : 0);
      }
      default:
        return full;
    }
  });

  return out;
}