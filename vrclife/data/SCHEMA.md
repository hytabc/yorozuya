# 事件数据契约 v1.0（冻结版）

> 本文件是所有事件 JSON 的**唯一契约**。生成事件时必须严格遵守；引擎、校验脚本、事件编辑器均以此为单一事实源。
> 任何字段的增删都必须先改本文件，再改数据。

---

## 0. 文件组织

```
data/
  SCHEMA.md              # 本文件
  vocab.json             # 受控词表（引擎可读版本）
  events/
    intro.json           # 初入期      0-10h
    newbie.json          # 萌新探索    10-50h
    social.json          # 社交起步    50-200h
    sugar_a.json         # 砂糖线·上  接触→暧昧→成为砂糖
    sugar_b.json         # 砂糖线·下  美好→矛盾→结束→低迷→新砂糖
    deep.json            # 深度社交    200-500h
    veteran.json         # 老油条      500-1000h
    legend.json          # 传奇        1000h+
    wild.json            # 随机/稀有事件
    idle.json            # 保底/日常/氛围事件
  endings.json           # 结局定义
  archetypes.json        # 出生（初始身份）定义
```

每个 events/*.json 的顶层格式：

```json
{
  "bucket": "intro",
  "version": "1.0",
  "events": [ /* Event[] */ ]
}
```

---

## 1. Event 结构

```jsonc
{
  "id": "intro_001",              // 全局唯一，见 §7 命名规范
  "title": "第一次进入 VRChat",     // ≤12 字，时间线/卡面标题
  "category": "key",              // 见 §2 category
  "stage": "初入",                // 见 §3 stage，必须是单值
  "hoursRange": [0, 10],          // [min, max]，闭区间；与 condition.minHours/maxHours 冗余但必须一致
  "weight": 100,                  // 基础权重，≥1 的整数
  "rarity": "common",             // common | uncommon | rare | legendary
  "once": true,                   // true=整局只能触发一次
  "cooldown": 0,                  // 触发后冷却的小时数；once=true 时无效
  "tags": ["初入", "社交"],         // 事件分类标签，用于防连发与导演系统，见 §5

  "condition": { /* 见 §4，全部可选 */ },

  "text": "……",                   // 正文，支持 §6 模板变量，建议 30-90 字
  "options": [ /* Option[]，2-4 个 */ ]
}
```

### 字段硬性要求

| 字段 | 必填 | 约束 |
|---|---|---|
| id | ✅ | 全局唯一，小写字母+数字+下划线 |
| title | ✅ | ≤12 个汉字 |
| category | ✅ | 枚举 |
| stage | ✅ | 枚举，单值 |
| hoursRange | ✅ | `[int,int]`，min ≤ max |
| weight | ✅ | 整数 1-1000 |
| rarity | ✅ | 枚举 |
| once | ✅ | bool |
| cooldown | ✅ | 整数 ≥0 |
| tags | ✅ | 1-3 个，取自 §5 |
| condition | ✅ | 对象，可写 `{}` 表示无限制 |
| text | ✅ | 含至少一个 `{占位}` 或 `|随机组|` 更佳 |
| options | ✅ | 2-4 个 |

---

## 2. category 枚举

| 值 | 说明 | 典型权重 |
|---|---|---|
| `key` | 关键节点，达到条件**强制触发**（不参与加权随机） | 100 |
| `normal` | 普通事件，随机抽取 | 20-60 |
| `chain` | 连锁事件，只能被 `schedule` 安排，**不进入随机池** | 40 |
| `random` | 随机事件（意外、抽奖、故障） | 10-40 |
| `pity` | 保底事件，无可用事件时兜底 | 1 |
| `sugar` | 砂糖关系线事件 | 30-80 |
| `ambient` | 氛围/日常事件，低影响短文案 | 10-30 |

> `key` 与 `chain` 的 `weight` 字段仍必填（用于排序与展示），但引擎不按权重抽取它们。

---

## 3. stage / hoursRange 阶段划分

| stage | hoursRange | 主题 |
|---|---|---|
| `初入` | [0, 10] | 第一次登录、教程、默认模型、社恐、第一次加好友 |
| `萌新探索` | [10, 50] | 逛世界、中文吧、第一次跳舞、被送模型、学基础操作 |
| `社交起步` | [50, 200] | 常驻圈子、技能入门、固定玩伴、第一次暧昧 |
| `深度社交` | [200, 500] | 砂糖期、社区小有名气、办活动、技能成型 |
| `老油条` | [500, 1000] | 社区名人、带新人、退坑念头、回归、关系破裂 |
| `传奇` | [1000, 99999] | 传奇、总结、退坑、传承 |

允许事件 `hoursRange` 跨阶段（如 `[180, 320]`），但 `stage` 取主阶段。

---

## 4. condition（触发条件 DSL）

**所有字段可选；缺省或 `null` 表示不限制。**

```jsonc
"condition": {
  "minHours": 0,                  // 累计时长下限
  "maxHours": 99999,              // 累计时长上限
  "minMood": 0,                   // 心态 0-100
  "maxMood": 100,
  "minFame": 0,                   // 声望 0-100
  "minFriends": 0,                // 好友数
  "maxFriends": null,
  "minAvatars": 0,                // 模型数
  "minAssets": 0,                 // 资产

  "requireTags": [],              // 必须全部拥有
  "requireAnyTags": [],           // 至少拥有其一
  "excludeTags": [],              // 必须一个都没有

  "requireFlags": [],             // 必须全部已设置（剧情旗标）
  "excludeFlags": [],             // 必须一个都未设置

  "requireCircles": [],           // 必须已加入的圈子
  "minSkills": { "dance": 20 },   // 技能下限，键见 §3.2
  "minSugarCount": 0,             // 累计砂糖次数下限
  "minBreakupCount": 0,           // 累计失恋次数下限

  "hasRelation": null,            // true=当前有活跃关系 false=无 null=不限
  "relationState": [],            // ["暧昧","砂糖"] 当前关系状态需命中其一
  "minIntimacy": 0,               // 当前关系亲密度下限
  "minDependence": 0,
  "minTrust": 0,
  "minFreshness": 0,
  "minRealPressure": 0,
  "maxRealPressure": null,

  "requiresEventDone": [],        // 前置事件 id（必须已触发过）
  "excludesEventDone": [],        // 前置事件 id（必须未触发过）
  "requiresEndingPath": [],       // 预留：结局倾向旗标

  "probability": null             // 额外独立触发概率 0-1；null=1（必定）
}
```

### Option.condition

同结构，但**通常只用**这几项：`minIntimacy`、`minSkills`、`requireTags`、`hasRelation`、`relationState`、`minFame`、`minFriends`、`minAvatars`、`requireFlags`。

```jsonc
{
  "id": "confess",
  "text": "表白",
  "condition": { "minIntimacy": 60, "relationState": ["暧昧"] },
  "lockedHint": "需要亲密度 ≥ 60",   // condition 不满足时置灰显示的提示；为空则隐藏该选项
  "outcomes": [ /* Outcome[]，1-3 个 */ ]
}
```

- 若 `condition` 不满足且 `lockedHint` 非空 → **置灰显示**。
- 若 `condition` 不满足且 `lockedHint` 为空 → **隐藏**。
- 保证：任何事件在任何状态下**至少有一个选项可选**。

---

## 5. Outcome（结果）

```jsonc
{
  "weight": 70,                   // 同一 option 内相对权重
  "tier": "normal",               // normal | rare | extreme（仅用于 UI 着色与统计）
  "text": "你加到了第一个好友，学会了基础操作。",   // 结果文案，20-80 字
  "effects": { /* 见 §5.1 */ },
  "relationOp": { /* 见 §5.2，可选 */ },
  "schedule": [ /* 见 §5.3，可选 */ ],
  "endingHint": null              // 可选：给结局系统 +N 倾向分，格式 {"path": "legend", "score": 3}
}
```

建议配比：同一 option 内 1 个 normal（权重 60-80）+ 可选 rare（15-30）+ 可选 extreme（5-12）。
**tier 与 weight 不必强绑定**，但 extreme 结果必须显著改变走向（不可只加几点属性）。

### 5.1 effects DSL

**所有键可选，数值为正负整数。**

```jsonc
"effects": {
  "mood": 5,                      // 心态 -100..100（引擎夹取到 0-100）
  "friends": 1,                   // 好友数
  "fame": 2,                      // 声望
  "avatars": 1,                   // 模型数
  "assets": 100,                  // 资产
  "sugarCount": 1,                // 累计砂糖次数（+1）
  "breakupCount": 1,              // 累计失恋次数（+1）
  "hoursBonus": 5,                // 额外推进小时（少见，慎用）

  "skills": { "modeling": 3, "dance": -1 },        // 技能增减
  "circles": { "add": ["中文吧"], "remove": [] },   // 圈子增减
  "tags":    { "add": ["话痨"], "remove": ["社恐"] },
  "flags":   { "add": ["met_mentor"], "remove": [] },
  "counters": { "photosTaken": 1 }                 // 自定义计数器，用于后续条件
}
```

### 5.2 relationOp

```jsonc
"relationOp": {
  "type": "spawn",          // spawn | setState | end | renew | none
  "state": "认识",           // 关系状态机中的状态，见 vocab.json
  "name": "auto",           // "auto"=引擎随机抽中文昵称；也可写死如"阿澈"

  // —— 绝对赋值：直接把该维度设为这个值 ——
  "initIntimacy": 10,
  "initTrust": 5,
  "initFreshness": 90,
  "initDependence": 0,
  "initRealPressure": 0,

  // —— 增量赋值：在当前值基础上增减（可正可负）——
  "intimacy": 8,
  "trust": 5,
  "freshness": -10,
  "dependence": 2,
  "realPressure": 15
}
```

**关系数值的两种写法（这是最容易写错的地方）：**

| 写法 | 语义 | 典型用途 |
|---|---|---|
| `initXxx`（如 `initIntimacy`） | **绝对赋值** `r.intimacy = 10` | `spawn` 时初始化；需要"重置到某个确定值"时 |
| `xxx`（如 `intimacy`） | **增量** `r.intimacy += 8` | 日常互动、吵架、亲密度推进——绝大多数场景用这个 |

**应用顺序**：先应用全部 `init*` 绝对赋值 → 再应用全部裸名增量 → 最后夹取到 `[0, 100]`。

**规则**：
- 五个可操作维度：`intimacy` / `trust` / `freshness` / `dependence` / `realPressure`，对应字段名去掉 `init` 前缀。
- `type: "end"` 时**忽略所有数值键**（关系即将清空）。
- 当前**无活跃关系**时，数值键被静默忽略（不报错）。
- `force`（可选，布尔）：**低迷期豁免**。当玩家带有 `失恋` 标签时，引擎会抑制所有 `spawn`
  ——你刚失恋，不会立刻开始下一段。设计好的恢复节点需要显式写 `"force": true` 来绕过该抑制
  （目前只有 `sugar_b_k07` 那天有人陪你、`sugar_b_k08` 新的砂糖 使用）。
  这是**数据驱动**的开关，引擎不硬编码任何事件 id。
- 两种写法**可以同时出现**在同一 relationOp 上（先赋值再增减）。
- `type` 语义：
  - `spawn`：若无活跃关系则创建；**若已有则忽略整个关系创建**（但数值键仍会应用到现有关系上）。
  - `setState`：推进当前关系状态。若目标状态不在合法转移表（§4.3）中，**引擎拒绝转移并记录警告**，数值键照常应用。
  - `end`：结束当前关系，清空 relation。`sugarCount` / `breakupCount` 已累计的不受影响。
  - `renew`：`freshness` 重置为 90、`realPressure` 清零，其余维度保留。
  - `none`：只应用数值键，不改状态（用于纯数值互动事件）。

### 5.3 schedule（连锁事件）

```jsonc
"schedule": [
  { "eventId": "sugar_conflict_001", "delayHours": [10, 60], "chance": 0.7,
    "requireFlags": [], "excludeIfFlags": ["sugar_resolved"] }
]
```

- `delayHours`：`[min,max]` 随机，或固定整数。
- `chance`：0-1，到时掷骰决定是否触发。
- **被安排的事件可以是任意 category**（`chain` / `normal` / `sugar` / `key` 均可）。
  引擎在连锁通道命中时直接返回该事件，并照常标记 `usedEvents`（若 `once: true`）。
- `requireFlags` / `excludeIfFlags`：可选，用于给连锁加额外门槛。

---

## 6. 文案模板变量

出现在 `text` / `outcome.text` 中，引擎渲染时替换：

| 变量 | 含义 |
|---|---|
| `{ta}` | 当前关系对象昵称；无关系时渲染为“某个陌生人” |
| `{我}` | 玩家昵称 |
| `{世界}` | 随机世界名 |
| `{中文吧}` | 固定“中文吧” |
| `{圈子}` | 玩家所属随机圈子 |
| `{技能}` | 玩家最高技能名 |
| `{N}` | 1-99 随机整数 |

随机组语法：`{中文吧|跳舞房|私人世界}` → 等概率取其一。
文案中每 1-2 句最多用 1 个随机组，避免阅读割裂。

---

## 7. ID 命名规范

`{bucket前缀}_{三位序号}`，序号从 001 连续递增，**不得跳号、不得重号**。

> ⚠️ **跨桶 schedule 引用必须落在目标桶的实际编号范围内**。各桶普通事件编号上限：
> intro 022 / newbie 025 / social 028 / sugar_a 024 / sugar_b 024 /
> deep 027 / veteran 025 / legend 021 / wild 032 / idle 028。
> 引用 `newbie_030` 这种超出上限的 id 是**错误**（该 id 不存在）。

| bucket | 前缀 | 序号区间 |
|---|---|---|
| intro | `intro` | 001-099 |
| newbie | `newbie` | 001-099 |
| social | `social` | 001-099 |
| sugar_a | `sugar_a` | 001-099 |
| sugar_b | `sugar_b` | 001-099 |
| deep | `deep` | 001-099 |
| veteran | `veteran` | 001-099 |
| legend | `legend` | 001-099 |
| wild | `wild` | 001-099 |
| idle | `idle` | 001-099 |

关键节点事件（`category: "key"`）在序号前加 `k`，如 `intro_k01`——**同一 bucket 内 key 事件单独编号**，形式 `{前缀}_k{两位序号}`。

---

## 8. 受控词表（vocab）

### 8.1 技能键（skills）

| 键 | 中文 | 影响 |
|---|---|---|
| `modeling` | 建模 | 改模型、做衣服、接单 |
| `coding` | 编程 | 写世界、做插件、Udon |
| `photo` | 摄影 | 拍照、出片、被关注 |
| `music` | 音乐 | 弹琴、DJ、做歌 |
| `dance` | 舞蹈 | 跳舞、舞房、演出 |
| `language` | 语言 | 语言交换、当翻译 |
| `social` | 社交 | 认识人、办活动、调解 |
| `meme` | 整活 | 搞笑、节目效果、玩梗 |

技能值 0-100，分级：0-9 入门 / 10-29 熟悉 / 30-59 熟练 / 60-84 高手 / 85+ 大师。

### 8.2 圈子（circles）

`中文吧` `跳舞圈` `模型圈` `摄影圈` `游戏圈` `语言交换圈` `音乐圈` `整活圈` `恐怖圈` `竞赛圈` `绘画圈` `ASMR圈`

### 8.3 状态标签（tags）

**核心标签（引擎有特殊逻辑，只能用这些拼写）：**

`萌新` `社恐` `话痨` `模型师` `摄影师` `舞者` `翻译` `夜猫子` `砂糖中` `失恋` `退坑边缘` `回归者` `暧昧` `隐患` `佛系` `整活王` `社区名人` `传奇` `独行侠` `挂机党` `小透明` `老好人` `元气` `疲惫`

**扩展标签（可自由使用，用于描述性标记）：**

`手残` `天赋型` `氪金` `白嫖` `技术宅` `审美在线` `声音好听` `社牛` `被动` `emo` `怀旧` `断舍离` `跨语言` `时差党` `VR晕` `设备党` `收藏家` `活动咖` `自闭` `开麦恐惧`

### 8.4 心态档位（由 mood 数值派生，不可直接写入）

| mood | 心态 |
|---|---|
| 80-100 | 好奇 |
| 60-79 | 热情 |
| 35-59 | 疲惫 |
| 15-34 | 低迷 |
| 1-14 | 退坑边缘 |
| 0 | 退坑（触发结局） |

### 8.5 声望档位（由 fame 数值派生）

| fame | 声望 |
|---|---|
| 0-19 | 默默无闻 |
| 20-49 | 小有名气 |
| 50-79 | 社区名人 |
| 80-100 | 传奇 |

### 8.6 关系状态机（relationState）

```
陌生人 → 认识 → 朋友 → 常一起玩 → 暧昧 → 砂糖 → 稳定
                                          ↓
                                       矛盾 → 结束 → 低迷 → 恢复 → (新关系)
```

枚举值：`陌生人` `认识` `朋友` `常一起玩` `暧昧` `砂糖` `稳定` `矛盾` `结束` `低迷` `恢复`

### 8.7 事件分类标签（Event.tags，用于防连发/导演系统）

`sugar` `社交` `技能` `整活` `孤独` `回忆` `负面` `正面` `消费` `现实` `活动` `随机` `关键` `日常` `冲突` `成长` `退坑` `回归`

---

## 9. 写作规范

1. **短**：正文 ≤ 90 字，结果文案 ≤ 80 字。单屏可读完。
2. **第二人称**，现在时。“你推开那扇门……”
3. **具体**：写“中文吧 2 号房”“Nardoragon 改的猫娘”，不写“某个地方”“某个模型”。
4. **VRChat 味**：Avatar、World、贴贴、砂糖、改模、Udon、Quest、掉帧、镜像、开麦、VRC+、跨年倒计时。
5. **拒绝真实人物、真实政治、真实平台纠纷**。所有名字为虚构昵称。
6. **不做道德评判**：砂糖关系、退坑、氪金都中立叙述。
7. **选项要有张力**：三个选项应代表三种不同价值取向（投入 / 抽离 / 冒险），不是“好/中/坏”。
8. **结果要有意外**：正面选项可能带来负面隐患，负面选项可能带来成长。
9. **避免**：说教、鸡汤、感叹号堆砌、网络烂梗。

---

## 10. 校验清单（生成后自检）

- [ ] `id` 唯一且符合 §7 命名规范
- [ ] `hoursRange` 与 `condition.minHours/maxHours` 一致
- [ ] `stage` 与 `hoursRange` 主段一致
- [ ] 每个事件的 `options` 数量在 2-4
- [ ] 每个 option 至少 1 个 outcome，最多 3 个
- [ ] 所有 outcome 至少修改一项状态（effects / relationOp / schedule 非空）
- [ ] 至少一个 option 无 condition（保证永远可选）
- [ ] `tags` / `skills` / `circles` 取值均在 §8 词表内
- [ ] `condition` 中引用的 eventId、flag 名在全局有意义且拼写一致
- [ ] 文案使用了至少一个模板变量或随机组
- [ ] JSON 语法合法，无尾随逗号，无注释
