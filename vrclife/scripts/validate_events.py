#!/usr/bin/env python3
"""
事件数据校验器 —— 对应 PRD §12.3 / SCHEMA.md §10

用法:
    python3 scripts/validate_events.py            # 校验并输出报告
    python3 scripts/validate_events.py --strict   # 有 ERROR 时退出码非 0

退出码: 0 = 通过(可能有 WARN), 1 = 存在 ERROR 或 --strict 下有 WARN
"""

import json
import os
import re
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
EVENTS_DIR = os.path.join(DATA, "events")

BUCKETS = [
    "intro", "newbie", "social", "sugar_a", "sugar_b",
    "deep", "veteran", "legend", "wild", "idle",
]

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

# 统计用
rel_delta_keys = set()
rel_init_keys = set()

STAGES = [
    ("初入", 0, 10),
    ("萌新探索", 10, 50),
    ("社交起步", 50, 200),
    ("深度社交", 200, 500),
    ("老油条", 500, 1000),
    ("传奇", 1000, 99999),
]

HOUR_BANDS = [(0, 10), (10, 50), (50, 200), (200, 500), (500, 1000), (1000, 10**9)]

BANNED_WORDS = ["习近平", "共产党", "六四", "台湾国", "法轮功"]

errors: list[str] = []
warns: list[str] = []


def err(msg):
    errors.append(msg)


def warn(msg):
    warns.append(msg)


def load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def stage_of(hours):
    for name, lo, hi in STAGES:
        if lo <= hours < hi:
            return name
    return "传奇"


def stages_overlapping(lo, hi):
    """hoursRange 跨越的所有阶段。用于跨阶段事件（idle / wild / sugar_b）的合法性判断。"""
    out = []
    for name, slo, shi in STAGES:
        if lo < shi and hi >= slo:
            out.append(name)
    return out


def main():
    vocab = load(os.path.join(DATA, "vocab.json"))
    known_skills = {s["key"] for s in vocab["skills"]}
    known_circles = set(vocab["circles"])
    known_tags = set(vocab["coreTags"]) | set(vocab["extendedTags"])
    known_evt_tags = set(vocab["eventTags"])
    known_paths = set(vocab["endingPaths"])
    path_aliases = vocab["endingPathAliases"]

    # ---------- 加载 ----------
    all_events = []
    by_id = {}
    per_bucket = {}

    for b in BUCKETS:
        p = os.path.join(EVENTS_DIR, f"{b}.json")
        if not os.path.exists(p):
            err(f"[缺失] {b}.json 不存在")
            continue
        try:
            doc = load(p)
        except json.JSONDecodeError as e:
            err(f"[JSON] {b}.json 解析失败: {e}")
            continue
        evs = doc.get("events", [])
        per_bucket[b] = evs
        if doc.get("bucket") != b:
            warn(f"[元数据] {b}.json 的 bucket 字段为 {doc.get('bucket')!r}，应为 {b!r}")
        for e in evs:
            all_events.append((b, e))
            eid = e.get("id")
            if eid in by_id:
                err(f"[重复ID] {eid} 在 {b}.json 与 {by_id[eid][0]}.json 中重复")
            else:
                by_id[eid] = (b, e)

    if not all_events:
        print("没有加载到任何事件。")
        return 1

    # ---------- 逐事件校验 ----------
    for bucket, e in all_events:
        eid = e.get("id", "<无id>")
        tag = f"[{bucket}/{eid}]"

        # 必填字段
        for f in ("id", "title", "category", "stage", "hoursRange", "weight",
                  "rarity", "once", "cooldown", "tags", "condition", "text", "options"):
            if f not in e:
                err(f"{tag} 缺少必填字段 `{f}`")

        if "id" not in e:
            continue

        # id 命名规范
        m = re.fullmatch(rf"({bucket})_(k\d{{2}}|\d{{3}})", eid)
        if not m:
            err(f"{tag} id 不符合命名规范 `{bucket}_NNN` 或 `{bucket}_kNN`")

        # category / rarity
        if e.get("category") not in CATEGORIES:
            err(f"{tag} category 非法: {e.get('category')!r}")
        if e.get("rarity") not in RARITIES:
            err(f"{tag} rarity 非法: {e.get('rarity')!r}")

        # hoursRange
        hr = e.get("hoursRange")
        if not (isinstance(hr, list) and len(hr) == 2 and all(isinstance(x, int) for x in hr)):
            err(f"{tag} hoursRange 必须是 [int,int]")
            hr = None
        elif hr[0] > hr[1]:
            err(f"{tag} hoursRange 下界大于上界: {hr}")

        # stage 必须落在 hoursRange 覆盖的阶段集合内（跨阶段事件合法）
        if hr:
            allowed = stages_overlapping(hr[0], hr[1])
            if e.get("stage") not in allowed:
                warn(f"{tag} stage={e.get('stage')!r} 不在 hoursRange {hr} "
                     f"覆盖的阶段 {allowed} 内")

        # condition 与 hoursRange 冗余一致
        cond = e.get("condition") or {}
        if hr:
            if "minHours" in cond and cond["minHours"] != hr[0]:
                warn(f"{tag} condition.minHours={cond['minHours']} 与 hoursRange[0]={hr[0]} 不一致")
            if "maxHours" in cond and cond["maxHours"] != hr[1]:
                warn(f"{tag} condition.maxHours={cond['maxHours']} 与 hoursRange[1]={hr[1]} 不一致")

        # tags
        evt_tags = e.get("tags") or []
        if not (1 <= len(evt_tags) <= 3):
            warn(f"{tag} tags 数量 {len(evt_tags)}，规范要求 1-3")
        for t in evt_tags:
            if t not in known_evt_tags:
                warn(f"{tag} 事件 tag `{t}` 不在 vocab.eventTags 中")

        # condition 值域
        for t in cond.get("requireTags", []) + cond.get("requireAnyTags", []) + cond.get("excludeTags", []):
            if t not in known_tags:
                warn(f"{tag} condition 中标签 `{t}` 不在 vocab 词表内")
        for c in cond.get("requireCircles", []):
            if c not in known_circles:
                warn(f"{tag} condition 中圈子 `{c}` 不在 vocab 词表内")
        for k in (cond.get("minSkills") or {}):
            if k not in known_skills:
                err(f"{tag} condition.minSkills 键 `{k}` 非法")
        for st in cond.get("relationState", []):
            if st not in RELATION_STATES:
                err(f"{tag} condition.relationState `{st}` 非法")
        if "requiresEventDone" in cond:
            for dep in cond.get("requiresEventDone") or []:
                if dep not in by_id:
                    warn(f"{tag} condition.requiresEventDone 引用了不存在的事件 `{dep}`")

        # options
        opts = e.get("options")
        if not isinstance(opts, list) or not (2 <= len(opts) <= 4):
            err(f"{tag} options 数量为 {len(opts) if isinstance(opts, list) else '非数组'}，要求 2-4")
            continue

        has_free_option = False
        for o in opts:
            oid = o.get("id", "?")
            otag = f"{tag}.{oid}"
            if not o.get("text"):
                err(f"{otag} 缺少 text")
            ocond = o.get("condition")
            if not ocond:
                has_free_option = True

            # option.condition 值域
            if ocond:
                for t in ocond.get("requireTags", []):
                    if t not in known_tags:
                        warn(f"{otag} option 条件标签 `{t}` 不在词表内")
                for k in (ocond.get("minSkills") or {}):
                    if k not in known_skills:
                        err(f"{otag} option 条件技能键 `{k}` 非法")
                if ocond.get("relationState"):
                    for st in ocond["relationState"]:
                        if st not in RELATION_STATES:
                            err(f"{otag} option 条件关系状态 `{st}` 非法")
                if not o.get("lockedHint"):
                    warn(f"{otag} 有 condition 但无 lockedHint（该选项将被隐藏而非置灰）")

            outs = o.get("outcomes")
            if not isinstance(outs, list) or not (1 <= len(outs) <= 3):
                err(f"{otag} outcomes 数量为 {len(outs) if isinstance(outs,list) else '非数组'}，要求 1-3")
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
                rop = oc.get("relationOp") or {}
                sch = oc.get("schedule") or []
                if not fx and not rop and not sch:
                    err(f"{octag} 未修改任何状态（effects/relationOp/schedule 全空）")

                # effects 值域
                for k in (fx.get("skills") or {}):
                    if k not in known_skills:
                        err(f"{octag} effects.skills 键 `{k}` 非法")
                for c in (fx.get("circles") or {}).get("add", []) + (fx.get("circles") or {}).get("remove", []):
                    if c not in known_circles:
                        warn(f"{octag} effects.circles 中 `{c}` 不在词表内")
                for t in (fx.get("tags") or {}).get("add", []) + (fx.get("tags") or {}).get("remove", []):
                    if t not in known_tags:
                        warn(f"{octag} effects.tags 中 `{t}` 不在词表内")

                # relationOp
                if rop:
                    rtype = rop.get("type")
                    if rtype not in RELATION_OPS:
                        err(f"{octag} relationOp.type 非法: {rtype!r}")
                    if rop.get("state") and rop["state"] not in RELATION_STATES:
                        err(f"{octag} relationOp.state 非法: {rop['state']!r}")
                    for k in rop:
                        if k in RELATION_OP_BASE_KEYS:
                            continue
                        if k == "force":
                            # SCHEMA §5.2：低迷期豁免开关（数据驱动，引擎不硬编码事件 id）
                            if rtype != "spawn":
                                err(f"{octag} relationOp.force 只对 type=spawn 有意义")
                            if not isinstance(rop[k], bool):
                                err(f"{octag} relationOp.force 必须是布尔值")
                            continue
                        if k == "target":
                            # 同时多段：'other' = 作用于「另一段活跃关系」而不是焦点
                            if rop[k] not in ("focus", "other"):
                                err(f"{octag} relationOp.target 非法: {rop[k]!r}（合法：focus/other）")
                            continue
                        if k in RELATION_DIMS:
                            rel_delta_keys.add(k)
                            continue
                        if k in RELATION_INIT_KEYS:
                            rel_init_keys.add(k)
                            continue
                        err(f"{octag} relationOp 含未知键 `{k}`"
                            f"（合法：type/state/name/target + {sorted(RELATION_INIT_KEYS)} + {sorted(RELATION_DIMS)}）")
                    if rtype != "spawn" and any(k in rop for k in RELATION_INIT_KEYS):
                        # setState/renew 上使用 init* 是合法的绝对赋值，仅提示
                        pass

                # schedule
                for s in sch:
                    tid = s.get("eventId")
                    if tid not in by_id:
                        err(f"{octag} schedule 引用了不存在的事件 `{tid}`")
                    dh = s.get("delayHours")
                    if isinstance(dh, list) and len(dh) != 2:
                        err(f"{octag} schedule.delayHours 数组长度必须为 2")
                    if "chance" in s and not (0 <= s["chance"] <= 1):
                        err(f"{octag} schedule.chance 必须在 0-1")

                # endingHint
                eh = oc.get("endingHint")
                if eh:
                    p = eh.get("path")
                    if p not in known_paths and p not in path_aliases:
                        err(f"{octag} endingHint.path `{p}` 不在合法取值内")
                    elif p in path_aliases:
                        warn(f"{octag} endingHint.path `{p}` 是别名，"
                             f"构建时将被规范化为 `{path_aliases[p]}`")
                    if not isinstance(eh.get("score"), (int, float)):
                        err(f"{octag} endingHint.score 必须为数字")

        if not has_free_option:
            err(f"{tag} 没有任何无条件选项 —— 玩家可能卡死")

        # 标题长度
        if len(e.get("title", "")) > 12:
            warn(f"{tag} title 长度 {len(e['title'])} > 12 字：{e['title']!r}")

        # key 事件应 once
        if e.get("category") == "key" and not e.get("once"):
            warn(f"{tag} category=key 但 once=false（关键节点通常只触发一次）")

        # 文案长度
        if len(e.get("text", "")) > 120:
            warn(f"{tag} text 长度 {len(e['text'])} > 120 字")
        for o in opts:
            for oc in o.get("outcomes", []):
                if len(oc.get("text", "")) > 100:
                    warn(f"{tag}.{o.get('id')} outcome 文案长度 {len(oc['text'])} > 100 字")

        # 敏感词
        blob = json.dumps(e, ensure_ascii=False)
        for w in BANNED_WORDS:
            if w in blob:
                err(f"{tag} 含敏感词 `{w}`")

    # ---------- 全局校验 ----------
    key_events = [(b, e) for b, e in all_events if e.get("category") == "key"]
    pity_events = [(b, e) for b, e in all_events if e.get("category") == "pity"]
    if not pity_events:
        err("[全局] 没有任何 pity 保底事件")

    # 每个小时段的可触发事件数（粗筛）
    band_counts = Counter()
    for b, e in all_events:
        if e.get("category") in ("key", "chain"):
            continue
        hr = e.get("hoursRange") or [0, 10**9]
        for lo, hi in HOUR_BANDS:
            if hr[0] < hi and hr[1] >= lo:
                band_counts[(lo, hi)] += 1
    for lo, hi in HOUR_BANDS:
        cnt = band_counts[(lo, hi)]
        label = f"{lo}-{hi if hi < 10**9 else '∞'}h"
        if cnt < 10:
            err(f"[覆盖] 时段 {label} 仅有 {cnt} 个非 key 事件（要求 ≥ 10）")

    # 关键节点覆盖
    required_keys = [
        "第一次加好友", "第一次去中文吧", "第一次砂糖", "成为砂糖",
    ]
    titles = " ".join(e.get("title", "") for _, e in all_events)

    # ---------- 报告 ----------
    print("=" * 62)
    print("事件数据校验报告")
    print("=" * 62)
    print(f"\n总事件数      : {len(all_events)}")
    print(f"  key 事件    : {len(key_events)}")
    print(f"  保底事件    : {len(pity_events)}")
    print(f"  唯一 id     : {len(by_id)}")
    print("\n各桶数量:")
    for b in BUCKETS:
        evs = per_bucket.get(b, [])
        k = sum(1 for e in evs if e.get("category") == "key")
        print(f"  {b:<10} {len(evs):>3} 个  (key {k})")

    print("\n分档统计:")
    tier_c = Counter()
    cat_c = Counter()
    rar_c = Counter()
    outcome_total = 0
    option_total = 0
    for _, e in all_events:
        cat_c[e.get("category")] += 1
        rar_c[e.get("rarity")] += 1
        for o in e.get("options", []):
            option_total += 1
            for oc in o.get("outcomes", []):
                outcome_total += 1
                tier_c[oc.get("tier")] += 1
    for k, v in cat_c.most_common():
        print(f"  category {k:<10} {v:>3}")
    for k, v in rar_c.most_common():
        print(f"  rarity   {k:<10} {v:>3}")
    for k, v in tier_c.most_common():
        pct = v / outcome_total * 100 if outcome_total else 0
        print(f"  tier     {k:<10} {v:>3}  ({pct:.1f}%)")
    print(f"\n选项总数      : {option_total}")
    print(f"结果总数      : {outcome_total}")
    if option_total:
        print(f"平均选项/事件 : {option_total/len(all_events):.2f}")
    if outcome_total:
        print(f"平均结果/选项 : {outcome_total/option_total:.2f}")

    print(f"\n时段覆盖:")
    for lo, hi in HOUR_BANDS:
        label = f"{lo}-{hi if hi < 10**9 else '∞'}h"
        print(f"  {label:<12} {band_counts[(lo,hi)]:>3} 个非 key 事件")

    print("\n" + "-" * 62)
    if errors:
        print(f"\n❌ ERROR ({len(errors)}):")
        for m in errors[:60]:
            print(f"  · {m}")
        if len(errors) > 60:
            print(f"  ... 另有 {len(errors)-60} 条")
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
