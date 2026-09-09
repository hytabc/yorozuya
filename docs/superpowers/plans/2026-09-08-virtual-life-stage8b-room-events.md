# 虚拟人生阶段 8b：房间事件（群聊式弹窗剧本）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 房间里出现可点击的事件入口，点开后是群聊式弹窗（多角色轮流说话、点击推进、选项点分支后汇回），每天一次、7 天剧本，管理端线性编辑器可配。

**Architecture:** 全部实现代码由 DeepSeek harness（`npx @deepseek-ai/dsh --profile headless`，cwd=项目根）编写；Kimi 只写 brief、跑测试/构建/E2E、审 diff、打回重写、提交。数据形状与 spec（`docs/superpowers/specs/2026-09-08-virtual-life-events-and-ending-design.md`）一致。

**Tech Stack:** Vue 3 `<script setup>` / FastAPI + pydantic / node --test + pytest。

## Global Constraints（每个 brief 必须原样携带）

- 项目根 `C:\Users\15572\Documents\deepseek\yorozuya`，分支 `feature/virtual-life-local`。
- 只许创建/修改 brief 中列出的文件；其他文件一律不碰；不运行 dev server；不安装新依赖；不执行 git 操作。
- 代码风格对齐同目录现有文件：前端 Vue 3 `<script setup>`、中文注释、scoped 样式、配色 `#237a57/#d9dedb/#69736e`；后端类型注解 + 现有 `_fail` 校验风格。
- 消息组契约（8a 已落地，必须沿用）：`lines: [str,...]` 非空、`image` 仅 `/uploads/` 前缀或 null；图片挂在消息组最后一句播放。
- 前端测试 `node --test --test-isolation=none tests/<file>.test.mjs`；后端 `backend/.venv/Scripts/python.exe -m pytest tests/<file> -q`。harness 写完必须自跑相关测试并保证通过。
- Windows 环境：Node 在 `C:\Program Files\nodejs`；Python 用 `backend/.venv/Scripts/python.exe`；读写文本文件用 utf-8。

## 数据契约（所有任务共用）

```
content.events（顶层数组，缺省迁移补 []）:
[{ id, roomId, title, icon,            // id 唯一；roomId 必须存在于 rooms；icon 为 emoji
   scripts: [dayScript ×7] }]          // 恰好 7 份，第 1~7 天，无第八天
dayScript = { messages: [item, ...] }  // 线性序列
item = 消息组: { speaker: {npcId} | {name, avatar?}, lines: [str,...], image: null|'/uploads/...' }
     | 选项点: { choice: { options: [{ label, effects: {stats?}, reply: [消息组...] }] } }
约束：选项点 reply 只含消息组（禁嵌套选项点）；effects 只允许 stats（禁 bond）；
     speaker 二选一：npcId 须在 npcIds 中，或 name 非空（自由路人，avatar 可 emoji 或 /uploads/ 图）。

存档扩展（schema v2 内兼容）:
eventProgress: { day: int≥1, done: [eventId...] }   // 默认 {day:1, done:[]}
  校验时宽容剔除 pack 中已不存在的事件 id；day 与 state.day 不同视为当日无进度（客户端语义）。
```

---

### Task B1（harness）：后端事件校验 + 存档 eventProgress

**Files:**
- Modify: `backend/app/virtual_life_packs.py`（`validate_pack_content`、`migrate_pack_content`、`derive_save_rules`）
- Modify: `backend/app/virtual_life.py`（GameState + `validate_state_against_pack`）
- Test: `backend/tests/test_virtual_life_packs.py`、`backend/tests/test_virtual_life.py`

- [x] **B1 brief（逐字派发，前后加上 Global Constraints 与数据契约）**

```
任务：给虚拟人生内容包加「房间事件」校验与存档 eventProgress 支持。
先读 backend/app/virtual_life_packs.py、backend/app/virtual_life.py、
backend/tests/test_virtual_life_packs.py、backend/tests/test_virtual_life.py 了解现状
（8a 已完成消息组：节点 lines[]/选项 replies[]/image 规则，照抄该风格）。

1) validate_pack_content 增加 events 校验（events 缺省视为 []）：
   - 每个 event：id 非空唯一；roomId 必须存在于 rooms；title 非空；icon 为非空字符串；
     scripts 必须是恰好 7 份 dayScript。
   - dayScript.messages 非空数组；元素二选一：
     a) 消息组：speaker 恰好二选一（{npcId: 存在于 npcIds} 或 {name: 非空}，可同时有 avatar 字符串）；
        lines 非空字符串数组；image 为 null 或以 /uploads/ 开头的字符串。
     b) 选项点：{choice:{options:[...]}}；options 非空；每个 option：label 非空；
        effects 只允许 stats 键（出现 bond 直接报错）；stats 键 ∈ {mood,energy,social,explore}、
        值为 -100..100 整数；reply 为非空消息组数组（消息组内禁止再出现 choice——嵌套报错）。
2) migrate_pack_content 增加：content 缺 events 键时补 events: []（幂等，返回 changed）。
3) derive_save_rules 增加 'eventIds': [全部事件 id]。
4) GameState 增加 eventProgress 字段：
   eventProgress: EventProgress | None = None（EventProgress: day:int≥1, done:list[str]，StrictModel）；
   反序列化缺省时补默认 {day:1, done:[]}（参考现有 model_validator 里 interactedNpcIds 的补默认方式）。
5) validate_state_against_pack：eventProgress.done 剔除不在 rules['eventIds'] 的 id（宽容，不报错）。
6) 测试（unittest 风格，照现有文件写法）：
   - 合法带 events 的包通过校验（mini_pack 工厂加 events 可选参数或新工厂）；
   - 非法 cases 各一例：嵌套选项点报错、bond 报错、roomId 未知报错、scripts 非 7 份报错、speaker 双给/都不给报错；
   - migrate 补 events: [] 幂等；
   - 存档 eventProgress 往返（PUT→GET 保留）、缺省补默认、未知事件 id 被剔除。
7) 自跑：backend/.venv/Scripts/python.exe -m pytest tests/test_virtual_life.py tests/test_virtual_life_packs.py -q
   必须全绿（现有 17 例 + 新增）。注意 Windows Python 读写文件加 encoding='utf-8'。
完成后回复：修改文件清单 + 新增测试数 + pytest 结果尾部。
```

- [x] **验收**：`git diff --stat` 只含列出的文件；我复跑 pytest 全绿；不符打回（附失败输出重派）。

---

### Task B2（harness）：前端事件规则层 + 引擎接线

**Files:**
- Create: `frontend/src/composables/lifeEvents.js`
- Create: `frontend/tests/lifeEvents.test.mjs`
- Modify: `frontend/src/life/registry.js`（events 校验 + 运行时 pack 携带 events）
- Modify: `frontend/src/life/useLifeGame.js`（eventProgress 状态 + 事件动作）
- Modify: `frontend/tests/lifeRegistry.test.mjs`（如默认包 events 相关断言需要）

- [x] **B2 brief**

```
任务：虚拟人生房间事件的前端规则层与游戏引擎接线（8a 消息组已落地，先读
frontend/src/composables/lifeDialogue.js、frontend/src/life/registry.js、
frontend/src/life/useLifeGame.js、frontend/tests/lifeDialogue.test.mjs 了解风格与现状）。

1) 新建 frontend/src/composables/lifeEvents.js（纯函数，不依赖 vue，中文注释）：
   - eventScriptForDay(event, day)：钳制取 scripts[min(day,7)-1]。
   - eventsForRoom(events, roomId)：该房间的事件列表。
   - isEventDone(eventProgress, day, eventId)：progress.day === day 且 done 含 id。
   - applyEventChoice(stats, effects)：返回结算后新 stats（仅 stats 键，0-100 钳制；
     语义照 useLifeGame 里 chooseOption 的 stats 结算）。
   - eventEffectsOf(options 选中项)：透传 effects.stats（无则 {}）。
   - normalizeEventProgress(saved, day)：缺省/形状错 → {day, done: []}；day 不同 → {day, done: []}（新的一天重置）。
2) registry.js：validateLifePack 增加 events 校验（规则与后端一致：恰好 7 份、speaker 二选一、
   禁嵌套选项点、禁 bond、image 仅 /uploads/ 前缀；events 缺省视为合法空）；
   createLifePackFromContent 的 pack 增加 events: content.events || []。
3) useLifeGame.js：
   - 新 ref：eventProgress（init: normalizeEventProgress(undefined, day) → {day, done: []}）、
     activeEvent（null | {event, script}）。
   - computed roomEvents：当前房间的 eventsForRoom(pack.events, currentRoomId)，
     每项附 done: isEventDone(eventProgress, day, id)。
   - 动作：openEvent(eventId)（saveReady 且无冲突且未完成才开；置 activeEvent={event, script: eventScriptForDay(event, day)}）、
     closeEvent()、finishEvent(effects)（stats 结算走 applyEventChoice 钳制、done  push eventId、
     activeEvent=null、showToast('✦ '+(effectText({stats:effects})||'已记录'))、markChanged()）。
   - nextDay 时 eventProgress 重置为新 day（normalizeEventProgress(eventProgress, newDay)）。
   - 存档接线：序列化带 eventProgress；载入时 normalizeEventProgress(saved.eventProgress, day)。
     （读 lifeSave 相关代码，照 dialogueNodes 的存取方式加。）
   - return 导出：roomEvents, activeEvent, eventProgress, openEvent, closeEvent, finishEvent。
4) 新建 tests/lifeEvents.test.mjs：eventScriptForDay 钳制、eventsForRoom、isEventDone、
   applyEventChoice 钳制、normalizeEventProgress 各分支，≥6 例。
5) 自跑全部前端测试：cd frontend && node --test --test-isolation=none tests/lifeEvents.test.mjs
   及其余 8 个 tests/life*.test.mjs，必须全绿（现有 34 例 + 新增）。
完成后回复：文件清单 + 测试结果。
```

- [x] **验收**：diff 范围核对；我复跑前端全量测试 + `npm run build`。

---

### Task B3（harness）：群聊弹窗组件 LifeEventModal.vue

**Files:**
- Create: `frontend/src/life/components/LifeEventModal.vue`

- [x] **B3 brief**

```
任务：新建群聊式事件播放弹窗 frontend/src/life/components/LifeEventModal.vue（只许新建这一个文件）。
先读 frontend/src/life/components/LifeImageLightbox.vue（8a，复用它）、
frontend/src/life/components/LifeHistoryDrawer.vue（气泡风格参考）。

Props:
- script: Object 必填 —— 当天事件剧本 {messages:[...]}（数据契约见下）
- resolveSpeaker: Function 必填 —— (speaker) => ({name, portrait}) ，portrait 可能是
  图片 URL、emoji 或空；调用方保证可处理 {npcId} 与 {name,avatar} 两种 speaker
- playerName: String 默认 '你'
Emits:
- choice(effects) —— 玩家在选项点做出选择时（effects 为该选项 effects 或 {}）
- finish() —— 剧本播完且玩家点击关闭时
- close() —— 玩家在中途点右上角 ✕ 时
数据契约：messages 元素为 消息组 {speaker, lines:[...], image} 或
选项点 {choice:{options:[{label, effects, reply:[消息组...]}]}}。

交互（仿微信群聊）：
- 全屏遮罩（z-index 9000，低于灯箱 9999）+ 居中面板（最大宽 560px、高 80vh、白底圆角 12px），
  顶部标题栏：剧名图标+标题（标题栏文字用 script 不必含标题，父组件传 title prop：String 默认 '事件'）。
  补一个 prop: title String 默认 '事件'，icon String 默认 '❗'。
- 消息区纵向滚动：每条消息组渲染为 头像+名字+气泡（lines 每句一个气泡，同组连排）；
  NPC/路人在左，玩家发言（选项 label 与玩家台词）在右（绿色 #237a57 气泡）。
- 推进：初始只显示第一组；点击消息区（或「继续 ▾」底部按钮）追加下一组，带淡入；
  到底自动滚动。选项点：暂停推进，底部显示选项按钮（编号+label）；
  点击后 emit('choice', option.effects||{})，把 option.label 作为玩家发言气泡插入，
  再把 option.reply 消息组逐组插入，然后恢复点击推进主线。
- 图片：消息组 image 在气泡内渲染缩略图（max-width 200px），点击用 LifeImageLightbox 全屏（组件内自管理 lightboxSrc）。
- 播完最后一组：底部显示「—— 剧终 ——」与「关闭」按钮，点击 emit('finish')。
- 打字机不做（整组直接出）；reduced-motion 无需特殊处理。
- 样式全 scoped，配色对齐项目（#237a57/#d9dedb/#69736e/#f5f6f4）。
无 vue 测试环境，不写单测；写完后回复契约自查结果（props/emits/流程）。
```

- [x] **验收**：Read 核对契约；`npm run build` 过；不符打回。

---

### Task B4（harness）：场景事件入口 + 弹窗接线

**Files:**
- Modify: `frontend/src/life/components/LifeScene.vue`

- [x] **B4 brief**

```
任务：把房间事件入口与群聊弹窗接进场景组件 frontend/src/life/components/LifeScene.vue。
先读该文件与 frontend/src/life/useLifeGame.js（8b 已导出 roomEvents/activeEvent/openEvent/closeEvent/finishEvent）、
frontend/src/life/components/LifeEventModal.vue（props: script/title/icon/resolveSpeaker/playerName；emits: choice/finish/close）、
frontend/src/life/registry.js（portraitFor）。

1) props.game 解构补：roomEvents, activeEvent, openEvent, closeEvent, finishEvent, npcs。
2) 场景内（位置标签下方或场景左下，自行选不遮挡的位置）渲染事件入口按钮列表：
   每个 roomEvents 项一个按钮：`{{ icon }} {{ title }}`；done 的置灰禁用并追加「 ✓」，
   title 属性「今天已经看过了，明天再来吧」；未完成的点击调 openEvent(id)。
   样式：白底 pill、边框 #d9dedb、圆角 999px、阴影轻微；done 透明度 .55。
3) 弹窗：`<LifeEventModal v-if="activeEvent" :script="activeEvent.script"
   :title="activeEvent.event.title" :icon="activeEvent.event.icon"
   :resolve-speaker="resolveEventSpeaker" player-name="白昼梦"
   @choice="onEventChoice" @finish="onEventFinish" @close="closeEvent" />`
   - resolveEventSpeaker(speaker)：{npcId} → ({name: npc.name, portrait: portraitFor(npcId)})；
     {name, avatar} → ({name, portrait: avatar||''})。npcs 从 game 解构。
   - onEventChoice(effects)：本任务只做暂存（const pendingEventEffects = ref([])，push effects?.stats||{}）。
   - onEventFinish()：把累计 stats 合并后调 finishEvent(merged)，清空暂存。
   （import LifeEventModal；以上函数写在 script setup。）
4) npm run build 必须过。完成后回复改动摘要。
```

- [x] **验收**：diff + build + 前端全量测试。

---

### Task B5（harness）：管理端事件线性编辑器

**Files:**
- Create: `frontend/src/life/admin/AdminEvents.vue`
- Modify: `frontend/src/life/admin/useLifeAdmin.js`（events CRUD helpers）
- Modify: `frontend/src/views/LifeAdmin.vue`（「事件」区块挂载 + 样式如需）

- [x] **B5 brief**

```
任务：管理端加「事件」编辑区块（线性剧本编辑器）。先读 frontend/src/life/admin/useLifeAdmin.js、
frontend/src/views/LifeAdmin.vue、frontend/src/life/admin/AdminDialogue.vue（天页签/编辑面板风格）、
frontend/src/life/admin/AdminImageField.vue（v-model 图片上传）。

1) useLifeAdmin.js 增加并导出：
   - addEvent(content, roomId)：push {id:'evt-'+slug(roomId)+'-'+n(去重), roomId, title:'新事件', icon:'❗',
     scripts: 7 份 {messages:[{speaker:{name:'旁白',avatar:'📢'},lines:['……'],image:null}]}}；返回 id。
   - removeEvent(content, eventId)。
   - addEventMessage(dayScript)（尾部追加路人消息组）、addEventChoice(dayScript)
     （尾部追加单选项选项点）、removeEventItem(dayScript, index)。
   - content 缺 events 时上述函数先补 []（与管理端载入老包兼容）。
2) AdminEvents.vue：
   - 事件列表按房间分组（房间 label + 世界名），每事件一行：icon/title 可编辑、房间下拉（全部 rooms）、删除按钮；
     「+ 新增事件」按钮（房间取当前分组或第一个房间）。
   - 选中事件后是线性编辑器：第 1~7 天页签（照 AdminDialogue 的 la-npc-tabs），
     messages 纵向卡片列表，卡片类型两种：
     a) 消息组卡：speaker 编辑（下拉：'路人' + 全部 NPC；NPC 选后存 {npcId}；路人显示 name input + avatar input）、
        lines 多行编辑（照 AdminDialogue 的 la-line-row：加一句/删）、AdminImageField 挂 image、删除卡、上移/下移。
     b) 选项点卡：options 列表（label input + 4 个 stats number input + reply 内嵌消息组编辑（同 a 的 lines/speaker 简化版）+ 删选项）；
        「+ 加选项」「删除此选项点」。不允许在 reply 里再加选项点（UI 上就没有这个入口）。
   - 「+ 加消息」「+ 加选项点」按钮插在列表尾部即可。
3) LifeAdmin.vue 挂载：区块导航加「事件」（放在「剧本」后），渲染 <AdminEvents />。
4) npm run build 必须过。回复改动摘要 + 契约自查。
```

- [x] **验收**：diff + build；管理端手动验证留到 E2E。

---

### Task B6（harness）：默认包示例事件 + 种子再生成

**Files:**
- Modify: `frontend/src/life/content/defaultPack.js`（content 加 events 示例）
- Modify: `backend/app/life_packs/wsw-default-life.json`（脚本再生成）

- [x] **B6 brief**

```
任务：默认内容包加 2 个示例房间事件并再生成后端种子。先读
frontend/src/life/content/defaultPack.js（注意：dialogue 经 normalizeDialogue 归一化；
events 不需要归一化，直接按最终形状写）、backend/app/life_packs/wsw-default-life.json。

1) defaultLifePackContent 增加 events 数组（恰好 2 个事件，每个恰好 7 份 scripts）：
   - evt-beach-tide（roomId: beach-1024，icon '🌊'，title '涨潮时分'）：
     7 天连续小剧情，说话人混用 {npcId:'ache'} 与路人（如 {name:'钓鱼大爷',avatar:'🎣'}）；
     每天至少 3 组消息；第 3/6 天各插一个选项点（2 个选项，effects 仅 stats，reply 1-2 组消息后汇回主线）。
   - evt-cafe-gossip（roomId: cafe-1101，icon '☕'，title '柜台边的闲聊'）：
     说话人 {npcId:'xiaomi'} + 路人 {name:'店主',avatar:'👩‍🍳'}；第 5 天一个选项点。
   文案风格对齐现有剧本（生活化、温柔、短句）。
2) 再生成种子（frontend 目录下）：
   node --input-type=module -e "import { defaultLifePackContent } from './src/life/content/defaultPack.js'; import { writeFileSync } from 'node:fs'; writeFileSync('../backend/app/life_packs/wsw-default-life.json', JSON.stringify(defaultLifePackContent, null, 2) + '\n', 'utf8')"
3) 自跑 node --test --test-isolation=none tests/lifeRegistry.test.mjs（parity 断言）+ 全部 tests/life*.test.mjs 全绿。
回复：事件 id 列表 + 测试结果。
```

- [x] **验收**：diff + parity + 全量测试。

---

### Task B7（Kimi）：隔离 E2E + 文档 + 收尾

- [x] 冒烟环境（8123/8124 配方）：事件入口出现 → 点开群聊弹窗 → 点击推进 → 选项点选择 → 汇回主线 → 剧终标记 done（入口变灰✓）→ 存档 eventProgress 落库 → 下一天重置可再玩；管理端新增/编辑事件保存生效；旧包（无 events）激活/迁移不炸。
- [x] 真实库：重启 8000 后端（迁移补 events:[]），确认活动包正常。
- [x] 同步 `VIRTUAL_LIFE.md` + 架构文档路线图（8b 行 ✅）。
- [x] 每个 Task 独立 commit（harness 产出注明 via deepseek harness），不推送。
