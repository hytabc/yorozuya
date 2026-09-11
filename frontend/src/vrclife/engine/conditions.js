/**
 * condition DSL 求值 —— 逐字段移植 simulate.py 的 match / _tags_ok / _flags_ok。
 */

/** 结束/低迷/恢复：上一段关系已经结束、下一段还没开始。见 match() 的 hasRelation。 */
export const INACTIVE_REL_STATES = ['结束', '低迷', '恢复'];

/**
 * 活跃关系列表（不含 结束 / 低迷 / 恢复）；兼容只有单个 relation 的旧状态。
 * @param {object} st
 * @returns {object[]}
 */
function activeRelationList(st) {
  const list = Array.isArray(st.relations) ? st.relations : (st.relation ? [st.relation] : []);
  return list.filter((r) => r && !INACTIVE_REL_STATES.includes(r.state));
}

/**
 * 单个关系是否满足 cond 里的关系数值条件。
 * @param {object} cond
 * @param {object|undefined} r
 * @param {boolean} active
 * @returns {boolean}
 */
function relationMatches(cond, r, active) {
  if (cond.relationState && cond.relationState.length) {
    // NOTE: relationState 不要求活跃 —— 结束/低迷/恢复也能命中，按 simulate.py 原样。
    if (!r || !cond.relationState.includes(r.state)) return false;
  }
  if (cond.minIntimacy !== undefined) {
    if (!active || r.intimacy < cond.minIntimacy) return false;
  }
  if (cond.minDependence !== undefined) {
    if (!active || r.dependence < cond.minDependence) return false;
  }
  if (cond.minTrust !== undefined) {
    if (!active || r.trust < cond.minTrust) return false;
  }
  if (cond.minFreshness !== undefined) {
    if (!active || r.freshness < cond.minFreshness) return false;
  }
  if (cond.minRealPressure !== undefined) {
    if (!active || r.realPressure < cond.minRealPressure) return false;
  }
  if (cond.maxRealPressure !== undefined) {
    if (!r || r.realPressure > cond.maxRealPressure) return false;
  }
  return true;
}

/**
 * @param {object} cond
 * @param {object} st
 * @returns {boolean}
 */
export function tagsOk(cond, st) {
  const req = cond.requireTags;
  if (req) {
    for (let i = 0; i < req.length; i++) {
      if (!st.tags.includes(req[i])) return false;
    }
  }
  const anyReq = cond.requireAnyTags;
  if (anyReq && anyReq.length) {
    let hit = false;
    for (let i = 0; i < anyReq.length; i++) {
      if (st.tags.includes(anyReq[i])) { hit = true; break; }
    }
    if (!hit) return false;
  }
  const exc = cond.excludeTags;
  if (exc) {
    for (let i = 0; i < exc.length; i++) {
      if (st.tags.includes(exc[i])) return false;
    }
  }
  return true;
}

/**
 * @param {object} cond
 * @param {object} st
 * @returns {boolean}
 */
export function flagsOk(cond, st) {
  const req = cond.requireFlags;
  if (req) {
    for (let i = 0; i < req.length; i++) {
      if (!st.flags.includes(req[i])) return false;
    }
  }
  const exc = cond.excludeFlags;
  if (exc) {
    for (let i = 0; i < exc.length; i++) {
      if (st.flags.includes(exc[i])) return false;
    }
  }
  return true;
}

/**
 * 求值 condition DSL。缺省字段视为不限制。
 * @param {object|null|undefined} cond
 * @param {object} st
 * @param {{next: () => number}} [rng] 仅当 condition 含 probability 时需要
 * @returns {boolean}
 */
export function match(cond, st, rng) {
  if (!cond) return true;
  if (cond.minHours !== undefined && st.hours < cond.minHours) return false;
  if (cond.maxHours !== undefined && st.hours > cond.maxHours) return false;
  if (cond.minMood !== undefined && st.mood < cond.minMood) return false;
  if (cond.maxMood !== undefined && st.mood > cond.maxMood) return false;
  if (cond.minFame !== undefined && st.fame < cond.minFame) return false;
  if (cond.minFriends !== undefined && st.friends < cond.minFriends) return false;
  if (cond.maxFriends !== undefined && st.friends > cond.maxFriends) return false;
  if (cond.minAvatars !== undefined && st.avatars < cond.minAvatars) return false;
  if (cond.minAssets !== undefined && st.assets < cond.minAssets) return false;
  if (cond.minSugarCount !== undefined && st.sugarCount < cond.minSugarCount) return false;
  if (cond.minBreakupCount !== undefined && st.breakupCount < cond.minBreakupCount) return false;
  // ---- DLC1 增量：好感度 / 圈子数量 ----
  if (cond.minFavor !== undefined && st.favor < cond.minFavor) return false;
  if (cond.maxFavor !== undefined && st.favor > cond.maxFavor) return false;
  if (cond.minCircles !== undefined && (st.circles || []).length < cond.minCircles) return false;
  // ---------------------------------------
  if (!tagsOk(cond, st)) return false;
  if (!flagsOk(cond, st)) return false;

  const circ = cond.requireCircles;
  if (circ) {
    for (let i = 0; i < circ.length; i++) {
      if (!st.circles.includes(circ[i])) return false;
    }
  }

  const minSkills = cond.minSkills;
  if (minSkills) {
    for (const k of Object.keys(minSkills)) {
      if ((st.skills[k] || 0) < minSkills[k]) return false;
    }
  }
  const maxSkills = cond.maxSkills;
  if (maxSkills) {
    for (const k of Object.keys(maxSkills)) {
      if (k === 'all') {
        const mx = Object.values(st.skills).reduce((a, b) => (b > a ? b : a), 0);
        if (mx > maxSkills[k]) return false;
      } else if ((st.skills[k] || 0) > maxSkills[k]) {
        return false;
      }
    }
  }

  // —— 关系条件 ——
  // 默认看「当前焦点关系」（st.relation）；cond.anyRelation 时任一活跃关系满足即可。
  const r = st.relation;
  // 「有关系」= 存在且处于活跃状态。结束/低迷/恢复 三段属于「上一段已经没了」。
  const active = !!r && !INACTIVE_REL_STATES.includes(r.state);
  if (cond.hasRelation === true && !active) return false;
  if (cond.hasRelation === false && active) return false;

  const needsRelCheck = !!cond.relationState
    || cond.minIntimacy !== undefined || cond.minDependence !== undefined
    || cond.minTrust !== undefined || cond.minFreshness !== undefined
    || cond.minRealPressure !== undefined || cond.maxRealPressure !== undefined;
  if (needsRelCheck) {
    if (cond.anyRelation) {
      if (!activeRelationList(st).some((rel) => relationMatches(cond, rel, true))) return false;
    } else if (!relationMatches(cond, r, active)) return false;
  }

  // 同时多段的计数条件
  const relList = activeRelationList(st);
  if (cond.minActiveRelations !== undefined && relList.length < cond.minActiveRelations) return false;
  if (cond.minSugarRelations !== undefined
      && relList.filter((rel) => rel.state === '砂糖').length < cond.minSugarRelations) return false;

  const reqDone = cond.requiresEventDone;
  if (reqDone) {
    for (let i = 0; i < reqDone.length; i++) {
      if (!st.usedEvents.includes(reqDone[i])) return false;
    }
  }
  const excDone = cond.excludesEventDone;
  if (excDone) {
    for (let i = 0; i < excDone.length; i++) {
      if (st.usedEvents.includes(excDone[i])) return false;
    }
  }

  if (cond.probability !== undefined && cond.probability !== null) {
    if (!rng) throw new Error('conditions.match: probability 需要 rng');
    if (rng.next() > cond.probability) return false;
  }
  return true;
}