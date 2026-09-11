/**
 * 结局判定 —— evaluate_ending + eval_score 表达式解析器移植。
 */

/**
 * endingHint.path 的别名规范化（vocab.endingPathAliases）。
 * @param {string} path
 * @param {object} vocab
 * @returns {string}
 */
export function canonicalHint(path, vocab) {
  const aliases = (vocab && vocab.endingPathAliases) || {};
  const seen = new Set();
  let p = path;
  while (Object.prototype.hasOwnProperty.call(aliases, p) && !seen.has(p)) {
    seen.add(p);
    p = aliases[p];
  }
  return p;
}

const TOKEN_RE = /\s*(?:(\d+\.?\d*)|([A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*)|(<=|>=|==|!=|&&|\|\||[-+*/()<>?:]))/y;

/**
 * @param {string} expr
 * @returns {string[]}
 */
function tokenize(expr) {
  const out = [];
  let pos = 0;
  while (pos < expr.length) {
    TOKEN_RE.lastIndex = pos;
    const m = TOKEN_RE.exec(expr);
    if (!m || m.index !== pos) {
      if (expr.slice(pos).trim() === '') break;
      throw new Error(`无法解析: ${JSON.stringify(expr.slice(pos, pos + 20))}`);
    }
    out.push(m[1] || m[2] || m[3]);
    pos = TOKEN_RE.lastIndex;
  }
  return out;
}

const INACTIVE_STATES = ['结束', '低迷', '恢复'];

/** 活跃关系列表；兼容只有单个 relation 的旧状态。 */
function activeRelList(st) {
  const list = Array.isArray(st.relations) ? st.relations : (st.relation ? [st.relation] : []);
  return list.filter((r) => r && !INACTIVE_STATES.includes(r.state));
}

function varsFor(st) {
  let maxSkill = 0;
  for (const v of Object.values(st.skills || {})) if (v > maxSkill) maxSkill = v;
  const rels = activeRelList(st);
  return {
    hours: st.hours,
    friends: st.friends,
    mood: st.mood,
    fame: st.fame,
    avatars: st.avatars,
    assets: st.assets,
    sugarCount: st.sugarCount,
    breakupCount: st.breakupCount,
    favor: st.favor,
    'skill.max': maxSkill,
    'circle.count': (st.circles || []).length,
    'tag.count': (st.tags || []).length,
    'relation.count': rels.length,
    'sugar.relation.count': rels.filter((r) => r.state === '砂糖').length,
  };
}

/**
 * 白名单表达式求值。
 * @param {string|undefined} expr
 * @param {object} st
 * @param {object} vocab
 * @returns {number}
 */
export function evalScore(expr, st, vocab) {
  if (!expr) return 0;
  const tokens = tokenize(expr);
  let pos = 0;
  const peek = () => (pos < tokens.length ? tokens[pos] : null);
  const take = () => tokens[pos++];

  function value(tok) {
    if (/^\d+\.?\d*$/.test(tok)) return parseFloat(tok);
    if (tok.startsWith('skill.')) {
      const k = tok.slice(6);
      const v = st.skills ? st.skills[k] : 0;
      return v === undefined ? 0 : v;
    }
    if (tok.startsWith('hint.')) {
      const p = canonicalHint(tok.slice(5), vocab);
      const v = st.hints ? st.hints[p] : 0;
      return v === undefined ? 0 : v;
    }
    if (tok.startsWith('hasFlag.')) {
      return (st.flags || []).includes(tok.slice(8)) ? 1 : 0;
    }
    const vars = varsFor(st);
    const v = vars[tok];
    return v === undefined ? 0 : v;
  }

  function atom() {
    const t = take();
    if (t === '(') {
      const v = tern();
      if (take() !== ')') throw new Error('缺少 )');
      return v;
    }
    return value(t);
  }
  function unary() {
    if (peek() === '-') { take(); return -unary(); }
    return atom();
  }
  function mul() {
    let v = unary();
    while (peek() === '*' || peek() === '/') {
      const op = take();
      const b = unary();
      v = op === '*' ? v * b : (b ? v / b : 0.0);
    }
    return v;
  }
  function add() {
    let v = mul();
    while (peek() === '+' || peek() === '-') {
      const op = take();
      const b = mul();
      v = op === '+' ? v + b : v - b;
    }
    return v;
  }
  const CMP_OPS = ['<', '<=', '>', '>=', '==', '!=', '&&', '||'];
  function cmp() {
    let v = add();
    while (peek() !== null && CMP_OPS.includes(peek())) {
      const op = take();
      const b = add();
      if (op === '&&') v = (v && b) ? 1.0 : 0.0;
      else if (op === '||') v = (v || b) ? 1.0 : 0.0;
      else {
        let res;
        if (op === '<') res = v < b;
        else if (op === '<=') res = v <= b;
        else if (op === '>') res = v > b;
        else if (op === '>=') res = v >= b;
        else if (op === '==') res = v === b;
        else res = v !== b;
        v = res ? 1.0 : 0.0;
      }
    }
    return v;
  }
  function tern() {
    const c = cmp();
    if (peek() === '?') {
      take();
      const a = tern();
      if (take() !== ':') throw new Error('三元缺少 :');
      const b = tern();
      return c ? a : b;
    }
    return c;
  }

  return tern();
}

/**
 * 结局判定：lock 满足即必中；其余取 score + priority*1e-6 最高者；兜底 end_default。
 * @param {object} st
 * @param {object} vocab
 * @param {object[]} endings
 * @returns {string}
 */
export function evaluateEnding(st, vocab, endings) {
  function ok(c) {
    if (!c) c = {};
    if (c.maxMood !== undefined && st.mood > c.maxMood) return false;
    if (c.minMood !== undefined && st.mood < c.minMood) return false;
    if (c.minHours !== undefined && st.hours < c.minHours) return false;
    if (c.minFame !== undefined && st.fame < c.minFame) return false;
    if (c.minFriends !== undefined && st.friends < c.minFriends) return false;
    if (c.maxFriends !== undefined && st.friends > c.maxFriends) return false;
    if (c.minSugarCount !== undefined && st.sugarCount < c.minSugarCount) return false;
    if (c.minBreakupCount !== undefined && st.breakupCount < c.minBreakupCount) return false;
    // ---- DLC1 结局条件增量 ----
    if (c.minFavor !== undefined && st.favor < c.minFavor) return false;
    if (c.maxFavor !== undefined && st.favor > c.maxFavor) return false;
    if (c.minCircles !== undefined && (st.circles || []).length < c.minCircles) return false;
    // 同时多段关系
    if (c.minActiveRelations !== undefined
        && activeRelList(st).length < c.minActiveRelations) return false;
    if (c.minSugarRelations !== undefined
        && activeRelList(st).filter((r) => r.state === '砂糖').length < c.minSugarRelations) return false;
    // --------------------------
    const minSkills = c.minSkills;
    if (minSkills) {
      for (const k of Object.keys(minSkills)) {
        if ((st.skills[k] || 0) < minSkills[k]) return false;
      }
    }
    const maxSkills = c.maxSkills;
    if (maxSkills) {
      for (const k of Object.keys(maxSkills)) {
        if (k === 'all') {
          let mx = 0;
          for (const v of Object.values(st.skills)) if (v > mx) mx = v;
          if (mx > maxSkills[k]) return false;
        } else if ((st.skills[k] || 0) > maxSkills[k]) {
          return false;
        }
      }
    }
    const reqFlags = c.requireFlags;
    if (reqFlags) {
      for (const f of reqFlags) if (!st.flags.includes(f)) return false;
    }
    const excFlags = c.excludeFlags;
    if (excFlags) {
      for (const f of excFlags) if (st.flags.includes(f)) return false;
    }
    return true;
  }

  // 1) lock 结局满足条件即必中
  for (const e of endings) {
    if (e.lock && ok(e.condition || {})) return e.id;
  }
  // 2) 其余：取 score 最高
  let best = 'end_default';
  let bestScore = null;
  for (const e of endings) {
    if (e.lock) continue;
    if (!ok(e.condition || {})) continue;
    const s = evalScore(e.score, st, vocab) + (e.priority || 0) * 1e-6;
    if (bestScore === null || s > bestScore) {
      best = e.id;
      bestScore = s;
    }
  }
  return best;
}