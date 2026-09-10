# DLC1 · 设备 · 友情 · 好感度

本体（`PRD.md` + `data/`）的一个**纯加法**扩展包。不改动 `data/` 里任何现有文件，所有新内容都在 `DLC1/` 下，通过 `merge_dlc1.py` 合并后即可被引擎消费。

## 这个 DLC 加了什么

| 维度 | 内容 |
|---|---|
| **设备设定** | Pico / Quest / PCVR、串流（VD / Air Link）、全身追踪（Tracker / SlimeVR / HaritoraX / FBT）、面捕（嘴追 / 眼追）、晕动症、幻肢、掉追、校准——共 28 条术语，全部落地进事件 |
| **好感度系统** | 新增 `favor`（0-100）、五档位、自然衰减、自动标签 `挚友` / `圈子浪人` |
| **圈子冲突** | 3 个新圈子（设备圈 / 追踪圈 / 面捕圈）、站队与调解机制 |
| **朋友情绪** | 闹情绪、寻求帮助、被排挤、退坑前夜、多年后的重逢 |
| **新事件** | **59 个**（device 16 / circle 15 / friend 15 / favor 13），其中 key 7 个 |
| **新结局** | **7 个**（调解人 / 挚友 / 重逢 / 圈子浪人 / 设备折腾家 / 全身追踪的人 / 深夜的独舞者） |
| **新出生** | **4 个**（Pico 一体机党 / 全身追踪狂热者 / 硬件折腾党 / 圈子调和者） |

完整设计见 [`PRD-DLC1.md`](./PRD-DLC1.md)。

## 目录结构

```
DLC1/
├── README.md                # 本文件
├── PRD-DLC1.md              # 设计文档（设定 / 系统 / 结局）
├── schema.dlc1.json         # 机器可读的契约增量（新字段 / 档位 / 权重修正）
├── vocab.dlc1.json          # 词表增量（圈子 / 标签 / 世界 / 昵称 / 结局路径 / 术语表）
├── endings.dlc1.json        # 7 个新结局
├── archetypes.dlc1.json     # 4 个新出生
├── events/
│   ├── device.json          # 16 个
│   ├── circle.json          # 15 个
│   ├── friend.json          # 15 个
│   └── favor.json           # 13 个
├── scripts/
│   ├── validate_dlc1.py     # DLC 感知的静态校验
│   ├── merge_dlc1.py        # 合并 DLC1 → DLC1/build/（不碰 data/）
│   └── simulate_dlc1.py     # DLC 感知的无头模拟（favor / 新结局 / 死事件）
└── build/                   # merge 产物（可删除重建）
```

## 用法

```bash
# 1. 静态校验：0 ERROR 才算通过
python DLC1/scripts/validate_dlc1.py

# 2. 合并本体 + DLC1，产出到 DLC1/build/
python DLC1/scripts/merge_dlc1.py

# 3. 跑 500 局 DLC 感知模拟（favor / 死事件 / 新结局可达性）
python DLC1/scripts/simulate_dlc1.py 500
```

最近一次运行结果：

- 校验：**✅ 0 ERROR / 0 WARN**
- 合并：事件 **355**（本体 296 + DLC 59）、结局 23、出生 14
- 模拟 500 局：无异常、无死事件（**59/59 触达**）、**DLC 结局 7/7 可达**、非法状态转移 0、`favor` 始终在 0–100

## 引擎整合清单

DLC1 需要引擎在**已有语义之上**增加下面几项。数据契约见 `schema.dlc1.json`，参考实现见 `scripts/simulate_dlc1.py`。

### 1. 状态

```ts
state.favor = 50;          // 好感度 0-100
// 每回合结算后自然漂移
state.favor = clamp(state.favor - 0.35, 0, 100);
```

### 2. effects

```
effects.favor      // 数字，累加到 favor 后夹取到 [0,100]
```

### 3. condition

```
minFavor / maxFavor          // 0-100
minCircles                   // 已加入圈子数量下限（结局用）
minCounters: { "friendsHelped": 3 }   // 自定义计数器下限
```

### 4. 自动标签（`deriveTags`）

```
favor >= 80 → 添加「挚友」；favor < 60 → 移除
circles.length >= 5 → 添加「圈子浪人」
```

### 5. 权重修正（接在主 `scoreEvent` 修正链末尾）

```
事件带「设备」tag 且玩家持有 Pico党/Quest党/串流党/全身追踪/设备党 → ×1.5
玩家持「挚友」且事件带「友情」「正面」 → ×1.4
favor < 30 且事件带「友情」 → ×1.3
```

### 6. 结局

- `endings.json` 的 `scoring.vars` 追加 `favor`。
- 结局 `condition` 支持 `minFavor` / `maxFavor` / `minCircles`。
- 7 个新结局直接追加进 `endings` 数组（判定规则不变：`lock` 必中，其余取 score 最高）。

### 7. 数据合并

`merge_dlc1.py` 演示了合并方式：词表做并集、结局/出生追加、事件桶直接新增（`device` / `circle` / `friend` / `favor`），最后重建 `events.index.json`。

## 数据文件校验要点

- 事件 id 规范：`{bucket}_NNN` / `{bucket}_kNN`，四个 DLC 桶前缀分别为 `device` / `circle` / `friend` / `favor`。
- 每个事件 2-4 个选项、每个选项 1-3 个结果、至少一个无条件选项。
- 所有新 tag / circle / world / endingPath 必须在 `vocab.dlc1.json` 声明。
- `vocab.dlc1.json` 的每个术语都必须在至少一个 DLC 事件文案中出现（校验脚本会查）。
- 每个新结局路径都必须被至少一个 `endingHint` 引用。

## 设计取向

- **设备平等**：Pico、Quest、PCVR 只影响体验与事件走向，不写成优劣。
- **帮忙一定有代价**：钱、时间、心情至少掉一样；拒绝不是罪，但会掉好感度。
- **圈子冲突没有全赢选项**：站队必失去一边；只有高 `social` 的调解才可能都不得罪。
- **好感度会淡**：不互动就每回合衰减，好友列表越长反而越考验你真正在意谁。
