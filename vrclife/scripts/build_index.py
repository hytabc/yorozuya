#!/usr/bin/env python3
"""
合并所有事件桶 → data/events.index.json

产物结构:
{
  "version": "1.0",
  "generatedFrom": {...},
  "counts": { total, byBucket, byCategory, byRarity, byTier, keyEvents },
  "events": [ ...全部事件... ],
  "byId": { "<id>": <event> },
  "keyEvents": ["id", ...],
  "chains": { "<eventId>": [ {eventId, delayHours, chance}, ... ] },
  "scheduleTargets": { "<eventId>": ["来源id", ...] }
}
"""

import json
import os
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
EVENTS_DIR = os.path.join(DATA, "events")

BUCKETS = [
    "intro", "newbie", "social", "sugar_a", "sugar_b",
    "deep", "veteran", "legend", "wild", "idle",
]


def canonicalize_paths(events, vocab):
    """把 endingHint.path 的别名规范化为 endings.json 中的标准 path。返回改写次数。"""
    aliases = vocab.get("endingPathAliases", {})
    legal = set(vocab.get("endingPaths", []))
    n = 0
    for e in events:
        for o in e.get("options", []):
            for oc in o.get("outcomes", []):
                eh = oc.get("endingHint")
                if not eh:
                    continue
                p = eh.get("path")
                if p in aliases:
                    eh["path"] = aliases[p]
                    n += 1
                elif p not in legal:
                    eh["path"] = None
                    eh["_unmappedPath"] = p
                    n += 1
    return n


def main():
    with open(os.path.join(DATA, "vocab.json"), "r", encoding="utf-8") as f:
        vocab = json.load(f)

    events = []
    by_bucket = {}
    sources = {}

    for b in BUCKETS:
        p = os.path.join(EVENTS_DIR, f"{b}.json")
        if not os.path.exists(p):
            print(f"  ! 跳过缺失的 {b}.json")
            continue
        with open(p, "r", encoding="utf-8") as f:
            doc = json.load(f)
        evs = doc.get("events", [])
        by_bucket[b] = len(evs)
        sources[b] = {"file": f"data/events/{b}.json", "version": doc.get("version"), "count": len(evs)}
        events.extend(evs)

    n_alias = canonicalize_paths(events, vocab)
    by_id = {e["id"]: e for e in events if "id" in e}

    cat_c = Counter(e.get("category") for e in events)
    rar_c = Counter(e.get("rarity") for e in events)
    tier_c = Counter()
    for e in events:
        for o in e.get("options", []):
            for oc in o.get("outcomes", []):
                tier_c[oc.get("tier")] += 1

    key_events = [e["id"] for e in events if e.get("category") == "key"]

    chains = {}
    targets = {}
    for e in events:
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

    out = {
        "version": "1.0",
        "generatedFrom": sources,
        "counts": {
            "total": len(events),
            "byBucket": by_bucket,
            "byCategory": dict(cat_c),
            "byRarity": dict(rar_c),
            "byTier": dict(tier_c),
            "keyEvents": len(key_events),
            "options": sum(len(e.get("options", [])) for e in events),
            "outcomes": sum(
                len(o.get("outcomes", []))
                for e in events for o in e.get("options", [])
            ),
        },
        "events": events,
        "byId": by_id,
        "keyEvents": key_events,
        "chains": chains,
        "scheduleTargets": targets,
    }

    dst = os.path.join(DATA, "events.index.json")
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    size = os.path.getsize(dst)
    print(f"✅ 已生成 {os.path.relpath(dst, ROOT)}  ({size/1024:.0f} KB)")
    print(f"   事件 {len(events)} 个 | key {len(key_events)} 个 | "
          f"选项 {out['counts']['options']} | 结果 {out['counts']['outcomes']}")
    print(f"   各桶: " + "  ".join(f"{b}={n}" for b, n in by_bucket.items()))
    if n_alias:
        print(f"   ↻ 规范化了 {n_alias} 处 endingHint.path 别名")
    orphan = [tid for tid in targets if tid not in by_id]
    if orphan:
        print(f"   ⚠️  {len(orphan)} 个 schedule 目标不存在: {orphan[:10]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
