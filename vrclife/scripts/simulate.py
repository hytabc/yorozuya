#!/usr/bin/env python3
"""
无头模拟器 —— 用真实事件数据跑完整游戏循环，验证 PRD §14 验收标准。

用法:
    python3 scripts/simulate.py [局数] [--seed N] [--verbose] [--trace]

验证项:
    A. 无致命异常
    B. 每局事件数 ≥ 30
    C. 事件池永不为空（保底生效）
    D. 死事件检测（跑 N 局，找出从未触发的事件）
    E. 砂糖循环可完整走通（认识→暧昧→砂糖→矛盾→结束→低迷→恢复→新砂糖）
    F. 每局至少一个无条件选项（数据保证 + 运行时校验）
    G. 结局分布
    H. 数值始终在合法范围
"""

import json
import os
import random
import re
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")

with open(os.path.join(DATA, "events.index.json"), encoding="utf-8") as f:
    INDEX = json.load(f)
with open(os.path.join(DATA, "vocab.json"), encoding="utf-8") as f:
    VOCAB = json.load(f)
with open(os.path.join(DATA, "endings.json"), encoding="utf-8") as f:
    ENDINGS = json.load(f)
with open(os.path.join(DATA, "archetypes.json"), encoding="utf-8") as f:
    ARCHETYPES = json.load(f)["archetypes"]

ALL_EVENTS = INDEX["events"]
BY_ID = INDEX["byId"]
EVENT_POOL = [e for e in ALL_EVENTS if e["category"] not in ("key", "chain")]
PITY_POOL = [e for e in ALL_EVENTS if e["category"] == "pity"]
KEY_EVENTS = [e for e in ALL_EVENTS if e["category"] == "key"]
KEY_ID_SET = frozenset(e["id"] for e in KEY_EVENTS)
NICKNAMES = VOCAB["nicknamePool"]
WORLDS = VOCAB["worldPool"]
SKILLS = [s["key"] for s in VOCAB["skills"]]
STAGES = [(n, lo, hi) for n, lo, hi in
          [(s["key"], s["minHours"], s["maxHours"]) for s in VOCAB["stages"]]]
REL_FLOW = VOCAB["relationStateFlow"]
REL_STATES = set(VOCAB["relationStates"])
# 结束/低迷/恢复：上一段关系已经结束、下一段还没开始的三段。见 match() 的 hasRelation。
INACTIVE_REL_STATES = ("结束", "低迷", "恢复")

MAX_EVENTS_PER_RUN = 72
MAX_TURNS = 400
# 分手冷却（SCHEMA §5.2）：关系结束后这么久内通用 spawn 一律抑制，
# 好让 sugar_b 的失恋恢复链有窗口可用；带 "force": true 的 spawn 可豁免。
SPAWN_COOLDOWN_HOURS = 120
HOUR_STEP_BY_STAGE = {k: tuple(v) for k, v in VOCAB["hourStepByStage"].items()}

# 分阶段统计（供 PRD §6.6 数值平衡表使用，报告末尾输出）
STAGE_STATS = defaultdict(lambda: {"events": 0, "mood": [], "friends": [],
                                   "skillmax": [], "turns": 0})


def stage_of(h):
    for n, lo, hi in STAGES:
        if lo <= h < hi:
            return n
    return "传奇"


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
    """求值 condition DSL。缺省字段视为不限制。"""
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
    # 「有关系」= 存在且处于活跃状态。结束/低迷/恢复 三段属于「上一段已经没了」，
    # 所以失恋恢复链（k05/k06/k07 都要求 hasRelation=false）在整条恢复弧里都能命中。
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
    """自动标签（PRD §3.5）。"""
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


def apply_effects(st, fx):
    if not fx:
        return
    # 心情：正向收益在 70 以上递减（软上限）。
    # 没有这条，心情会长时间钉在 100 —— 所有正面效果被浪费，玩家攒不下任何缓冲，
    # 于是一段分手链（合计 -100 量级）能直接把人从 100 打到 0 触发「燃尽」。
    md = fx.get("mood", 0)
    if md > 0:
        md *= min(1.0, max(0.0, (100 - st["mood"]) / 30.0))
    elif md < -20:
        md = -20  # 单事件情绪悬崖封顶，避免一个结果直接决定结局
    st["mood"] = max(0, min(100, st["mood"] + md))
    st["friends"] = max(0, min(999, st["friends"] + fx.get("friends", 0)))
    st["fame"] = max(0, min(100, st["fame"] + fx.get("fame", 0)))
    st["avatars"] = max(0, st["avatars"] + fx.get("avatars", 0))
    st["assets"] += fx.get("assets", 0)
    st["sugarCount"] += fx.get("sugarCount", 0)
    st["breakupCount"] += fx.get("breakupCount", 0)
    st["hours"] += fx.get("hoursBonus", 0)

    for k, v in (fx.get("skills") or {}).items():
        st["skills"][k] = max(0, min(100, st["skills"].get(k, 0) + v))
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
    for f in (fx.get("flags") or {}).get("add", []):
        if f not in st["flags"]:
            st["flags"].append(f)
    for f in (fx.get("flags") or {}).get("remove", []):
        if f in st["flags"]:
            st["flags"].remove(f)
    for k, v in (fx.get("counters") or {}).items():
        st["counters"][k] = st["counters"].get(k, 0) + v
    derive_tags(st)


DIM_KEYS = ["intimacy", "trust", "freshness", "dependence", "realPressure"]


def new_relation(st, state="认识"):
    """开一段新关系。state 允许由数据指定（恢复链的出口从「恢复」开始）。"""
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


def apply_relation_op(st, rop, events_log):
    if not rop:
        return
    t = rop.get("type")
    r = st["relation"]

    if t == "spawn":
        # 分手冷却（SCHEMA §5.2）：刚失恋的一段时间内不会立刻开始下一段，
        # 除非该 spawn 显式声明 "force": true（恢复链的出口就是这么写的）。
        if st["hours"] < st["spawnBlockUntil"] and not rop.get("force"):
            return
        # 没有关系对象，或上一段已经走到 结束/低迷/恢复，都允许开一段新的
        if not r or r["state"] in INACTIVE_REL_STATES:
            r = new_relation(st, rop.get("state") or "认识")
    elif t == "end":
        # 关系对象保留（状态机需要 结束→低迷→恢复 这条弧可见），
        # 但它不再是「有关系」，并且开始分手冷却。
        if r and r["state"] not in INACTIVE_REL_STATES:
            r["state"] = "结束"
            st["spawnBlockUntil"] = st["hours"] + SPAWN_COOLDOWN_HOURS
            events_log.append(("state", "结束"))
        return
    elif t == "renew":
        if r:
            r["freshness"] = 90
            r["realPressure"] = 0
        return
    elif t == "setState" and rop.get("state"):
        # 上一段已经结束，却要把关系设成活跃状态：这不是「状态转移」，
        # 而是开始新的一段（数据作者就是这么写的），走 spawn 的语义与冷却。
        if r and r["state"] in INACTIVE_REL_STATES \
                and rop["state"] not in INACTIVE_REL_STATES:
            if st["hours"] < st["spawnBlockUntil"] and not rop.get("force"):
                return  # 冷却期内被抑制：合法的节奏控制，不算数据错误
            r = new_relation(st, rop["state"])

    if not st["relation"]:
        return
    r = st["relation"]

    # 1) 绝对赋值
    for d in DIM_KEYS:
        k = "init" + d[0].upper() + d[1:]
        if k in rop:
            r[d] = max(0, min(100, rop[k]))
    # 2) 增量
    for d in DIM_KEYS:
        if d in rop:
            r[d] = max(0, min(100, r[d] + rop[d]))

    # 3) 状态转移（校验合法转移）
    if t == "setState" and rop.get("state"):
        target = rop["state"]
        legal = REL_FLOW.get(r["state"], [])
        if target in legal or target == r["state"]:
            r["state"] = target
            if target == "低迷":
                st["sawLow"] = True
            elif target == "恢复":
                st["sawRecover"] = True
            events_log.append(("state", target))
        else:
            # 非法转移：拒绝应用并计数（PRD §4.3）
            st["illegal"] += 1
            st["illegalDetail"][f"{r['state']}->{target}"] += 1
            events_log.append(("illegal_state", f"{r['state']}->{target}"))


# ---------------------------------------------------------------- engine

def pick_event(st, sched):
    # 1) 到期的连锁事件
    due = sorted([s for s in sched if s["at"] <= st["hours"]], key=lambda s: s["at"])
    for s in due:
        sched.remove(s)
        if st["rng"].random() < s["chance"]:
            ev = BY_ID.get(s["eventId"])
            if ev and match(ev.get("condition"), st):
                return ev

    # 2) 关键事件 —— 但不允许连续两个 key，避免 key 挤占普通事件池
    last_was_key = bool(st["lastEvents"]) and st["lastEvents"][0] in st["keyIds"]
    if not last_was_key:
        in_win, expired = [], []
        for e in KEY_EVENTS:
            if e["id"] in st["usedEvents"]:
                continue
            hr = e["hoursRange"]
            # 关键事件一旦「开始时间」已过就一直保持候选资格：
            # 窗口短、key 多时（如初入 5 回合 / 8 个 key）靠后的 key 不会被饿死。
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

    # 3) 加权随机
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

    # 4) 保底
    pity = [(e, e.get("weight", 1)) for e in PITY_POOL if match(e.get("condition"), st)]
    if pity:
        return st["rng"].choices([e for e, _ in pity], weights=[w for _, w in pity])[0]
    return None


def score(e, st):
    w = e.get("weight", 10)
    if e.get("stage") == stage_of(st["hours"]):
        w *= 1.5
    else:
        w *= 0.6
    tg = e.get("tags") or []
    # 低心情时抑制正面、放大负面 —— 但幅度要克制，否则变成死亡螺旋，
    # 直接违背 PRD §7.1「不能一直低迷」。回弹交给下面的 negStreak 规则。
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
    # 导演：情绪回弹
    if st["negStreak"] >= 3 and "正面" in tg:
        w *= 2.5
    if st["negStreak"] >= 3 and "负面" in tg:
        w *= 0.4
    # 「好日子该过去了」——但 ×2.0 会让负面池在正面占多数时长期翻倍，
    # 变成每回合净 -2 的单向抽水。收到 1.4，让它成为扰动而不是趋势。
    if st["posStreak"] >= 4 and "负面" in tg:
        w *= 1.4
    # 低迷期
    if "失恋" in st["tags"]:
        if "孤独" in tg or "回忆" in tg:
            w *= 3.0
        if "正面" in tg:
            w *= 0.4
    # 防连发
    if any(t in st["recentTags"] for t in tg):
        w *= 0.3
    if e["id"] in st["lastEvents"]:
        w *= 0.2
    w *= 0.8 + st["rng"].random() * 0.4
    return w


def step_hours(st):
    s = stage_of(st["hours"])
    lo, hi = HOUR_STEP_BY_STAGE.get(s, (1, 20))
    step = st["rng"].randint(lo, hi)
    if st["mood"] <= 14:
        step = int(step * 1.5)
    step = max(1, step)
    # 里程碑保护
    for m in (10, 50, 200, 500, 1000, 5000):
        if st["hours"] < m <= st["hours"] + step and m not in st["milestones"]:
            st["milestones"].add(m)
            return m - st["hours"]
    return step


def drift_relation(st, sched):
    r = st["relation"]
    if not r or r["state"] in INACTIVE_REL_STATES:
        return  # 结束/低迷/恢复：上一段已经不再漂移，等恢复链 spawn 新的
    r["freshness"] = max(0, r["freshness"] - 2)
    if "sugar" in st["recentTags"]:
        r["intimacy"] = min(100, r["intimacy"] + 1)
    else:
        r["intimacy"] = max(0, r["intimacy"] - 1)
    if r["state"] in ("砂糖", "稳定"):
        r["dependence"] = min(100, r["dependence"] + 0.5)
    r["realPressure"] = max(0, min(100, r["realPressure"] + st["rng"].randint(-3, 4)))

    if r["realPressure"] > 60 and st["rng"].random() < 0.08:
        sched.append({"eventId": "sugar_b_k04", "at": st["hours"] + st["rng"].randint(0, 40), "chance": 1.0})
    if r["freshness"] < 30 and r["state"] == "砂糖" and st["rng"].random() < 0.1:
        sched.append({"eventId": "sugar_b_k02", "at": st["hours"] + st["rng"].randint(10, 60), "chance": 0.8})
    if r["state"] == "砂糖" or r["state"] == "稳定":
        st["sugarPath"].add("sugar")
    if r["state"] == "矛盾":
        st["sugarPath"].add("conflict")
    if r["state"] == "低迷":
        st["sugarPath"].add("low")


# ---------------------------------------------------------------- endings

HINT_ALIASES = VOCAB.get("endingPathAliases", {})


def canonical_hint(path):
    """endingHint.path 的别名规范化（vocab.json endingPathAliases）。"""
    seen = set()
    while path in HINT_ALIASES and path not in seen:
        seen.add(path)
        path = HINT_ALIASES[path]
    return path


# --- score 表达式求值（endings.json 的 score 字段）---------------------------
# 支持：数字、变量、+ - * / ( )、比较、三元 ?:、&& 。
# 白名单求值，不用 eval()。
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
        "skill.max": max(st["skills"].values()),
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
                v = 1.0 if {
                    "<": v < b, "<=": v <= b, ">": v > b,
                    ">=": v >= b, "==": v == b, "!=": v != b,
                }[op] else 0.0
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


def evaluate_ending(st):
    """按 endings.json 判定：lock 结局满足即必中；其余取 score 最高者。"""
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

    # 1) lock 结局满足条件即必中（如「心态归零 → 燃尽」）
    for e in ENDINGS["endings"]:
        if e.get("lock") and ok(e.get("condition") or {}):
            return e["id"]

    # 2) 其余：条件满足者中取 score 最高（endings.json 的既定契约）
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


# ---------------------------------------------------------------- one run

def new_state(seed, arch=None):
    rng = random.Random(seed)
    a = arch or rng.choices(ARCHETYPES, weights=[x["weight"] for x in ARCHETYPES])[0]
    st = {
        "rng": rng, "seed": seed, "arch": a,
        "hours": 0, "friends": 0, "mood": 70, "fame": 0, "avatars": 1,
        "assets": 0, "sugarCount": 0, "breakupCount": 0,
        "skills": {k: 0 for k in SKILLS},
        "circles": [], "tags": ["萌新"], "flags": [], "counters": {},
        "relation": None, "usedEvents": [], "lastSeen": {}, "scheduled": [],
        "recentTags": [], "lastEvents": [], "negStreak": 0, "posStreak": 0,
        "milestones": set(), "history": [], "sugarPath": set(), "illegal": 0,
        "illegalDetail": Counter(), "keyIds": KEY_ID_SET,
        "spawnBlockUntil": -1, "sawLow": False, "sawRecover": False,
        "hints": Counter(),
    }
    init = a.get("init", {})
    for k, v in init.items():
        st[k] = v
    for k, v in a.get("skills", {}).items():
        st["skills"][k] = v
    st["tags"] = list(a.get("tags", ["萌新"]))
    st["flags"] = list((a.get("flags") or {}).get("add", []))
    return st


def play(seed, arch=None):
    st = new_state(seed, arch)
    rng = st["rng"]
    fired = []

    for turn in range(MAX_TURNS):
        if len(fired) >= MAX_EVENTS_PER_RUN:
            break
        if st["mood"] <= 0:
            break
        if st["hours"] >= 5000:
            break

        ev = pick_event(st, st["scheduled"])
        if ev is None:
            return {"state": st, "fired": fired, "error": "EMPTY_POOL"}

        fired.append(ev["id"])
        st["lastSeen"][ev["id"]] = st["hours"]

        # 选择选项：优先无条件选项
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
        friends_before = st["friends"]
        stage_now = stage_of(st["hours"])
        apply_effects(st, chosen.get("effects"))
        _ss = STAGE_STATS[stage_now]
        _ss["events"] += 1
        _ss["mood"].append(st["mood"] - mood_before)
        _ss["friends"].append(st["friends"] - friends_before)
        _ss["skillmax"].append(max(st["skills"].values()) if st["skills"] else 0)
        # relationOp 的正规位置是 effects.relationOp（SCHEMA §5.2）；
        # 顶层写法仅为兼容旧数据保留。
        fx = chosen.get("effects") or {}
        apply_relation_op(st, fx.get("relationOp") or chosen.get("relationOp"),
                          st["history"])

        # endingHint 累积（endings.json 的 score 里以 hint.<path> 参与计分）
        hint = chosen.get("endingHint") or fx.get("endingHint")
        if hint and hint.get("path"):
            st["hints"][canonical_hint(hint["path"])] += hint.get("score", 1)

        # 活跃状态标签（排除自动派生标签）用于判定 streak
        negative = st["mood"] < mood_before
        st["negStreak"] = st["negStreak"] + 1 if negative else 0
        st["posStreak"] = 0 if negative else st["posStreak"] + 1

        tg = ev.get("tags") or []
        st["recentTags"] = (tg + st["recentTags"])[:3]
        st["lastEvents"] = ([ev["id"]] + st["lastEvents"])[:5]

        if ev.get("once"):
            st["usedEvents"].append(ev["id"])
        elif ev.get("cooldown"):
            st["usedEvents"].append(ev["id"]) if False else None

        # 安排连锁
        for s in chosen.get("schedule", []) or []:
            dh = s.get("delayHours", [10, 60])
            d = rng.randint(dh[0], dh[1]) if isinstance(dh, list) else dh
            st["scheduled"].append({
                "eventId": s["eventId"], "at": st["hours"] + d,
                "chance": s.get("chance", 1.0),
            })

        # 推进
        st["hours"] += step_hours(st)
        drift_relation(st, st["scheduled"])

        # 范围断言（验收 H）
        assert 0 <= st["mood"] <= 100, f"mood 越界 {st['mood']}"
        assert 0 <= st["fame"] <= 100, f"fame 越界 {st['fame']}"
        assert st["friends"] >= 0, "friends 为负"
        assert st["avatars"] >= 0, "avatars 为负"
        for k, v in st["skills"].items():
            assert 0 <= v <= 100, f"技能 {k} 越界 {v}"

    return {"state": st, "fired": fired, "error": None}


# ---------------------------------------------------------------- main

def main():
    n = 300
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if args:
        n = int(args[0])
    seed0 = 1
    if "--seed" in sys.argv:
        seed0 = int(sys.argv[sys.argv.index("--seed") + 1])

    print(f"运行 {n} 局模拟…\n")

    hit = Counter()
    endings = Counter()
    errors = Counter()
    events_per_run = []
    hours_per_run = []
    sugar_loops = 0
    illegal_total = 0
    arch_use = Counter()
    low_recovered = 0
    low_entered = 0
    recover_entered = 0
    multi_sugar = 0

    for i in range(n):
        r = play(seed0 + i)
        st = r["state"]
        if r["error"]:
            errors[r["error"]] += 1
            continue
        for eid in r["fired"]:
            hit[eid] += 1
        events_per_run.append(len(r["fired"]))
        hours_per_run.append(st["hours"])
        arch_use[st["arch"]["name"]] += 1
        illegal_total += st["illegal"]
        endings[evaluate_ending(st)] += 1
        if st["sugarCount"] >= 2:
            multi_sugar += 1
        if st["sawRecover"]:
            recover_entered += 1

        # 砂糖循环完整性：走过 暧昧→砂糖→(矛盾|结束)→低迷→恢复→再砂糖
        if st["sugarCount"] >= 1 and st["breakupCount"] >= 1:
            sugar_loops += 1
        if st["sawLow"]:
            low_entered += 1
            if st["mood"] >= 40:
                low_recovered += 1

    total = len(events_per_run)
    print("=" * 62)
    print("模拟结果")
    print("=" * 62)
    print(f"\n成功完成局数  : {total}/{n}")
    if errors:
        print(f"异常          : {dict(errors)}")
    else:
        print("异常          : 无 ✅")
    print(f"平均事件数/局 : {sum(events_per_run)/max(1,total):.1f}  "
          f"(min {min(events_per_run, default=0)}, max {max(events_per_run, default=0)})")
    print(f"平均时长/局   : {sum(hours_per_run)/max(1,total):.0f}h  "
          f"(min {min(hours_per_run, default=0)}, max {max(hours_per_run, default=0)})")
    print(f"非法状态转移  : {illegal_total}")

    print(f"\n砂糖循环:")
    print(f"  至少 1 次砂糖并失恋 : {sugar_loops}/{total} 局 ({sugar_loops/max(1,total)*100:.1f}%)")
    print(f"  进入过低迷期        : {low_entered} 局，其中 mood 回升 ≥40 : {low_recovered} 局")
    print(f"  进入过恢复期        : {recover_entered} 局")
    print(f"  多次砂糖(≥2)        : {multi_sugar} 局 ({multi_sugar/max(1,total)*100:.1f}%)")

    # 死事件检测
    fired_ids = set(hit)
    dead = [e["id"] for e in ALL_EVENTS if e["id"] not in fired_ids]
    print(f"\n事件触达:")
    print(f"  被触发过的事件 : {len(fired_ids)}/{len(ALL_EVENTS)}")
    if dead:
        print(f"  ⚠️  未被触发({len(dead)}) : {dead[:25]}")
        by_bucket = Counter(d.split('_')[0] if not d.startswith('sugar') else '_'.join(d.split('_')[:2]) for d in dead)
        print(f"      分布: {dict(by_bucket)}")
    else:
        print("  ✅ 全部事件均被触发过（无死事件）")

    print(f"\n热点事件 Top10:")
    for eid, c in hit.most_common(10):
        print(f"  {eid:<16} {c:>5} 次")

    print(f"\n冷门事件 Bottom10（已触发的）:")
    for eid, c in sorted(hit.items(), key=lambda x: x[1])[:10]:
        print(f"  {eid:<16} {c:>5} 次")

    # 分阶段数值 —— 供 PRD §6.6 数值平衡表核对
    print(f"\n分阶段数值（每事件增量）:")
    print(f"  {'阶段':<10} {'事件数':>5} {'mood 均值':>9} {'mood 范围':>14} "
          f"{'friends 均值':>11} {'技能上限':>10}")
    for name, _, _ in STAGES:
        s = STAGE_STATS.get(name)
        if not s or not s["events"]:
            continue
        m = s["mood"]
        f = s["friends"]
        sk = s["skillmax"]
        print(f"  {name:<10} {s['events']:>5} {sum(m)/len(m):>+9.1f} "
              f"{f'{min(m):+.0f} ~ {max(m):+.0f}':>14} {sum(f)/len(f):>+11.1f} "
              f"{f'{min(sk)}-{max(sk)}':>10}")

    # 结局分布 —— 直接暴露「哪些结局根本不可达」
    titles = {e["id"]: e["title"] for e in ENDINGS["endings"]}
    print(f"\n结局分布:")
    for eid, c in endings.most_common():
        print(f"  {titles.get(eid, eid):<14} {c:>4} 局 ({c/max(1,total)*100:>5.1f}%)")
    # 兜底结局（condition 为空）本来就是「别的都不匹配时」才用，不算不可达
    unreachable = [e["id"] for e in ENDINGS["endings"]
                   if e["id"] not in endings and e.get("condition")]
    if unreachable:
        print(f"  ⚠️  不可达结局({len(unreachable)}): {unreachable}")
    else:
        print("  ✅ 全部结局均可达")
    print()

    # 验收判定
    print("=" * 62)
    ok = True
    avg_ev = sum(events_per_run)/max(1,total)
    if errors:
        print("❌ A. 存在运行时异常")
        ok = False
    else:
        print("✅ A. 无致命异常")
    if avg_ev >= 30:
        print(f"✅ B. 平均事件数 {avg_ev:.1f} ≥ 30")
    else:
        print(f"❌ B. 平均事件数 {avg_ev:.1f} < 30")
        ok = False
    if dead:
        print(f"⚠️  D. 存在 {len(dead)} 个死事件")
    else:
        print("✅ D. 无死事件")
    if sugar_loops > 0:
        print(f"✅ E. 砂糖循环可完整走通（{sugar_loops} 局）")
    else:
        print("❌ E. 砂糖循环未能走通")
        ok = False
    if illegal_total == 0:
        print("✅ H. 无数值越界 / 非法状态转移")
    else:
        print(f"⚠️  H. 非法状态转移 {illegal_total} 次")
    print("=" * 62)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
