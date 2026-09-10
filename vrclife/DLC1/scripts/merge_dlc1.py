#!/usr/bin/env python3
"""
把 DLC1 合并进本体数据，产出到 DLC1/build/（不修改 data/ 本体）。

产物:
    DLC1/build/vocab.json          # 本体词表 ∪ DLC 增量
    DLC1/build/endings.json        # 本体结局 ∪ DLC 结局（scoring.vars 追加 favor）
    DLC1/build/archetypes.json     # 本体出生 ∪ DLC 出生
    DLC1/build/events/*.json       # 本体 10 桶 + DLC 4 桶
    DLC1/build/events.index.json   # 合并索引（events / byId / keyEvents / chains / scheduleTargets）

用法:
    python3 DLC1/scripts/merge_dlc1.py
"""

import json
import os
import shutil
import sys
from collections import Counter

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DLC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(DLC_DIR)
DATA = os.path.join(ROOT, "data")
BUILD = os.path.join(DLC_DIR, "build")

BASE_BUCKETS = [
    "intro", "newbie", "social", "sugar_a", "sugar_b",
    "deep", "veteran", "legend", "wild", "idle",
]


def load(p):
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def dump(p, obj):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def union(a, b):
    out = list(a)
    for x in b:
        if x not in out:
            out.append(x)
    return out


def main():
    base_vocab = load(os.path.join(DATA, "vocab.json"))
    dlc_vocab = load(os.path.join(DLC_DIR, "vocab.dlc1.json"))
    add = dlc_vocab["additions"]

    # ---------- vocab ----------
    vocab = dict(base_vocab)
    vocab["circles"] = union(base_vocab["circles"], add["circles"])
    vocab["coreTags"] = union(base_vocab["coreTags"], add["coreTags"])
    vocab["extendedTags"] = union(base_vocab["extendedTags"], add["extendedTags"])
    vocab["eventTags"] = union(base_vocab["eventTags"], add["eventTags"])
    vocab["worldPool"] = union(base_vocab["worldPool"], add["worldPool"])
    vocab["nicknamePool"] = union(base_vocab["nicknamePool"], add["nicknamePool"])
    vocab["endingPaths"] = union(base_vocab["endingPaths"], add["endingPaths"])
    vocab["favorTiers"] = dlc_vocab["favorTiers"]
    vocab["devices"] = dlc_vocab["devices"]
    vocab["_dlc"] = {"name": "DLC1", "version": dlc_vocab["version"]}
    dump(os.path.join(BUILD, "vocab.json"), vocab)

    # ---------- endings ----------
    base_endings = load(os.path.join(DATA, "endings.json"))
    dlc_endings = load(os.path.join(DLC_DIR, "endings.dlc1.json"))
    endings = dict(base_endings)
    endings["endings"] = base_endings["endings"] + dlc_endings["endings"]
    s_vars = union(base_endings["scoring"]["vars"], ["favor"])
    endings["scoring"] = dict(base_endings["scoring"])
    endings["scoring"]["vars"] = s_vars
    endings["endingPaths"] = {
        "desc": base_endings["endingPaths"]["desc"],
        "paths": union(base_endings["endingPaths"]["paths"], dlc_endings["endingPaths"]),
    }
    dump(os.path.join(BUILD, "endings.json"), endings)

    # ---------- archetypes ----------
    base_arch = load(os.path.join(DATA, "archetypes.json"))
    dlc_arch = load(os.path.join(DLC_DIR, "archetypes.dlc1.json"))
    arch = dict(base_arch)
    arch["archetypes"] = base_arch["archetypes"] + dlc_arch["archetypes"]
    dump(os.path.join(BUILD, "archetypes.json"), arch)

    # ---------- events ----------
    events_dir = os.path.join(BUILD, "events")
    os.makedirs(events_dir, exist_ok=True)
    for b in BASE_BUCKETS:
        src = os.path.join(DATA, "events", f"{b}.json")
        if os.path.exists(src):
            shutil.copyfile(src, os.path.join(events_dir, f"{b}.json"))
    dlc_src_dir = os.path.join(DLC_DIR, "events")
    dlc_buckets = []
    for fn in sorted(os.listdir(dlc_src_dir)):
        if fn.endswith(".json"):
            shutil.copyfile(os.path.join(dlc_src_dir, fn),
                            os.path.join(events_dir, fn))
            dlc_buckets.append(fn[:-5])

    # ---------- events.index ----------
    all_events = []
    by_bucket = {}
    order = BASE_BUCKETS + dlc_buckets
    for b in order:
        p = os.path.join(events_dir, f"{b}.json")
        if not os.path.exists(p):
            continue
        evs = load(p).get("events", [])
        by_bucket[b] = len(evs)
        all_events.extend(evs)

    by_id = {e["id"]: e for e in all_events if "id" in e}
    cat_c = Counter(e.get("category") for e in all_events)
    rar_c = Counter(e.get("rarity") for e in all_events)
    tier_c = Counter()
    for e in all_events:
        for o in e.get("options", []):
            for oc in o.get("outcomes", []):
                tier_c[oc.get("tier")] += 1
    key_events = [e["id"] for e in all_events if e.get("category") == "key"]

    chains, targets = {}, {}
    for e in all_events:
        eid = e.get("id")
        for o in e.get("options", []):
            for oc in o.get("outcomes", []):
                for s in oc.get("schedule", []) or []:
                    tid = s.get("eventId")
                    if not tid:
                        continue
                    chains.setdefault(eid, []).append({
                        "eventId": tid,
                        "delayHours": s.get("delayHours"),
                        "chance": s.get("chance", 1.0),
                    })
                    targets.setdefault(tid, [])
                    if eid not in targets[tid]:
                        targets[tid].append(eid)

    index = {
        "version": "1.0",
        "dlc": "DLC1",
        "counts": {
            "total": len(all_events),
            "byBucket": by_bucket,
            "byCategory": dict(cat_c),
            "byRarity": dict(rar_c),
            "byTier": dict(tier_c),
            "keyEvents": len(key_events),
            "options": sum(len(e.get("options", [])) for e in all_events),
            "outcomes": sum(len(o.get("outcomes", [])) for e in all_events
                            for o in e.get("options", [])),
        },
        "events": all_events,
        "byId": by_id,
        "keyEvents": key_events,
        "chains": chains,
        "scheduleTargets": targets,
    }
    dump(os.path.join(BUILD, "events.index.json"), index)

    orphan = [t for t in targets if t not in by_id]
    size = os.path.getsize(os.path.join(BUILD, "events.index.json"))
    print("✅ DLC1 已合并到 DLC1/build/")
    print(f"   事件 {len(all_events)} 个（本体 296 + DLC {len(all_events)-296}）| "
          f"key {len(key_events)} | 选项 {index['counts']['options']} | 结果 {index['counts']['outcomes']}")
    print(f"   DLC 桶: " + "  ".join(f"{b}={by_bucket.get(b,0)}" for b in dlc_buckets))
    print(f"   结局 {len(endings['endings'])} 个 | 出生 {len(arch['archetypes'])} 个 | "
          f"index {size/1024:.0f} KB")
    if orphan:
        print(f"   ⚠️  {len(orphan)} 个 schedule 目标不存在: {orphan[:10]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
