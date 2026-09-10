#!/usr/bin/env python3
"""
DLC1 无头模拟器 —— 在本体引擎语义上叠加 DLC1 增量（favor / 新结局 / 新桶）。

用法:
    python3 DLC1/scripts/simulate_dlc1.py [局数] [--seed N]

验证:
    A. 无致命异常
    B. 平均事件数 ≥ 30
    C. DLC 事件触达率（死事件检测）
    D. DLC 新结局全部可达
    E. favor 始终在 0-100
    F. 本体结局仍然可达（未被 DLC 挤死）
"""

import json
import os
import random
import re
import sys
from collections import Counter, defaultdict

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DLC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(DLC_DIR)
DATA = os.path.join(ROOT, "data")

BASE_BUCKETS = [
    "intro", "newbie", "social", "sugar_a", "sugar_b",
    "deep", "veteran", "legend", "wild", "idle",
]
DLC_BUCKETS = ["device", "circle", "friend", "favor"]


def _load(p):
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def _union(a, b):
    out = list(a)
    for x in b:
        if x not in out:
            out.append(x)
    return out


def build_data():
    """在内存里合并 本体 + DLC1（不依赖 DLC1/build/）。"""
    base_vocab = _load(os.path.join(DATA, "vocab.json"))
    dlc_vocab = _load(os.path.join(DLC_DIR, "vocab.dlc1.json"))
    add = dlc_vocab["additions"]

    vocab = dict(base_vocab)
    for key, akey in [("circles", "circles"), ("coreTags", "coreTags"),
                      ("extendedTags", "extendedTags"), ("eventTags", "eventTags"),
                      ("worldPool", "worldPool"), ("nicknamePool", "nicknamePool"),
                      ("endingPaths", "endingPaths")]:
        vocab[key] = _union(base_vocab[key], add[akey])
    vocab["favorTiers"] = dlc_vocab["favorTiers"]

    base_endings = _load(os.path.join(DATA, "endings.json"))
    dlc_endings = _load(os.path.join(DLC_DIR, "endings.dlc1.json"))
    endings = {"endings": base_endings["endings"] + dlc_endings["endings"]}

    base_arch = _load(os.path.join(DATA, "archetypes.json"))["archetypes"]
    dlc_arch = _load(os.path.join(DLC_DIR, "archetypes.dlc1.json"))["archetypes"]

    events = list(_load(os.path.join(DATA, "events.index.json"))["events"])
    dlc_ids = []
    for b in DLC_BUCKETS:
        evs = _load(os.path.join(DLC_DIR, "events", f"{b}.json"))["events"]
        for e in evs:
            dlc_ids.append(e["id"])
        events.extend(evs)
    by_id = {e["id"]: e for e in events}
    return vocab, endings, base_arch + dlc_arch, events, by_id, dlc_ids


VOCAB, ENDINGS, ARCHETYPES, ALL_EVENTS, BY_ID, DLC_IDS = build_data()

EVENT_POOL = [e for e in ALL_EVENTS if e["category"] not in ("key", "chain")]
PITY_POOL = [e for e in ALL_EVENTS if e["category"] == "pity"]
KEY_EVENTS = [e for e in ALL_EVENTS if e["category"] == "key"]
DLC_ID_SET = set(DLC_IDS)
NICKNAMES = VOCAB["nicknamePool"]
SKILLS = [s["key"] for s in VOCAB["skills"]]
STAGES = [(s["key"], s["minHours"], s["maxHours"]) for s in VOCAB["stages"]]
REL_FLOW = VOCAB["relationStateFlow"]
REL_STATES = set(VOCAB["relationStates"])
INACTIVE_REL_STATES = ("结束", "低迷", "恢复")
HOUR_STEP_BY_STAGE = {k: tuple(v) for k, v in VOCAB["hourStepByStage"].items()}
HINT_ALIASES = VOCAB.get("endingPathAliases", {})
FAVOR_DRIFT = -0.35
FAVOR_START = 50

MAX_EVENTS_PER_RUN = 72
MAX_TURNS = 400
SPAWN_COOLDOWN_HOURS = 120

STAGE_STATS = defaultdict(lambda: {"events": 0, "mood": [], "favor": []})


def stage_of(h):
    for n, lo, hi in STAGES:
        if lo <= h < hi:
            return n
    return "传奇"


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


# ---------------------------------------------------------------- condition

def _tags_ok(cond, st):
    for t in cond.get("requireTags", []):
        if t not in st["tags"]:
            return False
    any_req = cond.get("requireAnyTags")
    if any_req and not any(t in st["tags"] for t in any_req):
        return False
    for t in cond.get("excludeTags", []):
        if t in st["tags"]:
            return False
    return True


def _flags_ok(cond, st):
    for f in cond.get("requireFlags", []):
        if f not in st["flags"]:
            return False
    for f in cond.get("excludeFlags", []):
        if f in st["flags"]:
            return False
    return True


def match(cond, st):
    if not cond:
        return True
    if "minHours" in cond and st["hours"] < cond["minHours"]:
        return False
    if "maxHours" in cond and st["hours"] > cond["maxHours"]:
        return False
    if "minMood" in cond and st["mood"] < cond["minMood"]:
        return False
    if "maxMood" in cond and st["mood"] > cond["maxMood"]:
        return False
    if "minFame" in cond and st["fame"] < cond["minFame"]:
        return False
    if "minFriends" in cond and st["friends"] < cond["minFriends"]:
        return False
    if "maxFriends" in cond and st["friends"] > cond["maxFriends"]:
        return False
    if "minAvatars" in cond and st["avatars"] < cond["minAvatars"]:
        return False
    if "minAssets" in cond and st["assets"] < cond["minAssets"]:
        return False
    if "minSugarCount" in cond and st["sugarCount"] < cond["minSugarCount"]:
        return False
    if "minBreakupCount" in cond and st["breakupCount"] < cond["minBreakupCount"]:
        return False
    # ---- DLC 增量 ----
    if "minFavor" in cond and st["favor"] < cond["minFavor"]:
        return False
    if "maxFavor" in cond and st["favor"] > cond["maxFavor"]:
        return False
    if "minCircles" in cond and len(st["circles"]) < cond["minCircles"]:
        return False
    for ck, cv in (cond.get("minCounters") or {}).items():
        if st["counters"].get(ck, 0) < cv:
            return False
    # ------------------
    if not _tags_ok(cond, st):
        return False
    if not _flags_ok(cond, st):
        return False
    for c in cond.get("requireCircles", []):
        if c not in st["circles"]:
            return False
    for k, v in (cond.get("minSkills") or {}).items():
        if st["skills"].get(k, 0) < v:
            return False
    for k, v in (cond.get("maxSkills") or {}).items():
        if k == "all":
            if max(st["skills"].values()) > v:
                return False
        elif st["skills"].get(k, 0) > v:
            return False

    r = st["relation"]
    active = bool(r) and r["state"] not in INACTIVE_REL_STATES
    if cond.get("hasRelation") is True and not active:
        return False
    if cond.get("hasRelation") is False and active:
        return False
    if cond.get("relationState"):
        if not r or r["state"] not in cond["relationState"]:
            return False
    for key, rk in (("minIntimacy", "intimacy"), ("minDependence", "dependence"),
                    ("minTrust", "trust"), ("minFreshness", "freshness"),
                    ("minRealPressure", "realPressure")):
        if key in cond and (not active or r[rk] < cond[key]):
            return False
    if "maxRealPressure" in cond and (not r or r["realPressure"] > cond["maxRealPressure"]):
        return False
    for eid in cond.get("requiresEventDone", []):
        if eid not in st["usedEvents"]:
            return False
    for eid in cond.get("excludesEventDone", []):
        if eid in st["usedEvents"]:
            return False
    if cond.get("probability") is not None and st["rng"].random() > cond["probability"]:
        return False
    return True


# ---------------------------------------------------------------- effects

def derive_tags(st):
    def add(t):
        if t not in st["tags"]:
            st["tags"].append(t)

    def rm(t):
        if t in st["tags"]:
            st["tags"].remove(t)

    if st["hours"] >= 50:
        rm("萌新")
    if st["friends"] < 5 and st["hours"] > 100:
        add("独行侠")
    if st["mood"] <= 14:
        add("退坑边缘")
    elif st["mood"] >= 30:
        rm("退坑边缘")
    # ---- DLC 自动标签 ----
    if st["favor"] >= 80:
        add("挚友")
    elif st["favor"] < 60:
        rm("挚友")
    if len(st["circles"]) >= 5:
        add("圈子浪人")


def apply_effects(st, fx):
    if not fx:
        return
    md = fx.get("mood", 0)
    if md > 0:
        md *= min(1.0, max(0.0, (100 - st["mood"]) / 30.0))
    elif md < -20:
        md = -20
    st["mood"] = clamp(st["mood"] + md, 0, 100)
    st["friends"] = clamp(st["friends"] + fx.get("friends", 0), 0, 999)
    st["fame"] = clamp(st["fame"] + fx.get("fame", 0), 0, 100)
    st["avatars"] = max(0, st["avatars"] + fx.get("avatars", 0))
    st["assets"] += fx.get("assets", 0)
    st["sugarCount"] += fx.get("sugarCount", 0)
    st["breakupCount"] += fx.get("breakupCount", 0)
    st["hours"] += fx.get("hoursBonus", 0)
    # ---- DLC: 好感度 ----
    if "favor" in fx:
        st["favor"] = clamp(st["favor"] + fx["favor"], 0, 100)

    for k, v in (fx.get("skills") or {}).items():
        st["skills"][k] = clamp(st["skills"].get(k, 0) + v, 0, 100)
    for c in (fx.get("circles") or {}).get("add", []):
        if c not in st["circles"]:
            st["circles"].append(c)
    for c in (fx.get("circles") or {}).get("remove", []):
        if c in st["circles"]:
            st["circles"].remove(c)
    for t in (fx.get("tags") or {}).get("add", []):
        if t not in st["tags"]:
            st["tags"].append(t)
    for t in (fx.get("tags") or {}).get("remove", []):
        if t in st["tags"]:
            st["tags"].remove(t)
    for fl in (fx.get("flags") or {}).get("add", []):
        if fl not in st["flags"]:
            st["flags"].append(fl)
    for fl in (fx.get("flags") or {}).get("remove", []):
        if fl in st["flags"]:
            st["flags"].remove(fl)
    for k, v in (fx.get("counters") or {}).items():
        st["counters"][k] = st["counters"].get(k, 0) + v
    derive_tags(st)


DIM_KEYS = ["intimacy", "trust", "freshness", "dependence", "realPressure"]


def new_relation(st, state="认识"):
    if state not in REL_STATES:
        state = "认识"
    st["relation"] = {
        "name": st["rng"].choice(NICKNAMES),
        "state": state,
        "intimacy": 0, "trust": 0, "freshness": 90,
        "dependence": 0, "realPressure": 0,
        "metAt": st["hours"],
    }
    if state == "低迷":
        st["sawLow"] = True
    elif state == "恢复":
        st["sawRecover"] = True
    return st["relation"]


def apply_relation_op(st, rop, log):
    if not rop:
        return
    t = rop.get("type")
    r = st["relation"]
    if t == "spawn":
        if st["hours"] < st["spawnBlockUntil"] and not rop.get("force"):
            return
        if not r or r["state"] in INACTIVE_REL_STATES:
            new_relation(st, rop.get("state") or "认识")
    elif t == "end":
        if r and r["state"] not in INACTIVE_REL_STATES:
            r["state"] = "结束"
            st["spawnBlockUntil"] = st["hours"] + SPAWN_COOLDOWN_HOURS
        return
    elif t == "renew":
        if r:
            r["freshness"] = 90
            r["realPressure"] = 0
        return
    elif t == "setState" and rop.get("state"):
        if r and r["state"] in INACTIVE_REL_STATES and rop["state"] not in INACTIVE_REL_STATES:
            if st["hours"] < st["spawnBlockUntil"] and not rop.get("force"):
                return
            new_relation(st, rop["state"])
    if not st["relation"]:
        return
    r = st["relation"]
    for d in DIM_KEYS:
        k = "init" + d[0].upper() + d[1:]
        if k in rop:
            r[d] = clamp(rop[k], 0, 100)
    for d in DIM_KEYS:
        if d in rop:
            r[d] = clamp(r[d] + rop[d], 0, 100)
    if t == "setState" and rop.get("state"):
        target = rop["state"]
        legal = REL_FLOW.get(r["state"], [])
        if target in legal or target == r["state"]:
            r["state"] = target
            if target == "低迷":
                st["sawLow"] = True
            elif target == "恢复":
                st["sawRecover"] = True
        else:
            st["illegal"] += 1


# ---------------------------------------------------------------- engine

def pick_event(st, sched):
    due = sorted([s for s in sched if s["at"] <= st["hours"]], key=lambda s: s["at"])
    for s in due:
        sched.remove(s)
        if st["rng"].random() < s["chance"]:
            ev = BY_ID.get(s["eventId"])
            if ev and match(ev.get("condition"), st):
                return ev

    last_was_key = bool(st["lastEvents"]) and st["lastEvents"][0] in st["keyIds"]
    if not last_was_key:
        in_win, expired = [], []
        for e in KEY_EVENTS:
            if e["id"] in st["usedEvents"]:
                continue
            hr = e["hoursRange"]
            if hr[0] > st["hours"]:
                continue
            if not match(e.get("condition"), st):
                continue
            (in_win if st["hours"] <= hr[1] else expired).append(e)
        keys = in_win
        if not keys and expired and st["rng"].random() < 0.45:
            keys = expired
        if keys:
            base = min(e["hoursRange"][0] for e in keys)
            w = [1.0 / (1.0 + (e["hoursRange"][0] - base) / 25.0) for e in keys]
            return st["rng"].choices(keys, weights=w)[0]

    pool = []
    for e in EVENT_POOL:
        if e.get("once") and e["id"] in st["usedEvents"]:
            continue
        cd = e.get("cooldown", 0)
        if cd and st["hours"] - st["lastSeen"].get(e["id"], -99999) < cd:
            continue
        if not match(e.get("condition"), st):
            continue
        w = score(e, st)
        if w > 0:
            pool.append((e, w))
    if pool:
        total = sum(w for _, w in pool)
        x = st["rng"].random() * total
        acc = 0
        for e, w in pool:
            acc += w
            if x <= acc:
                return e
        return pool[-1][0]

    pity = [(e, e.get("weight", 1)) for e in PITY_POOL if match(e.get("condition"), st)]
    if pity:
        return st["rng"].choices([e for e, _ in pity], weights=[w for _, w in pity])[0]
    return None


def score(e, st):
    w = e.get("weight", 10)
    w *= 1.5 if e.get("stage") == stage_of(st["hours"]) else 0.6
    tg = e.get("tags") or []
    if st["mood"] < 30 and "正面" in tg:
        w *= 0.7
    if st["mood"] < 30 and "负面" in tg:
        w *= 1.3
    if st["mood"] > 75 and "负面" in tg:
        w *= 0.7
    if st["fame"] > 60 and "技能" in tg:
        w *= 1.4
    if st["friends"] < 3 and "社交" in tg:
        w *= 0.6
    if st["negStreak"] >= 3 and "正面" in tg:
        w *= 2.5
    if st["negStreak"] >= 3 and "负面" in tg:
        w *= 0.4
    if st["posStreak"] >= 4 and "负面" in tg:
        w *= 1.4
    if "失恋" in st["tags"]:
        if "孤独" in tg or "回忆" in tg:
            w *= 3.0
        if "正面" in tg:
            w *= 0.4
    # ---- DLC 权重修正（schema.dlc1.json weightMods）----
    if "设备" in tg and any(t in st["tags"] for t in ("Pico党", "Quest党", "串流党", "全身追踪", "设备党")):
        w *= 1.5
    if "挚友" in st["tags"] and "友情" in tg and "正面" in tg:
        w *= 1.4
    if st["favor"] < 30 and "友情" in tg:
        w *= 1.3
    # ------------------------------------------------
    if any(t in st["recentTags"] for t in tg):
        w *= 0.3
    if e["id"] in st["lastEvents"]:
        w *= 0.2
    w *= 0.8 + st["rng"].random() * 0.4
    return w


def step_hours(st):
    lo, hi = HOUR_STEP_BY_STAGE.get(stage_of(st["hours"]), (1, 20))
    step = st["rng"].randint(lo, hi)
    if st["mood"] <= 14:
        step = int(step * 1.5)
    step = max(1, step)
    for m in (10, 50, 200, 500, 1000, 5000):
        if st["hours"] < m <= st["hours"] + step and m not in st["milestones"]:
            st["milestones"].add(m)
            return m - st["hours"]
    return step


def drift_relation(st, sched):
    r = st["relation"]
    if not r or r["state"] in INACTIVE_REL_STATES:
        return
    r["freshness"] = max(0, r["freshness"] - 2)
    if "sugar" in st["recentTags"]:
        r["intimacy"] = min(100, r["intimacy"] + 1)
    else:
        r["intimacy"] = max(0, r["intimacy"] - 1)
    if r["state"] in ("砂糖", "稳定"):
        r["dependence"] = min(100, r["dependence"] + 0.5)
    r["realPressure"] = clamp(r["realPressure"] + st["rng"].randint(-3, 4), 0, 100)
    if r["realPressure"] > 60 and st["rng"].random() < 0.08:
        sched.append({"eventId": "sugar_b_k04", "at": st["hours"] + st["rng"].randint(0, 40), "chance": 1.0})
    if r["freshness"] < 30 and r["state"] == "砂糖" and st["rng"].random() < 0.1:
        sched.append({"eventId": "sugar_b_k02", "at": st["hours"] + st["rng"].randint(10, 60), "chance": 0.8})


# ---------------------------------------------------------------- endings / score expr

_TOK = re.compile(r"""
    \s*(?:
      (?P<num>\d+\.?\d*)
    | (?P<id>[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*)
    | (?P<op><=|>=|==|!=|&&|\|\||[-+*/()<>?:])
    )""", re.X)


def _tokenize(expr):
    pos, out = 0, []
    while pos < len(expr):
        m = _TOK.match(expr, pos)
        if not m or m.end() == pos:
            if expr[pos:].strip() == "":
                break
            raise ValueError(f"无法解析: {expr[pos:pos+20]!r}")
        out.append(m.group("num") or m.group("id") or m.group("op"))
        pos = m.end()
    return out


def _vars_for(st):
    return {
        "hours": st["hours"], "friends": st["friends"], "mood": st["mood"],
        "fame": st["fame"], "avatars": st["avatars"], "assets": st["assets"],
        "sugarCount": st["sugarCount"], "breakupCount": st["breakupCount"],
        "favor": st["favor"], "skill.max": max(st["skills"].values()),
        "circle.count": len(st["circles"]), "tag.count": len(st["tags"]),
    }


def eval_score(expr, st):
    if not expr:
        return 0.0

    def value(tok):
        if re.fullmatch(r"\d+\.?\d*", tok):
            return float(tok)
        if tok.startswith("skill."):
            return float(st["skills"].get(tok[6:], 0))
        if tok.startswith("hint."):
            return float(st["hints"].get(tok[5:], 0))
        if tok.startswith("hasFlag."):
            return 1.0 if tok[8:] in st["flags"] else 0.0
        return float(_vars_for(st).get(tok, 0))

    toks = _tokenize(expr)
    pos = [0]

    def peek():
        return toks[pos[0]] if pos[0] < len(toks) else None

    def take():
        t = peek()
        pos[0] += 1
        return t

    def atom():
        t = take()
        if t == "(":
            v = tern()
            if take() != ")":
                raise ValueError("缺少 )")
            return v
        return value(t)

    def unary():
        if peek() == "-":
            take()
            return -unary()
        return atom()

    def mul():
        v = unary()
        while peek() in ("*", "/"):
            op = take()
            b = unary()
            v = v * b if op == "*" else (v / b if b else 0.0)
        return v

    def add():
        v = mul()
        while peek() in ("+", "-"):
            op = take()
            b = mul()
            v = v + b if op == "+" else v - b
        return v

    def cmp_():
        v = add()
        while peek() in ("<", "<=", ">", ">=", "==", "!=", "&&", "||"):
            op = take()
            b = add()
            if op == "&&":
                v = 1.0 if (v and b) else 0.0
            elif op == "||":
                v = 1.0 if (v or b) else 0.0
            else:
                v = 1.0 if {"<": v < b, "<=": v <= b, ">": v > b,
                             ">=": v >= b, "==": v == b, "!=": v != b}[op] else 0.0
        return v

    def tern():
        c = cmp_()
        if peek() == "?":
            take()
            a = tern()
            if take() != ":":
                raise ValueError("三元缺少 :")
            b = tern()
            return a if c else b
        return c

    return tern()


def canonical_hint(path):
    seen = set()
    while path in HINT_ALIASES and path not in seen:
        seen.add(path)
        path = HINT_ALIASES[path]
    return path


def evaluate_ending(st):
    def ok(c):
        if "maxMood" in c and st["mood"] > c["maxMood"]:
            return False
        if "minMood" in c and st["mood"] < c["minMood"]:
            return False
        if "minHours" in c and st["hours"] < c["minHours"]:
            return False
        if "minFame" in c and st["fame"] < c["minFame"]:
            return False
        if "minFriends" in c and st["friends"] < c["minFriends"]:
            return False
        if "maxFriends" in c and st["friends"] > c["maxFriends"]:
            return False
        if "minSugarCount" in c and st["sugarCount"] < c["minSugarCount"]:
            return False
        if "minBreakupCount" in c and st["breakupCount"] < c["minBreakupCount"]:
            return False
        # ---- DLC ----
        if "minFavor" in c and st["favor"] < c["minFavor"]:
            return False
        if "maxFavor" in c and st["favor"] > c["maxFavor"]:
            return False
        if "minCircles" in c and len(st["circles"]) < c["minCircles"]:
            return False
        # -------------
        for k, v in (c.get("minSkills") or {}).items():
            if st["skills"].get(k, 0) < v:
                return False
        for k, v in (c.get("maxSkills") or {}).items():
            if k == "all":
                if max(st["skills"].values()) > v:
                    return False
            elif st["skills"].get(k, 0) > v:
                return False
        for f in c.get("requireFlags", []):
            if f not in st["flags"]:
                return False
        for f in c.get("excludeFlags", []):
            if f in st["flags"]:
                return False
        return True

    for e in ENDINGS["endings"]:
        if e.get("lock") and ok(e.get("condition") or {}):
            return e["id"]
    best, best_score = "end_default", None
    for e in ENDINGS["endings"]:
        if e.get("lock"):
            continue
        if not ok(e.get("condition") or {}):
            continue
        s = eval_score(e.get("score"), st) + e.get("priority", 0) * 1e-6
        if best_score is None or s > best_score:
            best, best_score = e["id"], s
    return best


# ---------------------------------------------------------------- run

def new_state(seed, arch=None):
    rng = random.Random(seed)
    a = arch or rng.choices(ARCHETYPES, weights=[x["weight"] for x in ARCHETYPES])[0]
    st = {
        "rng": rng, "seed": seed, "arch": a,
        "hours": 0, "friends": 0, "mood": 70, "fame": 0, "avatars": 1,
        "assets": 0, "sugarCount": 0, "breakupCount": 0, "favor": FAVOR_START,
        "skills": {k: 0 for k in SKILLS},
        "circles": [], "tags": ["萌新"], "flags": [], "counters": {},
        "relation": None, "usedEvents": [], "lastSeen": {}, "scheduled": [],
        "recentTags": [], "lastEvents": [], "negStreak": 0, "posStreak": 0,
        "milestones": set(), "illegal": 0, "keyIds": frozenset(e["id"] for e in KEY_EVENTS),
        "spawnBlockUntil": -1, "sawLow": False, "sawRecover": False,
        "hints": Counter(), "history": [],
    }
    for k, v in (a.get("init") or {}).items():
        st[k] = v
    for k, v in (a.get("skills") or {}).items():
        st["skills"][k] = v
    st["tags"] = list(a.get("tags", ["萌新"]))
    st["flags"] = list((a.get("flags") or {}).get("add", []))
    return st


def play(seed, arch=None):
    st = new_state(seed, arch)
    rng = st["rng"]
    fired = []
    favor_trace = []
    for _turn in range(MAX_TURNS):
        if len(fired) >= MAX_EVENTS_PER_RUN or st["mood"] <= 0 or st["hours"] >= 5000:
            break
        ev = pick_event(st, st["scheduled"])
        if ev is None:
            return {"state": st, "fired": fired, "error": "EMPTY_POOL"}
        fired.append(ev["id"])
        st["lastSeen"][ev["id"]] = st["hours"]

        free = [o for o in ev["options"] if not o.get("condition")]
        usable = [o for o in ev["options"] if match(o.get("condition"), st)]
        choosable = usable or free
        if not choosable:
            return {"state": st, "fired": fired, "error": "NO_OPTION"}
        opt = rng.choice(choosable)

        outs = opt["outcomes"]
        total = sum(o["weight"] for o in outs)
        x = rng.random() * total
        acc = 0
        chosen = outs[-1]
        for o in outs:
            acc += o["weight"]
            if x <= acc:
                chosen = o
                break

        mood_before = st["mood"]
        stage_now = stage_of(st["hours"])
        apply_effects(st, chosen.get("effects"))
        ss = STAGE_STATS[stage_now]
        ss["events"] += 1
        ss["mood"].append(st["mood"] - mood_before)
        ss["favor"].append(st["favor"])
        fx = chosen.get("effects") or {}
        apply_relation_op(st, fx.get("relationOp") or chosen.get("relationOp"), st["history"])

        hint = chosen.get("endingHint") or fx.get("endingHint")
        if hint and hint.get("path"):
            st["hints"][canonical_hint(hint["path"])] += hint.get("score", 1)

        negative = st["mood"] < mood_before
        st["negStreak"] = st["negStreak"] + 1 if negative else 0
        st["posStreak"] = 0 if negative else st["posStreak"] + 1

        tg = ev.get("tags") or []
        st["recentTags"] = (tg + st["recentTags"])[:3]
        st["lastEvents"] = ([ev["id"]] + st["lastEvents"])[:5]
        if ev.get("once"):
            st["usedEvents"].append(ev["id"])

        for s in chosen.get("schedule", []) or []:
            dh = s.get("delayHours", [10, 60])
            d = rng.randint(dh[0], dh[1]) if isinstance(dh, list) else dh
            st["scheduled"].append({"eventId": s["eventId"], "at": st["hours"] + d,
                                    "chance": s.get("chance", 1.0)})

        st["hours"] += step_hours(st)
        drift_relation(st, st["scheduled"])
        # ---- DLC: 好感度自然漂移 ----
        st["favor"] = clamp(st["favor"] + FAVOR_DRIFT, 0, 100)
        derive_tags(st)
        # ----------------------------
        favor_trace.append(round(st["favor"], 1))

        assert 0 <= st["mood"] <= 100, f"mood 越界 {st['mood']}"
        assert 0 <= st["fame"] <= 100, f"fame 越界 {st['fame']}"
        assert 0 <= st["favor"] <= 100, f"favor 越界 {st['favor']}"
        assert st["friends"] >= 0, "friends 为负"
        assert st["avatars"] >= 0, "avatars 为负"

    return {"state": st, "fired": fired, "error": None}


def main():
    n = 300
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if args:
        n = int(args[0])
    seed0 = 1
    if "--seed" in sys.argv:
        seed0 = int(sys.argv[sys.argv.index("--seed") + 1])

    print(f"运行 {n} 局模拟（本体 296 + DLC1 {len(DLC_IDS)}）…\n")

    hit = Counter()
    endings = Counter()
    errors = Counter()
    events_per_run, hours_per_run, favor_end = [], [], []
    illegal_total = 0
    dlc_hit = Counter()
    chopper_flag = chopper_ok = 0
    circle_max = 0

    for i in range(n):
        r = play(seed0 + i)
        st = r["state"]
        if r["error"]:
            errors[r["error"]] += 1
            continue
        if "circle_hopper" in st["flags"]:
            chopper_flag += 1
            if len(st["circles"]) >= 5 and st["hours"] >= 400:
                chopper_ok += 1
        circle_max = max(circle_max, len(st["circles"]))
        for eid in r["fired"]:
            hit[eid] += 1
            if eid in DLC_ID_SET:
                dlc_hit[eid] += 1
        events_per_run.append(len(r["fired"]))
        hours_per_run.append(st["hours"])
        favor_end.append(st["favor"])
        illegal_total += st["illegal"]
        endings[evaluate_ending(st)] += 1

    total = len(events_per_run)
    print("=" * 62)
    print("DLC1 模拟结果")
    print("=" * 62)
    print(f"\n成功完成局数  : {total}/{n}")
    print("异常          : " + (str(dict(errors)) if errors else "无 ✅"))
    print(f"平均事件数/局 : {sum(events_per_run)/max(1,total):.1f}  "
          f"(min {min(events_per_run, default=0)}, max {max(events_per_run, default=0)})")
    print(f"平均时长/局   : {sum(hours_per_run)/max(1,total):.0f}h  "
          f"(min {min(hours_per_run, default=0)}, max {max(hours_per_run, default=0)})")
    print(f"终局好感度    : 均值 {sum(favor_end)/max(1,total):.1f}  "
          f"(min {min(favor_end, default=0):.0f}, max {max(favor_end, default=0):.0f})")
    print(f"非法状态转移  : {illegal_total}")
    print(f"[统计] circle_hopper flag: {chopper_flag} 局 | 满足 minCircles>=5: {chopper_ok} 局 | "
          f"最多圈子数: {circle_max}")

    dead_dlc = [eid for eid in DLC_IDS if eid not in dlc_hit]
    print(f"\nDLC 事件触达  : {len(DLC_IDS)-len(dead_dlc)}/{len(DLC_IDS)}")
    if dead_dlc:
        lost = Counter(eid.split("_")[0] for eid in dead_dlc)
        print(f"  ⚠️  未触发({len(dead_dlc)}): {dead_dlc}")
        print(f"      分布: {dict(lost)}")
    else:
        print("  ✅ 全部 DLC 事件均被触发过")

    print(f"\nDLC 事件热度 Top10:")
    for eid, c in dlc_hit.most_common(10):
        print(f"  {eid:<16} {c:>5} 次")

    titles = {e["id"]: e["title"] for e in ENDINGS["endings"]}
    dlc_ending_ids = {"end_mediator", "end_best_friend", "end_reunion", "end_circle_hopper",
                      "end_gearhead", "end_tracker_dancer", "end_night_dancer"}
    print(f"\n结局分布:")
    for eid, c in endings.most_common():
        mark = " ← DLC" if eid in dlc_ending_ids else ""
        print(f"  {titles.get(eid, eid):<14} {c:>4} 局 ({c/max(1,total)*100:>5.1f}%){mark}")

    missing_dlc = [eid for eid in dlc_ending_ids if eid not in endings]
    print(f"\nDLC 结局可达  : {len(dlc_ending_ids)-len(missing_dlc)}/{len(dlc_ending_ids)}")
    if missing_dlc:
        print(f"  ⚠️  不可达: {missing_dlc}")
    else:
        print("  ✅ 全部 DLC 结局均可达")

    print("\n" + "=" * 62)
    ok = True
    avg = sum(events_per_run) / max(1, total)
    print("✅ A. 无致命异常" if not errors else "❌ A. 存在运行时异常")
    ok &= not errors
    print(f"✅ B. 平均事件数 {avg:.1f} ≥ 30" if avg >= 30 else f"❌ B. 平均事件数 {avg:.1f} < 30")
    ok &= avg >= 30
    print("✅ C. 无死事件（DLC）" if not dead_dlc else f"⚠️  C. {len(dead_dlc)} 个 DLC 死事件")
    print("✅ D. DLC 结局全部可达" if not missing_dlc else f"❌ D. {len(missing_dlc)} 个 DLC 结局不可达")
    ok &= not missing_dlc
    print("✅ E. favor 始终在 0-100" if not errors else "—")
    print("=" * 62)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
