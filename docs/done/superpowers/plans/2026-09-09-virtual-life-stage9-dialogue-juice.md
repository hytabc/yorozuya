# Stage 9：对话体验「手感」重做（presentation-only）

**日期**：2026-09-09　**分支**：`feature/virtual-life-stage9`
**分工**：全部实现代码由 DeepSeek harness（`npx @deepseek-ai/dsh --profile headless`，cwd=项目根）编写；Kimi 只写 brief、审 diff、跑测试/构建/E2E、打回重写、提交。

## 背景

用户（站长）反馈：功能完整但 UI 平平无奇、没有游戏吸引力。审计结论（Kimi，已读码确认）：

- 已有：打字机（`lifePlayback.js` 38ms/字、点击补全、reduced-motion 降级）、属性条 0.3s 宽度过渡、`bondDelta` 静态文本。
- 缺失：`.npc-sprite` 立绘 CSS 是死代码（模板未渲染）；选项瞬间出现；数值变化零反馈；气泡无入场动效。

本阶段只做**表现层动画**，不改任何结算/存档/内容包逻辑。

## 验收标准

1. 对话中当前 NPC 有「立绘卡」出现在场景中央偏左：入场淡入上浮；玩家说话时立绘变暗、NPC 说话时恢复高亮（galgame 经典明暗切换）；待机有轻微呼吸浮动。
2. 新发言气泡 pop-in（scale .96→1 + fade 180ms）；打字中文字末尾有闪烁游标 ▍。
3. 选项按钮逐个 stagger 浮现（i×70ms，fade+translateY）；动作页签切换时动作按钮同待遇（i×50ms）。
4. 左侧属性条任一数值变化：所在行闪烁高亮（正=绿 #e5f3eb，负=红 #f9e8e8，600ms）+ 数字旁飘出 delta（+3/−2）上浮淡出；好感变化时 NPC 头像旁飘「好感 +N」。
5. 全部动画 `prefers-reduced-motion` 下降级为无动画。
6. 既有行为不回归：点击气泡补全打字、图片缩略图+灯箱、事件弹窗、存档/重置/下一天。
7. `npm run build` 与 `node --test --test-isolation=none tests/*.test.mjs`（85 个）全绿。

## 文件边界

- 允许修改：`frontend/src/life/components/LifeScene.vue`、`frontend/src/life/components/LifeCharPanel.vue`
- 允许新建：`frontend/src/life/components/` 内的新组件（如 `LifeDeltaFloat.vue`）
- 禁止改动：`useLifeGame.js`、`composables/*`、`registry.js`、`admin/*`、`tests/*`、后端、`package.json`（不加依赖）

## 执行

- [ ] Step 1：派发 brief（`stage9-brief.txt`，随本 plan 同目录）给 dsh headless
- [ ] Step 2：Kimi 验收——逐条核对验收标准，读 diff；不符点追加进 brief 重派
- [ ] Step 3：Kimi 自跑前端全量测试 + `npm run build`
- [ ] Step 4：InAppBrowser E2E（登录 → 对话 → 看立绘/选项/飘字）
- [ ] Step 5：Commit（标注 via deepseek harness），推送 origin
