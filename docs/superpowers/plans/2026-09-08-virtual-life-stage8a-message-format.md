# 虚拟人生阶段 8a：消息格式升级（多句 + 图片）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把剧本里的"一句话"升级为"消息组"（多句台词 + 可选图片），NPC 私聊全链路（引擎/播放/存档/管理端/默认包）支持多句连播与图片弹出。

**Architecture:** 数据形状 `line→lines[]`、`reply→replies[]`，新增 `image/replyImage`（仅允许 `/uploads/` 站内路径）；旧数据由后端 `migrate_pack_content` 与前端 defaultPack 归一化双边升级；播放机队列条目携带 `image`，图片挂在消息组最后一句上；灯箱组件由 DeepSeek harness 外包编写，Kimi 负责集成。

**Tech Stack:** Vue 3 `<script setup>` / 纯函数规则层（node --test）/ FastAPI + pydantic（pytest）。

## Global Constraints

- 只许动虚拟人生相关文件：`backend/app/virtual_life*.py`、`backend/app/life_packs/`、`backend/tests/test_virtual_life*.py`、`frontend/src/life/**`、`frontend/src/composables/life*.js`、`frontend/src/views/LifeSimulator.vue` 系、`frontend/tests/life*.test.mjs`、`VIRTUAL_LIFE.md`。其他模块一律不碰。
- 项目根：`C:\Users\15572\Documents\deepseek\yorozuya`；分支 `feature/virtual-life-local`；commit 不推送。
- Node 需 `export PATH="/c/Program Files/nodejs:$PATH"`；Python 一律 `backend/.venv/Scripts/python.exe`；Python 读写文件必须 `encoding='utf-8'`（Windows 默认 GBK）。
- 前端测试：`node --test --test-isolation=none tests/<file>.test.mjs`（8 个文件共 32 例，全绿才算过）；后端：`backend/.venv/Scripts/python.exe -m pytest tests/test_virtual_life.py tests/test_virtual_life_packs.py`（现 14 例）。
- 前端 defaultPack 与后端种子 `wsw-default-life.json` 必须保持 deepEqual（lifeRegistry.test.mjs 守门）。
- 全量 pytest 有预存失败 `test_api.py::test_staff_role_management_and_public_directory`，与虚拟人生无关，忽略。

## 新数据形状（本阶段的契约）

```
dayScript = { start, nodes: { nodeId: {
  lines: ['句1', '句2'],          // 非空字符串数组（旧 line 单句迁移为单元素数组）
  image: '/uploads/life/x.png',   // 可选；null/缺省 = 无图；仅允许 /uploads/ 前缀
  choices: [{ label, effects, next,
    replies: ['回1', '回2'],      // 非空字符串数组（旧 reply 迁移）
    replyImage: null,             // 同 image 规则
  }],
} } }
```

消息组播放语义：逐句连播（点击跳过/推进沿用现有交互）；**图片挂在该组最后一句的消息条目上**（说完才展示图）。

---

### Task 1: 后端迁移与校验升级（Kimi）

**Files:**
- Modify: `backend/app/virtual_life_packs.py`（`validate_pack_content` 139-162 行节点/选项段；`migrate_pack_content` 209-219 行）
- Test: `backend/tests/test_virtual_life_packs.py`

**Interfaces:**
- Produces: `migrate_pack_content(content) -> bool`（幂等；新增 line→lines、reply→replies、补 image/replyImage 默认 None）；校验拒绝：空 lines/replies、非 `/uploads/` 前缀图片。

- [ ] **Step 1: 写失败测试**（追加到 test_virtual_life_packs.py，**unittest 风格**：方法加进 `PackTests`，文件顶部 import 改为 `from app.virtual_life_packs import router as packs_router, seed_virtual_life_packs, validate_pack_content, migrate_pack_content`，`from fastapi import HTTPException`）

```python
    def test_migrate_upgrades_single_line_shape_idempotent(self):
        content = mini_pack(['ache'])
        node = content['dialogue']['ache'][0]['nodes']['n1']
        node['line'] = node.pop('lines'); node.pop('image')
        node['choices'][0]['reply'] = node['choices'][0].pop('replies')
        node['choices'][0].pop('replyImage')
        self.assertIs(migrate_pack_content(content), True)
        self.assertEqual(node['lines'], ['你好'])
        self.assertIsNone(node['image'])
        self.assertEqual(node['choices'][0]['replies'], ['嗯'])
        self.assertIsNone(node['choices'][0]['replyImage'])
        self.assertIs(migrate_pack_content(content), False)  # 幂等
        validate_pack_content(content)  # 迁移后必须通过校验

    def test_validate_rejects_external_image_and_empty_lines(self):
        content = mini_pack(['ache'])
        content['dialogue']['ache'][0]['nodes']['n1']['image'] = 'https://evil.com/x.png'
        with self.assertRaises(HTTPException):
            validate_pack_content(content)
        content = mini_pack(['ache'])
        content['dialogue']['ache'][0]['nodes']['n1']['lines'] = []
        with self.assertRaises(HTTPException):
            validate_pack_content(content)
```

> 注意：`mini_pack()` 工厂（39-40 行）当前是旧形状，本任务实现时要同步升级为新形状
>（`lines: ['你好']`、`image: None`、`replies: ['嗯']`、`replyImage: None`），否则既有用例全红。

- [ ] **Step 2: 跑测试确认失败** `.venv/Scripts/python.exe -m pytest tests/test_virtual_life_packs.py -k "migrate_upgrades or rejects_external" -v` → FAIL（旧校验报"缺少台词"）

- [ ] **Step 3: 实现**。`migrate_pack_content` 整体替换为：

```python
def migrate_pack_content(content: dict) -> bool:
    """Upgrade legacy dialogue shapes in place (idempotent):
    {npc: script} -> {npc: [script]}; node.line -> lines[]; choice.reply -> replies[];
    fill image/replyImage defaults (stage 8a)."""
    changed = False
    dialogue = content.get('dialogue')
    if not isinstance(dialogue, dict):
        return changed
    for npc_id, script in dialogue.items():
        if isinstance(script, dict) and 'nodes' in script:
            dialogue[npc_id] = [script]
            changed = True
    for days in dialogue.values():
        if not isinstance(days, list):
            continue
        for script in days:
            nodes = script.get('nodes') if isinstance(script, dict) else None
            if not isinstance(nodes, dict):
                continue
            for node in nodes.values():
                if not isinstance(node, dict):
                    continue
                if isinstance(node.get('line'), str):
                    node['lines'] = [node.pop('line')]
                    changed = True
                if 'image' not in node:
                    node['image'] = None
                    changed = True
                for choice in node.get('choices') or []:
                    if not isinstance(choice, dict):
                        continue
                    if isinstance(choice.get('reply'), str):
                        choice['replies'] = [choice.pop('reply')]
                        changed = True
                    if 'replyImage' not in choice:
                        choice['replyImage'] = None
                        changed = True
    return changed
```

`validate_pack_content` 节点段（原 139-151 行）替换为：

```python
            for node_id, node in nodes.items():
                lines = node.get('lines')
                if not isinstance(lines, list) or not lines or \
                        any(not isinstance(l, str) or not l for l in lines):
                    _fail(f"{where}/{node_id} 台词必须是非空句子数组")
                image = node.get('image')
                if image is not None and (not isinstance(image, str) or not image.startswith('/uploads/')):
                    _fail(f"{where}/{node_id} 图片必须是 /uploads/ 站内路径")
                choices = node.get('choices')
                if not isinstance(choices, list) or not choices:
                    _fail(f"{where}/{node_id} 缺少选项")
                for choice in choices:
                    if not isinstance(choice.get('label'), str) or not choice['label']:
                        _fail(f"{where}/{node_id} 存在无文案选项")
                    replies = choice.get('replies')
                    if not isinstance(replies, list) or not replies or \
                            any(not isinstance(r, str) or not r for r in replies):
                        _fail(f"{where}/{node_id} 存在无回复选项")
                    reply_image = choice.get('replyImage')
                    if reply_image is not None and (not isinstance(reply_image, str) or not reply_image.startswith('/uploads/')):
                        _fail(f"{where}/{node_id} 回复图片必须是 /uploads/ 站内路径")
                    if choice.get('next') is not None and choice.get('next') not in nodes:
                        _fail(f"{where}/{node_id} 选项跳转到未知节点 {choice.get('next')}")
```

（effects 段 152-162 行原样保留。）

- [ ] **Step 4: 跑测试确认通过**（同 Step 2 命令 + 全量两个测试文件 → 14+3 例全绿）

- [ ] **Step 5: Commit** `git add backend/app/virtual_life_packs.py backend/tests/test_virtual_life_packs.py && git commit -m "feat: multi-line message groups with optional images in pack validation (stage 8a, backend)"`

---

### Task 2: 存档 Message 支持图片（Kimi，后端）

**Files:**
- Modify: `backend/app/virtual_life.py:46-50`（Message 模型）
- Test: `backend/tests/test_virtual_life.py`

- [ ] **Step 1: 失败测试**（test_virtual_life.py 也是 unittest 风格，方法加进存档测试类；`state()` 是该文件已有工厂，`self.client`/`self.headers` 是已有夹具）

```python
    def test_save_message_with_image_roundtrip(self):
        s = state()
        s['conversations']['ache'].append(
            {'from': 'npc', 'text': '看这张', 'day': 1, 'time': '18:20', 'image': '/uploads/life/a.png'})
        r = self.client.put('/api/virtual-life/save', json={'revision': 0, 'state': s}, headers=self.headers(1))
        self.assertEqual(r.status_code, 200)
        got = self.client.get('/api/virtual-life/save', headers=self.headers(1)).json()
        self.assertEqual(got['state']['conversations']['ache'][-1]['image'], '/uploads/life/a.png')
```

- [ ] **Step 2: 确认失败**（extra="forbid" 报 image 多余字段）
- [ ] **Step 3: Message 模型加一行** `image: str | None = Field(default=None, max_length=300)`（注释：stage 8a 可选站内图片）
- [ ] **Step 4: 确认通过**；**Step 5: Commit**（`"...(stage 8a, save schema)"`）

---

### Task 3: 前端对话规则层升级（Kimi）

**Files:**
- Modify: `frontend/src/composables/lifeDialogue.js`
- Test: `frontend/tests/lifeDialogue.test.mjs`

**Interfaces:**
- Produces（后续任务依赖的准确签名）:
  - `groupMessages(texts: string[], image: string|null, day: number, from='npc') -> Message[]`（图片挂最后一句；`time:'18:20'`）
  - `startMessages(script, day=1) -> Message[]`（= `groupMessages(startNode.lines, startNode.image, day)`）
  - `resolveDialogueChoice(script, choice) -> {bond, stats, replies: string[], replyImage: string|null, nextNodeId: string|null, nextLines: string[]|null, nextImage: string|null, done: boolean}`
  - `scriptForDay`、`nodeFor`、`sanitizeDialogueNodes` 不变；`startLine` 删除（全局只有 useLifeGame 一处调用，同步改）。

- [ ] **Step 1: 改测试为失败态**（lifeDialogue.test.mjs 全部用例从 line/reply 改为 lines/replies 形状；新增用例）

```js
test('groupMessages 把图片挂在最后一句上', () => {
  const msgs = groupMessages(['一', '二', '三'], '/uploads/life/x.png', 2)
  assert.deepEqual(msgs.map(m => m.text), ['一', '二', '三'])
  assert.deepEqual(msgs.map(m => m.image), [null, null, '/uploads/life/x.png'])
  assert.ok(msgs.every(m => m.from === 'npc' && m.day === 2 && m.time === '18:20'))
})

test('resolveDialogueChoice 返回回复数组与下一节点台词数组', () => {
  const script = { start: 'n1', nodes: {
    n1: { lines: ['问'], image: null, choices: [
      { label: 'A', effects: { bond: 2 }, replies: ['答1', '答2'], replyImage: '/uploads/life/r.png', next: 'n2' },
      { label: 'B', effects: {}, replies: ['完'], replyImage: null, next: null },
    ] },
    n2: { lines: ['续1', '续2'], image: '/uploads/life/n.png', choices: [
      { label: 'C', effects: {}, replies: ['好'], replyImage: null, next: null },
    ] },
  } }
  const r = resolveDialogueChoice(script, script.nodes.n1.choices[0])
  assert.deepEqual(r.replies, ['答1', '答2'])
  assert.equal(r.replyImage, '/uploads/life/r.png')
  assert.deepEqual(r.nextLines, ['续1', '续2'])
  assert.equal(r.nextImage, '/uploads/life/n.png')
  assert.equal(r.done, false)
  const r2 = resolveDialogueChoice(script, script.nodes.n1.choices[1])
  assert.equal(r2.done, true)
  assert.equal(r2.nextLines, null)
})

test('startMessages 展开起点节点为多句消息', () => {
  const script = { start: 'n1', nodes: { n1: { lines: ['早', '吃了吗'], image: '/uploads/life/m.png', choices: [{ label: 'x', effects: {}, replies: ['y'], replyImage: null, next: null }] } } }
  assert.deepEqual(startMessages(script, 3), [
    { from: 'npc', text: '早', day: 3, time: '18:20', image: null },
    { from: 'npc', text: '吃了吗', day: 3, time: '18:20', image: '/uploads/life/m.png' },
  ])
})
```

- [ ] **Step 2: 跑 `node --test --test-isolation=none tests/lifeDialogue.test.mjs` 确认失败**
- [ ] **Step 3: 实现**——lifeDialogue.js 头部注释更新为新形状；`startLine` 替换为：

```js
// 消息组展开:多句台词逐条成消息,图片挂在最后一句(说完才展示图)。
export function groupMessages(texts, image, day, from = 'npc') {
  return texts.map((text, i) => ({
    from, text, day, time: '18:20',
    image: i === texts.length - 1 ? (image || null) : null,
  }))
}

// 开场/每日重置消息组(来自 start 节点)。
export function startMessages(script, day = 1) {
  const node = script.nodes[script.start]
  return groupMessages(node.lines, node.image, day)
}

// 选中选项后的推进结果(纯计算;effects 落账与消息写入由 useLifeGame 完成)。
export function resolveDialogueChoice(script, choice) {
  const effects = choice.effects || {}
  const next = choice.next && script.nodes[choice.next] ? choice.next : null
  const nextNode = next ? script.nodes[next] : null
  return {
    bond: effects.bond || 0,
    stats: { ...(effects.stats || {}) },
    replies: [...choice.replies],
    replyImage: choice.replyImage || null,
    nextNodeId: next,
    nextLines: nextNode ? [...nextNode.lines] : null,
    nextImage: nextNode ? (nextNode.image || null) : null,
    done: !next,
  }
}
```

- [ ] **Step 4: 确认通过**；**Step 5: Commit**（`"...(stage 8a, dialogue rules)"`）

---

### Task 4: 播放机携带图片（Kimi）

**Files:**
- Modify: `frontend/src/composables/lifePlayback.js:6-46`
- Test: `frontend/tests/lifePlayback.test.mjs`

- [ ] **Step 1: 失败测试**

```js
test('播放状态携带当前条目的图片', () => {
  const seen = []
  const pb = createLifePlayback(v => seen.push(v), { reducedMotion: () => true })
  pb.play([{ from: 'npc', text: '一', image: null }, { from: 'npc', text: '二', image: '/uploads/life/x.png' }])
  pb.complete()  // 推进到第二条
  const last = seen[seen.length - 1]
  assert.equal(last.image, '/uploads/life/x.png')
  assert.equal(last.playing, false)
})
```

- [ ] **Step 2: 确认失败**
- [ ] **Step 3: 实现**——三处改动：`state` 初始加 `image: null`；`play()` 里 `queue = lines.map(l => ({ from: l.from, text: l.text, image: l.image || null }))`；`startLine()` 里 `publish({ from: queue[index].from, text: '', typing: true, playing: true, image: queue[index].image })`；`stop()` 里 publish 补 `image: null`。
- [ ] **Step 4: 确认通过**（含既有 3 例）；**Step 5: Commit**

---

### Task 5: useLifeGame 多句播放与消息带图（Kimi）

**Files:**
- Modify: `frontend/src/life/useLifeGame.js:13`（import）、`:138-145`（switchNpc）、`:148-192`（chooseOption）

- [ ] **Step 1**: import 改为 `import { scriptForDay, nodeFor, startMessages, resolveDialogueChoice, sanitizeDialogueNodes, groupMessages } from '../composables/lifeDialogue'`
- [ ] **Step 2**: switchNpc 里 `conv.push({ ...startLine(scriptForDay(pack.dialogue[npcId], day.value), day.value) })` 改为：

```js
      conv.push(...startMessages(scriptForDay(pack.dialogue[npcId], day.value), day.value))
```

- [ ] **Step 3**: chooseOption 的消息写入段（原 174-187 行）改为：

```js
    // 回复消息组(多句连播;图片挂最后一句)。
    const replyMsgs = groupMessages(result.replies, result.replyImage, sentDay)
    conversations.value[npcId].push(...replyMsgs)
    const played = [{ from: 'player', text: choice.label }, ...replyMsgs]
    if (result.done) {
      delete dialogueNodes.value[npcId]
      completed.value[npcId] = true
    } else {
      // next 非空:当天推进到下一节点,NPC 接着说下一节点台词组。
      dialogueNodes.value[npcId] = result.nextNodeId
      const nextMsgs = groupMessages(result.nextLines, result.nextImage, sentDay)
      conversations.value[npcId].push(...nextMsgs)
      played.push(...nextMsgs)
    }
```

- [ ] **Step 4**: 全量前端测试 + `npm run build` 通过（旧形状测试已在 Task 3/8 同步改完）
- [ ] **Step 5: Commit**（`"...(stage 8a, game engine)"`）

---

### Task 6: 灯箱组件（DeepSeek harness 外包）

**Files:**
- Create: `frontend/src/life/components/LifeImageLightbox.vue`（只许新建这一个文件，不许改任何其他文件）

**Interfaces:**
- Produces（Task 7 依赖的准确契约）:
  - Props: `src: String`（必填，图片 URL）、`alt: String`（默认 `'图片'`）
  - Emits: `close`（点击遮罩任意处或按 ESC 时触发）
  - 用法：`<LifeImageLightbox v-if="lightboxSrc" :src="lightboxSrc" alt="剧本图片" @close="lightboxSrc = ''" />`

- [ ] **Step 1: 用 dsh headless 派发任务**（cwd = 项目根；完整 brief 如下，逐字传给 harness）

```
在 C:\Users\15572\Documents\deepseek\yorozuya 项目里，只新建一个文件：
frontend\src\life\components\LifeImageLightbox.vue
不要修改、删除、读取改动任何其他文件，不要运行 dev server，不要安装依赖。

这是一个 Vue 3 <script setup> 单文件组件：全屏图片灯箱（lightbox）。
契约：
- Props: src (String, 必填)；alt (String, 默认 '图片')
- Emits: close —— 点击全屏遮罩任意位置、或按下 ESC 键时 emit('close')
- 渲染：fixed 定位全屏遮罩（半透明黑底 rgba(0,0,0,.75)，z-index 9999），
  图片居中，max-width: 90vw，max-height: 90vh，object-fit: contain，
  图片带 8px 圆角与轻微阴影；右上角一个「×」关闭按钮（点击也 emit close）。
- 组件挂载时给 document 加 keydown 监听（ESC），卸载时移除；
  挂载期间给 document.body 加 overflow:hidden，卸载时恢复。
- 样式全部 scoped，配色与项目一致：边框 #d9dedb、圆角 8-12px、
  关闭按钮白底圆钮 32px。
- 文件顶部注释一行：// 全屏图片灯箱：点击遮罩或 ESC 关闭（阶段 8a）。
写完后用 node --check 之类的办法做不了 Vue 校验，所以你自己仔细复查
template/script/style 三段语法正确即可，然后回复：文件路径 + 组件契约摘要。
```

命令：`cd /c/Users/15572/Documents/deepseek/yorozuya && npx @deepseek-ai/dsh --profile headless "<上述 brief>"`

- [ ] **Step 2: 验收**——Read 该文件核对契约（props/emits/ESC/overflow/scoped），`npm run build` 通过；不符就打回重写（把不符点追加进 brief 重派）。

---

### Task 7: 场景气泡缩略图 + 灯箱接线（Kimi）

**Files:**
- Modify: `frontend/src/life/components/LifeScene.vue:60-71`（气泡）、`:100` 附近（template 尾部）、script 段
- Consumes: Task 6 的 `LifeImageLightbox.vue`

- [ ] **Step 1**: script 里 `import LifeImageLightbox from './LifeImageLightbox.vue'`，加 `const lightboxSrc = ref('')`（若文件无 script setup 段则按现有写法接入，并确认 `lightboxSrc` 暴露给模板）。
- [ ] **Step 2**: 气泡内（`current-speech` button 内 `</button>` 前）加缩略图——注意 button 内嵌 img 的点击要 `.stop`，避免触发跳过：

```html
            <span>{{ speech.text || '…' }}</span>
            <img v-if="speech.image && !speech.typing" :src="speech.image" class="speech-thumb" alt="对话图片" @click.stop="lightboxSrc = speech.image" />
            <small v-if="speech.typing">点击显示全文</small>
```

template 根部收尾前加 `<LifeImageLightbox v-if="lightboxSrc" :src="lightboxSrc" alt="对话图片" @close="lightboxSrc = ''" />`。
- [ ] **Step 3**: style 加 `.speech-thumb { display:block; max-width:180px; max-height:120px; border-radius:8px; margin-top:6px; cursor:zoom-in; border:1px solid #d9dedb; }`
- [ ] **Step 4**: 对话历史抽屉（LifeFeatureDrawer.vue 或历史面板所在组件）消息条目有 `image` 时渲染同款缩略图 + 同一个 lightboxSrc 接线（执行时先定位历史消息渲染处；若历史组件层级深，把 `lightboxSrc` 提升到 LifeScene 父层统一挂载）。
- [ ] **Step 5**: `npm run build` + 全量前端测试通过；**Commit**（`"...(stage 8a, scene UI)"`）

---

### Task 8: Registry 校验 + 默认包归一化 + 种子再生成（Kimi）

**Files:**
- Modify: `frontend/src/life/registry.js:86-94`（节点校验段）
- Modify: `frontend/src/life/content/defaultPack.js`（helpers + 归一化）
- Modify: `backend/app/life_packs/wsw-default-life.json`（脚本再生成）
- Test: `frontend/tests/lifeRegistry.test.mjs:28-49`

- [ ] **Step 1**: registry.js 校验段改为新形状（与后端 Task 1 规则逐条对齐：lines 非空数组、image 仅 `/uploads/` 前缀、replies 非空数组、replyImage 同规则；报错文案 `节点缺少台词: ...` 等沿用风格）。
- [ ] **Step 2**: defaultPack.js 在 `dialogue` const 之后加归一化（保持 412 行剧本字面量不动）：

```js
// 节点/选项归一化(阶段 8a):字面量里的单句 line/reply 升级为 lines/replies 数组,
// 补齐 image/replyImage 默认值;多句节点直接写字面量 lines: [...] 即可。
function normalizeDialogue(dialogue) {
  for (const days of Object.values(dialogue)) {
    for (const script of days) {
      for (const node of Object.values(script.nodes)) {
        if (typeof node.line === 'string') { node.lines = [node.line]; delete node.line }
        node.image = node.image ?? null
        for (const choice of node.choices) {
          if (typeof choice.reply === 'string') { choice.replies = [choice.reply]; delete choice.reply }
          choice.replyImage = choice.replyImage ?? null
        }
      }
    }
  }
  return dialogue
}
```

content 装配处用 `dialogue: normalizeDialogue(dialogue),`。
- [ ] **Step 3**: 多句示范——ache 第 1 天 n2 改为 `lines: ['拍好了！你看，浪刚好在你身后碎成一圈金边。', '这张洗出来送你一份？']`（删掉对应 `line:` 键）；maoyou 第 5 天汇合节点 n4 改 3 句 `lines`（执行时照原文拆句）。再挑 1 个选项把 `reply:` 改为 `replies: ['……', '……']` 两句示范。
- [ ] **Step 4**: 种子再生成（frontend 目录下）：

```bash
node --input-type=module -e "import { defaultLifePackContent } from './src/life/content/defaultPack.js'; import { writeFileSync } from 'node:fs'; writeFileSync('../backend/app/life_packs/wsw-default-life.json', JSON.stringify(defaultLifePackContent, null, 2) + '\n', 'utf8')"
```

- [ ] **Step 5**: lifeRegistry.test.mjs 更新断言：`typeof start.line === 'string'` → `Array.isArray(start.lines) && start.lines.length >= 1`；`typeof choice.reply` → `Array.isArray(choice.replies)`；`days[0].nodes.n1.line !== days[1].nodes.n1.line` → 比较 `.lines[0]`。
- [ ] **Step 6**: 全量前端测试 + 后端 pytest 全绿；**Commit**（`"...(stage 8a, registry + default pack)"`）

---

### Task 9: 管理端编辑器多行 + 图片（Kimi）

**Files:**
- Modify: `frontend/src/life/admin/AdminDialogue.vue:194-220`（编辑面板）、新建节点创建处（「＋新建节点」逻辑）
- Consumes: 既有共享组件 `AdminImageField`（执行时确认 props，阶段 4d 已用于立绘/背景上传）

- [ ] **Step 1**: 节点台词 textarea（`:203`）替换为多行编辑器：

```html
        <div class="la-node-lines">
          <div v-for="(l, i) in node.lines" :key="i" class="la-line-row">
            <textarea v-model="node.lines[i]" placeholder="NPC 台词（每行一句，连播）"></textarea>
            <button type="button" :disabled="node.lines.length <= 1" @click="node.lines.splice(i, 1)">删</button>
          </div>
          <button type="button" @click="node.lines.push('')">+ 加一句</button>
        </div>
        <AdminImageField v-model="node.image" label="节点图片（可选）" />
```

- [ ] **Step 2**: 选项回复 input（`:210`）替换为 replies 多行（同款 加一句/删 行编辑器，行内 input 即可）+ `<AdminImageField v-model="choice.replyImage" label="回复图片（可选）" />`。
- [ ] **Step 3**: 「＋新建节点」创建处的新节点对象改为 `{ lines: [''], image: null, choices: [{ label: '', effects: { bond: 0, stats: {} }, replies: [''], replyImage: null, next: null }] }`（effects.stats 的四键初始化沿用现有惯例）。
- [ ] **Step 4**: 管理端手动验证（预览环境 8080：改多句+传图→保存→游戏端生效），`npm run build` 通过；**Commit**（`"...(stage 8a, admin editor)"`）

---

### Task 10: 隔离 E2E + 文档 + 收尾（Kimi）

- [ ] **Step 1**: 起隔离环境（临时库 + 8123/8124，沿用阶段 7 冒烟配方），浏览器验证：
  1. 旧形状包（手工把种子改回 line/reply 构造一个旧包入库）启动时就地迁移成功；
  2. 游戏内 ache 第 1 天多句连播（点一下一句）；选项回复多句；
  3. 管理端给某节点传图保存 → 游戏内气泡出缩略图 → 点击全屏弹出 → 再点消失；
  4. 存档 PUT/GET 往返带 image 字段不丢。
- [ ] **Step 2**: 清理冒烟环境（杀进程、删临时目录与 token）。
- [ ] **Step 3**: 真实库重启 8000 后端（就地迁移生效），验证 GET /api/virtual-life/pack 新形状。
- [ ] **Step 4**: 同步 `VIRTUAL_LIFE.md`（消息组形状 + image 规则 + 迁移）与架构文档路线图（加 8a 行 ✅）。
- [ ] **Step 5**: **Commit**（`"docs: stage 8a message format"` 或并入 Task 9 commit）。

## 执行编排（模式 B）

1. 先派 Task 6 给 harness（它跑的同时我做 Task 1-3）；
2. 我按 Task 1→2→3→4→5 顺序 TDD；harness 交付后验收（Task 6 Step 2）再做 Task 7；
3. Task 8→9→10 顺序收尾。每个 Task 独立 commit，全程不推送。
