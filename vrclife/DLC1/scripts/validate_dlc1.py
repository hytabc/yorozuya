#!/usr/bin/env python3
"""
DLC1 事件数据校验器 —— 在 data/SCHEMA.md v1.0 之上叠加 schema.dlc1.json 的增量规则。

用法:
    python3 DLC1/scripts/validate_dlc1.py            # 校验并输出报告
    python3 DLC1/scripts/validate_dlc1.py --strict   # 有 WARN 时也返回非 0

退出码: 0 = 通过(可能有 WARN), 1 = 存在 ERROR 或 --strict 下有 WARN
"""

import json
import os
import re
import sys
from collections import Counter

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DLC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # .../DLC1
ROOT = os.path.dirname(DLC_DIR)                                         # 仓库根
DATA = os.path.join(ROOT, "data")
DLC_EVENTS_DIR = os.path.join(DLC_DIR, "events")

CATEGORIES = {"key", "normal", "chain", "random", "pity", "sugar", "ambient"}
RARITIES = {"common", "uncommon", "rare", "legendary"}
TIERS = {"normal", "rare", "extreme"}
RELATION_STATES = {
    "陌生人", "认识", "朋友", "常一起玩", "暧昧", "砂糖", "稳定",
    "矛盾", "结束", "低迷", "恢复",
}
RELATION_OPS = {"spawn", "setState", "end", "renew", "none"}
RELATION_OP_BASE_KEYS = {"type", "state", "name", "target"}
RELATION_DIMS = {"intimacy", "trust", "freshness", "dependence", "realPressure"}
RELATION_INIT_KEYS = {"init" + d[0].upper() + d[1:] for d in RELATION_DIMS}
EFFECT_BASE_KEYS = {
    "mood", "friends", "fame", "avatars", "assets", "sugarCount",
    "breakupCount", "hoursBonus", "skills", "circles", "tags", "flags",
    "counters", "relationOp", "endingHint",
}
# DLC 新增 effects 键
EFFECT_DLC_KEYS = {"favor"}
# DLC 新增 condition 键
COND_DLC_KEYS = {"minFavor", "maxFavor", "minCircles", "minCounters"}

STAGES = []
HOUR_BANDS = [(0, 10), (10, 50), (50, 200), (200, 500), (500, 1000), (1000, 10 ** 9)]
BANNED_WORDS = ["习近平", "共产党", "六四", "台湾国", "法轮功"]

errors = []
warns = []


def err(m):
    errors.append(m)


def warn(m):
    warns.append(m)


def load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def stages_overlapping(lo, hi):
    out = []
    for name, slo, shi in STAGES:
        if lo < shi and hi >= slo:
            out.append(name)
    return out


def main():
    global STAGES
    base_vocab = load(os.path.join(DATA, "vocab.json"))
    dlc_vocab = load(os.path.join(DLC_DIR, "vocab.dlc1.json"))
    add = dlc_vocab["additions"]

    STAGES = [(s["key"], s["minHours"], s["maxHours"]) for s in base_vocab["stages"]]
    stage_names = {s[0] for s in STAGES}

    known_skills = {s["key"] for s in base_vocab["skills"]}
    known_circles = set(base_vocab["circles"]) | set(add["circles"])
    known_tags = (set(base_vocab["coreTags"]) | set(base_vocab["extendedTags"])
                  | set(add["coreTags"]) | set(add["extendedTags"]))
    known_evt_tags = set(base_vocab["eventTags"]) | set(add["eventTags"])
    known_paths = set(base_vocab["endingPaths"]) | set(add["endingPaths"])
    path_aliases = base_vocab["endingPathAliases"]
    glossary = dlc_vocab.get("glossary", {})

    # 已知事件 id（本体索引 + DLC 自身），用于 schedule 引用检查
    known_event_ids = set()
    base_index_path = os.path.join(DATA, "events.index.json")
    if os.path.exists(base_index_path):
        known_event_ids |= set(load(base_index_path).get("byId", {}).keys())

    # ---------- 加载 DLC 事件 ----------
    buckets = []
    all_events = []
    by_id = {}
    for fn in sorted(os.listdir(DLC_EVENTS_DIR)):
        if not fn.endswith(".json"):
            continue
        bucket = fn[:-5]
        buckets.append(bucket)
        doc = load(os.path.join(DLC_EVENTS_DIR, fn))
        if doc.get("bucket") != bucket:
            err(f"[元数据] {fn} 的 bucket 字段为 {doc.get('bucket')!r}，应为 {bucket!r}")
        for e in doc.get("events", []):
            all_events.append((bucket, e))
            eid = e.get("id")
            if eid in by_id:
                err(f"[重复ID] {eid} 重复出现")
            else:
                by_id[eid] = e
            known_event_ids.add(eid)

    if not all_events:
        print("没有加载到任何 DLC 事件。")
        return 1

    # ---------- 逐事件校验 ----------
    used_paths = set()
    for bucket, e in all_events:
        eid = e.get("id", "<无id>")
        tag = f"[{bucket}/{eid}]"

        for f in ("id", "title", "category", "stage", "hoursRange", "weight",
                  "rarity", "once", "cooldown", "tags", "condition", "text", "options"):
            if f not in e:
                err(f"{tag} 缺少必填字段 `{f}`")
        if "id" not in e:
            continue

        if not re.fullmatch(rf"({bucket})_(k\d{{2}}|\d{{3}})", eid):
            err(f"{tag} id 不符合命名规范 `{bucket}_NNN` 或 `{bucket}_kNN`")

        if e.get("category") not in CATEGORIES:
            err(f"{tag} category 非法: {e.get('category')!r}")
        if e.get("rarity") not in RARITIES:
            err(f"{tag} rarity 非法: {e.get('rarity')!r}")

        hr = e.get("hoursRange")
        if not (isinstance(hr, list) and len(hr) == 2 and all(isinstance(x, int) for x in hr)):
            err(f"{tag} hoursRange 必须是 [int,int]")
            hr = None
        elif hr[0] > hr[1]:
            err(f"{tag} hoursRange 下界大于上界: {hr}")

        if hr:
            allowed = stages_overlapping(hr[0], hr[1])
            if e.get("stage") not in allowed:
                err(f"{tag} stage={e.get('stage')!r} 不在 hoursRange {hr} 覆盖阶段 {allowed} 内")
            if e.get("stage") not in stage_names:
                err(f"{tag} stage={e.get('stage')!r} 不是合法阶段")

        cond = e.get("condition") or {}
        if hr:
            if "minHours" in cond and cond["minHours"] != hr[0]:
                err(f"{tag} condition.minHours={cond['minHours']} != hoursRange[0]={hr[0]}")
            if "maxHours" in cond and cond["maxHours"] != hr[1]:
                err(f"{tag} condition.maxHours={cond['maxHours']} != hoursRange[1]={hr[1]}")

        evt_tags = e.get("tags") or []
        if not (1 <= len(evt_tags) <= 3):
            warn(f"{tag} tags 数量 {len(evt_tags)}，规范要求 1-3")
        for t in evt_tags:
            if t not in known_evt_tags:
                err(f"{tag} 事件 tag `{t}` 不在 vocab.eventTags 中")

        # condition 值域
        for t in cond.get("requireTags", []) + cond.get("requireAnyTags", []) + cond.get("excludeTags", []):
            if t not in known_tags:
                err(f"{tag} condition 标签 `{t}` 不在词表内")
        for c in cond.get("requireCircles", []):
            if c not in known_circles:
                err(f"{tag} condition 圈子 `{c}` 不在词表内")
        for k in (cond.get("minSkills") or {}):
            if k not in known_skills:
                err(f"{tag} condition.minSkills 键 `{k}` 非法")
        for k in (cond.get("maxSkills") or {}):
            if k != "all" and k not in known_skills:
                err(f"{tag} condition.maxSkills 键 `{k}` 非法")
        for st in cond.get("relationState", []):
            if st not in RELATION_STATES:
                err(f"{tag} condition.relationState `{st}` 非法")
        for k in ("minFavor", "maxFavor"):
            if k in cond and not (isinstance(cond[k], int) and 0 <= cond[k] <= 100):
                err(f"{tag} condition.{k}={cond[k]!r} 必须是 0-100 的整数")
        if "minCircles" in cond and not isinstance(cond["minCircles"], int):
            err(f"{tag} condition.minCircles 必须是整数")
        if "minCounters" in cond:
            if not isinstance(cond["minCounters"], dict):
                err(f"{tag} condition.minCounters 必须是对象")
            else:
                for ck, cv in cond["minCounters"].items():
                    if not isinstance(ck, str) or not ck:
                        err(f"{tag} condition.minCounters 键非法: {ck!r}")
                    if not isinstance(cv, (int, float)):
                        err(f"{tag} condition.minCounters[{ck}] 必须是数字")

        # options
        opts = e.get("options")
        if not isinstance(opts, list) or not (2 <= len(opts) <= 4):
            err(f"{tag} options 数量为 {len(opts) if isinstance(opts, list) else '非数组'}，要求 2-4")
            continue

        has_free = False
        for o in opts:
            oid = o.get("id", "?")
            otag = f"{tag}.{oid}"
            if not o.get("text"):
                err(f"{otag} 缺少 text")
            ocond = o.get("condition")
            if not ocond:
                has_free = True
            if ocond:
                for t in ocond.get("requireTags", []):
                    if t not in known_tags:
                        err(f"{otag} option 条件标签 `{t}` 不在词表内")
                for k in (ocond.get("minSkills") or {}):
                    if k not in known_skills:
                        err(f"{otag} option 条件技能键 `{k}` 非法")
                for st in ocond.get("relationState", []):
                    if st not in RELATION_STATES:
                        err(f"{otag} option 条件关系状态 `{st}` 非法")
                for k in ("minFavor", "maxFavor"):
                    if k in ocond and not (isinstance(ocond[k], int) and 0 <= ocond[k] <= 100):
                        err(f"{otag} option 条件 {k}={ocond[k]!r} 必须是 0-100 的整数")
                if not o.get("lockedHint"):
                    err(f"{otag} 有 condition 但无 lockedHint（应置灰而非隐藏）")

            outs = o.get("outcomes")
            if not isinstance(outs, list) or not (1 <= len(outs) <= 3):
                err(f"{otag} outcomes 数量异常，要求 1-3")
                continue
            for i, oc in enumerate(outs):
                octag = f"{otag}#{i}"
                if not isinstance(oc.get("weight"), (int, float)) or oc["weight"] <= 0:
                    err(f"{octag} weight 必须为正数")
                if oc.get("tier") not in TIERS:
                    err(f"{octag} tier 非法: {oc.get('tier')!r}")
                if not oc.get("text"):
                    err(f"{octag} 缺少 text")

                fx = oc.get("effects") or {}
                rop = fx.get("relationOp") or oc.get("relationOp") or {}
                sch = oc.get("schedule") or []
                if not fx and not rop and not sch:
                    err(f"{octag} 未修改任何状态（effects/relationOp/schedule 全空）")

                # effects 键白名单
                for k in fx:
                    if k not in EFFECT_BASE_KEYS and k not in EFFECT_DLC_KEYS:
                        err(f"{octag} effects 含未知键 `{k}`")
                if "favor" in fx and not isinstance(fx["favor"], (int, float)):
                    err(f"{octag} effects.favor 必须是数字")

                for k in (fx.get("skills") or {}):
                    if k not in known_skills:
                        err(f"{octag} effects.skills 键 `{k}` 非法")
                for c in ((fx.get("circles") or {}).get("add", [])
                          + (fx.get("circles") or {}).get("remove", [])):
                    if c not in known_circles:
                        err(f"{octag} effects.circles 中 `{c}` 不在词表内")
                for t in ((fx.get("tags") or {}).get("add", [])
                          + (fx.get("tags") or {}).get("remove", [])):
                    if t not in known_tags:
                        err(f"{octag} effects.tags 中 `{t}` 不在词表内")

                if rop:
                    rtype = rop.get("type")
                    if rtype not in RELATION_OPS:
                        err(f"{octag} relationOp.type 非法: {rtype!r}")
                    if rop.get("state") and rop["state"] not in RELATION_STATES:
                        err(f"{octag} relationOp.state 非法: {rop['state']!r}")
                    if rop.get("target") not in (None, "focus", "other"):
                        err(f"{octag} relationOp.target 非法: {rop['target']!r}（合法：focus/other）")
                    for k in rop:
                        if k in RELATION_OP_BASE_KEYS or k in RELATION_DIMS or k in RELATION_INIT_KEYS:
                            continue
                        if k == "force":
                            if rtype != "spawn" or not isinstance(rop[k], bool):
                                err(f"{octag} relationOp.force 非法")
                            continue
                        err(f"{octag} relationOp 含未知键 `{k}`")

                for s in sch:
                    tid = s.get("eventId")
                    if tid not in known_event_ids:
                        err(f"{octag} schedule 引用了不存在的事件 `{tid}`")
                    dh = s.get("delayHours")
                    if isinstance(dh, list) and len(dh) != 2:
                        err(f"{octag} schedule.delayHours 数组长度必须为 2")
                    if "chance" in s and not (0 <= s["chance"] <= 1):
                        err(f"{octag} schedule.chance 必须在 0-1")

                eh = oc.get("endingHint")
                if eh:
                    p = eh.get("path")
                    if p not in known_paths and p not in path_aliases:
                        err(f"{octag} endingHint.path `{p}` 不在合法取值内")
                    elif p in path_aliases:
                        warn(f"{octag} endingHint.path `{p}` 是别名，将被规范化")
                    if p in known_paths:
                        used_paths.add(p)
                    if not isinstance(eh.get("score"), (int, float)):
                        err(f"{octag} endingHint.score 必须为数字")

        if not has_free:
            err(f"{tag} 没有任何无条件选项 —— 玩家可能卡死")

        if len(e.get("title", "")) > 12:
            warn(f"{tag} title 长度 {len(e['title'])} > 12 字")
        if e.get("category") == "key" and not e.get("once"):
            warn(f"{tag} category=key 但 once=false")
        if len(e.get("text", "")) > 120:
            warn(f"{tag} text 长度 {len(e['text'])} > 120 字")
        for o in opts:
            for oc in o.get("outcomes", []):
                if len(oc.get("text", "")) > 100:
                    warn(f"{tag}.{o.get('id')} outcome 文案长度 {len(oc['text'])} > 100 字")

        blob = json.dumps(e, ensure_ascii=False)
        for w in BANNED_WORDS:
            if w in blob:
                err(f"{tag} 含敏感词 `{w}`")

    # ---------- 结局校验 ----------
    dlc_endings = load(os.path.join(DLC_DIR, "endings.dlc1.json"))
    seen_ids = set()
    for en in dlc_endings["endings"]:
        eid = en.get("id")
        if not re.fullmatch(r"end_[a-z_]+", eid or ""):
            err(f"[结局] id 非法: {eid!r}")
        if eid in seen_ids:
            err(f"[结局] id 重复: {eid}")
        seen_ids.add(eid)
        c = en.get("condition") or {}
        for k in ("minFavor", "maxFavor"):
            if k in c and not (isinstance(c[k], int) and 0 <= c[k] <= 100):
                err(f"[结局/{eid}] {k} 必须是 0-100 整数")
        if "minCircles" in c and not isinstance(c["minCircles"], int):
            err(f"[结局/{eid}] minCircles 必须是整数")
        for k in (c.get("minSkills") or {}):
            if k not in known_skills:
                err(f"[结局/{eid}] minSkills 键 `{k}` 非法")
        for p in dlc_endings.get("endingPaths", []):
            if p not in known_paths:
                err(f"[结局] endingPaths 中的 `{p}` 未在 vocab.dlc1.json 声明")

    # ---------- 术语覆盖 ----------
    all_blob = json.dumps(all_events, ensure_ascii=False)
    for term in glossary:
        if term not in all_blob:
            err(f"[术语] 词表术语 `{term}` 未出现在任何 DLC 事件文案中")

    # ---------- 新结局路径必须被引用 ----------
    for p in dlc_endings.get("endingPaths", []):
        if p not in used_paths:
            err(f"[结局] 新路径 `{p}` 没有被任何 DLC 事件的 endingHint 引用")

    # ---------- 桶前缀一致 ----------
    allowed_prefix = set(buckets)
    for b, e in all_events:
        eid = e.get("id", "")
        if "_" in eid and eid.split("_")[0] not in allowed_prefix:
            err(f"[{b}/{eid}] id 前缀与桶不一致")

    # ---------- 报告 ----------
    print("=" * 62)
    print("DLC1 事件数据校验报告")
    print("=" * 62)
    print(f"\n桶数量        : {len(buckets)}  ({', '.join(buckets)})")
    print(f"事件总数      : {len(all_events)}")
    print(f"  唯一 id     : {len(by_id)}")
    k = sum(1 for _, e in all_events if e.get("category") == "key")
    print(f"  key 事件    : {k}")
    print(f"新结局        : {len(dlc_endings['endings'])}")
    print(f"新词条        : 圈子 {len(add['circles'])} / 标签 {len(add['coreTags']) + len(add['extendedTags'])} / 世界 {len(add['worldPool'])}")

    cat_c = Counter(e.get("category") for _, e in all_events)
    tier_c = Counter()
    opt_total = out_total = 0
    for _, e in all_events:
        for o in e.get("options", []):
            opt_total += 1
            for oc in o.get("outcomes", []):
                out_total += 1
                tier_c[oc.get("tier")] += 1
    print("\n分档统计:")
    for kk, v in cat_c.most_common():
        print(f"  category {kk:<10} {v:>3}")
    for kk, v in tier_c.most_common():
        pct = v / out_total * 100 if out_total else 0
        print(f"  tier     {kk:<10} {v:>3}  ({pct:.1f}%)")
    print(f"\n选项总数      : {opt_total}")
    print(f"结果总数      : {out_total}")

    print("\n" + "-" * 62)
    if errors:
        print(f"\n❌ ERROR ({len(errors)}):")
        for m in errors[:80]:
            print(f"  · {m}")
        if len(errors) > 80:
            print(f"  ... 另有 {len(errors)-80} 条")
    if warns:
        print(f"\n⚠️  WARN ({len(warns)}):")
        for m in warns[:40]:
            print(f"  · {m}")
        if len(warns) > 40:
            print(f"  ... 另有 {len(warns)-40} 条")
    if not errors and not warns:
        print("\n✅ 全部通过，无 ERROR 无 WARN")
    print("-" * 62)

    strict = "--strict" in sys.argv
    if errors:
        return 1
    if strict and warns:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
