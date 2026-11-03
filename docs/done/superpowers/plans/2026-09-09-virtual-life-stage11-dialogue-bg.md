# 虚拟人生 Stage 11 — 对话图片改为节点级持续中央背景（CG 层）

## 需求原话

> 所有对话的图片显示，都要设置持续的对话节点，不在对应的节点范围就不显示，而且图片是放在中间当作对话背景的

## 语义设计

- 对话图片从气泡缩略图改为**场景中央的 CG/照片层**（`.dialog-bg`）：absolute 居中、相纸白边、pointer-events none、不遮挡点击。
- **节点级持续**：图片绑定到播放状态 `speech.bg`，只要对话仍在携带该图的节点/回复组内就一直显示；推进到无图节点时消失。
- 每条播放消息携带 `bg` 字段：
  - 节点台词组：`bg = node.image`
  - 回复组（replies）：`bg = choice.replyImage`（挂在最后一句，与历史抽屉一致）
  - 玩家发言气泡：`bg = replyImage || currentNode.image`（防止玩家打字期间背景闪没）
- `playback.stop()` 清空 bg；正常播放**播完不清空**（持续显示的关键）。
- 气泡内缩略图与全屏灯箱从 LifeScene 移除；历史抽屉缩略图与事件弹窗（LifeEventModal）自己的图片展示保持不变。

## 改动文件（6 个）

- `frontend/src/composables/lifeDialogue.js` — `groupMessages` 每条消息加 `bg: image || null`（image 仍只挂最后一句供历史抽屉）
- `frontend/src/composables/lifePlayback.js` — state 加 `bg`，startLine 透传、stop 清空、播完保留
- `frontend/src/life/useLifeGame.js` — chooseOption 计算 currentNode 并给玩家发言消息补 bg
- `frontend/src/life/components/LifeScene.vue` — 新增 `.dialog-bg` 中央层（Transition 淡入淡出），删除气泡缩略图/灯箱
- `frontend/tests/lifeDialogue.test.mjs`、`frontend/tests/lifePlayback.test.mjs` — 断言同步更新

## 生成与审计

- 代码由 DeepSeek（直连官方 API，模型 `deepseek-v4-flash-vision-exp`，推理型，max_tokens 60000）生成；Kimi 审计后落盘。
- 审计要点：diff 干净、无存档/奖励逻辑改动（playback 纯展示层）、history 抽屉行为保留。

## 验证记录

- 单测：`node --test tests/*.test.mjs` 85 全绿；`npm run build` 通过。
- 引擎仿真（真实模块 + 线上包 v10 数据）：第 3 天米米 n1（有图）→「雪球好可爱」→ n3（无图），played bg 序列 `[photo, null, null, null]`，final `bg: null` ✓
- 浏览器活体实测（InAppBrowser，nekotest2，第 3 天 cafe-1101）：
  - 对话开始：`.dialog-bg` 显示节点图 ✓
  - 选「雪球好可爱」（无回复图、下节点无图）：`speech.bg` → null，渲染输出无激活元素 ✓
  - 选「你拍得真好看」（replyImage 有图，下节点 n2 无图）：状态序列 `P[IMG] → N[IMG] → N[IMG] → N[--]...`，进入 n2 后 bg 稳定为 null ✓
- **踩坑记录（重要）**：内置浏览器面板未展开时 tab 处于 hidden/frozen 状态，CSS transition 的 transitionend 不触发，Vue Transition 的离场元素会卡在 DOM 里（opacity 0、不可见、pointer-events none），导致「背景图不消失」的假象。此前一轮误判为代码 bug，实际是测试环境问题；tab 恢复可见后动画帧恢复、残留元素自动清理。功能验证应以 `speech.bg` 状态为准，DOM 观察需在可见 tab 下进行。

## 遗留

- 事件弹窗（LifeEventModal）图片仍走自身灯箱，不在本次范围。
- 本地提交，未推送。
