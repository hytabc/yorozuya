# Stage 10：猫耳少女「米米」七日剧本（内容包扩充）

**日期**：2026-09-09　**分支**：`feature/virtual-life-stage9`
**分工**：剧本由 DeepSeek 官方 API 直连生成（`deepseek-v4-flash-vision-exp`，prompt 见 `stage10-mimi-prompt.txt`）；Kimi 负责 schema 设计、审计补丁、校验、上架与实测。

## 内容

新 NPC「米米」（id: `mimi`），猫耳少女、小小咖啡馆看板娘，自称喵星人观察员。

- **立绘**：用户提供的猫耳少女平面立绘，上传至 `/uploads/life/ab18fa5c85c34a8494cb35ec76757f54.png`（剧情图片暂复用同一张，站长可在内容管理里替换）
- **位置**：小小咖啡馆 `#1101`（与小弥同房间，occupants 1→2）
- **剧本成品**：`stage10-mimi-script.json`（含 npc 条目、presence、开场白、7 天 dialogue）

## 功能覆盖清单（实测全部命中）

| 天 | 测试点 | 结果 |
|---|---|---|
| 1 | 分支不汇合（n1→n2/n3 各自收尾）、相识数值 | ✓ 浏览器实测 bond 飘字 +2 |
| 2 | 分支合并（两选项同到 n4） | ✓ |
| 3 | 节点图片（她展示拍的照片）+ 选项回复图片 + 3 句连播 | ✓ 缩略图/灯箱/历史记录均验证 |
| 4 | 负面效果选项（mood −3，红闪 + 红色 -3 飘字） | ✓ 实测 |
| 5 | 3 节点长链 n1→n2→n3 | ✓ |
| 6 | 高好感大额选项（bond +5）+ replyImage | ✓ |
| 7 | start 3 句连播 + 告别收尾（replies 3 句） | ✓ |
| — | 好感耗尽后的 fallbackReplies（minBond 0/0/30/70 分档随机） | ✓ 实测出「欢迎光临喵～」 |

## 审计补丁（Kimi 手改，两点）

1. 第 1 天四个选项原本零效果，补了相识期数值（bond +1/+2、social/mood +1/+2）
2. 后端规则：dialogue 选项 `bond` 只允许 0..100（负好感仅事件支持）；第 4 天「惹她生气」由 bond −3 改为纯负属性 mood −3

## 上架记录

- `PUT /api/virtual-life/packs/wsw-life-7day-chains` → version 10，前后端校验均通过
- 新注册测试号 `nekotest`（uid 2）并设为内测用户（`is_beta_tester`），E2E 全程在该账号完成，admin 存档未动

## 已知观感问题（留待后续）

- 连播队列中 replyImage 只在该句展示期间出现（约 1-3 秒），随后被下一节点的台词顶掉；如果想要「图片驻留到用户点击」，需要改播放机行为（另开阶段）
