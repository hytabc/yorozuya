# VRChat 玩家历程模拟器 · 需求设计文档 PRD

**版本**：v1.0（基于 v0.2 草案扩展）
**日期**：2026-09-10
**状态**：待评审 → 可直接进入开发

### 交付状态一览

本 PRD 不只是规格说明——**内容侧已经落地并通过了可执行的验证**。实现引擎时，`data/` 与 `scripts/` 就是可直接消费的输入：

| 部分 | 状态 | 验证方式 |
|---|---|---|
| 事件数据契约 | ✅ 已冻结 | `data/SCHEMA.md`（10 节） |
| 受控词表 / 出生 / 结局 | ✅ 已交付 | `data/vocab.json`、`archetypes.json`、`endings.json` |
| 事件库 **296 个**（40 key / 894 选项 / 1606 结果） | ✅ 已交付 | `python3 scripts/validate_events.py` → **0 ERROR** |
| 死事件 / 可达性 / 平衡 | ✅ 已验证 | `python3 scripts/simulate.py 1000` → **296/296 触达，0 非法转移，15/15 结局可达** |
| 引擎（TypeScript） | ⬜ 待实现 | 见 §6、§11.3 的伪代码与 `scripts/simulate.py` 的参考语义 |
| UI | ⬜ 待实现 | 见 §9 |

> **重要**：`scripts/simulate.py` 用 Python 实现了一遍引擎语义（condition 求值、effects、
> relationOp、导演调制、结局判分）。它是数值平衡与可达性的**唯一事实来源**；
> 写 TS 引擎时请以它为准，而不是以散文描述为准。

---

## 目录

1. [项目概述](#1-项目概述)
2. [核心玩法与游戏循环](#2-核心玩法与游戏循环)
3. [状态系统](#3-状态系统)
4. [砂糖关系系统](#4-砂糖关系系统)
5. [事件系统](#5-事件系统)
6. [随机与数值机制](#6-随机与数值机制)
7. [导演系统](#7-导演系统)
8. [结局系统](#8-结局系统)
9. [页面交互与 UI](#9-页面交互与-ui)
10. [数据结构](#10-数据结构)
11. [内容清单](#11-内容清单)
12. [技术方案](#12-技术方案)
13. [开发计划与迭代](#13-开发计划与迭代)
14. [验收标准](#14-验收标准)
15. [附录](#15-附录)

---

## 1. 项目概述

### 1.1 一句话定义

一个以 **VRChat 游戏时长（小时）** 为主轴的文字模拟器。玩家从萌新进入 VRChat，经历探索、社交、学习、情感关系（尤其是"砂糖"关系）、低迷、回归、新关系的循环，最终根据累计小时数和关键选择生成人生总结。

### 1.2 核心设计目标

| 目标 | 说明 |
|---|---|
| **用小时数代替年龄** | 10h / 95h / 240h / 500h / 1000h，每个数字都是一段人生阶段 |
| **高度随机** | 事件池 + 条件过滤 + 权重随机 + 结果随机，同一局不会重演 |
| **VRChat 文化自洽** | Avatar、World、中文吧、贴贴、砂糖、改模、跳舞、摄影、语言交换、跨年、Udon、Quest |
| **砂糖循环是心脏** | 接触 → 成为砂糖 → 美好 → 结束 → 低迷 → 新朋友 → 新思考 → 新砂糖 |
| **短局可重开** | 单局 5-15 分钟，每局 45-75 个事件（上限 72） |
| **可复现** | 同一 seed + 同一选择序列 → 完全相同的结果 |

### 1.3 目标用户

- 玩过 VRChat 的人：来找共鸣，看到"这说的就是我"。
- 没玩过但刷到过 VRChat 内容的人：好奇这个圈子长什么样。
- 喜欢《人生重开模拟器》类文字游戏的玩家：来找随机性和多结局。

### 1.4 设计基调

- **不评判**：砂糖、退坑、氪金、网恋都是中性叙述，不劝人也不嘲笑。
- **不鸡汤**：低迷期不给"明天会更好"，只给"有人在旁边坐着"。
- **有画面**：每段文案都应该能截图。
- **有痛感**：失去要真的疼，重来要真的难。

### 1.5 非目标（Out of Scope）

- 不做真实 VRChat 客户端接入、不调用官方 API。
- 不做多人实时对战/联机。
- 不使用真实人物、真实社群、真实政治事件。
- 不做 3D 渲染。

---

## 2. 核心玩法与游戏循环

### 2.1 核心循环

```
开始
  ↓
随机生成出生（archetype）+ 初始状态
  ↓
┌──────────────────────────────────────┐
│  取当前状态                            │
│  ↓                                    │
│  检查强制触发事件（key / 到期 chain）    │
│  ↓ （无则进入加权随机抽取）              │
│  展示事件卡 + 2-4 个选项                │
│  ↓                                    │
│  玩家选择 → 加权随机结果                 │
│  ↓                                    │
│  应用 effects / relationOp / schedule  │
│  ↓                                    │
│  结算：夹取数值、派生标签、更新档位        │
│  ↓                                    │
│  推进小时：hours += rand(1, 20)         │
│  ↓                                    │
│  判断：心态归零？到结局阈值？玩家结束？     │
└──────────────────────────────────────┘
  ↓
结局页（称号 + 总结 + 雷达图 + 时间线回放）
```

### 2.2 时间推进规则

- 初始 `hours = 0`。
- 每回合推进量取自 `vocab.json` 的 **`hourStepByStage`**——按当前阶段取一个区间，区间内取随机整数：

  | 阶段 | 小时区间 | 步长区间 |
  |---|---|---|
  | 初入 | 0 - 10 | `[1, 3]` |
  | 萌新探索 | 10 - 50 | `[3, 8]` |
  | 社交起步 | 50 - 200 | `[6, 15]` |
  | 深度社交 | 200 - 500 | `[10, 24]` |
  | 老油条 | 500 - 1000 | `[15, 35]` |
  | 传奇 | 1000+ | `[25, 60]` |

- **修正因子**：
  - 出生 `hourStepMod`（如"深夜失眠者" ×1.4，"沉默观察者" ×0.85）。
  - 心情修正：`退坑边缘` 时步长 ×1.5（低迷期快进）。
- **里程碑保护**：当推进后会跨过里程碑（10 / 50 / 200 / 500 / 1000 / 5000）且该里程碑的 key 事件尚未触发时，**强制推进到里程碑小时数**，而不是跳过。
- 单局事件数上限 **72**（防止无限局），达到后进入结局结算。

> **步长校准依据**（`vocab.json` 的 `hourStepNote`）：阶段区间取代了旧的「基础 `randInt(1,20)` × 阶段倍率」公式。该公式在高阶段会指数式放大步长，导致 key 事件窗口被整段跳过。六段区间是线性标定的结果：**约 45 个事件推进到 500h**（砂糖线主战场），**约 70 个事件推进到 1000h**（legend 桶可达）。1000 局实测平均 **68.3 事件 / 1150 小时**，与设计目标一致。

### 2.3 里程碑与阶段

**已交付事件库：296 个事件 / 40 个关键事件 / 894 个选项 / 1606 个结果**，全部通过 `scripts/validate_events.py` 静态校验（0 错误），并在 `scripts/simulate.py` 1000 局模拟中**全部至少触发过一次**（无死事件）。

| 桶文件 | 阶段 | 小时区间 | 主题 | 事件数 | key |
|---|---|---|---|---|---|
| `intro.json` | 初入 | 0 - 10 | 第一次登录、教程、默认模型、社恐 | 30 | 8 |
| `newbie.json` | 萌新探索 | 10 - 50 | 逛世界、中文吧、第一次跳舞、被送模型 | 30 | 5 |
| `social.json` | 社交起步 | 50 - 200 | 常驻圈子、技能入门、固定玩伴、暧昧 | 32 | 4 |
| `sugar_a.json` | 深度社交 | 200 - 500 | 靠近、暧昧、成为砂糖 | 30 | 6 |
| `sugar_b.json` | 深度社交+ | 200 - 900 | 砂糖期、矛盾、结束、低迷、恢复 | 32 | 8 |
| `deep.json` | 深度社交 | 200 - 500 | 技能成型、小有名气、办活动 | 30 | 3 |
| `veteran.json` | 老油条 | 500 - 1000 | 社区名人、带新人、退坑念头、回归 | 28 | 3 |
| `legend.json` | 传奇 | 1000+ | 传奇、总结、退坑、传承 | 24 | 3 |
| `wild.json` | 全阶段 | 任意 | 随机稀有事件 | 32 | 0 |
| `idle.json` | 全阶段 | 任意 | 保底 / 日常 / 低迷 | 28 | 0 |
| **合计** | | | | **296** | **40** |

### 2.4 单局流程示例（预期体验）

> **0h** — 你戴上头显，看到的第一件事是自己的虚拟手。它看起来不像你的手。 → 选择"先捏个脸"　`intro_k01`
> **6h** — 有人在中文吧角落问你："萌新？" → 选择"跟着他" → 加到了第一个好友　`intro_k02`
> **23h** — 有人记住了你的名字 → 选择"受宠若惊" → 好友 +2　`newbie_k02`
> **95h** — 你们经常一起玩，今晚 ta 送你一个模型 → 选择"回赠礼物" → 成为固定玩伴　`sugar_a_k02`
> **240h** — ta 问你："我们算什么关系？" → 选择"我也想说这个" → 成为砂糖　`sugar_a_k05`
> **320h** — 回复变慢了。你说的话 ta 没记住。 → 选择"问清楚" → 状态「矛盾」　`sugar_b_k02`
> **430h** — ta 说现实里有了别人。 → 选择"主动结束" → 失恋，心态 -30　`sugar_b_k04`
> **470h** — 你反复点开 ta 的主页，又关掉。 → 进入低迷期　`sugar_b_k05`
> **620h** — 有个新人问你"萌新？" → 选择"我带带你" → 恢复，你成了别人眼里的老人　`sugar_b_k07`
> **1000h** — 你回顾这段虚拟人生。 → 结局：**砂糖循环者** 或 **安静地不再来了**

> 上表小时数取自各 key 事件 `hoursRange` 的实际触发窗口（见 §4.4）。因为步长随机，每局落点都不同——这正是"23h / 95h / 240h"这些数字的来源。

---

## 3. 状态系统

### 3.1 完整状态对象（GameState）

```ts
interface GameState {
  // —— 元信息 ——
  seed: string;              // 随机种子
  rngState: number;          // mulberry32 内部状态（存档用）
  turn: number;              // 回合数
  phase: 'playing' | 'ended';

  // —— 核心数值 ——
  hours: number;             // 累计时长，核心进度
  friends: number;           // 好友数量 0-999
  mood: number;              // 心态 0-100
  fame: number;              // 声望 0-100
  avatars: number;           // 模型数量
  assets: number;            // 资产（虚拟币）
  sugarCount: number;        // 累计成为砂糖次数
  breakupCount: number;      // 累计失恋次数

  // —— 集合 ——
  skills: Record<SkillKey, number>;   // 8 项技能 0-100
  circles: string[];                  // 已加入的圈子
  tags: string[];                     // 状态标签
  flags: string[];                    // 剧情旗标（不可见）
  counters: Record<string, number>;   // 自定义计数器

  // —— 关系 ——
  relation: Relation | null;          // 当前活跃关系（同时最多一段）

  // —— 事件引擎 ——
  usedEvents: string[];               // 已触发的 once 事件 id
  cooldowns: Record<string, number>;  // eventId → 冷却结束的小时数
  scheduled: ScheduledEvent[];        // 待触发的连锁事件
  recentTags: string[];               // 最近 3 个事件的 tags（防连发）
  lastEvents: string[];               // 最近 5 个事件 id
  moodHistory: number[];              // 每回合心态快照（导演系统用）
  negativeStreak: number;             // 连续负面结果计数
  positiveStreak: number;             // 连续正面结果计数

  // —— 结局 ——
  endingHints: Record<string, number>; // 结局倾向分 path → score
  history: HistoryEntry[];             // 完整时间线
  archetypeId: string;                 // 出生 id
}
```

### 3.2 初始值

```json
{
  "hours": 0, "friends": 0, "mood": 70, "fame": 0,
  "avatars": 1, "assets": 0, "sugarCount": 0, "breakupCount": 0,
  "skills": { "modeling": 0, "coding": 0, "photo": 0, "music": 0,
              "dance": 0, "language": 0, "social": 0, "meme": 0 },
  "circles": [], "tags": ["萌新"], "flags": [], "counters": {},
  "relation": null, "usedEvents": [], "cooldowns": {}, "scheduled": [],
  "recentTags": [], "lastEvents": [], "negativeStreak": 0,
  "positiveStreak": 0, "endingHints": {}, "history": []
}
```

> 实际开局值由 `data/archetypes.json` 的 `init` / `skills` / `tags` / `flags` 字段覆盖。共 10 种出身，见 §11.4。

### 3.3 数值范围与夹取

| 属性 | 范围 | 夹取时机 | 归零/满值处理 |
|---|---|---|---|
| `hours` | 0 - ∞ | 不夹取 | 5000h 触发总结结局 |
| `friends` | 0 - 999 | 每次结算 | 0 = 独行 |
| `mood` | 0 - 100 | 每次结算 | **0 → 立即触发「燃尽」结局** |
| `fame` | 0 - 100 | 每次结算 | 不归零 |
| `avatars` | 0 - ∞ | 不夹取 | 0 = 只剩默认模型 |
| `assets` | -9999 - ∞ | 不夹取 | 可为负（负债/欠单） |
| 技能 | 0 - 100 | 每次结算 | 满值后不再提示 |
| 关系四维 | 0 - 100 | 每次结算 | — |

### 3.4 派生值（不存储，实时计算）

| 派生值 | 计算方式 | 用途 |
|---|---|---|
| 心态档位 | mood → 好奇/热情/疲惫/低迷/退坑边缘 | 事件条件、UI 显示、导演系统 |
| 声望档位 | fame → 默默无闻/小有名气/社区名人/传奇 | 事件条件、UI 显示 |
| 技能等级 | 技能值 → 入门/熟悉/熟练/高手/大师 | 事件条件、称号 |
| 最高技能 | `argmax(skills)` | 文案变量 `{技能}` |

> 词表定义见 `data/vocab.json`。

### 3.5 标签系统

标签分三类：

1. **核心标签**（24 个）：引擎有特殊逻辑，如 `砂糖中` 影响事件池、`失恋` 解锁低迷事件、`退坑边缘` 影响结局。**只能从 `vocab.json` 的 `coreTags` 中取值**。
2. **扩展标签**（20 个）：纯描述性标记，也用于条件过滤，如 `夜猫子`、`氪金`。
3. **动态自动标签**：引擎根据数值自动增删——
   - `萌新`：hours < 50 时保持，≥ 50 时自动移除。
   - `独行侠`：friends < 5 且 hours > 100 时自动添加。
   - `话痨`：累计选择"主动搭话"类选项 ≥ 8 次时添加。
   - `社恐`：累计选择"回避社交"类选项 ≥ 8 次时添加。
   - `夜猫子`：深夜主题事件触发 ≥ 5 次时添加。
   - `退坑边缘`：mood ≤ 14 时添加，mood ≥ 30 时移除。
   - `回归者`：触发过"回归"事件后永久保留。

### 3.6 圈子系统

圈子是"归属标签"，影响事件池与文案。加入方式：特定事件 outcome 的 `circles.add`。

| 圈子 | 主要获取途径 | 解锁事件倾向 |
|---|---|---|
| 中文吧 | 萌新期常驻 | 社交、冲突、日常 |
| 跳舞圈 | dance 技能 ≥ 20 | 表演、活动、音乐 |
| 模型圈 | modeling 技能 ≥ 20 | 改模、接单、抄袭冲突 |
| 摄影圈 | photo 技能 ≥ 20 | 出片、被拍、婚礼记录 |
| 游戏圈 | 常玩恐怖图/密室 | 恐怖、竞赛、整活 |
| 语言交换圈 | language 技能 ≥ 15 | 翻译、跨文化、时差 |
| 音乐圈 | music 技能 ≥ 20 | 演奏、DJ、原创 |
| 整活圈 | meme 技能 ≥ 20 | 整活、节目效果、反向出圈 |
| 恐怖圈 | 游戏圈 + 特定 flag | 恐怖图、惊吓、深夜 |
| 竞赛圈 | 游戏圈 + fame ≥ 30 | 比赛、排名、代打 |
| 绘画圈 | photo ≥ 30 或 modeling ≥ 30 | 约稿、画师、版权 |
| ASMR圈 | 特定 flag `asmr_met` | 助眠、深夜、声音 |

加入圈子后：该圈子相关事件的 `circles` 条件满足，权重 ×1.3；同时解锁 2-3 个专属事件。

### 3.7 出生（Archetype）系统

开局随机抽 1 个出身（权重抽取），决定初始数值、初始 flag 与特殊规则。详细定义见 `data/archetypes.json`。

| id | 名称 | 权重 | 稀有度 | 特殊规则摘要 |
|---|---|---|---|---|
| arch_001 | 纯粹萌新 | 30 | common | 基准体验 |
| arch_002 | VR 设备党 | 15 | common | 已有设备，coding 起点 5 |
| arch_003 | 社恐患者 | 20 | common | 未开麦前社交事件 ×0.6、独处 ×1.5 |
| arch_004 | 朋友带入坑 | 15 | common | 开局即有 1 个「常一起玩」关系 |
| arch_005 | 二次元老宅 | 12 | uncommon | 开局 3 个模型，懂文化梗 |
| arch_006 | 外语学习者 | 10 | uncommon | language 起点 15，语言圈事件 ×2 |
| arch_007 | 创作者 | 8 | rare | modeling 起点 25，模型圈 ×1.8，技能成长 ×1.3 |
| arch_008 | 深夜失眠者 | 10 | uncommon | 步长 ×1.4，深夜事件 ×1.6，mood 上限 80 |
| arch_009 | 被安利来的 | 8 | uncommon | 砂糖线 ×1.5，失恋额外 -5 mood |
| arch_010 | 沉默观察者 | 5 | rare | 好友增长 ×0.5，风景事件 ×2，结局偏「孤独探索者」 |

---

## 4. 砂糖关系系统（核心）

> 这是整个游戏的心脏。事件数量占比最高（`sugar_a` 30 个 + `sugar_b` 32 个 = 62 个），且是全流程唯一有独立状态机的子系统。

### 4.1 关系对象（Relation）

```ts
interface Relation {
  id: string;            // 内部 id
  name: string;          // 昵称，从 vocab.nicknamePool 随机抽
  metAtHours: number;    // 相遇时的小时数
  state: RelationState;  // 状态机当前状态
  intimacy: number;      // 亲密度 0-100
  dependence: number;    // 依赖度 0-100
  trust: number;         // 信任 0-100
  freshness: number;     // 新鲜感 0-100（每回合自然衰减）
  realPressure: number;  // 现实压力 0-100（影响结束概率）
  flags: string[];       // 关系专属旗标，如 "has_irl_contact"
  memory: string[];      // 已发生的记忆点，用于文案回扣
}
```

### 4.2 关系数值语义

| 属性 | 含义 | 自然变化 | 影响 |
|---|---|---|---|
| **亲密度** | 你们有多近 | 每回合 -1（不互动时） | 决定暧昧/砂糖能否触发 |
| **依赖度** | 你有多离不开 ta | 每回合 +0.5（砂糖期） | 越高，结束时时 mood 掉得越狠 |
| **信任** | 你敢说多真的话 | 不自然变化 | 决定"现实话题"类选项门槛 |
| **新鲜感** | 还有多少好奇 | **每回合 -2** | 低于 30 时矛盾事件权重 ×2 |
| **现实压力** | 现实对这段关系的挤压 | 随机波动 | **> 60 时，每回合有 8% 概率触发结束链** |

### 4.3 状态机

```
       ┌──────────────── 前跳允许：认识/朋友 可直接跳到 暧昧 甚至 砂糖（闪恋）
       │
陌生人 ──→ 认识 ⇄ 朋友 ⇄ 常一起玩 ⇄ 暧昧 ──→ 砂糖 ⇄ 稳定
              └──────┴──────────┴─────┴──→ 矛盾 ──┘
                                            │
                                            ↓
                                           结束 ──→ 低迷 ──→ 恢复
                                                              │
                                                              └──→ 新关系（认识 / 朋友 / 常一起玩）
```

**合法转移表**（引擎按 `vocab.json` 的 `relationStateFlow` 强制校验，非法转移直接拒绝）：

| 从 | 可到 |
|---|---|
| 陌生人 | 认识、结束 |
| 认识 | 朋友、常一起玩、暧昧、砂糖、稳定、矛盾、结束 |
| 朋友 | 常一起玩、暧昧、砂糖、稳定、矛盾、认识、结束 |
| 常一起玩 | 暧昧、砂糖、稳定、矛盾、朋友、结束 |
| 暧昧 | 砂糖、稳定、矛盾、常一起玩、朋友、结束 |
| 砂糖 | 稳定、矛盾、常一起玩、暧昧、朋友 |
| 稳定 | 矛盾、砂糖、常一起玩、朋友、暧昧 |
| 矛盾 | 稳定、砂糖、结束、朋友、暧昧、常一起玩 |
| 结束 | 低迷 |
| 低迷 | 恢复 |
| 恢复 | 认识、朋友、常一起玩 |

> **前跳允许，退行受限**（`vocab.json` 的 `relationFlowNote`）：关系可以不按部就班，从「认识」直接跳到「常一起玩」甚至「砂糖」——闪恋是真实的玩法。只对少数几条边做限制：一旦到「结束」只能进「低迷」，低迷只能转「恢复」，恢复后重新开始。反向边仅保留「常一起玩→朋友」「朋友→认识」「稳定↔砂糖」「矛盾→稳定」这类**有叙事含义的退行**（关系降温、和好、退回朋友）。1000 局模拟中非法转移 **0 次**。

**推进门槛（引擎强制）**：`vocab.json` 的 `relationGate` 由引擎强制执行（`relation.js` 的 `relationGateBlocks`，`simulate_dlc1.py` 同名逻辑）。
不满足时该次状态推进被拒绝，但选项的数值效果照常结算；`spawn` 与「已结束→重新开始」还没有关系数值，只校验 `minFavor`。

| 目标状态 | minFavor | minIntimacy | 其他 |
|---|---|---|---|
| 暧昧 | 30 | 25 | minFreshness 40 |
| 砂糖 | 40 | 50 | minTrust 35 |
| 稳定 | 50 | 60 | maxRealPressure 80 |

> 门槛按**无门槛模拟的实际分布校准**（400 局通率：暧昧 90% / 砂糖 80% / 稳定 39%），只拦「关系数值明显不够却硬推进」。
> 早期版本给的是 intimacy ≥ 50 / 65 / 80 与 realPressure ≤ 40，但实测暧昧的 intimacy p90 只有 48，
> 而 realPressure 每回合只涨不落（稳定期 p50 已 64）——照原值强制会把关系系统掐死（暧昧通率 8%、稳定 3%）。

**其余转移的触发条件**（供事件 condition 参考，未由引擎强制）：

| 转移 | 建议条件 |
|---|---|
| 认识 → 朋友 | intimacy ≥ 20 且互动 ≥ 2 次 |
| 朋友 → 常一起玩 | intimacy ≥ 35 且一起经历过 ≥ 1 个事件 |
| 砂糖/稳定 → 矛盾 | freshness ≤ 30 或 realPressure ≥ 60 |
| 矛盾 → 结束 | trust ≤ 30 或 realPressure ≥ 75 |

### 4.4 关键节点事件（强制剧情骨架）

| 小时 | 事件 | 事件 id 建议 | 结果 |
|---|---|---|---|
| 80-150 | 第一次遇见 ta | `sugar_a_k01` | spawn 关系，状态「认识」 |
| 95-240 | 变成固定玩伴 | `sugar_a_k02` | 状态 →「常一起玩」 |
| 140-340 | 第一次一起看日出 | `sugar_a_k03` | 状态 →「暧昧」 |
| 170-420 | "我们算什么关系" | `sugar_a_k04` | 分歧点 |
| 200-500 | **成为砂糖** | `sugar_a_k05` | 状态 →「砂糖」，sugarCount +1，tag `砂糖中` |
| 230-560 | 甜蜜中的隐忧 | `sugar_a_k06` | 加 tag `隐患` 或 `元气` |
| 200-420 | 不再心跳 | `sugar_b_k01` | freshness 加速衰减 |
| 230-480 | 第一次真正吵架 | `sugar_b_k02` | 状态 →「矛盾」 |
| 250-540 | 现实压力介入 | `sugar_b_k03` | realPressure 大涨 |
| 280-640 | **关系结束** | `sugar_b_k04` | 状态 →「结束」，breakupCount +1，tag `失恋` |
| 60+ | 低迷期的第一个夜晚 | `sugar_b_k05` | 状态 →「低迷」，mood 大跌，tag `退坑边缘` |
| 120+ | 最难熬的时刻 | `sugar_b_k06` | 状态 →「低迷」，情绪谷底 |
| 200+ | 那天有人陪你 | `sugar_b_k07` | 状态 →「恢复」，spawn 新朋友，清 `失恋`、加 `回归者` |
| 500-960 | **新的砂糖** | `sugar_b_k08` | 状态 →「砂糖」，sugarCount +1，循环重启 |

> 小时区间为**触发窗口**，实际触发点由随机步长决定，所以每次玩到的具体小时数都不同（这正是 §2.4 中"23h / 95h / 240h"这些数字的来源）。
>
> `sugar_b_k05/k06/k07` 构成恢复链，其 `hoursRange` 只设下界——它们真正的入口闸门是**关系结束后的冷却计时器**（见 §4.6），而非小时数。三者都要求 `excludeTags: ["砂糖中"]`，且各自把关系状态推进一格：`结束 → 低迷 → 恢复`。

### 4.5 结束原因池（随机）

结束事件（`sugar_b_k04`）的三种分支，每种再随机一个具体原因：

**A. ta 提出（被动结束）**
- 现实工作/学业忙不过来
- 现实里有了伴侣
- 觉得"我们还是做朋友吧"
- 要去别的平台/退坑了
- 家人发现了这段关系

**B. 你提出（主动结束）**
- 你发现自己只是依赖，不是喜欢
- 你受不了这种不确定
- 你想保护自己
- 你决定去现实里找答案
- 你只是想试试能不能放手

**C. 自然消亡（无事件结束）**
- 回复越来越慢，某天就没了
- 两个人都在等对方先开口，等到都不上线了
- 世界更新了，你们的私人世界没了
- 谁也没说分手，但都不再找对方
- 模型被换掉了，情侣装没了

> 每种原因对应不同的 mood 跌幅、不同的后续事件链、不同的 endingHint。

### 4.6 低迷期与分手冷却机制

进入条件：关系结束时 `relationOp.type = "end"`，`breakupCount +1`，加 tag `失恋`。

此处**不设「低迷期状态」这种全局开关**（早期草案里的「低迷期专用事件池 / 强制保底 / 心情基线 -1」已废弃）。
原因是那套机制要么需要引擎硬编码事件 id，要么会引入一条永远不会被清除的标记，把玩家永久锁死。
最终实现拆成两个正交的机制：**分手冷却**（引擎）与**恢复链**（数据）。

**机制 1：分手冷却（引擎，`simulate.py`）**

关系进入 `结束` 时，引擎记录 `spawnBlockUntil = hours + SPAWN_COOLDOWN_HOURS`（**120 小时**）。
冷却期内，通用事件里的 `relationOp.type = "spawn"` **一律被抑制**。

| 要点 | 说明 |
|---|---|
| 目的 | 刚失恋的这段时间不会立刻开启下一段关系，恢复链（`sugar_b_k05 → k06 → k07`）才有窗口可用 |
| 豁免 | 若某个 spawn 显式声明 `"force": true`（SCHEMA §5.2），冷却不生效。恢复链的出口 `sugar_b_k07` 就是这么写的 |
| 到期 | 冷却按小时计时，到期自动放行，玩家得以进入第二段关系 → 解锁「≥2 次砂糖」的循环结局 |
| 关系对象 | `end` **不销毁**关系对象，只把状态置为 `结束`。这样 `结束 → 低迷 → 恢复` 这条弧在状态机上可见、可被事件继续推进 |

> **为什么不用 tag 当开关**：`失恋` 标签目前从不清除，用它来抑制 spawn 等于永久锁死后续关系。
> 计时器是数据驱动的（改常数即可调参），且天然自愈。

**机制 2：恢复链（数据，`sugar_b.json`）**

`sugar_b_k05 / k06 / k07` 是三个 key 节点，入口条件为 `excludeTags: ["砂糖中"]`（"此刻不是情侣"），
各自持有一个状态转移，把关系从 `结束` 一路推回 `恢复`：

| 事件 | 状态转移 | 附加效果 |
|---|---|---|
| `sugar_b_k05` 第一个晚上 | → `低迷` | mood 大跌，tag `退坑边缘` |
| `sugar_b_k06` 最难熬的那晚 | → `低迷` | 情绪谷底 |
| `sugar_b_k07` 那天有人陪你 | → `恢复` | spawn 新朋友（`force: true`），**清除 `失恋`**，加 `回归者` |

清除 `失恋` 是循环闭合的关键：否则玩家单局永远只有一段关系，「砂糖循环」这条主线不成立。

**氛围调节（导演系统，见 §7.1）**：低迷期不靠专用事件池，而靠权重调制——
`失恋` 期间 `孤独`/`回忆` 标签事件 ×3.0、`正面` ×0.4；`mood < 30` 时正面 ×0.7、负面 ×1.3；
`负面连击 ≥ 3` 时正面 ×2.5（情绪回弹）。**不做单向下滑**。

1000 局实测：进入过低迷期 **532 局（53.2%）**，其中 **503 局（94.5%）**最终被恢复链推到 `恢复` 状态；
另 88 局（8.8%）完成过 ≥2 次砂糖，循环真正闭合。

**低迷期专用事件必须包含出口**：`idle` 桶中 6 个低迷专用事件里，至少 4 个提供向上选项；`sugar_b` 桶中至少 6 个以 `失恋` 为条件的事件，其中至少 4 个有出口。

### 4.7 循环与迭代

一次完整的砂糖循环（`sugar_a_k01` 遇见 ta → `sugar_b_k04` 关系结束）由 key 事件的触发窗口决定：
**约 200-500 小时、15-20 个事件**。之后经过分手冷却（120h）与恢复链，可在 500-960h 窗口进入下一段。

**多次循环的差异——尚未实现，仅是迭代方向**（`sugarCount` 计数器已在状态里，但没有消费它的引擎分支）：

| 循环次数 | 规划中的变化 | 现状 |
|---|---|---|
| 第 1 次 | 标准流程，mood 波动最大 | ✅ 实现 |
| 第 2 次 | 结束时 mood 跌幅 ×0.8（有经验了） | ⬜ 未实现 |
| 第 3 次 | 触发专属事件："你是不是早就知道会这样" | ⬜ 未实现 |
| 第 4 次+ | 解锁 tag `佛系`，可选择"不再找砂糖"分支 | ⬜ 未实现 |

> 想要实现时，建议在 `score()` 里按 `sugarCount` 调整 `sugar_b_*` 的权重、在 `apply_effects()` 里按次数
> 缩放 mood 负增量，而不是硬编码事件 id。当前 1000 局实测 8.8% 的局完成过 ≥2 次砂糖，
> 这个比例偏低的部分原因就是缺少这套迭代差异。

---

## 5. 事件系统

### 5.1 事件完整字段

```jsonc
{
  "id": "sugar_a_k05",
  "title": "成为砂糖",
  "category": "sugar",
  "stage": "深度社交",
  "hoursRange": [220, 420],
  "weight": 60,
  "rarity": "uncommon",
  "once": true,
  "cooldown": 0,
  "tags": ["sugar", "关键", "正面"],

  "condition": {
    "minHours": 220, "maxHours": 420,
    "hasRelation": true,
    "relationState": ["暧昧"],
    "minIntimacy": 60, "minTrust": 40,
    "excludeTags": ["砂糖中"]
  },

  "text": "你和{ta}经常一起玩。今晚在{世界}，只有你们两个。ta忽然说：我们要不要成为砂糖？",
  "options": [
    {
      "id": "yes",
      "text": "好呀",
      "condition": null,
      "lockedHint": null,
      "outcomes": [
        {
          "weight": 70, "tier": "normal",
          "text": "你们成为了砂糖。那晚你们改了同款模型，拍了很多照片。",
          "effects": {
            "mood": 20, "fame": 0, "sugarCount": 1,
            "tags": { "add": ["砂糖中", "元气"], "remove": ["暧昧"] }
          },
          "relationOp": { "type": "setState", "state": "砂糖" }
        },
        {
          "weight": 20, "tier": "rare",
          "text": "你们成为了砂糖，但ta说起现实里的工作，语气很累。你记下了这件事。",
          "effects": { "mood": 16, "sugarCount": 1, "tags": { "add": ["砂糖中", "隐患"], "remove": ["暧昧"] } },
          "relationOp": { "type": "setState", "state": "砂糖" },
          "schedule": [{ "eventId": "sugar_b_k03", "delayHours": [60, 200], "chance": 0.8 }]
        },
        {
          "weight": 10, "tier": "extreme",
          "text": "你们成为了砂糖。第二天你才知道，ta同时也在和别人说一样的话。",
          "effects": { "mood": 8, "sugarCount": 1, "tags": { "add": ["砂糖中", "隐患"], "remove": ["暧昧"] } },
          "relationOp": { "type": "setState", "state": "砂糖" },
          "schedule": [{ "eventId": "sugar_b_k02", "delayHours": [30, 90], "chance": 1.0 }]
        }
      ]
    },
    {
      "id": "maybe",
      "text": "再想想",
      "condition": null,
      "outcomes": [
        {
          "weight": 100, "tier": "normal",
          "text": "你说再想想。ta笑了笑说好，但那晚之后ta上线少了一些。",
          "effects": { "mood": -6, "tags": { "add": ["emo"] } },
          "relationOp": { "type": "setState", "state": "常一起玩" },
          "schedule": [{ "eventId": "sugar_a_k04", "delayHours": [30, 120], "chance": 0.7 }]
        }
      ]
    },
    {
      "id": "honest",
      "text": "说清楚你怕什么",
      "condition": { "minTrust": 55 },
      "lockedHint": "需要信任 ≥ 55",
      "outcomes": [
        {
          "weight": 60, "tier": "normal",
          "text": "你说了你的顾虑。ta认真听完，说：那我们就慢慢来。你们比之前更近了。",
          "effects": { "mood": 14, "tags": { "add": ["砂糖中", "元气"], "remove": ["暧昧"] } },
          "relationOp": { "type": "setState", "state": "砂糖", "initTrust": 80 }
        },
        {
          "weight": 40, "tier": "rare",
          "text": "你说完之后ta沉默了一会儿，说：其实我也是这么想的。你们决定先不做砂糖，但你们比砂糖还近。",
          "effects": { "mood": 10, "tags": { "add": ["元气"] } },
          "relationOp": { "type": "setState", "state": "稳定", "initTrust": 85 }
        }
      ]
    }
  ]
}
```

### 5.2 事件类型

| category | 说明 | 是否参与随机抽取 | 数量 |
|---|---|---|---|
| `key` | **关键节点**，达到条件**强制触发**，优先级最高 | ❌ 强制 | 26 |
| `chain` | **连锁事件**，只能被 `schedule` 安排 | ❌ 仅被安排 | 引擎生成 |
| `normal` | 普通事件，随机抽取 | ✅ | 主体 |
| `sugar` | 砂糖线事件 | ✅ | 62 |
| `random` | 随机事件（意外、抽奖、故障） | ✅ | 32 |
| `ambient` | 氛围/日常，低影响短文案 | ✅ | 主体 |
| `pity` | **保底事件**，无可用事件时兜底 | ✅（仅兜底） | 10 |

### 5.3 触发优先级（每回合判定顺序）

```
1. 强制结局判定（mood === 0 / hours ≥ 1000 且已触发 legend_k01 / 玩家主动结束）
   ↓ 否
2. 到期 scheduled 事件（按 scheduled 的 triggerAtHours 排序，取最早的 1 个，
   掷 chance 骰；失败则移除并继续）
   ↓ 无
3. 未触发的 key 事件（条件满足者中，hoursRange 最小者优先；同区间随机取 1）
   ↓ 无
4. 加权随机抽取普通事件池
   ↓ 池为空
5. 保底事件池（pity 类），保证永远有事件
```

### 5.4 选项规则

- 每个事件 **2-4 个选项**。
- 选项可有 `condition` + `lockedHint`：
  - condition 不满足 + `lockedHint` 非空 → **置灰显示**（让玩家看到"如果我当时……"）
  - condition 不满足 + `lockedHint` 为空 → **隐藏**
- **硬性保证**：每个事件必须至少有一个无 condition 的选项。校验脚本强制检查。
- 选项设计原则：三个选项应代表**三种价值取向**（投入 / 抽离 / 冒险），不是"好/中/坏"。

### 5.5 结果规则

- 每个选项 **1-3 个结果**，按 `weight` 加权随机。
- 结果分三档（`tier`）：

| tier | 建议权重占比 | 特征 |
|---|---|---|
| `normal` | 70% | 常规推进，数值小幅变化 |
| `rare` | 20% | 意外转折，改变后续事件链 |
| `extreme` | 10% | **显著改变走向**（不可只加几点属性） |

- 每个结果**必须至少修改一项状态**（`effects` / `relationOp` / `schedule` 三者之一非空）。
- 结果可以带 `endingHint`：`{"path": "legend", "score": 3}`，累积到 `endingHints`。

### 5.6 事件池抽取伪代码

```ts
function pickEvent(state: GameState, rng: RNG): Event {
  // 1. 到期的连锁事件
  const due = state.scheduled
    .filter(s => s.triggerAtHours <= state.hours)
    .sort((a, b) => a.triggerAtHours - b.triggerAtHours);
  for (const s of due) {
    state.scheduled.splice(state.scheduled.indexOf(s), 1);
    if (rng() < s.chance && flagsOk(s, state)) {
      const ev = EVENT_MAP[s.eventId];
      if (ev && match(ev.condition, state)) return ev;
    }
  }

  // 2. 关键事件（条件满足 + 未触发 + 在小时窗口内）
  const keys = ALL_EVENTS.filter(e =>
    e.category === 'key' &&
    !state.usedEvents.includes(e.id) &&
    withinHours(e, state) &&
    match(e.condition, state)
  );
  if (keys.length) return pickMinByHoursRange(keys, rng);

  // 3. 加权随机
  const pool = ALL_EVENTS.filter(e =>
    e.category !== 'key' &&
    e.category !== 'chain' &&
    e.category !== 'pity' &&
    match(e.condition, state) &&
    !(e.once && state.usedEvents.includes(e.id)) &&
    !isOnCooldown(e, state)
  );

  if (pool.length) return weightedRandom(pool.map(e => ({ e, w: scoreEvent(e, state, rng) })), rng);

  // 4. 保底
  const pity = PITY_EVENTS.filter(e => match(e.condition, state));
  return weightedRandom(pity.map(e => ({ e, w: e.weight })), rng);
}
```

### 5.7 效果应用伪代码

```ts
function applyEffects(state: GameState, fx: Effects, rng: RNG): void {
  if (!fx) return;

  state.mood    = clamp(state.mood + (fx.mood ?? 0), 0, 100);
  state.friends = clamp(state.friends + (fx.friends ?? 0), 0, 999);
  state.fame    = clamp(state.fame + (fx.fame ?? 0), 0, 100);
  state.avatars = Math.max(0, state.avatars + (fx.avatars ?? 0));
  state.assets  += fx.assets ?? 0;
  state.sugarCount  += fx.sugarCount ?? 0;
  state.breakupCount += fx.breakupCount ?? 0;

  for (const [k, v] of Object.entries(fx.skills ?? {})) {
    state.skills[k] = clamp(state.skills[k] + v, 0, 100);
  }
  for (const c of fx.circles?.add ?? [])    if (!state.circles.includes(c)) state.circles.push(c);
  for (const c of fx.circles?.remove ?? []) state.circles = state.circles.filter(x => x !== c);
  for (const t of fx.tags?.add ?? [])       if (!state.tags.includes(t)) state.tags.push(t);
  for (const t of fx.tags?.remove ?? [])    state.tags = state.tags.filter(x => x !== t);
  for (const f of fx.flags?.add ?? [])      if (!state.flags.includes(f)) state.flags.push(f);
  for (const f of fx.flags?.remove ?? [])   state.flags = state.flags.filter(x => x !== f);
  for (const [k, v] of Object.entries(fx.counters ?? {})) {
    state.counters[k] = (state.counters[k] ?? 0) + v;
  }

  deriveTags(state);   // 自动标签（见 §3.5）
}
```

### 5.8 文案模板渲染

```ts
function render(text: string, state: GameState, rng: RNG): string {
  return text
    // 随机组：{中文吧|跳舞房|私人世界}
    .replace(/\{([^{}|]+\|[^{}]*)\}/g, (_, group) => {
      const opts = group.split('|');
      return opts[Math.floor(rng() * opts.length)];
    })
    // 变量
    .replace(/\{ta\}/g,     state.relation?.name ?? '那个陌生人')
    .replace(/\{我\}/g,     state.playerName)
    .replace(/\{世界\}/g,   pick(WORLD_POOL, rng))
    .replace(/\{中文吧\}/g, '中文吧')
    .replace(/\{圈子\}/g,   state.circles.length ? pick(state.circles, rng) : '这里')
    .replace(/\{技能\}/g,   topSkillName(state))
    .replace(/\{N\}/g,      String(randInt(1, 99, rng)));
}
```

> 渲染结果应**写入 history 快照**，保证回放时文案与当时一致（不会被 rng 重新抽）。

---

## 6. 随机与数值机制

### 6.1 随机种子

- 每局生成一个 `seed`（默认 6 位数字字符串，可手动输入）。
- 使用 **mulberry32**（快、可序列化、无外部依赖）：

```ts
function mulberry32(a: number) {
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
```

- `seed` 字符串 → 数字：`hash(seed)`（FNV-1a 或简单 charCode 累加）。
- **单一 RNG 实例贯穿全局**，所有随机（抽事件、掷结果、抽小时步长、渲染文案）都从它取。这样"同 seed + 同选择 = 同结果"才成立。
- 存档时保存 `rngState`（mulberry32 的内部 `a`），可精确恢复。

### 6.2 权重计算

```
最终权重 = 基础权重
         × 阶段修正
         × 属性修正
         × 标签修正
         × 圈子修正
         × 出生修正
         × 冷却惩罚
         × 导演修正
         × 随机扰动 (0.8 ~ 1.2)
         × 防连发惩罚
```

```ts
function scoreEvent(e: Event, state: GameState, rng: RNG): number {
  let w = e.weight;

  // 阶段修正：事件主阶段与当前阶段一致时加成
  w *= (e.stage === currentStage(state.hours)) ? 1.5 : 0.6;

  // 属性修正
  if (state.mood < 30 && e.tags.includes('正面')) w *= 0.7;   // 早期用 0.4/1.8，
  if (state.mood < 30 && e.tags.includes('负面')) w *= 1.3;   // 会造成死亡螺旋，见 §7.2
  if (state.mood > 75 && e.tags.includes('负面')) w *= 0.7;
  if (state.fame > 60 && e.tags.includes('技能')) w *= 1.4;
  if (state.friends < 3 && e.tags.includes('社交')) w *= 0.6;

  // 圈子修正
  if (e.condition?.requireCircles?.length) w *= 1.3;

  // 出生修正
  const arch = ARCHETYPES[state.archetypeId];
  w *= applyArchetypeMod(arch, e, state);

  // 冷却惩罚
  if (isOnCooldown(e, state)) return 0;
  const sinceLast = state.hours - (state.lastTriggered[e.id] ?? -9999);
  if (sinceLast < e.cooldown) return 0;

  // 导演修正
  w *= directorMod(e, state);

  // 随机扰动
  w *= 0.8 + rng() * 0.4;

  // 防连发：最近 3 个事件出现过相同 tag
  if (state.recentTags.some(t => e.tags.includes(t))) w *= 0.3;

  // 最近 5 个事件内出现过同一事件
  if (state.lastEvents.includes(e.id)) w *= 0.2;

  return Math.max(0, w);
}
```

### 6.3 结果随机

- 同一选项的多个 outcome 按 `weight` 加权随机。
- 权重应是"相对值"，引擎内部归一化，不要求总和为 100。
- **结果随机必须与事件随机共享同一 RNG**，否则种子复现会失效。

### 6.4 小时步长

```ts
// 步长区间来自 vocab.json 的 hourStepByStage，不在代码里硬编码
function stepHours(state: GameState, rng: RNG): number {
  const stage = currentStage(state.hours);
  const [lo, hi] = VOCAB.hourStepByStage[stage];
  let step = randInt(lo, hi, rng);

  // 出生修正
  step *= ARCHETYPES[state.archetypeId].hourStepMod ?? 1;

  // 心态修正
  if (state.mood <= 14) step *= 1.5;    // 退坑边缘快进

  step = Math.round(step);

  // 里程碑保护
  const next = state.hours + step;
  for (const m of [10, 50, 200, 500, 1000, 5000]) {
    if (state.hours < m && next >= m && !milestoneDone(m, state)) {
      return m - state.hours;   // 精确停在里程碑
    }
  }
  return Math.max(1, step);
}
```

> 校准目标（`vocab.json` 的 `hourStepNote`）：**约 45 个事件到 500h，约 70 个事件到 1000h**，单局 55-75 个事件。

### 6.5 关系数值的自然漂移

每回合结束、推进小时之后执行：

```ts
function driftRelation(state: GameState, rng: RNG): void {
  const r = state.relation;
  if (!r) return;

  // 新鲜感持续衰减
  r.freshness = clamp(r.freshness - 2, 0, 100);

  // 亲密度：不互动则缓慢下降
  if (state.recentTags.includes('sugar')) {
    r.intimacy = clamp(r.intimacy + 1, 0, 100);
  } else {
    r.intimacy = clamp(r.intimacy - 1, 0, 100);
  }

  // 依赖度：砂糖期上升
  if (r.state === '砂糖' || r.state === '稳定') {
    r.dependence = clamp(r.dependence + 0.5, 0, 100);
  }

  // 现实压力：随机波动
  r.realPressure = clamp(r.realPressure + randInt(-3, 4, rng), 0, 100);

  // 高压自动触发结束链
  if (r.realPressure > 60 && rng() < 0.08) {
    scheduleChain(state, 'sugar_b_k04', [0, 40], 1.0);
  }

  // 新鲜感过低触发矛盾
  if (r.freshness < 30 && r.state === '砂糖' && rng() < 0.1) {
    scheduleChain(state, 'sugar_b_k02', [10, 60], 0.8);
  }
}
```

### 6.6 数值平衡参考

下表为 **1000 局模拟的实测值**（`scripts/simulate.py` 报告中的「分阶段数值」），不是设计目标：

| 阶段 | 事件数 | mood 增量均值 | mood 增量范围 | friends 增量均值 | 技能上限区间 |
|---|---|---|---|---|---|
| 初入 (0-10h) | 5308 | +0.2 | -20 ~ +13 | +0.3 | 0-31 |
| 萌新探索 (10-50h) | 7696 | +1.4 | -20 ~ +8 | +0.8 | 0-47 |
| 社交起步 (50-200h) | 14793 | +0.5 | -20 ~ +15 | +1.0 | 1-73 |
| 深度社交 (200-500h) | 18031 | **-1.5** | -20 ~ +18 | +1.0 | 10-100 |
| 老油条 (500-1000h) | 17935 | -0.9 | -20 ~ +24 | +0.1 | 13-100 |
| 传奇 (1000h+) | 4557 | +0.7 | -20 ~ +21 | +0.3 | 16-100 |

**关键平衡原则（均已由模拟验证）：**

- **mood 的净趋势由阶段决定**：深度社交期是唯一的净负阶段（-1.5/事件）——这正是砂糖线矛盾、结束、失恋集中的地方，
  是设计意图而非失衡。其余阶段在 +0.2 ~ +1.4 之间，缓慢回血。**不存在单向下滑**：全局无「每回合强制 -1」这类规则。
- **单次增量有硬上限**：正面增量按 `(100-mood)/30` 缩放（接近满值时收益递减），单个负值截断在 `-20`，
  防止一个 extreme 结果直接把玩家从满血砸到退坑。
- **好友数增长在 200h 后显著放缓**（+1.0 → +0.1），对应圈子饱和。
- **技能上限在深度社交期后段触顶**（100，个别极端局）——但门槛不算廉价：`end_creator` 要求 `modeling ≥ 36`，
  1000 局中只有 6.9% 的局真的被判定为「模型/世界大师」。
- 资产可以为负（接单赔钱、氪金超支），这本身是有趣的叙事。

---

## 7. 导演系统

### 7.1 目的

防止游戏体验单调：**不能一直低迷，也不能一直顺风顺水，更不能重复同样的剧情三次**。

### 7.2 三条规则

**规则 1：情绪回弹**
```
if (state.negativeStreak >= 3)  → 正面事件权重 ×2.5，负面 ×0.4
if (state.positiveStreak >= 4)  → 负面事件权重 ×1.4（好日子该过去了）
```

> **数值来源**：早期方案里「`mood < 30` → 正面 ×0.4 / 负面 ×1.8」与「正面连击 ≥4 → 负面 ×2.0」组合起来，
> 会在心态下滑时形成**单向下滑螺旋**：负面池被放大、正面池被压制，整个低迷期变成每回合净负的抽水，
> 1000 局模拟里出现过「mood 连续 15 个事件钉在 100（正面全浪费）后一路砸到 0（燃尽 24%）」的极端分布。
> 现在 `mood < 30` 的修正收到 **×0.7 / ×1.3**，正面连击的惩罚收到 **×1.4**——让它成为扰动而不是趋势。
> 另外引擎对 `mood` 增量做软上限（正值按 `(100-mood)/30` 缩放，单个负值截断在 -20），防止溢出与一次性砸穿。

**规则 2：防重复**
```
同一 tag 的事件在最近 3 回合内出现过 → 权重 ×0.3
同一事件在最近 5 回合内出现过     → 权重 ×0.2
同一事件在整局内出现 ≥ 3 次        → 权重 ×0.1
连续 3 个事件都是「社交」类        → 社交类权重 ×0.5，其他类 ×1.3
```

**规则 3：节奏控制**
```
每 5 个回合必须至少有 1 个「高影响」事件（|mood 变化| ≥ 15 或关系状态变化）
若连续 4 个回合所有事件的 |mood 变化| 都 < 5 → 提升高影响事件权重 ×2.5
玩家 3 个回合内没有获得任何标签/技能/关系变化 → 提升成长类事件权重 ×2.0
```

### 7.3 实现

```ts
function directorMod(e: Event, state: GameState): number {
  let m = 1.0;

  // 情绪回弹
  if (state.negativeStreak >= 5 && e.tags.includes('正面')) m *= 2.5;
  else if (state.negativeStreak >= 3 && e.tags.includes('正面')) m *= 2.5;
  if (state.negativeStreak >= 3 && e.tags.includes('负面')) m *= 0.4;
  if (state.positiveStreak >= 4 && e.tags.includes('负面')) m *= 1.4;

  // 防重复
  if (state.recentTags.some(t => e.tags.includes(t))) m *= 0.3;

  // 节奏控制
  if (state.turnsSinceHighImpact >= 4 && isHighImpact(e)) m *= 2.5;
  if (state.turnsSinceGrowth >= 3 && isGrowthEvent(e))    m *= 2.0;

  // 低迷期强制转向
  if (state.tags.includes('失恋')) {
    if (e.tags.includes('孤独') || e.tags.includes('回忆')) m *= 3.0;
    if (e.tags.includes('正面')) m *= 0.4;
  }

  return m;
}
```

### 7.4 导演系统的可观测性（调试）

开发模式下提供导演面板，实时显示：
- 当前 streak 值
- 每个事件被抽中的**最终权重**与**各项修正因子**
- 当前事件池大小与过滤掉的事件数
- 本回合的"高影响"计数器状态

---

## 8. 结局系统

### 8.1 触发条件

| 触发方式 | 条件 |
|---|---|
| 里程碑总结 | `hours >= 1000` 且触发 `legend_k01` |
| 大幅总结 | `hours >= 5000` 且触发 `legend_k02` |
| 心态归零 | `mood === 0` → 强制「燃尽」 |
| 玩家主动结束 | 结局页入口按钮 + `legend_k03` |
| 单局事件上限 | 事件数 ≥ **72** |
| 特定标签 | `传奇`、`退坑边缘` 持续 > 20 回合 |

### 8.2 结局判定算法

```ts
function resolveEnding(state: GameState): Ending {
  const scored = ENDINGS.map(e => {
    // 条件不满足直接排除
    if (!matchEndingCondition(e.condition, state)) return null;
    // lock 为 true 且条件满足 → 越权直接命中
    if (e.lock) return { e, score: Infinity, locked: true };
    // 计算分数：hint.* 是 evalScore 可读的变量之一（见 endings.json 的 scoring.vars），
    // 不做额外的 + hint*n 二次加权，权重直接写在各自的 score 表达式里。
    return { e, score: evalScore(e.score, state), locked: false };
  }).filter(Boolean);

  scored.sort((a, b) => {
    if (a.locked !== b.locked) return a.locked ? -1 : 1;
    if (b.score !== a.score) return b.score - a.score;
    return b.e.priority - a.e.priority;
  });

  return scored[0]?.e ?? ENDING_DEFAULT;
}
```

### 8.3 结局列表（16 个）

| id | 称号 | 优先级 | 触发要点 |
|---|---|---|---|
| `end_burnout` | **燃尽** | 100 (lock) | mood 归零 |
| `end_retire` | **退坑，回到现实** | 90 | 500h+ 且 mood ≤ 30 |
| `end_legend` | **VRChat 传奇** | 85 | 1000h+ 且 fame ≥ 80 |
| `end_creator` | **模型/世界大师** | 80 | 300h+ 且 modeling ≥ 36 |
| `end_leader` | **社区领袖** | 78 | 400h+ 且 friends ≥ 60 |
| `end_sugar_loop` | **砂糖循环者** | 75 | sugarCount ≥ 2 |
| `end_lonely` | **孤独探索者** | 70 | 200h+ 且 friends ≤ 25 且 photo ≥ 20 |
| `end_zen` | **佛系养老** | 65 | 800h+ 且 mood 在 50-80 |
| `end_forever_newbie` | **永远萌新** | 60 | 300h+ 且所有技能 < 30 |
| `end_creator_burnout` | **创作者倦怠** | 58 | 400h+ 且 modeling ≥ 30 且 mood ≤ 35 |
| `end_translator` | **语言的桥** | 55 | 200h+ 且 language ≥ 36 |
| `end_performer` | **舞台上的那个人** | 53 | 250h+ 且 dance ≥ 36 |
| `end_photographer` | **取景框里的人** | 52 | 250h+ 且 photo ≥ 36 |
| `end_irl_friends` | **从虚拟走进现实** | 50 | 600h+ 且 friends ≥ 50 且 flag `met_offline` |
| `end_silent` | **安静地不再来了** | 48 | 1000h+ 且无 flag `had_farewell` 且 fame ≤ 40 |
| `end_default` | **普通玩家** | 0 | 兜底 |

> 技能门槛统一取 `vocab.json` 的 `skillTiers` **「熟练」档下沿（36）**，与技能经济（见 §5.3）配套标定。
> `end_silent` 的 `maxFame: 40` 是必需的：没有它，这个条件最宽松的结局会吞掉绝大多数对局（早期版本实测占比 58.7%），
> 让技能型结局全部不可达。

完整定义（含 summaryTemplate、评分公式、雷达图配置）见 `data/endings.json`。

**1000 局实测结局分布**（15 个条件结局全部可达，无死结局）：

| 结局 | 占比 | 结局 | 占比 |
|---|---|---|---|
| 燃尽 | 24.0% | VRChat 传奇 | 2.4% |
| 取景框里的人 | 12.5% | 语言的桥 | 1.7% |
| 从虚拟走进现实 | 10.8% | 创作者倦怠 | 0.9% |
| 安静地不再来了 | 9.9% | 退坑，回到现实 | 0.6% |
| 舞台上的那个人 | 9.6% | 孤独探索者 | 0.3% |
| 社区领袖 | 9.0% | 砂糖循环者 | 0.1% |
| 佛系养老 | 7.4% | 模型/世界大师 | 6.9% |
| 永远萌新 | 3.9% | | |

### 8.4 结局页内容

```
┌─────────────────────────────────────────┐
│           【 砂糖循环者 】                │
│      "你爱过很多次，每次都很认真"          │
├─────────────────────────────────────────┤
│  累计时长    1832h                        │
│  好友数量    47                           │
│  砂糖次数    4                            │
│  失恋次数    4                            │
│  最高技能    摄影 (72)                    │
│  最终声望    小有名气                      │
├─────────────────────────────────────────┤
│  人生总结                                 │
│  你成为过 4 次砂糖，结束过 4 次。每一次你都  │
│  以为这次不一样。也许确实不一样——只是结局   │
│  相同。你还在等下一次。                    │
├─────────────────────────────────────────┤
│  [ 属性雷达图 ]                           │
│      社交 / 技能 / 声望 / 情感 / 心态 / 投入 │
├─────────────────────────────────────────┤
│  关键选择回放（8 个转折点）                │
│  · 95h   回赠礼物  → 亲密度 +15            │
│  · 240h  我也想说这个 → 成为砂糖            │
│  · 430h  主动结束  → 失恋                  │
│  · 700h  这次我慢一点 → 新的砂糖            │
├─────────────────────────────────────────┤
│  [重开]  [分享卡片]  [查看完整时间线]       │
│  种子：834271                              │
└─────────────────────────────────────────┘
```

**雷达图公式**：

| 轴 | 公式 |
|---|---|
| 社交 | `clamp(friends, 0, 100)` |
| 技能 | `clamp(skill.max, 0, 100)` |
| 声望 | `clamp(fame, 0, 100)` |
| 情感 | `clamp(sugarCount * 20 + breakupCount * 10, 0, 100)` |
| 心态 | `clamp(mood, 0, 100)` |
| 投入 | `clamp(hours / 10, 0, 100)` |

**关键选择回放**：从 `history` 中筛选出"转折点"事件——满足任一条件：
- outcome 改变了关系状态
- `|mood 变化| ≥ 15`
- 是 `category: "key"`
- 新增了标签或圈子
取最多 8 个，按时间排序。

**分享卡片**：生成一张 750×1334 的图片，包含称号、时长、雷达图、一句话总结、种子号。

---

## 9. 页面交互与 UI

### 9.1 页面结构

```
┌──────────────────────────────────────────────────────┐
│ 顶部栏                                                │
│  [ 1832h ]  [ 深度社交 ]  [ 种子 834271 ]  [☰]        │
├──────────────┬───────────────────────────────────────┤
│              │                                        │
│  左侧面板     │   中部：时间线                          │
│              │   ┌─────────────────────────────┐      │
│  心态  ████░  │   │ 240h  成为砂糖               │      │
│  声望  ██░░░  │   │ 你选了：我也想说这个          │      │
│  好友  47     │   │ → 你们成为了砂糖。            │      │
│  模型  12     │   ├─────────────────────────────┤      │
│  资产  3.2k   │   │ 430h  关系结束               │      │
│              │   │ 你选了：主动结束              │      │
│  ── 情感 ──   │   │ → ta 沉默了很久，说好。       │      │
│  砂糖中       │   ├─────────────────────────────┤      │
│  亲密度 ███░  │   │ ...                          │      │
│  新鲜感 ██░░  │   └─────────────────────────────┘      │
│  压力   ████  │                                        │
│              │   ┌─────────────────────────────┐      │
│  ── 技能 ──   │   │  当前事件卡                   │      │
│  摄影   ███   │   │  标题：深夜的中文吧            │      │
│  建模   ██░   │   │  正文：房间里只剩三个人……     │      │
│  舞蹈   █░░   │   │  [ 过去打招呼 ]                │      │
│              │   │  [ 坐在角落听 ]                │      │
│  ── 标签 ──   │   │  [ 换个世界 ]                  │      │
│  砂糖中 emo   │   └─────────────────────────────┘      │
│              │                                        │
└──────────────┴───────────────────────────────────────┘
```

### 9.2 交互流程

| 步骤 | 交互 | 反馈 |
|---|---|---|
| 1 | 玩家点击选项 | 选项按钮收起，事件卡淡出 |
| 2 | 展示结果弹层 | 结果文案 + 属性变化浮动数字（`+20 心态` 绿色上浮） |
| 3 | 弹层停留 1.5s 或玩家点击 | 淡出 |
| 4 | 时间线追加新条目 | 滚动到最新 |
| 5 | 左侧面板数值动画 | 进度条平滑过渡，标签新增有高亮闪烁 |
| 6 | 进入下一回合 | 顶部小时数滚动增加 |

### 9.3 视觉规范

**风格选项（择一或混搭）**：
- **A. VRChat 界面风**：深色 + 霓虹紫/青渐变，圆角卡片，玻璃拟态
- **B. 像素风**：8-bit 字体，硬边框，色带限制
- **C. 手账风**：米色纸感，手写字体，胶带/贴纸装饰

**推荐：A 为主 + C 的卡片质感**。

| 元素 | 规范 |
|---|---|
| 主色 | `#7C3AED`（霓虹紫） |
| 辅色 | `#06B6D4`（青）、`#EC4899`（粉，用于砂糖线） |
| 背景 | `#0F0A1E` → `#1A1033` 径向渐变 |
| 正文 | `#E9E4F5` |
| 次要文字 | `#8B7FA8` |
| 正面数值 | `#10B981` |
| 负面数值 | `#F43F5E` |
| 卡片圆角 | 16px |
| 卡片阴影 | `0 8px 32px rgba(124, 58, 237, 0.25)` |
| 正文字号 | 16px / 行高 1.8 |
| 标题字号 | 20px / 600 |

**结果 tier 的视觉区分**：
- `normal`：默认卡片色
- `rare`：青色描边 + 微光
- `extreme`：粉色描边 + 粒子动画 + 震屏（可选）

### 9.4 响应式

| 断点 | 布局 |
|---|---|
| ≥ 1024px | 三栏（左侧面板 + 时间线 + 事件卡） |
| 768-1023px | 两栏（折叠左侧面板为顶部条） |
| < 768px | 单栏，左侧面板折叠为底部抽屉，事件卡固定底部 |

**移动端关键**：选项按钮最小高度 48px，事件卡固定底部不随滚动，时间线可上滑。

### 9.5 无障碍与体验细节

- 所有交互元素支持键盘操作（数字键 1/2/3 快速选择）。
- 事件卡切换时有 `prefers-reduced-motion` 检测，关闭动画。
- 存档自动写入 localStorage，刷新不丢失进度。
- 「重开」有二次确认（避免误触毁掉长局）。

---

## 10. 数据结构

### 10.1 事件数据

完整事件数据结构见 §5.1。**权威契约文档**：`data/SCHEMA.md`。

### 10.2 事件 JSON 文件组织

```
data/
  SCHEMA.md               # 事件数据契约（唯一事实源）
  vocab.json              # 受控词表（阶段/技能/圈子/标签/心态/声望/昵称池/世界池）
  archetypes.json         # 10 种出生定义
  endings.json            # 16 个结局定义
  events/
    intro.json            # 初入      0-10h      30 个
    newbie.json           # 萌新探索   10-50h     30 个
    social.json           # 社交起步   50-200h    32 个
    sugar_a.json          # 砂糖线上   80-400h    30 个
    sugar_b.json          # 砂糖线下   200-1000h  32 个
    deep.json             # 深度社交   200-500h   30 个
    veteran.json          # 老油条     500-1000h  28 个
    legend.json           # 传奇       1000h+     24 个
    wild.json             # 随机稀有   全阶段      32 个
    idle.json             # 保底日常   全阶段      28 个
  events.index.json       # 构建产物：合并 + 索引
```

### 10.3 存档结构（localStorage）

```jsonc
{
  "version": "1.0",
  "savedAt": 1757480000000,
  "state": { /* 完整 GameState，见 §3.1 */ },
  "meta": {
    "playCount": 7,             // 累计游玩局数
    "unlockedEndings": ["end_zen", "end_lonely"],  // 已解锁结局（跨局持久）
    "unlockedArchetypes": ["arch_001", "..."],     // 已解锁出生
    "seenEvents": ["intro_001", "..."]             // 已见过的全局事件（图鉴用）
  }
}
```

### 10.4 时间线条目（HistoryEntry）

```ts
interface HistoryEntry {
  turn: number;
  hoursAtStart: number;
  hoursAfter: number;
  eventId: string;
  eventTitle: string;
  renderedText: string;        // 已渲染的正文快照（回放用，不重新渲染）
  optionId: string;
  optionText: string;
  outcomeText: string;         // 已渲染的结果文案快照
  outcomeTier: 'normal' | 'rare' | 'extreme';
  deltas: Delta[];             // 展示用的属性变化列表
  relationSnapshot: Relation | null;
  isKey: boolean;
  isTurnPoint: boolean;        // 是否算作"转折点"（结局回放用）
}

interface Delta {
  key: string;      // "mood" | "skill.photo" | "relation.intimacy"
  label: string;    // "心态" | "摄影"
  before: number;
  after: number;
  diff: number;
}
```

---

## 11. 内容清单

### 11.1 事件总数：296 个 / 40 key / 894 选项 / 1606 结果

| 桶 | 文件 | 数量 | 其中 key | 小时范围 |
|---|---|---|---|---|
| 初入 | `intro.json` | 30 | 8 | 0-10 |
| 萌新探索 | `newbie.json` | 30 | 5 | 10-50 |
| 社交起步 | `social.json` | 32 | 4 | 50-200 |
| 砂糖线·上 | `sugar_a.json` | 30 | 6 | 80-560 |
| 砂糖线·下 | `sugar_b.json` | 32 | 8 | 200-960（恢复链只设下界） |
| 深度社交 | `deep.json` | 30 | 3 | 200-500 |
| 老油条 | `veteran.json` | 28 | 3 | 500-1050 |
| 传奇 | `legend.json` | 24 | 3 | 1000+ |
| 随机稀有 | `wild.json` | 32 | 0 | 全阶段 |
| 保底日常 | `idle.json` | 28 | 0 | 全阶段 |
| **合计** | | **296** | **40** | |

**分档统计**（由 `validate_events.py` 输出）：

| category | 数量 | rarity | 数量 | tier | 数量 |
|---|---|---|---|---|---|
| normal | 124 | common | 139 | normal | 912（56.8%） |
| sugar | 48 | uncommon | 107 | rare | 552（34.4%） |
| key | 40 | rare | 39 | extreme | 142（8.8%） |
| random | 38 | legendary | 11 | | |
| ambient | 23 | | | | |
| chain | 13 | | | | |
| pity | 10 | | | | |

### 11.2 后续需补充的事件池（迭代用）

若需要继续扩充，按以下优先级：

1. **砂糖线扩展**（+20）：分手后的重逢、共同好友的婚礼、偶然看到 ta 的新砂糖、多年后的一句"最近好吗"
2. **技能专线**（+8/技能）：建模线、编程线、摄影线、舞蹈线、音乐线、语言线各一条完整成长链
3. **节日事件**（+12）：跨年、春节、中秋、圣诞、情人节、愚人节、生日、服务器周年
4. **社区事件**（+10）：活动、比赛、婚礼、葬礼、线下聚会、社区分裂
5. **角色专线**（+15）：特定 NPC 的长期支线（如"教你操作的那个人"、"总是挂机的老人"、"初见时的小学生"）

### 11.3 关键节点清单（40 个 key 事件）

| 小时 | 节点 | 桶 |
|---|---|---|
| 0-2 | 第一次登录 | intro |
| 1-4 | 第一次有人问"萌新？" | intro |
| 2-6 | 学会移动/瞬移 | intro |
| 3-8 | 第一次加好友 | intro |
| 4-9 | 第一次被送模型 | intro |
| 5-10 | 第一次开麦说话 | intro |
| 6-10 | 第一次去中文吧 | intro |
| 8-10 | 第一次被冷落 | intro |
| 10-20 | 第一次换 Avatar | newbie |
| 15-30 | 第一次被记住名字 | newbie |
| 20-40 | 第一次参加群体活动 | newbie |
| 25-48 | 第一次想学做模型 | newbie |
| 30-50 | 第一次通宵在线 | newbie |
| 50-90 | 第一次成为圈子固定成员 | social |
| 90-150 | 第一次技能达到"熟练" | social |
| 120-180 | 第一次被人主动找 | social |
| 150-200 | 第一次社交过载 | social |
| 80-150 | 第一次遇见 ta | sugar_a |
| 95-240 | 变成固定玩伴 | sugar_a |
| 140-340 | 第一次一起看日出 | sugar_a |
| 170-420 | "我们算什么关系" | sugar_a |
| 200-500 | **成为砂糖** | sugar_a |
| 230-560 | 甜蜜中的隐忧 | sugar_a |
| 200-260 | 第一次被叫"大佬" | deep |
| 280-380 | 第一次出圈 | deep |
| 400-500 | 意识到投入太多 | deep |
| 200-420 | 关系日常化 | sugar_b |
| 230-480 | 第一次真正吵架 | sugar_b |
| 250-540 | 现实压力介入 | sugar_b |
| 280-640 | **关系结束** | sugar_b |
| 60+ | 低迷期的第一个夜晚 | sugar_b |
| 120+ | 最难熬的时刻 | sugar_b |
| 200+ | 那天有人陪你 | sugar_b |
| 500-960 | **新的砂糖** | sugar_b |
| 500-620 | 该退了吗 | veteran |
| 560-700 | 断舍离 | veteran |
| 760-1050 | 回归 | veteran |
| 1000-1025 | **一千小时** | legend |
| 1350-2150 | 五千小时 | legend |
| 1000+ | 主动结束（最后一扇门） | legend |

### 11.4 事件质量清单

每个事件必须满足：
- [ ] 有具体的场景描写（世界名、动作、对话），不空泛
- [ ] 至少一个模板变量或随机组
- [ ] 选项代表三种不同价值取向，不是好坏之分
- [ ] 至少一个 `tier: "extreme"` 结果能改变走向
- [ ] 结果文案有"意外感"，不是选项的直译
- [ ] 不出现真实人物、真实平台纠纷、政治内容

---

## 12. 技术方案

### 12.1 技术栈

| 层 | 选型 | 理由 |
|---|---|---|
| 框架 | React 18 + TypeScript | 类型安全，事件数据结构复杂 |
| 构建 | Vite | 快，配置简单 |
| 状态管理 | Zustand | 轻量，适合单一 store 的游戏状态 |
| 样式 | Tailwind CSS | 快速迭代，响应式方便 |
| 随机 | 自实现 mulberry32（无依赖） | 可序列化，可复现 |
| 内容 | JSON | 可直接被事件编辑器读写 |
| 存储 | localStorage | 无需后端 |
| 图表 | 自绘 SVG（雷达图） | 避免引入图表库 |
| 测试 | Vitest + fast-check | 单测 + 属性测试（种子复现） |
| 部署 | 静态托管（Vercel / Netlify / GitHub Pages） | — |

### 12.2 目录结构

```
src/
  main.tsx
  App.tsx
  store/
    gameStore.ts          # Zustand store
    actions.ts            # 纯函数式状态变更
  engine/
    rng.ts                # mulberry32 + hash + randInt/pick/weightedRandom
    eventPool.ts          # 事件池构建、过滤、加权抽取
    condition.ts          # condition DSL 求值
    effects.ts            # effects / relationOp / schedule 应用
    director.ts           # 导演系统
    relation.ts           # 关系状态机、数值漂移
    ending.ts             # 结局判定
    template.ts           # 文案模板渲染
    derive.ts             # 派生值（心态档位、自动标签等）
    types.ts              # 所有 TS 类型
  components/
    TopBar.tsx            # 小时数 / 阶段 / 种子
    SidePanel.tsx         # 属性面板
    Timeline.tsx          # 时间线
    EventCard.tsx         # 当前事件卡
    OptionButton.tsx      # 选项按钮（含 locked 态）
    ResultOverlay.tsx     # 结果弹层 + 数值浮动
    EndingScreen.tsx      # 结局页
    RadarChart.tsx        # 雷达图
    ShareCard.tsx         # 分享卡片
    StartScreen.tsx       # 开始页（输入种子 / 选出生）
  data/
    loader.ts             # 加载 data/*.json 并合并成索引
  utils/
    storage.ts            # localStorage 读写
    format.ts             # 数值格式化
scripts/
  validate-events.ts      # 事件数据校验（CI 必跑）——移植 scripts/validate_events.py 的规则
  build-index.ts          # 生成 events.index.json ——移植 scripts/build_index.py
  simulate.ts             # 1000 局无头模拟 ——移植 scripts/simulate.py
```

> 上述三个 `scripts/*.ts` 是**待实现**的前端版。当前仓库里已有等价的 Python 参考实现
> （`validate_events.py` / `build_index.py` / `simulate.py`），数据契约以它们为准；
> TS 版的作用是把校验与模拟纳入前端 CI。

### 12.3 校验脚本（`scripts/validate-events.ts`）

**CI 必跑**，任何一条失败则构建失败：

```
1. 所有 id 唯一，符合命名规范（前缀 + 序号）
2. hoursRange 与 condition.minHours/maxHours 一致
3. stage 与 hoursRange 主段一致
4. options 数量 2-4
5. 每个 option 的 outcomes 数量 1-3
6. 每个 outcome 至少有一项 effects / relationOp / schedule 非空
7. 每个事件至少有一个无 condition 的 option（保证永远可选）
8. tags / skills / circles 取值均在 vocab 中
9. schedule 引用的 eventId 存在于全部事件中
10. relationOp.state 在合法状态枚举内
11. 所有 once: true 的 key 事件在其 hoursRange 内 condition 可达
    （静态分析：是否存在满足条件的状态空间，至少做符号级检查）
12. 每个小时段 [0,10) [10,50) [50,200) [200,500) [500,1000) [1000,∞)
    至少有 10 个非 key 事件可被触发（模拟 100 局统计触达率）
13. 文案长度：text ≤ 120 字，outcome.text ≤ 100 字
14. 禁止词检查：真实人物名、政治敏感词
```

### 12.4 测试策略

| 测试类型 | 内容 |
|---|---|
| 单元测试 | `condition` 求值、`effects` 应用、模板渲染、状态机转移合法性 |
| 属性测试 | 随机 1000 个状态，`pickEvent` 永远返回非空；`applyEffects` 后数值永远在范围 |
| 快照测试 | 固定 seed + 固定选择序列 → 断言最终 GameState 完全一致 |
| 集成测试 | 模拟 1000 局自动游玩（随机选择），断言：无异常、每局 ≥ 45 事件、结局分布合理、低迷期能恢复 |
| 覆盖率测试 | 跑 1000 局，统计每个事件被触发的次数，找出**从未触发**的事件（死事件） |
| 平衡测试 | 跑 1000 局，统计结局分布、平均局时长、平均事件数、mood 曲线 |

**平衡目标 vs 1000 局实测**：

| 指标 | 目标 | 实测 |
|---|---|---|
| 平均单局事件数 | 55-75 | **68.3**（min 35, max 72） |
| 平均单局时长 | 900-1300h | **1150h**（min 348, max 1673） |
| 死事件数 | 0 | **0**（触达 296/296） |
| 非法状态转移 | 0 | **0** |
| 最高结局占比 | ≤ 25% | **24.0%**（燃尽） |
| 条件结局全部可达 | 15/15 | **15/15** |
| 心情曲线 | 不单调下降 | 深度社交期为唯一净负阶段（-1.5/事件），其余为净正 |

> **稀有结局是刻意的**：「孤独探索者」「砂糖循环者」停在 0.1-0.3%，因为它们的条件苛刻
> （前者要求好友极少却摄影熟练，后者要求 ≥2 次完整失恋）。这不视为「不可达」——
> 覆盖率测试只断言**占比 > 0**，不断言下限。把稀有结局强行拉到 1% 会让叙事失真。

### 12.5 性能

- 全部事件 JSON 体积预估 < 500KB（gzip 后 < 100KB）。
- 事件池过滤 + 打分每次 O(n)，n ≈ 300，可忽略。
- 首次加载：JSON 解析 < 50ms。
- 时间线超过 100 条时使用虚拟滚动。

---

## 13. 开发计划与迭代

### 13.1 MVP（第 1 阶段）

| 模块 | 交付物 |
|---|---|
| 引擎 | rng / condition / effects / eventPool / template / derive |
| 内容 | 296 个事件（40 key / 894 选项 / 1606 结果）、10 个出生、16 个结局 |
| 界面 | 开始页、主界面（顶部栏 + 侧栏 + 时间线 + 事件卡）、结果弹层、结局页 |
| 功能 | 小时推进、事件抽取、选项、随机结果、时间线、重开、种子输入 |
| 存储 | localStorage 自动存档 |
| 质量 | 校验脚本、单元测试、1000 局模拟 |
| **验收** | 见 §14 |

### 13.2 第 2 阶段

- 导演系统完整实现 + 调试面板
- 结局分享卡片（Canvas 导出 PNG）
- 成就系统（30 个成就）
- 事件图鉴（已见过的全局事件收集）
- 出生解锁（达成特定结局解锁稀有出生）
- 音效与动画（选择音、结果音、tier 特效）
- 更多事件（+80，按 §11.2 优先级）

### 13.3 第 3 阶段

- 账号系统 + 云存档
- UGC 事件编辑器（可视化编辑 JSON，导出/导入）
- AI 生成事件文案（接入 LLM，用 SCHEMA 约束输出）
- 排行榜（最长时长、最多砂糖、最稀有结局）
- 多人对比（同一 seed 两个人跑，比较结果）
- 数据统计页（全局结局分布、事件触发热力图）

---

## 14. 验收标准

### 14.1 功能验收

- [ ] 每局至少触发 45 个事件，上限 **72** 个后自动结算。
- [ ] 至少 16 种结局，且每个条件结局都有可达路径（模拟验证）。
- [ ] 同一 seed + 同一选择序列 → 最终 GameState 完全一致（含渲染后文案）。
- [ ] 无满足条件事件时，自动触发保底事件；连续 100 回合不会出现"无事件"。
- [ ] 属性、小时数、标签、关系数值变化正确，且始终在合法范围内。
- [ ] 砂糖关系循环至少能完整走通一次：接触 → 暧昧 → 砂糖 → 矛盾 → 结束 → 低迷 → 恢复 → 新砂糖。
- [ ] 低迷期必有出口：模拟 1000 局，进入低迷期的局中 ≥ 90% 能恢复到 `恢复` 状态（除非 mood 归零）。
- [ ] 每个事件至少有一个无条件的选项，永不卡死。
- [ ] 存档、读档、重开功能正常。
- [ ] 移动端（375px 宽）可正常操作，选项按钮可点击。

### 14.2 数据验收

**以下全部已在 `scripts/` 的 Python 参考实现中通过。**

- [ ] **296 个事件**全部通过 `validate_events.py`（0 ERROR）。
- [ ] 无重复 id，无死引用（`schedule` 指向不存在的 id）。
- [ ] 所有 tags / skills / circles 取值在 vocab 内。
- [ ] 每个小时段至少 10 个可触发事件。
- [ ] 无事件从未被触发（跑 1000 局，**触达 296/296**）。
- [ ] 关系状态机无非法转移（跑 1000 局，**非法转移 0 次**）。

### 14.3 体验验收

- [ ] 单局时长 5-15 分钟（按平均 **68** 个事件、每个 8-15 秒计算）。
- [ ] 文案单屏可读完，无滚动。
- [ ] 无致命报错（1000 局模拟 0 异常）。
- [ ] 情绪曲线合理：不会连续 5 个事件都在掉心态。
- [ ] 至少 1 个结局能让人想截图分享。

### 14.4 内容验收

- [ ] 无真实人物、真实政治、真实平台纠纷。
- [ ] 不出现说教、鸡汤、感叹号堆砌。
- [ ] 砂糖关系事件的描写中立、细腻、有痛感。
- [ ] 每个事件的 extreme 结果都能改变走向，不是数值微调。

---

## 15. 附录

### 15.1 术语表

| 术语 | 含义 |
|---|---|
| **砂糖** | VRChat 中文社群对"虚拟伴侣/CP"的称呼 |
| **贴贴** | 两个 Avatar 靠在一起（拥抱/依偎）的动作 |
| **Avatar** | 虚拟形象模型 |
| **World** | 玩家可进入的虚拟场景 |
| **改模** | 修改现成模型（换衣服、改身材、加配件） |
| **Udon** | VRChat 的脚本系统，用于制作可交互的世界 |
| **Quest** | 一体机版本，画质受限但无需 PC |
| **VRC+** | VRChat 的付费订阅 |
| **中文吧** | 中文玩家聚集的经典世界 |
| **开麦** | 打开麦克风说话 |
| **挂机** | 在线但不动、不说话 |
| **退坑** | 不再玩这个游戏 |
| **整活** | 制造节目效果、搞笑 |
| **老油条** | 玩很久的老玩家 |
| **萌新** | 新手 |

### 15.2 参考体验

- 《人生重开模拟器》：核心循环与随机事件池的结构参考
- 《中国式家长》：阶段推进与属性积累的节奏参考
- 《去月球》：情感叙事的克制与留白参考

### 15.3 风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| 事件重复感强 | 玩家重开几次就腻 | 296 个事件 + 导演系统防重复 + 权重随机 |
| 数值失衡 | 玩家必然退坑或必然传奇 | 1000 局模拟调参（`scripts/simulate.py`）+ 平衡测试进 CI |
| 文案同质化 | 读起来像一个人写的 | 分桶并行创作 + 风格指南 + 交叉评审 |
| 低迷期太难熬 | 玩家直接关掉 | 分手冷却（120h）保证恢复链有窗口 + 步长 ×1.5 + 情绪回弹导演（负面连击 ≥3 → 正面 ×2.5） |
| 死事件 | 写了但永远触发不到 | 覆盖率测试，1000 局触达率必须 100%（当前 296/296） |
| 关系被永久锁死 | 单局只有一段关系，循环主线不成立 | 分手冷却用**计时器**而非 tag 驱动；`sugar_b_k07` 显式清除 `失恋` 标签 |
| 砂糖线过重 | 非情感向玩家不适 | key 事件可跳过 + 提供"只谈 VRChat"分支 |
| 题材敏感性 | 被误解为鼓吹网恋 | 保持中立叙述 + 结局多样性（不只有爱情结局） |

### 15.4 待决问题

1. 玩家昵称是否需要？还是统称"你"？（倾向：开始页可选填，默认"你"）
2. 是否允许同时存在多段关系？（倾向：MVP 单关系，第 2 阶段支持多关系）
3. 结局页是否要展示"如果你当初选了另一个"？（倾向：第 2 阶段）
4. 是否需要"跳过已读文案"功能？（倾向：需要，重开体验关键）
5. 分享卡片是否包含敏感信息（如具体选择）？（倾向：仅展示统计与称号）

### 15.5 文件清单

```
vrclife/
├── PRD.md                        # 本文档
├── VRChat 玩家历程模拟器.txt       # 原始需求草案 v0.2
├── data/
│   ├── SCHEMA.md                 # 事件数据契约（唯一事实源）
│   ├── vocab.json                # 受控词表（含 hourStepByStage）
│   ├── archetypes.json           # 10 种出生
│   ├── endings.json              # 16 个结局
│   ├── events.index.json         # 构建产物：10 桶合并 + endingHint 别名规范化
│   └── events/
│       ├── intro.json            # 30（key 8）
│       ├── newbie.json           # 30（key 5）
│       ├── social.json           # 32（key 4）
│       ├── sugar_a.json          # 30（key 6）
│       ├── sugar_b.json          # 32（key 8）
│       ├── deep.json             # 30（key 3）
│       ├── veteran.json          # 28（key 3）
│       ├── legend.json           # 24（key 3）
│       ├── wild.json             # 32
│       └── idle.json             # 28
└── scripts/
    ├── validate_events.py        # 静态契约校验（对应 SCHEMA §10）
    ├── build_index.py            # 合并 10 桶 → events.index.json
    └── simulate.py               # 无头模拟器：死事件 / 可达性 / 平衡 / 结局分布
```

### 15.6 如何验证交付物

三个脚本是**数据的可执行验收标准**，实现引擎前应先跑通：

```bash
python3 scripts/validate_events.py     # 期望：0 ERROR（8 条 endingHint 别名 WARN 属正常）
python3 scripts/build_index.py         # 重建 data/events.index.json
python3 scripts/simulate.py 1000       # 期望：见 §12.4 平衡目标表
```

`simulate.py` 是**唯一的平衡性真相来源**——它用 Python 实现了一遍引擎的 condition / effects /
relationOp / 导演 / 结局判定语义。TS 引擎的行为若与它不一致，以数据契约为准并回过来对齐模拟器。
静态校验查不出的问题（死事件、非法状态转移、数值越界、结局不可达）全靠它暴露。

---

**文档结束**

> 下一步：按 `data/SCHEMA.md` 契约实现引擎（TypeScript），用 `validate_events.py` 的规则写
> `validate-events.ts`，用 `simulate.py` 的语义写引擎单测，然后接入 UI。
